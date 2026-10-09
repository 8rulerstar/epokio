"""The agent's HTTP: reads (GET) are open, runs (POST) need a token with run rights. Also serves the web page (/) and images (/file).

There can be several tokens (auth.py, tokens.py). Reads take any token, runs (POST) only scope=run tokens.
Calling a run with a read-only token gives 403, not 401 (the token is valid but lacks permission)."""
from __future__ import annotations

import json
import logging
import re
import socket
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import auth, msg, tokens
from typing import TYPE_CHECKING

from .textnorm import deep_nfc

MAX_BODY = 20_000_000                                   # POST body limit (settings and label edits are a few KB)

if TYPE_CHECKING:
    from .agent import Agent

HOSTNAME = socket.gethostname().lower().split(".")[0]

# Do reads (GET) need a token? On by default when reachable from outside this machine (0.0.0.0 etc.): run names, scores, images
# were visible to anyone on the network (2026-09-22 review). Only --open-reads turns it off. Web page and /health stay open (they ask for it)
OPEN_PATHS = {"/", "/index.html", "/health"}
# Reads that always need a token: they read or scan arbitrary paths (security review 2026-09-22). auth.get_needs_token also locks them
TOKEN_PATHS = {"/names", "/health-check"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _allowed_hosts() -> set[str]:
    import os
    return {h.strip().lower().rstrip(".") for h in os.environ.get("EPOKIO_ALLOWED_HOSTS", "").split(",") if h.strip()}


def host_ok(host_header: str | None, exposed: bool) -> bool:
    """DNS rebinding guard: an agent open only on this machine answers only when Host is a loopback name (or EPOKIO_ALLOWED_HOSTS)
    (blocks evil.example -> 127.0.0.1). No exception even with a token.
    An agent open to the network passes here; the handler then checks host_trusted or the token again"""
    if exposed:
        return True
    h = (host_header or "").strip().lower()
    if h.startswith("[") and "]" in h:
        h = h[:h.index("]") + 1]                        # [::1]:8787 -> [::1]
    elif h.count(":") == 1:
        h = h.split(":")[0]                             # 127.0.0.1:8787 -> 127.0.0.1
    return h in LOOPBACK_HOSTS or h.rstrip(".") in _allowed_hosts()


def _is_ip(host: str) -> bool:
    import ipaddress
    try:
        ipaddress.ip_address(host.split("%")[0])          # zone suffix like fe80::1%eth0
        return True
    except ValueError:
        return False


def host_trusted(header: str | None) -> bool:
    """Does the Host header point at this machine (DNS rebinding guard for an agent open to the network)?
    Accepts IP addresses, localhost, and **names whose first label is this machine's name** (pc, pc.local, pc.lan, company domain,
    Tailscale MagicDNS pc.tailXXXX.ts.net). An attacker domain would need to know this machine's name.
    Other names must be listed in EPOKIO_ALLOWED_HOSTS (comma separated) or carry a token.
    Originally only the bare name and .local were accepted, so the Mac app and web via pc.lan or MagicDNS looked 'off'"""
    from urllib.parse import urlsplit
    try:
        host = (urlsplit("//" + (header or "")).hostname or "").rstrip(".")   # handles [::1]:8787, pc.:8787, no port
    except ValueError:
        return False
    return host in ("", "localhost") or _is_ip(host) or host.split(".")[0] == HOSTNAME or host in _allowed_hosts()


def _no_constant(name: str):
    raise ValueError(f"{name} is not allowed")


def u_path_is_login(path: str) -> bool:
    return urlparse(path).path == "/login"


log = logging.getLogger("epokio")


def setup_log() -> Path:
    """~/.epokio/agent.log (two 1 MB files). setup and the tray discarded helper output, so on Windows/Linux errors were never kept"""
    from logging.handlers import RotatingFileHandler
    f = Path.home() / ".epokio" / "agent.log"
    try:
        auth.private_dir(f.parent)
        h = RotatingFileHandler(f, maxBytes=1_000_000, backupCount=1, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
    except OSError:
        pass
    return f


def make_handler(agent: Agent, reads_need_token: bool = False):
    # Read the web page once at start. Reading it per request made an old helper serve the new page after a pip upgrade (page/code mismatch)
    page = (Path(__file__).parent / "web" / "index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        _enc: list = []                                   # the last few (payload, gzip flag, bytes)

        def _encode(self, payload, gz: bool) -> tuple[bytes, bool]:
            """Convert to JSON and compress if large. The same response object (/runs, reused by the agent for 1 s) is encoded once.
            Previously every viewer and request re-serialized, NFC-normalized and compressed thousands of runs"""
            for obj, g, body, zipped in Handler._enc:
                if obj is payload and g == gz:
                    return body, zipped
            body = json.dumps(deep_nfc(payload), ensure_ascii=False).encode()   # all outgoing strings are NFC
            zipped = gz and len(body) > 4096
            if zipped:
                import gzip
                body = gzip.compress(body, compresslevel=5)
            if isinstance(payload, dict) and "runs" in payload:     # remember only the big cached responses
                Handler._enc = [(payload, gz, body, zipped)] + Handler._enc[:3]
            return body, zipped

        def _send(self, code, payload):
            body, zipped = self._encode(payload, "gzip" in (self.headers.get("Accept-Encoding") or ""))
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            # Compress large responses (browsers, Mac URLSession decode them). /runs for 2,000 runs was 1.9 MB every 4 s (79 KB gzip)
            if zipped:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(len(body)))
            self._cookie()
            self.end_headers()
            self.wfile.write(body)

        def _set_cookie(self, tok: str):
            self.send_header("Set-Cookie", f"{auth.COOKIE}={tok}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000")

        def _cookie(self):
            """After a read passes with a header token, give a cookie for images: <img> and AsyncImage cannot add headers.
            The cookie holds exactly the token the client sent (previously it held the single token, so even a read-only token
              got a cookie with run rights)"""
            tok = getattr(self, "give_cookie", "")
            if tok:
                self._set_cookie(tok)

        def _login(self, tok: str, can_run: bool):
            # scope: whether the web page may show controls that change things. A read-only token saw Save, Stage and
            #   Folder buttons that all ended in an English 403 (and the message vanished on the next refresh)
            body = json.dumps({"ok": True, "scope": tokens.RUN if can_run else tokens.READ}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._set_cookie(tok)
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self) -> bool:
            """DNS rebinding guard. A malicious page points its domain at 127.0.0.1 to read this agent's run list and images.
            IP addresses, localhost and this machine's name pass; other names (e.g. Tailscale MagicDNS) only with a token."""
            return host_trusted(self.headers.get("Host")) or auth.check(self.headers.get("Authorization"))

        def do_GET(self):
            msg.set_from_header(self.headers.get("Accept-Language"))   # reply in the app's language
            u = urlparse(self.path)
            static = u.path in ("/", "/index.html") or u.path.startswith("/web/")
            # Reads with a header token skip the Host check (a rebinding page does not know the token; MagicDNS etc.). POST always checks Host
            host_fine = host_ok(self.headers.get("Host"), reads_need_token) and (static or self._host_ok())
            if not host_fine and not auth.check(self.headers.get("Authorization")):
                return self._send(403, {"error": "unknown host name", "hint": "Open Epokio by this machine's IP address or name, "
                                        "or set EPOKIO_ALLOWED_HOSTS on this machine to the name you use."})
            if u.path in TOKEN_PATHS and not auth.check_request(self.headers):
                return self._send(401, {"error": "token required"})
            # Missing file-like paths (/favicon.ico, /robots.txt, /.well-known/...) get 404. Request paths have no dots (files use /file, /web/).
            # Previously the token was asked first, so a 401 showed in the console every time the browser opened the page
            segs = u.path.split("/")
            if not static and ("." in segs[-1] or any(s.startswith(".") for s in segs)):
                return self._send(404, {"error": "not found"})
            if u.path == "/health" and "nonce" in u.query:           # prove this is really this machine's agent (the token is not sent)
                import hashlib, hmac
                n = parse_qs(u.query).get("nonce", [""])[0][:128]
                proof = hmac.new(auth.token().encode(), n.encode(), hashlib.sha256).hexdigest()      # old clients (no port)
                from .port import proof_for                              # bound to the port this server listens on (relays fail)
                return self._send(200, {**agent.get("/health", {}), "proof": proof,
                                        "proof_port": proof_for(auth.token(), n, self.server.server_address[1])})
            if u.path == "/health" and self.client_address[0] in ("127.0.0.1", "::1"):
                # Only for pages opened on this machine: the command that shows the token (autostart.cli: exe, venv or py form). The web lock card
                #   said epokio-agent --show-token, not on PATH on Windows. The venv path may contain the user name, so it is not sent outside
                from .autostart import cli, short_home       # venv paths with the user name become ~
                return self._send(200, {**agent.get("/health", {}), "token_cmd": short_home(cli("agent --show-token"))})
            if reads_need_token and u.path not in OPEN_PATHS and not u.path.startswith("/web/") \
                    and not auth.check_request(self.headers):
                return self._send(401, {"error": "token required"})
            self.give_cookie = auth.presented(self.headers) if (
                reads_need_token and auth.COOKIE not in (self.headers.get("Cookie") or "")) else ""
            if u.path in ("/", "/index.html"):   # web page: open http://machine:8787/ in a browser (Windows, Linux, phone)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(page)
                return
            m = re.fullmatch(r"/web/([a-z]+\.(js|css))", u.path)     # other web page files (fixed names only)
            if m and (Path(__file__).parent / "web" / m.group(1)).is_file():
                body = (Path(__file__).parent / "web" / m.group(1)).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ("text/javascript" if m.group(2) == "js" else "text/css") + "; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path.startswith("/web/"):    # other /web/ paths do not exist (checked before asking for a token)
                return self._send(404, {"error": "not found"})
            from . import scope
            lim = auth.request_roots(self.headers)     # a token limited to folders sees only runs inside them (scope.py)
            if u.path == "/file":             # images are sent as files, not JSON
                with scope.limited(lim):
                    f = agent.file(parse_qs(u.query).get("path", [""])[0])
                if not f:
                    return self._send(404, {"error": "not found"})
                data = f.read_bytes()
                self.send_response(200)
                ctype = {".png": "image/png", ".webp": "image/webp", ".bmp": "image/bmp"}.get(f.suffix.lower(), "image/jpeg")
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=30")
                self.end_headers()
                self.wfile.write(data)
                return
            if auth.get_needs_token(u.path) and not (auth.check(self.headers.get("Authorization"))
                                                     or auth.check_request(self.headers)):   # header or HttpOnly, SameSite=Strict cookie
                return self._send(401, {"error": "token required"})
            try:
                with scope.limited(lim):
                    payload = agent.get(u.path.rstrip("/") or "/runs", parse_qs(u.query))
            except Exception as e:
                log.exception("GET %s failed", u.path)          # previously the cause of a 500 was not recorded anywhere
                return self._send(500, {"error": str(e)})
            if payload is None:
                return self._send(404, {"error": "not found"})
            if isinstance(payload, tuple):   # previously (code, body) results went out as an array with status 200 (errors looked like success)
                return self._send(*payload)
            self._send(200, payload)

        def do_POST(self):
            msg.set_from_header(self.headers.get("Accept-Language"))
            # Read the body before replying. Sending 401 unread dropped the connection on Windows (ConnectionAborted), so the 401 never arrived
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.close_connection = True
                return self._send(400, {"error": "bad Content-Length"})
            if n < 0 or n > MAX_BODY:                        # previously negative read until close, huge loaded fully into memory
                self.close_connection = True
                return self._send(413, {"error": f"body must be under {MAX_BODY // 1_000_000} MB"})
            raw = self.rfile.read(n) if n > 0 else b""
            if not host_ok(self.headers.get("Host"), reads_need_token) or not self._host_ok():
                return self._send(403, {"error": "unexpected Host header"})
            scope = auth.post_scope(self.headers.get("Authorization"))
            if scope is None:
                return self._send(401, {"error": "token required"})
            limited = auth.request_roots(self.headers) is not None   # a token limited to folders is read-only (scope.py)
            if u_path_is_login(self.path):                     # web page: if the token is valid, give the image cookie (read-only too)
                return self._login(auth.bearer(self.headers.get("Authorization")), scope == tokens.RUN and not limited)
            # code: the web page hides the controls from then on. The text follows the page language (it came in English)
            if scope != tokens.RUN:                            # token valid but read-only: cannot start training
                return self._send(403, {"error": msg.tr("This token is read-only. It can view runs, but not start them or change anything."),
                                        "code": "read_only"})
            if limited:
                return self._send(403, {"error": msg.tr("This token can see only some folders and cannot change anything."),
                                        "code": "read_only"})
            try:
                try:
                    # Reject NaN and Infinity. Previously a NaN goal was saved and sent as is in /runs,
                    #   so strict JSON parsers in browsers and the Mac could not read the whole list (not even the undo screen appeared)
                    body = json.loads(raw or b"{}", parse_constant=_no_constant)
                except ValueError:
                    return self._send(400, {"error": "body must be JSON"})
                if not isinstance(body, dict):
                    return self._send(400, {"error": "body must be a JSON object"})
                route = urlparse(self.path).path.rstrip("/")
                if route == "/shutdown":            # when replacing an old helper with a new version (setup, tray, epokio agent --stop)
                    self._send(200, {"ok": True})
                    import threading
                    srv = self.server

                    def stop():
                        # Stop serving, then close the listening socket too. Without the close, macOS and Linux
                        # keep accepting connections into the backlog until the process exits, so stop_agent
                        # (which waits for the port to refuse connections) saw a stopped helper as still running.
                        srv.shutdown()
                        srv.server_close()
                    threading.Thread(target=stop, daemon=True).start()
                    log.info("stopping on request")
                    return
                code, payload = agent.post(route, body)
            except Exception as e:
                log.exception("POST %s failed", self.path)
                return self._send(500, {"error": str(e)})
            self._send(code, payload)

        def log_message(self, *a):
            pass

    return Handler


def main():
    """epokio-agent. The body is in server_cli.py (split because of the file length limit)"""
    from .server_cli import main as run
    run()


if __name__ == "__main__":
    main()
