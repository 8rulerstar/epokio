"""스윕 요청: 목록·요약(GET /sweeps, /sweeps/<id>), 만들기(POST /sweeps), 멈추기(POST /sweeps/<id>/cancel). 계산은 sweep.py"""
from __future__ import annotations

from .. import sweep
from . import NOT_MINE


def get(agent, route: str, q: dict):
    if route == "/sweeps":                                # 스윕 목록 (요약)
        out = []
        for x in sweep.all_specs()[:12]:                  # 깨진 파일 하나 때문에 목록 전체가 죽지 않게
            try:
                out.append(sweep.summary(x, agent.queue))
            except (KeyError, TypeError, ValueError):
                continue
        return {"sweeps": out}
    if route.startswith("/sweeps/"):
        spec = sweep.load(route.split("/")[2])
        return sweep.summary(spec, agent.queue) if spec else (404, {"error": "no such sweep"})
    return NOT_MINE


def post(agent, route: str, body: dict):
    if route == "/sweeps":                                # 스윕 만들기: 시도마다 학습 작업을 대기열에
        b = body
        if not isinstance(b.get("base"), dict) or not b["base"].get("data") or not b.get("python"):
            return 400, {"error": "base (with data) and python are needed"}
        if not isinstance(b.get("space"), list):
            return 400, {"error": "space must be a list"}
        try:
            prune_at = float(b.get("prune_at", 0.3))
            if not 0.05 <= prune_at <= 0.9:
                raise ValueError("prune_at must be between 0.05 and 0.9")
            spec = sweep.create(agent.queue, str(b.get("name") or "sweep"), b["python"], b["base"], b["space"],
                                b.get("mode", "grid"), int(b.get("trials", 8)), bool(b.get("prune")), prune_at, b.get("seed"),
                                b.get("machines") if isinstance(b.get("machines"), list) else None, b.get("second"))
        except (KeyError, TypeError, ValueError) as e:
            return 400, {"error": str(e)}
        return 200, {"id": spec["id"], "runs": spec.get("budget", len(spec["trials"]))}
    if route == "/remotes/tokens":                        # 앱이 키체인의 원격 토큰을 넘겨 준다. ★메모리에만(디스크에 안 씀)
        from .. import sweep_remote
        return 200, {"accepted": sweep_remote.set_tokens(body.get("tokens") if isinstance(body.get("tokens"), dict) else {})}
    if route.startswith("/sweeps/") and route.endswith("/cancel"):
        spec = sweep.load(route.split("/")[2])
        if not spec:
            return 404, {"error": "no such sweep"}
        from .. import sweep_remote
        n = sum(sweep_remote.cancel(t["machine"], t["job"]) if t.get("machine") else agent.queue.cancel(t["job"])
                for t in spec["trials"])
        spec["stopped"] = True                            # 똑똑한 스윕이 다음 값을 더 넣지 않게
        sweep._save(spec)
        return 200, {"cancelled": n}
    return NOT_MINE
