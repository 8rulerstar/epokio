"""여러 기계 스윕 나눠 주기. sweep.py가 400줄을 넘어 나눴다(규칙은 sweep.py 머리말, 토큰은 sweep_remote.py)."""
from __future__ import annotations

from .sweep import _next_trial, _params, _queue_trial, _rep_of, _save, _status, all_specs


def dispatch(queue, only: str | None = None) -> list[str]:
    """여러 기계 스윕: 비어 있는 기계(이 스윕 작업이 대기·도는 중이 아님)마다 다음 시도를 하나 넣는다.
    격자·무작위는 pending에서 차례로, 똑똑하게는 그때까지 끝난 점수로 고른다(기계마다 다른 씨앗이라 같은 값을 겹쳐 고르지 않는다).
    원격 토큰이 메모리에 없으면 그 기계는 건너뛰고 needs_tokens로 알린다. 넣은 (스윕, 기계) 목록"""
    from . import sweep_remote, tpe
    added = []
    for spec in all_specs():
        if not spec.get("machines") or spec.get("stopped") or (only and spec["id"] != only):
            continue
        busy = {t.get("machine") or "local" for t in spec["trials"] if _status(queue, t)[0] in ("queued", "running")}
        needs, changed = [], False
        for m in spec["machines"]:
            if m["url"] in busy or len(spec["trials"]) >= spec.get("budget", 0):
                continue
            if m["url"] != "local" and m["url"] not in sweep_remote.TOKENS:
                needs.append(m["url"])
                continue
            if spec["mode"] == "smart":
                t = _next_trial(queue, spec, tpe)   # 되풀이가 덜 찬 설정이 있으면 그것부터(sweep.py)
            elif spec.get("pending"):
                t = spec["pending"].pop(0)
            else:
                break
            try:
                if m["url"] == "local":
                    _queue_trial(queue, spec, t, m)
                else:
                    r = _rep_of(spec, t)
                    name, p = _params(spec, t, r)
                    spec["trials"].append({"job": sweep_remote.submit(m, name, p), "trial": t,
                                           "rep": r, "machine": m["url"]})
                added.append((spec["id"], m["url"]))
                changed = True
            except Exception as e:                    # 원격이 안 받으면(연결·토큰·검증) 시도는 되돌리고 다음에 다시
                if spec["mode"] != "smart":
                    spec["pending"].insert(0, t)
                spec.setdefault("dispatch_errors", {})[m["url"]] = str(e)[:200]
                changed = True
        if needs != spec.get("needs_tokens", []):
            spec["needs_tokens"], changed = needs, True
        if changed:
            _save(spec)
    return added