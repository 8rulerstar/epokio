"""AI 도구를 지금 얼마나 쓰고 있나. 메뉴바 캐릭터 속도(barPaceSource = "aiUse")의 재료다.

두 가지 출처가 있다.

  1) 이 맥에서 도는 AI 도구 프로세스의 CPU (기본, 키도 인터넷도 필요 없다)
     `ps -Ao %cpu=,comm=` 한 번이면 된다. sysinfo._mac_cpu_ai가 ps를 한 번만 불러 CPU와 같이 내므로 추가 비용은 0이다.
     ★프로세스의 '실행 파일 경로'만 본다. 명령줄 인자(`comm`이 아니라 `command`)는 읽지 않는다.
       인자에는 파일 경로나 프롬프트가 섞일 수 있어서다.
     ★대화 내용·프롬프트·토큰 기록·설정 파일은 어떤 것도 읽지 않는다. 재는 것은 "지금 일하는 중인가"
       하나뿐이고 "무엇을 말했나"는 이 기능과 무관하다.

  2) AI 도구가 스스로 알려 주는 값 (더 정확)
     MCP 도구 `report_ai_activity` 또는 POST /ai/report. 토큰이 필요하고 0~100 범위만 받는다.
     1)은 네트워크를 기다리는 동안(생각 중)을 못 본다. 2)는 도구가 직접 말하므로 그 구멍이 없다.

우선순위: 2)가 FRESH_SEC 안에 들어와 있으면 2)를 쓴다. 도구가 자기 상태를 직접 말한 것이
프로세스 CPU라는 대리 지표보다 정확하고, "이제 끝났다(0)"를 말할 수 있어야 캐릭터가 멈춘다.
max(1, 2)를 쓰면 0 보고가 무시돼 멈출 방법이 없어진다.

값이 끊기면: 마지막 보고에서 FRESH_SEC가 지나면 2)는 없는 셈이 되고 1)로 내려간다.
1)도 조용하면 0이다. 옛 값을 계속 들고 달리는 일은 없다.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

TOOLS_FILE = Path.home() / ".epokio" / "ai_tools.json"

# 기본 목록. 근거: 맥에서 흔한 AI 코딩 도구와 로컬 추론 서버 가운데, 실행 파일 경로에
# 이름이 그대로 드러나는 것들. 사람마다 쓰는 도구가 다르므로 TOOLS_FILE로 통째로 갈아끼운다.
#   claude   Claude 데스크톱 · Claude Code (이 맥에서 실측 확인)
#   codex · gemini · aider · copilot · cursor   AI 코딩 도구(CLI·에디터·언어 서버)
#   ollama · lm studio · llama · mlx · vllm · gpt4all   로컬 추론(맥에서 GPU·CPU를 실제로 태운다)
DEFAULT_TOOLS = ["claude", "codex", "gemini", "aider", "copilot", "cursor",
                 "ollama", "lm studio", "llama", "mlx", "vllm", "gpt4all"]

# 이름이 겹치는 시스템 프로세스. 경계 규칙이 이미 걸러내지만 한 번 더 막는다.
# CursorUIViewService는 macOS의 글자 커서 도우미지 에디터 Cursor가 아니다.
DENY = ("cursoruiviewservice",)

# 코어 하나를 꽉 채우면 100%. 근거: ollama 같은 로컬 추론은 코어 여러 개를 태우므로 금방 천장에 닿고,
# Claude Code처럼 네트워크를 기다리는 도구는 일할 때 코어 0.1~0.3개를 쓴다(실측 6~26%).
# 기계 전체(12코어) 기준으로 나누면 후자가 1~2%가 되어 RunnerPace.stopBelow 5%에 걸려 영영 안 달린다.
FULL_CPU = 100.0
FRESH_SEC = 90.0        # 보고가 이보다 오래되면 버린다. AI 한 턴이 30~60초 이어지는 일이 흔해
                        # 그보다 짧으면 일하는 중에 캐릭터가 껌뻑인다. 넘으면 끝난 것으로 본다.
MIN_GAP = 0.5           # 보고 최소 간격(초). 더 자주 부르면 429


def _cfg() -> dict:
    try:
        d = json.loads(TOOLS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def tools() -> list[str]:
    """알아볼 도구 이름. 환경변수 EPOKIO_AI_TOOLS(쉼표) > ~/.epokio/ai_tools.json > 기본값"""
    env = os.environ.get("EPOKIO_AI_TOOLS")
    if env is not None:
        return clean_tools(env.split(","))
    got = _cfg().get("tools")
    return clean_tools(got) if isinstance(got, list) else list(DEFAULT_TOOLS)


def clean_tools(names) -> list[str]:
    """믿을 수 없는 입력을 거른다: 문자열만, 소문자, 40자 이내, 30개까지, 빈 것 제외"""
    out = []
    for n in names or []:
        if not isinstance(n, str):
            continue
        s = " ".join(n.strip().lower().split())[:40]
        if s and s not in out:
            out.append(s)
    return out[:30]


def save_tools(names) -> list[str]:
    got = clean_tools(names)
    TOOLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOOLS_FILE.write_text(json.dumps({**_cfg(), "tools": got}, indent=1), encoding="utf-8")
    return got


def _match(names: list[str]):
    """이름 앞뒤가 영숫자가 아닐 때만 맞는 것으로 친다.
    'ollama' 안의 'llama'나 'CursorUIViewService' 안의 'cursor'를 세지 않기 위해서다."""
    if not names:
        return None
    body = "|".join(re.escape(n) for n in names)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")


def scan_ps(out: str, names: list[str] | None = None) -> float | None:
    """`ps -Ao %cpu=,comm=` 결과 → AI 도구 사용률(0~100). 줄 하나 = "  6.4 /경로/실행파일".
    돌아가는 도구가 없으면 0.0, ps가 비었으면 None."""
    if not out.strip():
        return None
    pat = _match(names if names is not None else tools())
    if pat is None:
        return 0.0
    total = 0.0
    for line in out.splitlines():
        part = line.strip().split(None, 1)
        if len(part) != 2:
            continue
        try:
            pct = float(part[0])
        except ValueError:
            continue
        path = part[1].lower()
        if any(d in path for d in DENY):
            continue
        if pat.search(path):
            total += pct
    return min(total / FULL_CPU * 100.0, 100.0)


# ── 출처 2: 도구가 알려 주는 값 ──────────────────────────────

_LOCK = threading.Lock()
_LAST: dict = {}        # {"value": float, "at": float, "by": str}


def report(value, by: str = "", now: float | None = None) -> float:
    """믿을 수 없는 입력. 숫자가 아니면 ValueError, 범위 밖이면 잘라 낸다. 너무 잦으면 ValueError."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("activity must be a number from 0 to 100")
    v = float(value)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("activity must be a number from 0 to 100")
    v = min(max(v, 0.0), 100.0)
    now = time.time() if now is None else now
    with _LOCK:
        last = _LAST.get("at")
        if last is not None and 0 <= now - last < MIN_GAP:
            raise TooOften("too many reports: at most one every %.1fs" % MIN_GAP)
        _LAST.update(value=v, at=now, by=str(by)[:40])
    return v


class TooOften(ValueError):
    """부르는 간격이 너무 짧다 (HTTP 429)"""


def reported(now: float | None = None) -> float | None:
    """FRESH_SEC 안에 들어온 보고만. 지나면 None이고, 부르는 쪽이 출처 1로 내려간다."""
    now = time.time() if now is None else now
    with _LOCK:
        at, v = _LAST.get("at"), _LAST.get("value")
    if at is None or v is None or now - at > FRESH_SEC or now < at - FRESH_SEC:
        return None
    return v


def combine(scanned: float | None, now: float | None = None) -> tuple[float | None, str]:
    """(사용률, 출처). 신선한 보고가 있으면 그것을, 없으면 프로세스 값을."""
    r = reported(now)
    if r is not None:
        return r, "reported"
    return scanned, ("process" if scanned is not None else "none")


def status(now: float | None = None) -> dict:
    """GET /ai 용. 값이 어디서 왔고 마지막 보고가 몇 초 전인지."""
    now = time.time() if now is None else now
    with _LOCK:
        at, by = _LAST.get("at"), _LAST.get("by")
    return {"tools": tools(), "fresh_sec": FRESH_SEC,
            "reported": reported(now), "reported_age": (now - at) if at else None, "reported_by": by}


def _reset_for_tests():
    with _LOCK:
        _LAST.clear()
