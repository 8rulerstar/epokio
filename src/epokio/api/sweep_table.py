"""설정 표(GET /sweep): 보이는 학습 전부의 '값이 다른 설정'과 대표 점수를 한 표에.
★비교는 4개까지라, 스윕 12개의 '어떤 설정이 점수를 움직였나'를 한눈에 볼 곳이 없었다(MLflow·W&B의 표).
(POST /sweeps 로 스윕을 '만드는' 것은 sweeps.py. 이것은 이미 돈 학습을 읽기만 한다)
hparams.yaml 전부(비밀 키가 들 수 있다)를 읽으므로 auth.OPEN_GET에 넣지 않는다(토큰 필요)."""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from .. import rundetail
from ..auth import SECRET_KEY as SECRET
from ..scan import scan, unique
from . import NOT_MINE

# 값이 학습마다 다른 설정만 싣는다. 기록용 설정은 뺀다
SKIP = {"name", "project", "save_dir", "exist_ok", "resume", "mode", "task", "val", "plots", "verbose",
        "save", "save_period", "save_json", "show", "workers", "device", "cache"}
# 비밀일 수 있는 키(값을 싣지 않는다)는 auth.SECRET_KEY 한 곳. ★열어 두어 LAN의 누구나 wandb 키를 읽을 수 있었다
_lock = threading.Lock()                # 동시에 온 요청이 둘 다 다시 계산하지 않게


def looks_like_path(v) -> bool:
    """/data/x.yaml · C:\\x · ~/models/best.pt 같은 값(설정 표의 열로는 쓸모가 없고 사용자 이름이 샌다)"""
    s = str(v or "").strip("'\"")
    return bool(re.match(r"^([A-Za-z]:[\\/]|/|~[\\/]|\\\\)", s)) or ("/" in s and "." in s.rsplit("/", 1)[-1])


def run_args(d: Path, memo: dict, keep: dict) -> dict:
    """args.yaml(없으면 hparams.yaml)의 한 줄짜리 값. 파일 시각이 그대로면 다시 읽지 않는다"""
    for name in ("args.yaml", "hparams.yaml"):
        f = d / name
        try:
            mt = f.stat().st_mtime_ns
        except OSError:
            continue
        got = memo.get(str(f))
        if not got or got[0] != mt:
            got = (mt, rundetail._args_file(f))
        keep[str(f)] = got
        return got[1]
    return {}


def table(agent) -> dict:
    """학습마다 값이 다른 설정을 전부 보낸다(어느 열을 보일지는 화면이 거른 학습으로 정한다).
    빼는 것: 기록용 설정, 비밀일 수 있는 키, 경로 값. 설정 읽기는 파일 시각으로 기억하고, 한 번에 하나만 계산한다"""
    with _lock:
        hit = getattr(agent, "_sweep_cache", None)
        if hit and time.time() - hit[0] < 10:
            return hit[1]
        sc = getattr(agent, "_scanned", None)
        runs = sc[2] if sc and time.time() - sc[0] < 30 else [
            r for root in agent.watch_roots() if root.exists() for r in scan(root)]
        memo, keep = getattr(agent, "_sweep_args", {}), {}
        rows = []
        for r in unique(runs):
            args = run_args(Path(r.path), memo, keep)
            rows.append({"path": str(r.path), "display": r.to_dict()["display"], "state": r.state,
                         "best": r.best, "lower": r.lower, "metric_name": r.metric_name, "args": args})
        agent._sweep_args = keep
        seen: dict[str, set] = {}
        for row in rows:
            for k, v in row["args"].items():
                seen.setdefault(k, set()).add(v)
        keys = [k for k, vs in seen.items() if len(vs) > 1 and k not in SKIP
                and not SECRET.search(k) and not all(looks_like_path(v) for v in vs)]
        keys.sort(key=lambda k: (-len(seen[k]), k))         # 많이 바뀐 설정부터
        keys = keys[:200]
        for row in rows:
            row["args"] = {k: row["args"][k] for k in keys if k in row["args"]}
        res = {"keys": keys, "runs": rows}
        agent._sweep_cache = (time.time(), res)
        return res


def get(agent, route: str, q: dict):
    return table(agent) if route == "/sweep" else NOT_MINE


def post(agent, route: str, body: dict):
    return NOT_MINE
