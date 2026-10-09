"""agent가 꺼진 사이에 끝난 학습도 알린다. 도는 학습의 상태를 ~/.epokio/watch_state.json에 남기고, 다시 켜면 그때와 비교한다.

★켜면 첫 바퀴는 옛 일로 알림이 쏟아지지 않게 기준만 잡는다(monitor.py). 그래서 agent를 다시 켜는 사이(업데이트,
  트레이 끄기, 재부팅)에 끝나거나 죽은 학습은 폰 알림이 영영 없었다. 재부팅으로 학습이 같이 죽었으면 그것도 알린다(멎음).
"""
from __future__ import annotations

import time
from pathlib import Path

from . import jsonfile
from .monitor import Event, Monitor, classify

KEEP = ("running", "starting", "stalled")      # 아직 알릴 일이 남은 상태만 적는다
MAX_AGE = 2 * 86400                            # 이보다 오래 꺼져 있었으면 옛 상태로 알리지 않는다
REFRESH = 600                                  # 바뀐 게 없어도 이만큼마다 시각을 새로 적는다(며칠 도는 학습)


def file() -> Path:
    return Path.home() / ".epokio" / "watch_state.json"


def missed(mon, now: float | None = None) -> list[Event]:
    """지난번에 적은 상태와 지금 모니터가 본 상태를 비교해, 그 사이의 변화를 사건으로(같은 규칙: monitor.classify)"""
    now = time.time() if now is None else now
    try:
        saved = jsonfile.read(file(), {}, move_broken=False)
    except (OSError, ValueError):
        return []
    if not isinstance(saved, dict) or not isinstance(saved.get("runs"), dict):
        return []
    try:
        if now - float(saved.get("at") or 0) > MAX_AGE:
            return []
    except (TypeError, ValueError):
        return []
    out = []
    for r in mon.runs:
        before = saved["runs"].get(Monitor.key(r))
        kind = classify(before, r) if before in KEEP else None
        if kind:
            out.append(Event(kind, r, before))
    return out


class Saver:
    """도는 학습이 바뀔 때만(또는 REFRESH마다) 적는다. 감시 루프가 몇 초마다 부른다"""

    def __init__(self):
        self.last: dict | None = None
        self.at = 0.0

    def save(self, mon, now: float | None = None):
        now = time.time() if now is None else now
        live = {Monitor.key(r): r.state for r in mon.runs if r.state in KEEP}
        if live == self.last and (not live or now - self.at < REFRESH):
            return
        try:
            jsonfile.write(file(), {"at": now, "runs": live})
        except OSError:
            return
        self.last, self.at = live, now
