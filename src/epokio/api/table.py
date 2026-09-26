"""학습 기록 표(GET /runs/table): 학습 하나 = 한 줄. 점수·에폭·상태·태그 + 설정값(args.yaml).
화면이 칸으로 정렬·거르기·여러 개 고르기를 한다. args.yaml은 파일 시각이 바뀔 때만 다시 읽는다."""
from __future__ import annotations

from pathlib import Path

from .. import rundetail
from . import NOT_MINE

TABLE_KEYS = ["task", "model", "data", "epochs", "imgsz", "batch", "optimizer", "lr0", "patience"]
_cache: dict[str, tuple[float, dict]] = {}


def _args(path: str) -> dict:
    f = Path(path) / "args.yaml"
    try:
        mt = f.stat().st_mtime
    except OSError:
        return {}
    hit = _cache.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    a = {k: v for k, v in rundetail._args(Path(path)).items() if k in TABLE_KEYS}
    if "model" in a:
        a["model"] = a["model"].replace("\\", "/").split("/")[-1]      # 경로면 파일 이름만
    if "data" in a:
        a["data"] = "/".join(a["data"].replace("\\", "/").split("/")[-2:])
    _cache[path] = (mt, a)
    return a


def get(agent, route: str, q: dict):
    if route != "/runs/table":
        return NOT_MINE
    runs = agent.get("/runs", {})["runs"]
    rows = [{"path": r["path"], "name": r["name"], "state": r["state"], "epoch": r["epoch"], "total": r.get("total"),
             "best": r.get("best"), "metric_name": r.get("metric_name"),
             "metric_higher": bool(r.get("metric_higher", True)), "idle": r.get("idle"),
             "tags": (r.get("meta") or {}).get("tags", []), "star": bool((r.get("meta") or {}).get("star")),
             "framework": r.get("framework"), "args": _args(r["path"])} for r in runs]
    keys = [k for k in TABLE_KEYS if any(k in x["args"] for x in rows)]      # 한 번이라도 나온 설정만 칸으로
    return {"label": agent.label, "keys": keys, "rows": rows}


def post(agent, route: str, body: dict):
    return NOT_MINE
