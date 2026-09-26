"""두 목표 스윕: 점수(첫 목표)에 더해 "작은 모델"(best.pt MB) 또는 "빠른 학습"(초)을 함께 본다.
두 번째 값은 낮을수록 좋다. 결과는 파레토 앞줄(어느 쪽으로도 더 나은 시도가 없는 것들)로 보여 준다."""
from __future__ import annotations

from pathlib import Path

from . import adapters


def second_value(t: dict, out: str, which: str | None) -> float | None:
    """두 번째 목표(낮을수록 좋다): size = best.pt MB, time = 학습 시간(초)"""
    if not which or not out:
        return None
    if t.get("machine"):
        from . import sweep_remote
        return sweep_remote.second(t["machine"], out, which)
    d = Path(out)
    if which == "size":
        w = d / "weights" / "best.pt"
        return round(w.stat().st_size / 1e6, 2) if w.exists() else None
    got = adapters.load(d) if d.is_dir() else None
    ts = [r.get("time") for r in (got.rows if got else []) if r.get("time") not in (None, "")]
    try:
        return float(ts[-1]) if ts else None
    except (TypeError, ValueError):
        return None


def pareto(points: list[tuple[str, float, float]], higher: bool = True) -> list[str]:
    """(id, 점수, 두 번째 값) 중 어느 쪽으로도 더 나은 것이 없는 것들(파레토 앞줄). 점수는 higher 방향, 두 번째는 낮을수록 좋다"""
    better = (lambda a, b: a > b) if higher else (lambda a, b: a < b)
    front = []
    for i, s, v in points:
        dominated = any((better(s2, s) or s2 == s) and v2 <= v and (better(s2, s) or v2 < v) for j, s2, v2 in points if j != i)
        if not dominated:
            front.append(i)
    return front


