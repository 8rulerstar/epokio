"""똑똑한 스윕의 다음 값 고르기: TPE(Tree-structured Parzen Estimator, Optuna 기본 방식)를 단순하게, 표준 라이브러리만으로.

1. 끝난 시도를 점수로 줄 세워 위 25%(최소 1개)를 "좋음", 나머지를 "나쁨"으로 나눈다
2. 설정마다 따로(독립 TPE) 좋음·나쁨 분포를 만든다
   * 숫자: 관측값마다 가우스 봉우리(폭 = 범위의 1/6에서 관측이 늘면 좁아짐). 로그 설정은 로그 눈금에서
   * 고른 값(목록): 나온 횟수 + 1(한 번도 안 나온 값도 기회가 있게)
3. 좋음 분포에서 후보 24개를 뽑아 l(x)/g(x)(좋음 밀도 ÷ 나쁨 밀도)가 가장 큰 것을 고른다
   (24 = Optuna n_ei_candidates 기본값. 합성 목표에서 48로 늘려도 이득이 잡음 수준이라 그대로 둔다)
시도가 startup(space)개(= max(5, 2 x 설정 수)) 모이기 전에는 무작위(탐색 공간 전체를 한 번 훑는다).
★예전엔 설정 수와 상관없이 4개 뒤 바로 TPE였다: 설정이 많으면 좋음 그룹이 1개짜리라 한 점에 달라붙었다.
조기 중단된 시도(pruned): 부분 곡선의 최고값은 끝까지 간 시도의 점수와 비교할 수 없다. Optuna처럼
순위에는 넣지 않고 "나쁨" 그룹에만 넣는다(그 근처는 덜 고르게), 무작위 단계 개수에는 센다.
"""
from __future__ import annotations

import math
import random

GAMMA = 0.25
CANDIDATES = 24


def startup(space: list[dict]) -> int:
    """무작위로 훑을 시도 수. 설정이 많을수록 늘린다"""
    return max(5, 2 * len(space))


def validate_space(space: list[dict]) -> None:
    """범위 설정이 쓸 수 있는지. 안 되면 무엇이 틀렸는지 담은 ValueError(로그 눈금 low<=0이면 math 오류로 죽었다)"""
    for s in space:
        k = s.get("key", "?")
        if s.get("values"):
            continue
        if "low" not in s or "high" not in s:
            raise ValueError(f"{k}: give either values or low and high")
        lo, hi = float(s["low"]), float(s["high"])
        if not lo < hi:
            raise ValueError(f"{k}: low ({lo:g}) must be below high ({hi:g})")
        if s.get("log") and lo <= 0:
            raise ValueError(f"{k}: a log range needs low > 0 (got {lo:g})")


def _is_num(s: dict) -> bool:
    return not s.get("values") and "low" in s and "high" in s


def _to_unit(s: dict, x: float) -> float:
    lo, hi = float(s["low"]), float(s["high"])
    if s.get("log"):
        return (math.log(x) - math.log(lo)) / (math.log(hi) - math.log(lo))
    return (x - lo) / (hi - lo)


def _from_unit(s: dict, u: float):
    lo, hi = float(s["low"]), float(s["high"])
    u = min(max(u, 0.0), 1.0)
    x = math.exp(math.log(lo) + u * (math.log(hi) - math.log(lo))) if s.get("log") else lo + u * (hi - lo)
    return int(round(x)) if s.get("int") else float(f"{x:.4g}")


def _random(space: list[dict], rng: random.Random) -> dict:
    return {s["key"]: (rng.choice(s["values"]) if s.get("values") else _from_unit(s, rng.random())) for s in space}


def _kde(points: list[float], u: float, bw: float) -> float:
    """[0,1] 위 가우스 봉우리들의 밀도(끝에서 새는 건 무시해도 비교엔 충분). 관측이 없으면 균등"""
    if not points:
        return 1.0
    return sum(math.exp(-0.5 * ((u - p) / bw) ** 2) for p in points) / (len(points) * bw * math.sqrt(2 * math.pi)) + 1e-12


def suggest(space: list[dict], history: list[tuple[dict, float]], higher: bool = True,
            seed: int | None = None, n_startup: int | None = None, pruned: list[dict] | None = None) -> dict:
    """다음 시도 설정. history = [(끝까지 간 시도 설정, 점수)], pruned = [조기 중단된 시도 설정] (나쁨 그룹에만)"""
    validate_space(space)
    rng = random.Random(seed)
    pruned = list(pruned or [])
    if len(history) + len(pruned) < (startup(space) if n_startup is None else n_startup) or not history:
        return _random(space, rng)
    ranked = sorted(history, key=lambda h: h[1], reverse=higher)
    n_good = max(1, int(math.ceil(GAMMA * len(ranked))))
    good, bad = [t for t, _ in ranked[:n_good]], [t for t, _ in ranked[n_good:]] + pruned
    out = {}
    for s in space:
        k = s["key"]
        if _is_num(s):
            gp = [_to_unit(s, float(t[k])) for t in good if k in t]
            bp = [_to_unit(s, float(t[k])) for t in bad if k in t]
            bw = max(0.03, (1 / 6) / max(1, len(gp) + len(bp)) ** 0.2)          # 관측이 늘수록 조금씩 좁게
            cands = [min(max(rng.choice(gp) + rng.gauss(0, bw), 0.0), 1.0) if gp else rng.random()
                     for _ in range(CANDIDATES)]
            best = max(cands, key=lambda u: _kde(gp, u, bw) / _kde(bp, u, bw))
            out[k] = _from_unit(s, best)
        else:
            vals = list(s.get("values") or [])
            gc = {v: 1 + sum(str(t.get(k)) == str(v) for t in good) for v in vals}
            bc = {v: 1 + sum(str(t.get(k)) == str(v) for t in bad) for v in vals}
            gsum, bsum = sum(gc.values()), sum(bc.values())
            weights = [gc[v] / gsum for v in vals]
            cands = [rng.choices(vals, weights)[0] for _ in range(CANDIDATES)]
            out[k] = max(cands, key=lambda v: (gc[v] / gsum) / (bc[v] / bsum))
    return out
