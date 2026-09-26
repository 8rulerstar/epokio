"""실행 API용 토큰.

무언가를 '실행'하는 요청은 토큰 없이는 절대 받지 않는다.
  → 같은 와이파이의 누군가가 학습 PC에서 아무 명령이나 돌리는 일을 막는다.
POST는 전부 해당하고, GET도 실행하거나 감시 폴더 밖을 읽는 것은 해당한다(GET_NEEDS_TOKEN).
진행을 '보기만' 하는 GET(runs·system·events·run·health)은 열어 둔다. 웹 화면이 그것만 쓴다.
같은 맥의 스위프트 앱은 이 파일을 직접 읽는다. 원격 기계의 토큰은 사용자가 한 번 붙여 넣는다.

토큰은 둘이다.
  * ~/.epokio/token  : 예전부터 있는 단일 토큰. 권한은 늘 '실행 가능'(run). 앱이 이 파일을 읽는다
  * ~/.epokio/tokens.json : 사람마다 발급하는 여러 토큰(이름·권한·지문). tokens.py
권한은 read(보기만)·run(학습 시작·중지까지) 둘뿐이다.
"""
from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

TOKEN_FILE = Path.home() / ".epokio" / "token"


def _chmod(p: Path, mode: int):
    """윈도우는 POSIX 권한이 없어 조용히 넘어간다"""
    if os.name == "nt":
        return
    try:
        os.chmod(p, mode)
    except OSError:
        pass


def private_dir(p: Path) -> Path:
    """나만 들어가는 폴더(0700). ~/.epokio·logs 등"""
    p.mkdir(parents=True, exist_ok=True)
    _chmod(p, 0o700)
    return p


def private_file(p: Path):
    """있으면 권한만 0600으로 교정. 새로 만들 파일은 create_private로"""
    if p.exists():
        _chmod(p, 0o600)


def create_private(p: Path, text: str) -> bool:
    """O_EXCL로 0600 파일을 만든다(만드는 순간부터 남이 못 읽게). 이미 있으면 False"""
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
    """이 기계의 토큰. 없으면 한 번만 만든다.
    ★예전엔 요청마다 파일을 다시 읽고, 쓰는 도중(빈 파일)을 읽으면 새 토큰을 만들어 덮었다. 붙여 넣어 둔 토큰이 조용히 죽었다.
      그리고 0644로 만든 뒤 chmod해서, 잠깐 다른 사용자가 읽을 수 있었다.
      이제: 처음부터 0600 임시 파일에 쓰고, 이미 있으면 절대 덮지 않는(link) 방식으로 내건다. 읽은 값은 기억해 둔다"""
    f = TOKEN_FILE
    if f in _CACHE:
        return _CACHE[f]
    private_file(f)                                # 예전 버전이 644로 만들었어도 교정
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
                    os.replace(tmp, f)             # 짧거나 깨진 옛 파일만 바꾼다
                else:
                    os.link(tmp, f)                # 동시에 처음 켠 다른 프로세스가 먼저 썼으면 FileExistsError
            except FileExistsError:
                pass
            except OSError:                        # 하드링크를 못 하는 파일 시스템
                if _read(f) is None:
                    os.replace(tmp, f)
        finally:
            tmp.unlink(missing_ok=True)
        t = _read(f) or new
    _CACHE[f] = t
    return t


def bearer(header_value: str | None) -> str:
    """Authorization: Bearer <토큰> 에서 토큰만."""
    if not header_value or not header_value.startswith("Bearer "):
        return ""
    return header_value[7:].strip()


def verify(tok: str) -> str | None:
    """이 토큰의 권한: "run" · "read" · None(모르는 토큰).
    ★단일 토큰(~/.epokio/token)은 늘 run이다. 하위 호환이 깨지면 맥 앱이 학습을 못 건다"""
    if not tok:
        return None
    from . import tokens as tokenstore
    # 시간차 공격 방지. ★바이트로 비교한다(문자열이면 한글 같은 비ASCII 토큰에서 TypeError로 연결이 끊겼다)
    if hmac.compare_digest(tok.encode(), token().encode()):
        return tokenstore.RUN
    return tokenstore.verify(tok)


def header_scope(header_value: str | None) -> str | None:
    """헤더(Bearer)만 본다. 쿠키는 남의 사이트가 대신 보낼 수 있어 실행 요청에는 쓰지 않는다"""
    return verify(bearer(header_value))


def page_url(base: str) -> str:
    """이 기계에서 웹 화면을 열 주소. 같은 기계면 토큰을 '#' 뒤에 실어 학습·대기열 탭이 바로 열리게 한다.
    ★'#' 뒤는 서버로 가지 않고, 웹 화면이 읽자마자 주소창에서 지운다. 원격 주소에는 절대 싣지 않는다.
    예전엔 잠금 카드가 `epokio-agent --show-token`을 치라고 했는데 exe 사용자에겐 그런 명령이 없어 막혔다"""
    from urllib.parse import urlsplit
    base = base.rstrip("/") + "/"
    return base + "#t=" + token() if urlsplit(base).hostname in ("127.0.0.1", "localhost") else base


def check(header_value: str | None) -> bool:
    """맞는 토큰인가(권한은 묻지 않는다). 예전 이름 그대로"""
    return header_scope(header_value) is not None


def post_scope(header_value: str | None) -> str | None:
    """실행 요청(POST)을 통과시킬 권한. None이면 401, "read"면 403, "run"이면 실행.
    check()가 통과시킨 토큰인데 목록에 없으면 run으로 본다(예전 관문을 그대로 두어 하위 호환)"""
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
    """이 요청을 통과시킨 토큰(쿠키를 다시 내줄 때 쓴다). 없으면 빈 문자열"""
    tok = bearer(headers.get("Authorization"))
    if verify(tok):
        return tok
    tok = cookie_token(headers)
    return tok if verify(tok) else ""


def request_scope(headers) -> str | None:
    """헤더 또는 같은 사이트 쿠키로 본 권한. 쿠키는 웹 화면의 그림(<img>)이 헤더를 못 보내서 쓴다"""
    return header_scope(headers.get("Authorization")) or verify(cookie_token(headers))


def check_request(headers) -> bool:
    return request_scope(headers) is not None


def is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


# 토큰 없이 여는 GET은 여기 적은 '보기'뿐이다. 나머지는 전부 토큰(새로 만든 경로도 저절로 잠긴다).
# ★예전엔 반대로 '잠글 것'을 적어서, 새 GET을 만들 때마다 열린 채로 나갔다(2026-09-23 사고가 그렇게 났다).
#   잠긴 것의 예: /schema·/pythons(남이 준 실행 파일을 띄운다), /names·/health-check(감시 폴더 밖을 걷는다),
#   /jobs*(실행 명령·학습 로그 전문)
# 웹 화면의 보기 탭은 runs·system·events·run·file만 부르고, 학습 시작·대기열 탭은 토큰을 Bearer로 싣는다.
# 맥 앱(AgentClient)과 MCP 서버는 모든 요청에 Bearer를 싣는다. /file은 server.py가 따로 감시 폴더 안만 내준다.
# /sweep는 잠근다: hparams.yaml 전부(비밀 키가 들 수 있다)를 싣는다. ★열어 두어 LAN의 누구나 wandb 키를 읽을 수 있었다
# 맥 쪽에서 더한 보기: /ai(AI 사용량, 메뉴 막대 캐릭터) · /runs/table(설정 몇 칸, 비밀 키 없음) · /review/state(검수 판정)
OPEN_GET = ("/runs", "/system", "/events", "/run", "/health", "/config", "/webhooks",
            "/ai", "/runs/table", "/review/state")


def get_needs_token(route: str) -> bool:
    route = route.split("?")[0].rstrip("/") or "/runs"
    return route not in OPEN_GET
