"""agent 포트 정하기와 찾기.

8787은 RStudio Server 기본 포트라 연구실 GPU 서버에서 이미 쓰이는 일이 있다. 그래서:
* 기동: 기본 포트가 막혀 있으면 +SPAN 안의 빈 포트로 옮긴다. 사용자가 --port를 직접 줬으면 옮기지 않고
  멈춘다(원격 앱·SSH 터널·방화벽이 그 번호를 믿고 있다).
* 공유: 실제 포트를 ~/.epokio/agent.json 에 적고 끝날 때 지운다. 앱·트레이·MCP·epokio watch는
  이 파일 → /health 순서로 찾는다. /health 응답이 Epokio 모양이 아니면 다른 프로그램으로 본다.
"""
from __future__ import annotations

import errno
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PORT = 8787
NO_AGENT = "http://127.0.0.1:1"   # 붙을 곳이 없을 때(닫힌 포트). 화면에는 "agent 꺼짐"으로 보인다
SPAN = 20                        # 기본 포트에서 몇 칸까지 옮겨 보나


def record_file() -> Path:
    return Path.home() / ".epokio" / "agent.json"


def url_for(port: int, host: str = "127.0.0.1") -> str:
    return f"http://{host}:{port}"


def probe(url: str, timeout: float = 1.0) -> str | None:
    """'epokio' · 'other'(무언가 답하지만 Epokio가 아님) · None(아무도 없음)"""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=timeout) as r:
            body = r.read(65536)
    except urllib.error.HTTPError:
        return "other"                           # 답은 하는데 /health가 없거나 거절: Epokio가 아니다
    except (OSError, ValueError):
        return None
    try:
        d = json.loads(body)
    except ValueError:
        return "other"
    ok = isinstance(d, dict) and d.get("ok") is True and "label" in d and "version" in d
    return "epokio" if ok else "other"


def other_program_message(port: int = DEFAULT_PORT) -> str:
    return f"Port {port} is used by another program (not Epokio)."


def listening(port: int) -> bool:
    """이 기계에서 누가 그 포트로 받고 있나"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def bind(make_server, host: str, port: int | None):
    """서버를 연다. port=None이면 기본 포트부터 빈 곳을 찾는다. 돌려주는 값: (서버, 실제 포트)"""
    explicit = port is not None
    first = port if explicit else DEFAULT_PORT
    last = first if explicit else first + SPAN
    for p in range(first, last + 1):
        try:
            if listening(p):          # ★맥·BSD는 0.0.0.0에 떠 있는 포트도 127.0.0.1로는 bind가 된다(SO_REUSEADDR)
                raise OSError(errno.EADDRINUSE, "in use")
            return make_server(host, p), p
        except OSError as e:
            if e.errno not in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1), errno.EACCES):
                raise
            if p == first:
                who = probe(url_for(p))
                # ★같은 서버를 여러 사람이 쓰면 8787은 남의 Epokio일 수 있다. 내 것일 때만 "이미 실행 중",
                #   남의 것이면 조용히 다음 포트로 옮긴다(예전엔 먼저 띄운 사람이 포트를 잡으면 나머지가 못 띄웠다)
                if who == "epokio" and (explicit or mine_at(p)):
                    raise SystemExit(f"An Epokio agent is already running at {url_for(p)}")
                if explicit:
                    why = other_program_message(p) if who == "other" else f"Port {p} is already in use."
                    raise SystemExit(f"{why} Choose another one with --port, or leave --port out to pick a free port.")
    raise SystemExit(f"No free port between {first} and {last}. Choose one with --port.")


def write_record(port: int, host: str):
    from .auth import private_dir
    f = record_file()
    private_dir(f.parent)
    tmp = f.with_name(f"agent.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)   # 클라이언트가 이 파일을 믿고 토큰을 보낸다: 나만 쓰게
    with os.fdopen(fd, "w") as fh:
        fh.write(json.dumps({"pid": os.getpid(), "port": port, "host": host, "started": time.time()}))
    os.replace(tmp, f)


def read_record() -> dict | None:
    try:
        d = json.loads(record_file().read_text())
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and isinstance(d.get("port"), int) else None


def clear_record():
    """내가 쓴 기록만 지운다(뒤에 뜬 다른 agent의 기록은 둔다)"""
    d = read_record()
    if d and d.get("pid") == os.getpid():
        try:
            record_file().unlink()
        except OSError:
            pass


def _pid_alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        return True                  # 윈도우의 os.kill(pid, 0)은 프로세스를 끈다. /health 확인에 맡긴다
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False                 # 다른 사용자의 프로세스: 내 agent가 아니다
    except OSError:
        return False
    return True


def trusted_record() -> dict | None:
    """토큰을 보내도 되는 기록만: 내 소유, 남이 쓸 수 없음, 기록된 pid가 살아 있음.
    남이 기록을 바꿔 치거나 죽은 agent의 포트를 다른 프로그램이 차지하면 토큰이 그쪽으로 샌다(보안 감사 2026-09-22)"""
    f = record_file()
    try:
        st = f.stat()
    except OSError:
        return None
    if os.name != "nt":
        if st.st_uid != os.getuid() or st.st_mode & 0o022:
            return None
    d = read_record()
    if not d or not _pid_alive(d.get("pid")):
        return None
    return d


def write_url() -> str:
    """토큰을 실어 보낼(POST) 주소. 믿을 만한 기록이 없으면 기본 포트로 넘어가지 않고 실패한다"""
    d = trusted_record()
    if not d:
        raise RuntimeError("No running Epokio agent record (~/.epokio/agent.json missing, not owned by you, "
                           "writable by others, or its process is gone). Start it with `epokio-agent` and retry.")
    url = url_for(d["port"])
    if not verify_agent(url):
        raise RuntimeError(f"The agent at {url} could not prove it holds this machine's Epokio token. "
                           "Not sending the token. Restart `epokio-agent`.")
    return url


def verify_agent(url: str, timeout: float = 2.0) -> bool:
    """/health?nonce=<무작위> 의 proof = HMAC-SHA256(token, nonce) hex 를 내 토큰으로 검증(server.py와 같은 형식).
    토큰을 보내지 않고 상대가 진짜 이 기계의 agent인지 확인한다"""
    import hashlib
    import hmac
    import secrets
    from . import auth
    nonce = secrets.token_hex(16)
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/health?nonce={nonce}", timeout=timeout) as r:
            d = json.loads(r.read(65536))
    except (OSError, ValueError):
        return False
    proof = d.get("proof") if isinstance(d, dict) else None
    if not isinstance(proof, str):
        return False
    want = hmac.new(auth.token().encode(), nonce.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(proof, want)


def mine_at(port: int) -> bool:
    """그 포트의 agent가 내 토큰을 가진(=내 계정의) agent인가"""
    return verify_agent(url_for(port))


def local_url(warn: bool = False) -> str:
    """이 기계의 agent 주소: 기록 파일 → 기본 포트 순. 아무도 없으면 기본 주소(띄울 자리).
    ★기본 포트 폴백은 내 agent임을 확인했을 때만 쓴다: 공용 서버에서 남의 학습 목록이 내 화면에 뜨던 문제"""
    d = trusted_record() or read_record()
    if d and probe(url_for(d["port"])) == "epokio" and mine_at(d["port"]):
        return url_for(d["port"])
    default = url_for(DEFAULT_PORT)
    who = probe(default)
    if who == "epokio" and not mine_at(DEFAULT_PORT):
        if warn:
            print(f"An Epokio agent at {default} belongs to another user. Start your own with `epokio-agent`.", file=sys.stderr)
        return NO_AGENT                                 # 남의 agent에는 붙지 않는다
    if warn and who == "other":
        print(other_program_message(), file=sys.stderr)
    return default


def wait_local(timeout: float = 8.0) -> str | None:
    """방금 띄운 agent가 기록을 남길 때까지 기다린다"""
    end = time.time() + timeout
    while time.time() < end:
        d = read_record()
        if d and probe(url_for(d["port"]), timeout=0.5) == "epokio":
            return url_for(d["port"])
        time.sleep(0.2)
    return None
