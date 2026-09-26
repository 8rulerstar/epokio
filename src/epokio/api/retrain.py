"""재학습 요청 본문 만들기(POST /retrain/args). 계산은 retrain_args.py. 파일만 읽고 아무것도 시작하지 않는다."""
from __future__ import annotations

from pathlib import Path

from .. import rundetail, retrain_args
from . import NOT_MINE
from ..textnorm import resolve


def get(agent, route: str, q: dict):
    return NOT_MINE


def post(agent, route: str, body: dict):
    if route != "/retrain/args":
        return NOT_MINE
    raw = str(body.get("path", "")).strip()
    d = Path(resolve(raw))
    if not raw or not rundetail.inside(d, agent.watch_roots()) or not (d / "args.yaml").exists():
        return 400, {"error": "path must be an Ultralytics run in a watched folder"}
    if body.get("mode") == "resume":
        try:
            return 200, retrain_args.resume(d)
        except ValueError as e:
            return 400, {"error": f"cannot resume: {e}"}
    return 200, retrain_args.same(d)
