"""사람마다 하나씩 주는 토큰. 이름과 권한(읽기 전용 / 실행 가능)이 붙는다.

원칙
  1. 평문으로 저장하지 않는다. 파일에는 sha256 지문만 남고, 진짜 토큰은 발급할 때 한 번만 보여 준다
     (토큰은 32바이트 난수라 사전 공격이 뜻이 없다. 느린 KDF는 요청마다 붙으면 손해다)
  2. 파일은 0600, 폴더는 0700 (auth.private_dir/create_private과 같은 규칙)
  3. 기존 ~/.epokio/token(단일 토큰)은 그대로 둔다. 그 토큰은 계속 '실행 가능'이다
     (맥 앱이 그 파일을 직접 읽는다. 여기서 형식을 바꾸면 앱이 붙지 못한다)
  4. 발급·폐기는 HTTP로 열지 않는다. 그 기계에서 명령으로만 한다
     (실행 토큰 하나가 새 토큰을 찍어낼 수 있으면 권한 구분이 뜻을 잃는다)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

FILE = Path.home() / ".epokio" / "tokens.json"

READ = "read"          # 보기만
RUN = "run"            # 학습 시작·중지까지
SCOPES = (READ, RUN)


def digest(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


def _path() -> Path:
    return FILE


def load() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("hash")] if isinstance(data, list) else []


def _save(entries: list[dict]):
    from .auth import private_dir
    p = _path()
    private_dir(p.parent)
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=1)
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    tmp.replace(p)
    if os.name != "nt":
        os.chmod(p, 0o600)              # replace가 tmp의 권한을 가져가지만, 옛 파일이 644였던 경우까지 교정


def listed() -> list[dict]:
    """화면·명령줄용. 지문은 빼고 앞 8자만 보여 준다(어느 줄이 어느 토큰인지 알아보게)."""
    return [{"id": e.get("id", ""), "name": e.get("name", ""), "scope": e.get("scope", RUN),
             "created": e.get("created", 0), "last_used": e.get("last_used", 0)} for e in load()]


def issue(name: str, scope: str = RUN) -> tuple[str, dict]:
    """(평문 토큰, 기록). 평문은 여기서 한 번 돌려주고 어디에도 남기지 않는다."""
    name = (str(name or "").strip() or "token")[:60]
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}")
    tok = secrets.token_urlsafe(32)
    entry = {"id": secrets.token_hex(4), "name": name, "scope": scope,
             "hash": digest(tok), "created": time.time(), "last_used": 0}
    _save(load() + [entry])
    return tok, entry


def revoke(which: str) -> bool:
    """id 또는 이름으로 지운다."""
    want = str(which or "").strip()
    keep = [e for e in load() if e.get("id") != want and e.get("name") != want]
    if len(keep) == len(load()):
        return False
    _save(keep)
    return True


def verify(tok: str) -> str | None:
    """맞는 토큰이면 권한(read·run), 아니면 None."""
    if not tok:
        return None
    d = digest(tok)
    for e in load():
        if hmac.compare_digest(str(e.get("hash", "")), d):      # 시간차 공격 방지
            return e.get("scope") if e.get("scope") in SCOPES else RUN
    return None
