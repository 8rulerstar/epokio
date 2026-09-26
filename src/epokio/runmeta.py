"""학습마다 붙이는 사람의 기록: 별표·태그·메모·목표 점수. ~/.epokio/runmeta.json 하나에 둔다.

학습 폴더 안에는 쓰지 않는다(남의 폴더·읽기 전용 폴더일 수 있다). 경로는 key()로 맞춰 키로 쓴다.
목표 점수(goal)는 agent가 지켜보다가 넘으면 'goal' 사건을 쌓는다(W&B의 지표 문턱 알림을 가져온 것).
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
import unicodedata
from pathlib import Path

FILE = Path.home() / ".epokio" / "runmeta.json"
_lock = threading.Lock()
FIELDS = {"star": bool, "tags": list, "note": str, "goal": (int, float, type(None)), "goal_hit": bool, "stage": str,
          "collections": list,                                      # 내가 만든 모음(폴더처럼). 한 학습이 여러 모음에
          # 대표 점수를 사람이 고른다(W&B의 요약 지표처럼). metric: 열 이름, lower: 낮을수록 좋은가
          "metric": (str, type(None)), "lower": bool}
STAGES = {"", "candidate", "production", "archived"}          # 모델 단계 (빈 값 = 없음)
VERSION = 0                  # 저장할 때마다 1씩. scan이 대표 점수 설정을 바로 다시 읽게


def key(path: str) -> str:
    """한 폴더는 한 키. 쓰는 쪽은 사람이 보낸 글자, 읽는 쪽은 scan이 만든 글자라 반드시 여기를 거친다.

    윈도우는 같은 폴더를 여러 가지로 적을 수 있다. C:/x 와 C:\\x\\ 와 c:\\x 가 전부 같은 곳이다.
    normpath가 구분자와 끝 슬래시를, normcase가 대소문자를 맞춘다(맥·리눅스에서 normcase는 아무것도 안 한다).
    resolve()를 안 쓰는 건 디스크를 만지지 않으려는 것이다. 지워졌거나 안 붙은 원격 폴더도 키는 나와야 한다.
    """
    s = str(path)
    if not s:
        return ""
    return unicodedata.normalize("NFC", os.path.normcase(os.path.normpath(s)))


def load() -> dict:
    """키를 맞춰서 돌려준다. 정규화 전에 저장된 옛 파일도 그대로 찾아진다.

    파일을 여기서 고쳐 쓰지는 않는다. update()가 다음에 쓸 때 맞춰진 키로 저장되며 스스로 낫는다.
    한 폴더가 두 키로 들어 있으면(이 버그가 남긴 흔적) 뒤에 오는 줄이 이긴다.
    """
    try:
        return _read(strict=False)
    except (OSError, ValueError):
        return {}


def _read(strict: bool) -> dict:
    """파일이 없으면 빈 것. 윈도우에서 바꿔치기 중이라 잠깐 못 읽으면 다시 해 본다.
    strict면 깨졌거나 끝내 못 읽을 때 예외(★예전엔 '빈 것'으로 보고 update가 그 위에 써서 별표·메모가 전부 지워졌다)"""
    if not FILE.exists():
        return {}
    for i in range(6):
        try:
            raw = json.loads(FILE.read_text(encoding="utf-8"))
            break
        except PermissionError:
            if i == 5:
                raise
            time.sleep(0.05 * (i + 1))
    if not isinstance(raw, dict):
        if strict:
            raise ValueError(f"{FILE} is not a JSON object")
        return {}
    return {key(k): v for k, v in raw.items()}


def get(path: str) -> dict:
    return load().get(key(path), {})


def update(path: str, changes: dict) -> dict:
    """알려진 칸만, 형식이 맞을 때만 바꾼다. 목표를 바꾸면 '이미 넘음' 표시는 지운다."""
    with _lock:
        try:
            all_ = _read(strict=True)
        except ValueError:
            # 손으로 고치다 깨졌다. 지우지 않고 옆에 남긴 뒤 새로 시작한다(무엇이 있었는지는 .broken에 그대로)
            FILE.replace(FILE.with_suffix(f".broken-{int(time.time())}.json"))
            all_ = {}
        global VERSION
        VERSION += 1
        m = dict(all_.get(key(path), {}))
        for k, v in changes.items():
            # bool은 int이기도 하다(★goal: true 가 목표 1로 들어갔다). 숫자는 유한한 것만
            if k in FIELDS and isinstance(v, FIELDS[k]) and not (k == "goal" and isinstance(v, bool)):
                if k == "goal" and v is not None and not math.isfinite(v):
                    continue
                if k in ("tags", "collections"):
                    v = sorted({str(t).strip()[:60] for t in v if str(t).strip()})[:12]
                if k == "note":
                    v = v[:2000]
                if k == "metric" and v is not None:
                    v = v[:200]
                if k == "stage" and v not in STAGES:
                    continue
                m[k] = v
        before = {k: all_.get(key(path), {}).get(k) for k in ("goal", "metric", "lower")}
        if not m.get("metric"):
            m.pop("lower", None)     # 고른 점수가 없으면 방향도 없다(★lower만 켜져 목표 판정이 거꾸로 됐다)
        # 값이 실제로 바뀔 때만 다시 본다(★바꾸지 않고 저장만 눌러도 이미 보낸 목표 알림이 또 갔다)
        if any((m.get(k) or None) != (v or None) for k, v in before.items()):      # False·None·""는 같다
            m["goal_hit"] = False
        m = {k: v for k, v in m.items() if v is not False and v not in (None, "", [])}   # 빈 칸은 저장하지 않는다
        if m.get("goal") is None:
            m.pop("goal_hit", None)
        if m:
            all_[key(path)] = m
        else:
            all_.pop(key(path), None)
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(all_, ensure_ascii=False, indent=1), encoding="utf-8")
        # ★윈도우는 다른 스레드가 읽는 중인 파일을 바꿔치기하지 못한다(WinError 5). 잠깐 뒤에 다시
        for i in range(5):
            try:
                tmp.replace(FILE)
                break
            except PermissionError:
                if i == 4:
                    raise
                time.sleep(0.05 * (i + 1))
        return m


def goals_reached(runs) -> list:
    """목표를 막 넘긴 학습들. 한 번 알린 것은 다시 알리지 않는다."""
    all_ = load()
    out = []
    for r in runs:
        m = all_.get(key(r.path))
        if not m or m.get("goal") is None or m.get("goal_hit"):
            continue
        # 방향은 scan이 실제로 쓴 것(★고른 열이 없어 자동 점수로 돌아가도 저장된 lower로 판정해 거짓 알림이 갔다).
        # scan이 방향을 안 적은 옛 Run이면 열 이름으로 추정한다(rmse처럼 낮을수록 좋은 점수)
        lower = getattr(r, "lower", None)
        if lower is None:
            from .schema import higher_is_better
            lower = not higher_is_better(r.metric_name) if r.metric_name else False
        if r.best is not None and (r.best <= m["goal"] if lower else r.best >= m["goal"]):
            update(str(r.path), {"goal_hit": True})
            out.append(r)
    return out
