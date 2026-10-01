"""학습 손실만 보는 신호(analysis._notes가 쓴다). analysis.py가 400줄을 넘어 나눴다"""
from __future__ import annotations

import math


def _f(v):
    try:
        x = float(v)
        return None if math.isnan(x) or math.isinf(x) else x
    except (TypeError, ValueError):
        return None


def _train_loss_blowup(rows) -> tuple[float, int, float] | None:
    """학습 손실이 바닥을 찍은 뒤 두 배 넘게 불어났다(NaN이 아니어도 학습이 무너진 것). (바닥 값, 바닥 에폭 자리, 끝 값)"""
    tl = [c for c in rows[0].keys() if c.startswith("train/") and c.endswith("loss")]
    n = len(rows)
    if not tl or n < 6:
        return None
    s = [sum(v) if all(x is not None for x in v) else None for v in ([_f(r.get(c)) for c in tl] for r in rows)]
    ok = [k for k in range(n) if s[k] is not None]
    if len(ok) < 6:
        return None
    lo = min(ok, key=lambda k: s[k])
    tail = [s[k] for k in ok[-3:]]
    end = sum(tail) / len(tail)
    return (s[lo], lo, end) if lo < n - 3 and s[lo] > 0 and end > s[lo] * 2 else None


def _train_loss_rising(rows) -> tuple[int, float, float] | None:
    """점수가 없는 학습(MAE 사전학습 등)의 신호: 학습 손실이 바닥 뒤로 꾸준히(15% 넘게) 오른다. 두 배(폭주)보다 약한 것"""
    tl = [c for c in rows[0].keys() if c.startswith("train/") and c.endswith("loss")]
    n = len(rows)
    if not tl or n < 10:
        return None
    s = [sum(v) if all(x is not None for x in v) else None for v in ([_f(r.get(c)) for c in tl] for r in rows)]
    ok = [k for k in range(n) if s[k] is not None]
    if len(ok) < 10:
        return None
    lo = min(ok, key=lambda k: s[k])
    tail = [s[k] for k in ok[-max(3, n // 5):]]
    end = sum(tail) / len(tail)
    return (lo, s[lo], end) if lo < n - len(tail) and s[lo] > 0 and end > s[lo] * 1.15 else None
