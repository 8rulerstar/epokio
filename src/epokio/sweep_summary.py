"""스윕 결과 요약: 순위표·최고·설정값별 평균·영향도·되풀이 묶음. sweep.py가 400줄을 넘어 나눴다(규칙은 sweep.py 머리말)."""
from __future__ import annotations

import statistics

from . import schema
from .sweep import MIN_N, _agg, _key, _second, _status, _trial_curve
from .sweep_goals import pareto


def summary(spec: dict, queue) -> dict:
    """순위표 · 최고 · 설정값별 평균 · 영향도"""
    rows = []
    metric = None
    # ★옛 판·손으로 고친 스윕 파일에 열쇠 하나가 없으면 KeyError로 스윕 목록 전체가 죽었다: 빠진 것은 기본값으로
    spec = {"name": spec.get("id", "sweep"), "mode": "grid", "space": [], "prune": False, "prune_at": 0.3, "created": 0,
            "trials": [], **spec}
    for t in spec["trials"]:
        state, out = _status(queue, t)
        m, pts = _trial_curve(t, out)
        sec = _second(t, out, spec.get("second")) if spec.get("second") and state in ("done", "running") else None
        metric = metric or m
        hib = schema.higher_is_better(m) if m else True
        best = (max if hib else min)(pts, key=lambda x: x[1]) if pts else None
        rows.append({"job": t["job"], "trial": t.get("trial", {}), "rep": t.get("rep", 0), "state": ("pruned" if t["job"] in spec.get("pruned", []) else state),
                     "pruned": t["job"] in spec.get("pruned", []),
                     "machine": t.get("machine") or "", "run": (out or None) if not t.get("machine") else None, "second": sec,
                     "epochs": pts[-1][0] if pts else 0,
                     "best": best[1] if best else None, "best_epoch": best[0] if best else None,
                     "curve": [v for _, v in pts][-60:]})
    hib = schema.higher_is_better(metric) if metric else True
    scored = [r for r in rows if r["best"] is not None]
    groups = _groups(scored, hib)
    reps = spec.get("repeats", 1)
    if reps > 1:                              # ★되풀이가 있으면 순위는 한 번 돌린 점수가 아니라 설정의 평균으로
        gr = {g["key"]: g["rank"] for g in groups}
        scored.sort(key=lambda r: (gr[_key(r["trial"])], -r["best"] if hib else r["best"]))
    else:
        scored.sort(key=lambda r: r["best"], reverse=hib)
    for i, r in enumerate(scored, 1):
        r["rank"] = i
    by_key = {}
    # 값별 평균·영향도는 "시도"가 아니라 "설정"이 표본이다: 되풀이 N번을 N개 표본으로 세면 n이 부풀고 잡음이 줄어 보인다
    sample = [{"trial": g["trial"], "best": g["mean"]} for g in groups] if reps > 1 else scored
    for sp in spec["space"]:
        k = sp.get("key") if isinstance(sp, dict) else None
        if not k:
            continue
        buckets: dict = {}
        label = _binner(k, sample)                       # 연속 값(무작위·똑똑하게)은 구간으로 묶는다
        for r in sample:
            buckets.setdefault(label(r["trial"].get(k)), []).append(r["best"])
        vals = [{"value": v, **_agg(b)} for v, b in buckets.items()]
        try:
            vals.sort(key=lambda x: float(x["value"]))
        except (TypeError, ValueError):
            vals.sort(key=lambda x: str(x["value"]))
        spread = (max(x["mean"] for x in vals) - min(x["mean"] for x in vals)) if len(vals) > 1 else 0.0
        by_key[k] = {"values": vals, "spread": spread, "n": sum(x["n"] for x in vals),
                     "min_n": min((x["n"] for x in vals), default=0), "groups": len(vals),
                     "low_n": len(vals) < 2 or min((x["n"] for x in vals), default=0) < MIN_N}
    total = sum(v["spread"] for v in by_key.values()) or 1
    # ★영향도에 n·low_n을 같이 낸다: n=2에서도 share는 100%까지 나오지만 그건 순위가 아니라 잡음이다
    importance = sorted(({"key": k, "share": v["spread"] / total, "n": v["n"], "min_n": v["min_n"],
                          "groups": v["groups"], "low_n": v["low_n"]} for k, v in by_key.items()),
                        key=lambda x: -x["share"])
    return {**{k: spec[k] for k in ("id", "name", "mode", "space", "prune", "prune_at", "created")},
            "metric": metric, "higher": hib, "rows": rows, "best": scored[0] if scored else None,
            "by_key": by_key, "importance": importance, "repeats": reps, "groups": groups,
            "low_n": any(i["low_n"] for i in importance), "min_n": MIN_N,
            "done": sum(r["state"] in ("done", "failed", "cancelled", "pruned") for r in rows),
            "total": max(len(rows), 0 if spec.get("stopped") else spec.get("budget", 0)),
            "best_so_far": _best_so_far(rows, hib), "stopped": bool(spec.get("stopped")),
            "machines": [m["url"] for m in spec.get("machines", [])], "needs_tokens": spec.get("needs_tokens", []),
            "dispatch_errors": spec.get("dispatch_errors", {}), "second": spec.get("second"),
            "pareto": pareto([(r["job"], r["best"], r["second"]) for r in rows if r["best"] is not None and r["second"] is not None], hib)
                      if spec.get("second") else []}


def _groups(scored: list[dict], higher: bool) -> list[dict]:
    """같은 설정(되풀이)끼리 묶어 평균·표준편차·n. 순위는 평균으로. 되풀이가 1이면 n=1 묶음이 시도 수만큼 나온다"""
    by: dict[str, dict] = {}
    for r in scored:
        k = _key(r["trial"])
        g = by.setdefault(k, {"key": k, "trial": r["trial"], "jobs": [], "scores": []})
        g["jobs"].append(r["job"])
        g["scores"].append(r["best"])
    out = [{**{a: b for a, b in g.items() if a != "scores"}, **_agg(g["scores"]),
            "best": (max if higher else min)(g["scores"])} for g in by.values()]
    out.sort(key=lambda g: g["mean"], reverse=higher)
    for i, g in enumerate(out, 1):
        g["rank"] = i
    return out


def _binner(k: str, scored: list[dict]):
    """값 → 묶을 이름. 숫자 값이 7개 이상 제각각이면(연속 탐색) 4구간(사분위)으로 묶는다.
    ★시도마다 값이 달라 "값별 평균"이 한 개짜리 막대 12개가 되고, 영향도도 시도 하나끼리 비교했다"""
    vals = [r["trial"].get(k) for r in scored]
    nums = sorted(v for v in vals if isinstance(v, (int, float)))
    if len(nums) != len(vals) or len(set(nums)) <= 6:
        return lambda v: v
    cuts = [nums[int(len(nums) * q)] for q in (0.25, 0.5, 0.75)]
    edges = [nums[0], *cuts, nums[-1]]
    fmt = lambda x: f"{x:.3g}"
    def label(v):
        i = sum(v > c for c in cuts)
        return f"{fmt(edges[i])}–{fmt(edges[i + 1])}"
    return label


def _best_so_far(rows: list[dict], higher: bool) -> list[float | None]:
    """시도 순서대로 "지금까지 최고" (똑똑한 스윕이 무작위보다 빨리 좋은 값을 찾는지 보는 선)"""
    out, cur = [], None
    for r in rows:
        b = r.get("best")
        if b is not None and (cur is None or (b > cur if higher else b < cur)):
            cur = b
        out.append(cur)
    return out
