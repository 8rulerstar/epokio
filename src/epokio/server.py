"""agent의 HTTP: 보기(GET)는 그냥, 실행(POST)은 실행 권한이 있는 토큰. 웹 화면(/)과 그림(/file)도 여기서 내준다.

토큰이 여럿일 수 있다(auth.py·tokens.py). 보기는 아무 토큰이나, 실행(POST)은 scope=run 토큰만.
읽기 전용 토큰으로 실행을 부르면 401이 아니라 403이다(토큰은 맞는데 권한이 없다는 뜻이라서)."""
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

MAX_BODY = 20_000_000                                   # POST 본문 상한(설정·라벨 수정은 수 KB)

if TYPE_CHECKING:
    from .agent import Agent

HOSTNAME = socket.gethostname().lower().split(".")[0]

# 보기(GET)에도 토큰이 필요한가. 이 기계 밖에서 닿게 띄우면(0.0.0.0 등) 기본으로 켠다: 학습 이름·점수·결과 그림이
# 같은 네트워크 누구에게나 보였다(2026-09-22 점검). --open-reads 로만 끈다. 웹 화면·/health 는 토큰 없이 열린다(토큰을 묻는 화면이라서)
OPEN_PATHS = {"/", "/index.html", "/health"}
# 보기지만 늘 토큰: 임의 경로를 읽거나 훑는다(보안 점검 2026-09-22). auth.get_needs_token도 잠그지만 이중으로 둔다
TOKEN_PATHS = {"/names", "/health-check"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _allowed_hosts() -> set[str]:
    import os
    return {h.strip().lower().rstrip(".") for h in os.environ.get("EPOKIO_ALLOWED_HOSTS", "").split(",") if h.strip()}


def host_ok(host_header: str | None, exposed: bool) -> bool:
    """★DNS 리바인딩 막기: 이 기계 안에서만 여는 agent는 Host가 루프백 이름(또는 EPOKIO_ALLOWED_HOSTS)일 때만 답한다
    (evil.example → 127.0.0.1 우회). 토큰이 있어도 예외 없다.
    네트워크에 연 agent는 여기서는 통과시키고, 핸들러가 host_trusted 또는 토큰을 한 번 더 본다"""
    if exposed:
        return True
    h = (host_header or "").strip().lower()
    if h.startswith("[") and "]" in h:
        h = h[:h.index("]") + 1]                        # [::1]:8787 → [::1]
    elif h.count(":") == 1:
        h = h.split(":")[0]                             # 127.0.0.1:8787 → 127.0.0.1
    return h in LOOPBACK_HOSTS or h.rstrip(".") in _allowed_hosts()


def _is_ip(host: str) -> bool:
    import ipaddress
    try:
        ipaddress.ip_address(host.split("%")[0])          # fe80::1%eth0 같은 범위 표시
        return True
    except ValueError:
        return False


def host_trusted(header: str | None) -> bool:
    """Host 머리말이 이 기계를 가리키는가(네트워크에 연 agent의 DNS 리바인딩 막기).
    IP 주소·localhost, 그리고 **첫 칸이 이 기계 이름인 이름**(pc, pc.local, pc.lan, 회사 도메인,
    Tailscale MagicDNS pc.tailXXXX.ts.net)은 받는다. 공격자 도메인이 그렇게 되려면 이 기계 이름을 알아야 한다.
    그 밖의 이름은 EPOKIO_ALLOWED_HOSTS(쉼표로 여럿)에 적거나 토큰을 실어야 한다.
    ★처음엔 이름 그대로·.local만 받아서 pc.lan·MagicDNS로 붙은 맥 앱과 웹이 '꺼져 있다'로 보였다"""
    from urllib.parse import urlsplit
    try:
        host = (urlsplit("//" + (header or "")).hostname or "").rstrip(".")   # [::1]:8787, pc.:8787, 포트 없음까지
    except ValueError:
        return False
    return host in ("", "localhost") or _is_ip(host) or host.split(".")[0] == HOSTNAME or host in _allowed_hosts()


def _no_constant(name: str):
    raise ValueError(f"{name} is not allowed")


def u_path_is_login(path: str) -> bool:
    return urlparse(path).path == "/login"


log = logging.getLogger("epokio")


def setup_log() -> Path:
    """~/.epokio/agent.log (1MB씩 둘). ★setup·트레이가 도우미 출력을 버려서, 윈도우·리눅스에서는 오류가 어디에도 남지 않았다"""
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
    # 웹 화면은 켤 때 한 번 읽는다. ★요청마다 읽어, pip으로 올린 뒤 옛 도우미가 새 화면을 내주었다(화면과 코드가 어긋남)
    page = (Path(__file__).parent / "web" / "index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        _enc: list = []                                   # (payload, gzip 여부, 바이트) 최근 몇 개

        def _encode(self, payload, gz: bool) -> tuple[bytes, bool]:
            """JSON으로 바꾸고 크면 압축한다. 같은 응답 객체(agent가 1초 동안 재사용하는 /runs)는 한 번만.
            ★보는 화면마다, 요청마다 학습 수천 개를 다시 직렬화·NFC·압축했다"""
            for obj, g, body, zipped in Handler._enc:
                if obj is payload and g == gz:
                    return body, zipped
            body = json.dumps(deep_nfc(payload), ensure_ascii=False).encode()   # 나가는 문자열은 전부 NFC
            zipped = gz and len(body) > 4096
            if zipped:
                import gzip
                body = gzip.compress(body, compresslevel=5)
            if isinstance(payload, dict) and "runs" in payload:     # 캐시해 두는 큰 응답만 기억한다
                Handler._enc = [(payload, gz, body, zipped)] + Handler._enc[:3]
            return body, zipped

        def _send(self, code, payload):
            body, zipped = self._encode(payload, "gzip" in (self.headers.get("Accept-Encoding") or ""))
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            # 큰 응답은 압축한다(브라우저·맥 URLSession은 알아서 푼다). ★학습 2,000개의 /runs가 4초마다 1.9MB였다(gzip 79KB)
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
            """토큰(헤더)으로 보기를 한 번 통과하면 그림용 쿠키를 준다: <img>·AsyncImage는 헤더를 못 붙인다.
            ★쿠키에는 그 사람이 보낸 토큰을 그대로 담는다(예전엔 단일 토큰을 담아, 읽기 전용 토큰으로 들어와도
              실행 권한 쿠키를 받아 갔다)"""
            tok = getattr(self, "give_cookie", "")
            if tok:
                self._set_cookie(tok)

        def _login(self, tok: str):
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._set_cookie(tok)
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self) -> bool:
            """DNS 리바인딩 막기. 악성 페이지가 자기 도메인을 127.0.0.1로 돌려 이 agent의 학습 목록·그림을 읽는다.
            IP 주소·localhost·이 기계 이름은 그대로 받고, 그 밖의 이름(예: Tailscale MagicDNS)은 토큰이 있을 때만."""
            return host_trusted(self.headers.get("Host")) or auth.check(self.headers.get("Authorization"))

        def do_GET(self):
            msg.set_from_header(self.headers.get("Accept-Language"))   # 앱 언어로 문장을 돌려준다
            u = urlparse(self.path)
            static = u.path in ("/", "/index.html") or u.path.startswith("/web/")
            # 토큰(헤더)을 실은 보기는 Host를 묻지 않는다(리바인딩 페이지는 토큰을 모른다. MagicDNS 등). 실행(POST)은 늘 Host도 본다
            host_fine = host_ok(self.headers.get("Host"), reads_need_token) and (static or self._host_ok())
            if not host_fine and not auth.check(self.headers.get("Authorization")):
                return self._send(403, {"error": "unknown host name", "hint": "Open Epokio by this machine's IP address or name, "
                                        "or set EPOKIO_ALLOWED_HOSTS on this machine to the name you use."})
            if u.path in TOKEN_PATHS and not auth.check_request(self.headers):
                return self._send(401, {"error": "token required"})
            if u.path == "/health" and "nonce" in u.query:           # 진짜 이 기계의 agent인지 증명(토큰은 보내지 않는다)
                import hashlib, hmac
                n = parse_qs(u.query).get("nonce", [""])[0][:128]
                proof = hmac.new(auth.token().encode(), n.encode(), hashlib.sha256).hexdigest()
                return self._send(200, {**agent.get("/health", {}), "proof": proof})
            if reads_need_token and u.path not in OPEN_PATHS and not u.path.startswith("/web/") \
                    and not auth.check_request(self.headers):
                return self._send(401, {"error": "token required"})
            self.give_cookie = auth.presented(self.headers) if (
                reads_need_token and auth.COOKIE not in (self.headers.get("Cookie") or "")) else ""
            if u.path in ("/", "/index.html"):   # 웹 화면: 브라우저로 http://기계:8787/ (윈도우·리눅스·폰)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(page)
                return
            m = re.fullmatch(r"/web/([a-z]+\.(js|css))", u.path)     # 웹 화면의 나머지 파일(이름을 정해 둔 것만)
            if m and (Path(__file__).parent / "web" / m.group(1)).is_file():
                body = (Path(__file__).parent / "web" / m.group(1)).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ("text/javascript" if m.group(2) == "js" else "text/css") + "; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path.startswith("/web/"):    # 정해 둔 이름 밖의 /web/ 경로는 없는 것(토큰 요구보다 먼저)
                return self._send(404, {"error": "not found"})
            if u.path == "/file":             # 그림은 JSON이 아니라 파일 그대로
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
                                                     or auth.check_request(self.headers)):   # 헤더 또는 HttpOnly·SameSite=Strict 쿠키
                return self._send(401, {"error": "token required"})
            try:
                payload = agent.get(u.path.rstrip("/") or "/runs", parse_qs(u.query))
            except Exception as e:
                log.exception("GET %s failed", u.path)          # ★500의 원인이 어디에도 남지 않았다
                return self._send(500, {"error": str(e)})
            if payload is None:
                return self._send(404, {"error": "not found"})
            if isinstance(payload, tuple):   # ★(코드, 내용)을 돌려주는 요청이 상태 200에 배열로 나갔다(오류가 성공처럼 보임)
                return self._send(*payload)
            self._send(200, payload)

        def do_POST(self):
            msg.set_from_header(self.headers.get("Accept-Language"))
            # ★본문을 읽고 나서 답한다. 안 읽고 401을 보내면 윈도우에서 연결이 끊겨(ConnectionAborted) 401이 안 닿았다
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.close_connection = True
                return self._send(400, {"error": "bad Content-Length"})
            if n < 0 or n > MAX_BODY:                        # ★음수면 연결이 닫힐 때까지 읽고, 아주 크면 메모리에 다 올렸다
                self.close_connection = True
                return self._send(413, {"error": f"body must be under {MAX_BODY // 1_000_000} MB"})
            raw = self.rfile.read(n) if n > 0 else b""
            if not host_ok(self.headers.get("Host"), reads_need_token) or not self._host_ok():
                return self._send(403, {"error": "unexpected Host header"})
            scope = auth.post_scope(self.headers.get("Authorization"))
            if scope is None:
                return self._send(401, {"error": "token required"})
            if u_path_is_login(self.path):                     # 웹 화면: 토큰이 맞으면 그림용 쿠키를 준다(읽기 전용도)
                return self._login(auth.bearer(self.headers.get("Authorization")))
            if scope != tokens.RUN:                            # 토큰은 맞지만 보기 전용: 학습을 걸 수 없다
                return self._send(403, {"error": "this token is read-only"})
            try:
                try:
                    # NaN·Infinity는 받지 않는다. ★목표에 NaN을 넣으면 저장되고, /runs에 그대로 실려
                    #   브라우저·맥의 엄격한 JSON 파서가 목록 전체를 못 읽었다(되돌릴 화면도 안 떴다)
                    body = json.loads(raw or b"{}", parse_constant=_no_constant)
                except ValueError:
                    return self._send(400, {"error": "body must be JSON"})
                if not isinstance(body, dict):
                    return self._send(400, {"error": "body must be a JSON object"})
                route = urlparse(self.path).path.rstrip("/")
                if route == "/shutdown":            # 옛 도우미를 새 판으로 바꿀 때(setup·트레이·epokio agent --stop)
                    self._send(200, {"ok": True})
                    import threading
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
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
    """epokio-agent. 본체는 server_cli.py(파일 길이 상한 때문에 나눴다)"""
    from .server_cli import main as run
    run()


if __name__ == "__main__":
    main()
