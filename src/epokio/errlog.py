"""문제 신고용 오류 기록. 자동 전송은 없다: 파일로 남기고, 사용자가 보고 직접 이슈로 올린다.

* `record(...)`: 오류 한 건을 ~/.epokio/logs/errors.log 에 덧붙인다(크기 상한을 넘으면 .1 로 밀어낸다)
* `issue_body(...)`: 최근 기록 + 버전·OS·파이썬 버전을 모아 GitHub 이슈 본문 텍스트를 만든다
홈 경로는 `~`로 바꿔 적는다(사용자 이름이 새지 않게). 표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import os
import platform
import re
import sys
import time
import traceback
from pathlib import Path

MAX_BYTES = 256 * 1024          # 파일 하나 상한. 넘으면 errors.log.1 로 밀고 새로 쓴다(백업은 한 벌)
BODY_LIMIT = 6000               # 이슈 본문 글자 상한(URL 길이 제한 때문에 최근 것부터 자른다)
REPO_URL = "https://github.com/8rulerstar/epokio"


def log_dir(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".epokio" / "logs"


def scrub(text: str, home: Path | None = None) -> str:
    """홈 경로를 `~`로 바꾼다. 실제 경로(realpath)도 함께 바꾼다."""
    h = str(home or Path.home()).rstrip("/")
    if not h or h == "/":
        return text
    variants = sorted({h, os.path.realpath(h)}, key=len, reverse=True)
    for v in variants:      # 뒤가 경로 끝(/, 공백, 따옴표 등)일 때만: /Users/a 가 /Users/ab 를 먹지 않게
        text = re.sub(re.escape(v) + r"(?![\w.-])", "~", text)
    return text


def _rotate(path: Path, max_bytes: int) -> None:
    try:
        if path.stat().st_size >= max_bytes:
            os.replace(path, path.with_name(path.name + ".1"))
    except FileNotFoundError:
        pass


def record(where: str, exc: BaseException | None = None, message: str = "",
           home: Path | None = None, max_bytes: int = MAX_BYTES) -> Path | None:
    """오류 한 건을 남긴다. 기록 실패가 원래 일을 막으면 안 되므로 예외를 삼키고 None을 돌려준다."""
    try:
        d = log_dir(home)
        d.mkdir(parents=True, exist_ok=True)
        path = d / "errors.log"
        _rotate(path, max_bytes)
        lines = [f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {where}" + (f": {message}" if message else "")]
        if exc is not None:
            lines.append("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip())
        with path.open("a", encoding="utf-8") as f:
            f.write(scrub("\n".join(lines), home) + "\n")
        return path
    except OSError:
        return None


def recent(home: Path | None = None, max_chars: int = BODY_LIMIT) -> str:
    """최근 기록을 끝에서부터 max_chars 글자만(백업 파일이 있으면 그 뒤를 이어서)."""
    d = log_dir(home)
    text = ""
    for name in ("errors.log.1", "errors.log"):
        try:
            text += (d / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    text = scrub(text, home)
    if len(text) > max_chars:
        cut = text[-max_chars:]
        nl = cut.find("\n")
        text = cut[nl + 1:] if 0 <= nl < 200 else cut
    return text.strip()


def environment() -> dict[str, str]:
    try:
        from importlib.metadata import version
        ver = version("epokio")
    except Exception:
        ver = "unknown"
    mac = platform.mac_ver()[0]
    return {"epokio": ver,
            "os": f"macOS {mac}" if mac else f"{platform.system()} {platform.release()}",
            "machine": platform.machine(),
            "python": platform.python_version()}


def issue_body(home: Path | None = None, note: str = "", max_chars: int = BODY_LIMIT) -> str:
    """이슈 본문. 환경 표 + 사용자 메모 + 최근 오류 기록. 전체가 max_chars를 넘지 않게 기록 쪽을 줄인다."""
    env = environment()
    head = ["### What happened", note.strip() or "(describe what you were doing)", "",
            "### Environment", *[f"- {k}: {v}" for k, v in env.items()], "", "### Recent errors"]
    head_text = scrub("\n".join(head), home)
    room = max(0, max_chars - len(head_text) - 20)
    log = recent(home, room) if room else ""
    return head_text + "\n```\n" + (log or "(no errors recorded)") + "\n```\n"


if __name__ == "__main__":     # python -m epokio.errlog : 본문을 찍기만 한다(보내지 않는다)
    sys.stdout.write(issue_body())
