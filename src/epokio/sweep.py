"""스윕: 여러 설정을 시도하고 결과를 한데 모아 비교한다. 앱·웹·터미널이 같은 API를 쓴다.

* 방식  grid   = 값 목록의 모든 조합 (설정 1~2개)
        random = 범위에서 N개 뽑기 (로그 눈금 가능). 학습률처럼 자릿수가 바뀌는 값은 로그로
        smart  = 처음 몇 개는 무작위, 그다음부터는 끝난 시도 점수를 보고 다음 값을 고른다(tpe.py). 한 번에 하나씩 대기열에
                 넣으므로(advance) 앞 결과가 다음 선택에 쓰인다. 합성 목표(test_smart_sweep.py, 200번)로 16회: 무작위보다 74%, 30회: 80% 경우에 더 좋은 값
* 조기 중단(중앙값 규칙, Optuna MedianPruner와 같은 뜻): 확인 지점은 계획 에폭의 prune_at(= 준비 구간), 50%, 70%.
  도는 시도가 지난 가장 늦은 확인 지점에서, 그 에폭에 값이 있는 다른 모든 시도(★이미 멈춘 시도 포함)의 중앙값보다
  낮으면 멈춘다. 비교할 시도가 2개 미만이면 멈추지 않는다.
  ★예전엔 멈춘 시도를 비교군에서 빼서 중앙값이 점점 올라갔고(살아남은 좋은 시도만 남음), 30% 한 지점만 봤다.
  멈춘 시도의 부분 최고값은 TPE 순위에 넣지 않는다(tpe.py 머리말). 결과 행에는 "pruned": true.
  ★대기열은 한 번에 하나씩 돌므로 먼저 도는 시도는 늘 끝까지 간다(그게 비교 기준이 된다).
* 되풀이(repeats, 기본 1 = 예전 그대로): 같은 설정을 씨앗만 바꿔 N번 돌린다. 학습은 씨앗에 따라 흔들리므로
  한 번만 돌린 점수로 매긴 순위는 잡음일 수 있다. 순위는 그 설정의 **평균**으로 매기고 표준편차·n을 같이 낸다.
  TPE에도 평균 하나를 관측값으로 넣는다(같은 설정을 N개 점으로 넣으면 그 설정에 달라붙는다).
  씨앗은 base의 seed에서 0,1,2…를 더해 쓴다(파라미터 이름 seed = ultralytics·transformers 공통).
* 결과  순위표 · 최고 조합 · 설정값별 평균 점수 · 설정 영향도(값에 따라 점수가 얼마나 달라지나)
  ★영향도·값별 평균에는 n을 같이 낸다. n=2에서도 막대는 그려지지만 그건 순위가 아니라 잡음이다(low_n).

저장: ~/.epokio/sweeps/<id>.json (스윕 정의 + 멈춘 시도 목록). 학습 작업에는 job.sweep = id 가 붙는다.
"""
from __future__ import annotations

import itertools
import json
import math
import random
import re
import statistics
import time
import uuid
from pathlib import Path

from . import adapters, schema

DIR = Path.home() / ".epokio" / "sweeps"
MAX_TRIALS = 64
MIN_N = 3                   # 이보다 적은 표본은 "표본 적음"(low_n)으로 표시한다
PRUNE_RUNGS = (0.5, 0.7)    # prune_at 뒤에 더 보는 확인 지점(계획 에폭 비율)


def _typed(v):
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    for t in (int, float):
        try:
            return t(s)
        except ValueError:
            pass
    return s


def expand(space: list[dict], mode: str, trials: int = 8, seed: int | None = None) -> list[dict]:
    """탐색 공간 → 시도별 설정 목록"""
    if not space:
        raise ValueError("space is empty")
    if mode == "grid":
        lists = []
        for s in space:
            vals = [_typed(v) for v in s.get("values", [])]
            if not s.get("key") or not vals:
                raise ValueError("grid needs a key and values for each setting")
            lists.append([(s["key"], v) for v in vals])
        out = [dict(c) for c in itertools.product(*lists)]
    elif mode == "random":
        rng = random.Random(seed)
        out = []
        for _ in range(max(1, int(trials))):
            t = {}
            for s in space:
                if s.get("values"):
                    t[s["key"]] = _typed(rng.choice(s["values"]))
                    continue
                lo, hi = float(s["low"]), float(s["high"])
                if not lo < hi or (s.get("log") and lo <= 0):
                    raise ValueError(f"bad range for {s.get('key')}")
                x = math.exp(rng.uniform(math.log(lo), math.log(hi))) if s.get("log") else rng.uniform(lo, hi)
                t[s["key"]] = int(round(x)) if s.get("int") else float(f"{x:.4g}")
            out.append(t)
    elif mode == "smart":                              # 처음 몇 개만. 나머지는 advance()가 결과를 보며 하나씩
        from . import tpe
        rng = random.Random(seed)
        tpe.validate_space(space)
        out = [tpe.suggest(space, [], seed=rng.randrange(1 << 30)) for _ in range(min(tpe.startup(space), max(1, int(trials))))]
    else:
        raise ValueError("mode must be grid, random or smart")
    if len(out) > MAX_TRIALS:
        raise ValueError(f"too many runs ({len(out)}); keep it under {MAX_TRIALS}")
    return out


def _key(t: dict) -> str:
    """같은 설정인지 보는 열쇠(되풀이 묶기용)"""
    return json.dumps(t, sort_keys=True, ensure_ascii=False, default=str)


def _agg(vals: list[float]) -> dict:
    """되풀이 묶음 요약. n=1이면 표준편차는 0이 아니라 None(0으로 내면 "흔들림 없음"으로 읽힌다)"""
    return {"mean": statistics.fmean(vals), "std": statistics.stdev(vals) if len(vals) > 1 else None,
            "n": len(vals), "low_n": len(vals) < MIN_N}


def _label(t: dict) -> str:
    return "_".join(f"{k}={v}" for k, v in t.items())


def create(queue, name: str, python: str, base: dict, space: list[dict], mode: str = "grid",
           trials: int = 8, prune: bool = False, prune_at: float = 0.3, seed: int | None = None,
           machines: list[dict] | None = None, second: str | None = None, repeats: int = 1) -> dict:
    """machines(선택): [{"url": "local" 또는 원격 주소, "python", "data"}]. 주면 여러 기계에 나눠 돈다(dispatch).
    ★토큰은 받지 않는다: sweep_remote.TOKENS(메모리)에서 쓴다"""
    tri = expand(space, mode, trials, seed)
    reps = max(1, int(repeats))
    if len(tri) * reps > MAX_TRIALS:
        raise ValueError(f"too many runs ({len(tri)} x {reps}); keep it under {MAX_TRIALS}")
    sid = uuid.uuid4().hex[:6]
    spec = {"id": sid, "name": name, "mode": mode, "space": space, "base": base, "created": time.time(),
            "prune": bool(prune), "prune_at": float(prune_at), "trials": [], "pruned": [], "python": python,
            "repeats": reps,
            "budget": min(int(trials) * reps, MAX_TRIALS) if mode == "smart" else len(tri) * reps, "seed": seed,
            "second": second if second in ("size", "time") else None}
    ms = [{"url": str(m.get("url") or "local").rstrip("/"), "python": str(m.get("python") or python),
           "data": str(m.get("data") or base.get("data", ""))} for m in (machines or []) if isinstance(m, dict)]
    if ms and not (len(ms) == 1 and ms[0]["url"] == "local"):
        spec["machines"] = ms                         # 나눠 돌기: 처음엔 비어 있고 dispatch()가 기계마다 하나씩 넣는다
        spec["pending"] = [] if mode == "smart" else [t for t in tri for _ in range(reps)]
        DIR.mkdir(parents=True, exist_ok=True)
        _save(spec)
        dispatch(queue, only=sid)
        return load(sid) or spec
    for t in tri:
        for _ in range(reps):
            _queue_trial(queue, spec, t)
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / f"{sid}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    return spec


def _rep_of(spec: dict, t: dict) -> int:
    """이 설정이 지금까지 몇 번 돌았나(= 이번이 몇 번째 되풀이인가)"""
    k = _key(t)
    return sum(_key(x.get("trial", {})) == k for x in spec["trials"])


def _params(spec: dict, t: dict, rep: int | None = None) -> tuple[str, dict]:
    base, i = spec["base"], len(spec["trials"]) + 1
    rep = _rep_of(spec, t) if rep is None else rep
    p = {**base, **t}
    if str(t.get("model", "")) in ("n", "s", "m", "l", "x"):            # 크기 글자만 주면 기본 모델 이름에서 바꾼다
        p["model"] = re.sub(r"^(yolo\w*?\d+)[nslmx]", rf"\g<1>{t['model']}", str(base.get("model", "")))
    name = f"{spec['name']}_{i:02d}_{_label(t)}"
    if spec.get("repeats", 1) > 1:
        p["seed"] = _typed(base.get("seed", 0)) + rep if isinstance(_typed(base.get("seed", 0)), int) else rep
        name += f"_r{rep + 1}"
    return name[:120], p


def _queue_trial(queue, spec: dict, t: dict, machine: dict | None = None):
    rep = _rep_of(spec, t)
    name, p = _params(spec, t, rep)
    if machine:
        p["data"] = machine.get("data") or p.get("data")
    j = queue.add("train", name, (machine or {}).get("python") or spec.get("python", ""), p, sweep=spec["id"])
    spec["trials"].append({"job": j.id, "trial": t, "rep": rep})


def dispatch(queue, only: str | None = None) -> list[str]:
    """여러 기계 스윕: 빈 기계마다 다음 시도(sweep_dispatch.py)"""
    from .sweep_dispatch import dispatch as run
    return run(queue, only)


def _status(queue, t: dict) -> tuple[str, str]:
    """시도의 (상태, 결과 폴더). 원격 시도는 그 기계의 /jobs에서(5초 기억)"""
    if t.get("machine"):
        from . import sweep_remote
        j = sweep_remote.job(t["machine"], t["job"])
        return (j.get("state", "missing"), j.get("output", "")) if j else ("unreachable", "")
    j = queue.get(t["job"])
    return (j.state, j.output) if j else ("missing", "")


def _trial_curve(t: dict, output: str):
    if not output:
        return None, []
    if t.get("machine"):
        from . import sweep_remote
        return sweep_remote.curve(t["machine"], output)
    return _curve(Path(output))


from .sweep_goals import pareto, second_value as _second  # noqa: E402  (두 목표: 두 번째 값·파레토)


def _mean_by_config(pairs: list[tuple[dict, float]]) -> list[tuple[dict, float]]:
    """되풀이(같은 설정 여러 번)를 평균 하나로 접는다. ★N개 점을 그대로 넣으면 TPE 좋음/나쁨 그룹이 한 설정으로 채워진다"""
    order, by = [], {}
    for t, v in pairs:
        k = _key(t)
        if k not in by:
            by[k], _ = [], order.append((k, t))
        by[k].append(v)
    return [(t, statistics.fmean(by[k])) for k, t in order]


def _history(queue, spec: dict) -> tuple[list, bool, list]:
    """끝난 시도의 (설정, 점수), 높을수록 좋음, 조기 중단된 시도 설정 목록(TPE 나쁨 그룹에만). 두 목표면 점수와 두 번째 값을 섞은 하나로(가중치는 고를 때마다 달리: 앞줄 여러 곳을 훑는다)
    되풀이가 있으면 설정마다 평균 하나만 낸다(sweep.py 머리말)."""
    raw, higher, pruned = [], True, []
    cut = set(spec.get("pruned", []))
    for t in spec["trials"]:
        if t["job"] in cut:                           # ★부분 곡선 최고값을 끝난 점수처럼 넣으면 TPE가 속는다
            pruned.append(t["trial"])
            continue
        _, out = _status(queue, t)
        m, pts = _trial_curve(t, out)
        if not pts:
            continue
        higher = schema.higher_is_better(m) if m else True
        raw.append((t["trial"], (max if higher else min)(v for _, v in pts), _second(t, out, spec.get("second"))))
    if not spec.get("second"):
        return _mean_by_config([(t, s) for t, s, _ in raw]), higher, pruned
    both = [(t, s, v) for t, s, v in raw if v is not None]
    if len(both) < 2:
        return _mean_by_config([(t, s) for t, s, _ in raw]), higher, pruned
    w = random.Random((spec.get("seed") or 0) + len(spec["trials"])).uniform(0.2, 0.8)
    s_lo, s_hi = min(x[1] for x in both), max(x[1] for x in both)
    v_lo, v_hi = min(x[2] for x in both), max(x[2] for x in both)
    ns = lambda s: ((s - s_lo) / (s_hi - s_lo) if s_hi > s_lo else 0.5) * (1 if higher else -1)
    nv = lambda v: (v - v_lo) / (v_hi - v_lo) if v_hi > v_lo else 0.5
    return _mean_by_config([(t, w * ns(s) - (1 - w) * nv(v)) for t, s, v in both]), True, pruned


def advance(queue) -> list[str]:
    """똑똑한 스윕: 기다리는 시도가 없고 예산이 남았으면, 끝난 시도 점수로 다음 값을 골라 대기열에 넣는다. 넣은 스윕 id 목록"""
    from . import tpe
    added = []
    for spec in all_specs():
        if spec.get("mode") != "smart" or spec.get("machines") or spec.get("stopped") \
                or len(spec.get("trials", [])) >= spec.get("budget", 0):
            continue                                      # 여러 기계 스윕은 dispatch()가 맡는다
        if any(_status(queue, t)[0] in ("queued", "running") for t in spec["trials"]):
            continue                                  # 한 번에 하나씩: 앞 결과가 나와야 다음 선택이 똑똑해진다
        nxt = _next_trial(queue, spec, tpe)
        _queue_trial(queue, spec, nxt)
        _save(spec)
        added.append(spec["id"])
    return added


def _next_trial(queue, spec: dict, tpe) -> dict:
    """똑똑한 스윕의 다음 설정. 되풀이가 덜 찬 설정이 있으면 새 값을 고르기 전에 그것을 먼저 채운다
    (★평균이 나오기 전에 다음 값을 고르면 TPE가 한 번 뽑은 잡음으로 판단한다)"""
    reps = spec.get("repeats", 1)
    if reps > 1 and spec["trials"]:
        last = spec["trials"][-1]["trial"]
        if _rep_of(spec, last) < reps:
            return last
    history, higher, pruned = _history(queue, spec)
    return tpe.suggest(spec["space"], history, higher, pruned=pruned,
                       seed=(spec.get("seed") or 0) * 1000 + len(spec["trials"]))


def load(sid: str) -> dict | None:
    f = DIR / f"{sid}.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(spec: dict):
    (DIR / f"{spec['id']}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")


def all_specs() -> list[dict]:
    if not DIR.is_dir():
        return []
    out = []
    for f in sorted(DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def _curve(run_dir: Path) -> tuple[str | None, list[tuple[int, float]]]:
    """(점수 열, [(에폭, 점수)])"""
    got = adapters.load(run_dir) if run_dir.is_dir() else None
    if not got or not got.rows:
        return None, []
    m = schema.pick_metric(got.rows[-1].keys())
    pts = []
    for r in got.rows:
        try:
            v = float(r.get(m, ""))
            e = int(float(r["epoch"]))
        except (TypeError, ValueError, KeyError):
            continue
        if not math.isnan(v):
            pts.append((e, v))
    return m, pts


def summary(spec: dict, queue) -> dict:
    """순위표 · 최고 · 설정값별 평균 · 영향도 (sweep_summary.py)"""
    from .sweep_summary import summary as f
    return f(spec, queue)


def check_prune(queue) -> list[str]:
    """도는 시도 중 가망 없는 것을 멈춘다(이 맥·원격 모두). 멈춘 작업 id 목록.
    ★예전엔 이 맥 대기열의 도는 작업만 봐서, 원격에서 도는 시도는 뒤처져도 끝까지 갔다"""
    from . import sweep_remote
    stopped = []
    for spec in all_specs():
        if not spec.get("prune") or spec.get("stopped"):
            continue
        pruned = set(spec.get("pruned", []))
        curves: dict[str, dict] = {}

        def at(t, rung):
            if t["job"] not in curves:
                _, out = _status(queue, t)
                curves[t["job"]] = dict(_trial_curve(t, out)[1])
            return curves[t["job"]].get(rung)
        for t in spec["trials"]:
            if t["job"] in pruned or _status(queue, t)[0] != "running":
                continue
            total = int(t["trial"].get("epochs") or spec.get("base", {}).get("epochs") or 0)
            if not total:
                continue
            first = float(spec.get("prune_at", 0.3))
            rungs = sorted({max(1, int(round(total * f))) for f in (first, *PRUNE_RUNGS) if f >= first})
            rung = mine = others = None
            for r in reversed(rungs):                     # 지난 가장 늦은 확인 지점, 비교할 시도가 2개 이상인 곳
                v = at(t, r)
                if v is None:
                    continue
                # ★멈춘 시도도 그 에폭 값이 있으면 넣는다(빼면 살아남은 좋은 시도만 남아 중앙값이 올라간다)
                o = [x for ot in spec["trials"] if ot["job"] != t["job"] for x in [at(ot, r)] if x is not None]
                if len(o) >= 2:
                    rung, mine, others = r, v, o
                    break
            if rung is None:
                continue
            _, out = _status(queue, t)
            m, _ = _trial_curve(t, out)
            med = statistics.median(others)
            worse = mine < med if schema.higher_is_better(m or "") else mine > med
            if not worse:                                 # ★앞서면 건드리지 않는다(멈추기를 비교보다 먼저 부르면 다 멈췄다)
                continue
            ok = sweep_remote.cancel(t["machine"], t["job"]) if t.get("machine") else queue.cancel(t["job"])
            if ok:
                spec.setdefault("pruned", []).append(t["job"])
                spec.setdefault("prune_log", []).append({"job": t["job"], "epoch": rung, "score": mine, "median": med,
                                                         "machine": t.get("machine", ""), "at": time.time()})
                _save(spec)
                stopped.append(t["job"])
    return stopped
