"""Tokens for the execution API.

Any request that *runs* something is never accepted without a token.
  -> Stops someone on the same Wi-Fi from running arbitrary commands on the training PC.
This covers every POST, plus GETs that execute something or read outside the watched folders (GET_NEEDS_TOKEN).
GETs that only *view* progress (runs, system, events, run, health) stay open. The web UI uses only those.
The Swift app on the same Mac reads this file directly. For a remote machine, the user pastes its token once.

There are two kinds of token:
  * ~/.epokio/token  : the original single token. Its scope is always 'run'. The app reads this file
  * ~/.epokio/tokens.json : multiple per-person tokens (name, scope, fingerprint). See tokens.py
There are only two scopes: read (view only) and run (also start and stop training).
"""
from __future__ import annotations

import hmac
import os
import re
import secrets
from pathlib import Path

TOKEN_FILE = Path.home() / ".epokio" / "token"

# Config keys that may be secret (their values are never exported). Every place that exports config (/sweep, /run) uses this.
# Previously only /sweep filtered, so tokenless GET /run showed args.yaml's api_key (all_args) to anyone on the machine/LAN
SECRET_KEY = re.compile(r"(key|token|secret|passw|api|auth|credential|cookie|session)", re.IGNORECASE)


def without_secrets(d):
    """Copy without secret-looking keys (nested dicts included). Non-dicts are returned as is"""
    if not isinstance(d, dict):
        return d
    return {k: without_secrets(v) for k, v in d.items() if not SECRET_KEY.search(str(k))}


def _chmod(p: Path, mode: int):
    """Windows has no POSIX permissions, so this silently does nothing there"""
    if os.name == "nt":
        return
    try:
        os.chmod(p, mode)
    except OSError:
        pass


def private_dir(p: Path) -> Path:
    """Owner-only folder (0700), e.g. ~/.epokio, logs"""
    p.mkdir(parents=True, exist_ok=True)
    _chmod(p, 0o700)
    return p


def private_file(p: Path):
    """If it exists, just fix its mode to 0600. Use create_private for new files"""
    if p.exists():
        _chmod(p, 0o600)


def create_private(p: Path, text: str) -> bool:
    """Create a 0600 file with O_EXCL (unreadable by others from the moment it exists). False if it already exists"""
    private_dir(p.parent)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    return True


_CACHE: dict[Path, str] = {}


def _read(f: Path) -> str | None:
    try:
        t = f.read_text().strip()
    except OSError:
        return None
    return t if len(t) >= 32 else None


def token() -> str:
    """This machine's token. Created once if missing.
    Previously the file was re-read on every request, and reading it mid-write (empty) created a new token over it,
      silently killing tokens users had pasted. It was also created as 0644 then chmodded, briefly readable by other users.
      Now: written to a 0600 temp file from the start and put in place with link, which never overwrites. The value is cached"""
    f = TOKEN_FILE
    if f in _CACHE:
        return _CACHE[f]
    private_file(f)                                # fix it even if an older version created it as 644
    t = _read(f)
    if t is None:
        private_dir(f.parent)
        new = secrets.token_urlsafe(32)
        tmp = f.with_name(f"{f.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as out:
                out.write(new)
                out.flush()
                os.fsync(out.fileno())
            try:
                if f.exists() and _read(f) is None:
                    os.replace(tmp, f)             # only replace a short or broken old file
                else:
                    os.link(tmp, f)                # FileExistsError if another process started at the same time wrote first
            except FileExistsError:
                pass
            except OSError:                        # file system without hard links
                if _read(f) is None:
                    os.replace(tmp, f)
        finally:
            tmp.unlink(missing_ok=True)
        t = _read(f) or new
    _CACHE[f] = t
    return t


def bearer(header_value: str | None) -> str:
    """Just the token from "Authorization: Bearer <token>"."""
    if not header_value or not header_value.startswith("Bearer "):
        return ""
    return header_value[7:].strip()


def verify(tok: str) -> str | None:
    """This token's scope: "run", "read" or None (unknown token).
    The single token (~/.epokio/token) is always run. Breaking that compatibility stops the Mac app from starting training"""
    if not tok:
        return None
    from . import tokens as tokenstore
    # Guards against timing attacks. Compared as bytes (as str, non-ASCII tokens like Hangul raised TypeError, dropping the connection)
    if hmac.compare_digest(tok.encode(), token().encode()):
        return tokenstore.RUN
    return tokenstore.verify(tok)


def header_scope(header_value: str | None) -> str | None:
    """Looks only at the header (Bearer). Cookies can be sent by other sites, so they are not used for execution requests"""
    return verify(bearer(header_value))


def page_url(base: str) -> str:
    """URL to open the web UI on this machine. On the same machine, the token goes after '#' so training and queue tabs open.
    The part after '#' never reaches the server, and the web UI clears it from the address bar on read. Never added to remote URLs.
    Previously the lock card said to run `epokio-agent --show-token`, which exe users don't have, so they were stuck"""
    from urllib.parse import urlsplit
    base = base.rstrip("/") + "/"
    return base + "#t=" + token() if urlsplit(base).hostname in ("127.0.0.1", "localhost") else base


def check(header_value: str | None) -> bool:
    """Is this a valid token (scope not checked)? Old name kept"""
    return header_scope(header_value) is not None


def post_scope(header_value: str | None) -> str | None:
    """Scope for letting an execution request (POST) through. None means 401, "read" means 403, "run" means execute.
    A token check() accepts but that is not in the list counts as run (the old gate is kept for backward compatibility)"""
    if not check(header_value):
        return None
    from . import tokens as tokenstore
    return header_scope(header_value) or tokenstore.RUN


COOKIE = "epokio_token"


def cookie_token(headers) -> str:
    for part in (headers.get("Cookie") or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE and v:
            return v.strip()
    return ""


def presented(headers) -> str:
    """The token that let this request through (used when re-issuing the cookie). Empty string if none"""
    tok = bearer(headers.get("Authorization"))
    if verify(tok):
        return tok
    tok = cookie_token(headers)
    return tok if verify(tok) else ""


def request_scope(headers) -> str | None:
    """Scope from the header or a same-site cookie. The cookie exists because web UI images (<img>) cannot send headers"""
    return header_scope(headers.get("Authorization")) or verify(cookie_token(headers))


def check_request(headers) -> bool:
    return request_scope(headers) is not None


def is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


# Only the view GETs listed here are open without a token. Everything else needs one (new routes are locked automatically).
# Previously this listed what to lock instead, so every new GET shipped open (that is how the 2026-09-23 incident happened).
#   Locked examples: /schema, /pythons (launch executables given by others), /names, /health-check (walk outside watched folders),
#   /jobs* (run commands and full training logs)
# The web UI view tabs call only runs, system, events, run, file; the start-training and queue tabs send the token as Bearer.
# The Mac app (AgentClient) and MCP server send Bearer on every request. server.py serves /file only inside watched folders.
# /sweep is locked: it carries all of hparams.yaml (may hold secret keys). Once open, letting anyone on the LAN read wandb keys
# Mac-side views: /ai (AI usage, menu bar character), /runs/table (a few config cells, no secrets), /review/state (review verdicts)
OPEN_GET = ("/runs", "/system", "/events", "/run", "/health", "/config", "/webhooks",
            "/ai", "/runs/table", "/review/state")


def get_needs_token(route: str) -> bool:
    route = route.split("?")[0].rstrip("/") or "/runs"
    return route not in OPEN_GET


def request_roots(headers):
    """Folders assigned to the token that let this request through (scope.py). None if none"""
    from . import tokens as tokenstore
    return tokenstore.roots_for(presented(headers))
