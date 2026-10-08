"""기록 줄의 시간으로 한 칸(에폭, step 축이면 step)에 걸린 시간을 잰다. scan에서 재수출한다(400줄 규칙으로 나눔)."""
from __future__ import annotations

import math


def _to_float(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def recent_epoch_sec(rows: list[dict], n: int = 10) -> float | None:
    """최근 n에폭의 에폭당 시간 중앙값(누적 time 열의 차이). 시간 열이 없거나 2행 미만이면 None"""
    ts = [t for t in (_to_float(r.get("time")) for r in rows[-(n + 1):]) if t is not None]
    d = sorted(b - a for a, b in zip(ts, ts[1:]) if b > a)
    return d[len(d) // 2] if d else None


def recent_unit_sec(rows: list[dict], n: int = 10) -> float | None:
    """최근 n줄에서 진행 한 칸(에폭, step 축이면 step)에 걸린 시간의 중앙값: 시간 차이 / epoch 열 차이.
    ★ETA가 줄 사이 시간에 남은 칸 수를 곱해서, 100 step마다 기록하는 step 학습은 남은 시간이 100배로 나왔다
      (15분이 "1d 1h")."""
    pts = [(_to_float(r.get("time")), _to_float(r.get("epoch"))) for r in rows[-(n + 1):]]
    pts = [(t, x) for t, x in pts if t is not None and x is not None]
    d = sorted((t2 - t1) / (x2 - x1) for (t1, x1), (t2, x2) in zip(pts, pts[1:]) if t2 > t1 and x2 > x1)
    return d[len(d) // 2] if d else None
