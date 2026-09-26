"""버전 요청: 데이터 차이(GET /data-diff), 모델 등록부(GET /models), 사용 중으로 올리기(POST /models/promote). 계산은 lineage.py"""
from __future__ import annotations

from pathlib import Path

from .. import lineage, rundetail, runmeta
from . import NOT_MINE
from ..scan import read_run as scan_one
from ..textnorm import resolve


def get(agent, route: str, q: dict):
    if route == "/data-diff":      # 두 데이터 버전(지문) 사이에 바뀐 파일
        try:
            return lineage.diff(q.get("a", [""])[0], q.get("b", [""])[0])
        except ValueError as e:
            return 400, {"error": str(e)}
    if route == "/models":         # 모델 등록부
        return {"models": lineage.registry()}
    return NOT_MINE


def post(agent, route: str, body: dict):
    if route == "/models/promote":                        # 배포로 올리기: best.pt를 등록부에 복사
        d = Path(resolve(str(body.get("path", ""))))
        if not str(body.get("path", "")).strip() or not rundetail.inside(d, agent.watch_roots()):
            return 400, {"error": "path must be a run in a watched folder"}
        r = scan_one(d)
        info = {"metric": r.metric_name if r else "", "best": r.best if r else None,
                "data": rundetail.detail_versions(d).get("data"), "note": str(body.get("note", ""))[:500]}
        try:
            got = lineage.promote(d, body.get("name") or None, info)
        except ValueError as e:
            return 400, {"error": str(e)}
        runmeta.update(str(d), {"stage": "production"})
        agent._runs_cache = None
        return 200, got
    return NOT_MINE
