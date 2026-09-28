"""클래스별 성능 계산 요청(POST /classes). 밖에서 돌렸거나 예전 판으로 돌린 학습은 epokio_classes.json이 없다.
best.pt로 검증을 한 번 돌리는 작업을 대기열에 넣는다. 결과는 그 학습 폴더에 쓰이고, 상세 화면이 다시 읽는다."""
from __future__ import annotations

from pathlib import Path

from .. import envs, msg, rundetail
from . import NOT_MINE
from ..textnorm import resolve


def get(agent, route: str, q: dict):
    return NOT_MINE


def post(agent, route: str, body: dict):
    if route != "/classes":
        return NOT_MINE
    raw = str(body.get("path", "")).strip()
    d = Path(resolve(raw))
    best = d / "weights" / "best.pt"
    if not raw or not rundetail.inside(d, agent.watch_roots()) or not best.exists():
        return 400, {"error": msg.tr("This run has no weights/best.pt to check.")}
    data = str(rundetail._args(d, None).get("data", "")).strip("'\"")
    if not data:
        return 400, {"error": msg.tr("This run does not say which dataset it used (data in args.yaml).")}
    # 처음 이 학습을 띄운 파이썬, 없으면 ultralytics가 준비된 첫 파이썬(jobs_post.resume_where와 같은 순서)
    py = next((j.python for j in reversed(agent.queue.jobs) if j.output == str(d) and j.python), None) \
        or next((e["path"] for e in envs.list_envs() if e["ready"]), None)
    if not py:
        return 400, {"error": msg.tr("No Python with ultralytics found. Set one up in Train first.")}
    j = agent.queue.add("classes", msg.tr("Per-class scores for {name}", name=d.name), py,
                        {"model": str(best), "data": data, "run": str(d)})
    return 200, {"id": j.id}
