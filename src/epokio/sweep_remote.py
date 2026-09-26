"""여러 기계에 나눠 도는 스윕: 원격 agent에 학습을 넣고, 상태·점수를 읽어 온다.

* 토큰은 **메모리에만**(`TOKENS`). 앱이 키체인에서 꺼내 POST /remotes/tokens 로 넘겨 준다. 디스크에 쓰지 않는다(사용자 결정 2026-09-22).
  agent가 다시 켜지면 비어 있어, 앱이 다시 넘겨 줄 때까지 그 기계로는 새 시도를 넣지 않는다(needs_tokens로 알림)
* 읽기(GET /jobs, /run)는 토큰이 필요 없다. 넣기·멈추기(POST)만 토큰
* 원격 상태는 5초 동안 기억한다(감시 루프가 2초마다 돌아도 원격에는 5초에 한 번)
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import schema

TOKENS: dict[str, str] = {}              # 기계 주소 → 토큰 (메모리에만)
_jobs_cache: dict[str, tuple[float, dict]] = {}
TIMEOUT = 5


def set_tokens(tokens: dict) -> int:
    n = 0
    for url, tok in (tokens or {}).items():
        if isinstance(url, str) and isinstance(tok, str) and url.startswith(("http://", "https://")) and tok:
            TOKENS[url.rstrip("/")] = tok
            n += 1
    return n


def _req(url: str, route: str, body: dict | None = None, q: dict | None = None):
    base = url.rstrip("/")
    full = f"{base}/{route.lstrip('/')}" + (("?" + urllib.parse.urlencode(q)) if q else "")
    headers = {"Content-Type": "application/json"}
    tok = TOKENS.get(base)
    if body is not None and not tok:
        raise PermissionError(f"no token for {base}")
    if tok:     # 보기(GET /jobs 등)도 토큰 뒤라(dev 보안) 있으면 늘 싣는다
        headers["Authorization"] = f"Bearer {tok}"
    r = urllib.request.Request(full, data=json.dumps(body).encode() if body is not None else None, headers=headers,
                               method="POST" if body is not None else "GET")
    with urllib.request.urlopen(r, timeout=TIMEOUT) as resp:
        return json.loads(resp.read() or b"{}")


def submit(machine: dict, name: str, params: dict) -> str:
    """원격 기계에 학습 하나를 넣는다. 원격 작업 id"""
    p = {**params, "data": machine.get("data") or params.get("data")}
    got = _req(machine["url"], "jobs", {"kind": "train", "name": name, "python": machine["python"], "params": p})
    return got["id"]


def cancel(url: str, job_id: str) -> bool:
    try:
        return bool(_req(url, f"jobs/{job_id}/cancel", {}).get("ok"))
    except (OSError, ValueError, PermissionError, urllib.error.URLError):
        return False


def job(url: str, job_id: str) -> dict | None:
    """원격 작업 상태(5초 기억). 연결이 안 되면 None"""
    base = url.rstrip("/")
    hit = _jobs_cache.get(base)
    if not hit or time.time() - hit[0] > 5:
        try:
            jobs = {j["id"]: j for j in _req(base, "jobs").get("jobs", [])}
        except (OSError, ValueError, urllib.error.URLError):
            jobs = hit[1] if hit else {}
        hit = (time.time(), jobs)
        _jobs_cache[base] = hit
    return hit[1].get(job_id)


def curve(url: str, output: str) -> tuple[str | None, list[tuple[int, float]]]:
    """원격 학습의 (점수 열, [(에폭, 점수)]). 원격 /run이 준 열에서 대표 점수를 고른다(schema 한 곳)"""
    try:
        d = _req(url, "run", q={"path": output})
    except (OSError, ValueError, urllib.error.URLError):
        return None, []
    cols = d.get("columns") or {}
    m = schema.pick_metric(cols.keys()) if cols else None
    if not m:
        return None, []
    ep = cols.get("epoch") or list(range(1, len(cols[m]) + 1))
    return m, [(int(e), float(v)) for e, v in zip(ep, cols[m]) if e is not None and v is not None]


def second(url: str, output: str, which: str) -> float | None:
    """두 번째 목표 값(원격): size = best.pt MB, time = 학습 시간(초, results의 time 열 마지막 값)"""
    try:
        d = _req(url, "run", q={"path": output})
    except (OSError, ValueError, urllib.error.URLError):
        return None
    if which == "size":
        return d.get("weights_mb")
    t = [v for v in (d.get("columns") or {}).get("time", []) if v is not None]
    return float(t[-1]) if t else None
