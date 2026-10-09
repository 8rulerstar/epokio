"""학습별 기계 기록: 학습이 도는 동안 GPU·CPU·메모리·온도·팬을 그 학습 몫으로 남긴다.

지금 값만 보이면 "어제 그 학습은 왜 느렸지", "GPU를 30%밖에 못 썼네"를 나중에 되짚을 수 없다.
파일은 ~/.epokio/sysrec/<학습 경로 해시>.jsonl (사용자의 학습 폴더에는 쓰지 않는다). 한 줄 = 한 표본.

⚠같은 기계에서 두 학습이 동시에 돌면 두 파일에 같은 값이 들어간다(기계 값이지 학습 값이 아니다).
  화면은 "동시에 돈 학습이 있었다"를 알 수 없으니 기록마다 그때 돈 학습 수(n)를 남겨 둔다.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

DIR = Path.home() / ".epokio" / "sysrec"
EVERY_SEC = 15.0               # 한 학습에 이보다 자주 적지 않는다
MAX_LINES = 20000              # 15초 간격으로 약 3.5일. 넘으면 더 적지 않는다(파일이 끝없이 크지 않게)
LOW_GPU = 50.0                 # 평균 GPU 사용률이 이보다 낮으면 해설 한 줄
MIN_SAMPLES = 20               # 5분쯤. 이보다 적으면 평균을 믿지 않는다

_last: dict[str, float] = {}
_count: dict[str, int] = {}


def _file(run_path) -> Path:
    return DIR / (hashlib.sha1(str(run_path).encode("utf-8")).hexdigest()[:16] + ".jsonl")


def _row(s, n: int, now: float) -> dict:
    g = (s.gpus or [None])[0] if getattr(s, "gpus", None) else None
    mem = s.mem_used / s.mem_total * 100 if getattr(s, "mem_used", None) and getattr(s, "mem_total", None) else None
    gmem = g.mem_used / g.mem_total * 100 if g and g.mem_used and g.mem_total else None
    r = {"t": round(now, 1), "n": n, "gpu": getattr(g, "util", None), "gmem": gmem, "cpu": s.cpu, "mem": mem,
         "gtemp": getattr(g, "temp", None), "temp": getattr(s, "cpu_temp", None), "fan": getattr(s, "fan", None)}
    return {k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items() if v is not None}


def record(run_paths, s, now: float | None = None) -> int:
    """도는 학습들 몫으로 표본 하나씩. 적은 수를 돌려준다. 실패는 조용히(기록 때문에 감시가 멈추면 안 된다)"""
    if s is None or not run_paths:
        return 0
    now = time.time() if now is None else now
    wrote = 0
    for p in run_paths:
        key = str(p)
        if key in _last and now - _last[key] < EVERY_SEC:
            continue
        f = _file(key)
        try:
            if key not in _count:
                _count[key] = sum(1 for _ in f.open(encoding="utf-8")) if f.exists() else 0
            if _count[key] >= MAX_LINES:
                continue
            DIR.mkdir(parents=True, exist_ok=True)
            with f.open("a", encoding="utf-8") as out:
                out.write(json.dumps(_row(s, len(run_paths), now)) + "\n")
            _count[key] += 1
            _last[key] = now
            wrote += 1
        except OSError:
            continue
    return wrote


def live_paths(agent) -> list:
    """지금 도는 학습들. 대기열 학습은 폴더 훑기를 기다리지 않고 바로(★배터리 절전이면 훑기가 30~120초라
    1~2분짜리 학습은 한 번도 안 적혔다). 밖에서 돌린 학습은 마지막 훑기에서 '도는 중'이던 것"""
    out = [r.path for r in getattr(getattr(agent, "_mon", None), "runs", []) or [] if r.state == "running"]
    for j in getattr(getattr(agent, "queue", None), "jobs", []) or []:
        if j.state == "running" and j.kind == "train" and j.output and Path(j.output) not in [Path(p) for p in out]:
            out.append(Path(j.output))
    return out


def loop(agent):
    """agent 곁에서 EVERY_SEC마다 적는다. 감시가 멈추면 같이 멈춘다"""
    import logging
    while not getattr(agent, "_stop_watching", False):
        try:
            record(live_paths(agent), getattr(getattr(agent, "sampler", None), "latest", None))
        except Exception:
            logging.getLogger("epokio").exception("system record failed")
        time.sleep(EVERY_SEC)


def read(run_path) -> dict | None:
    """화면용: 시작부터 흐른 분(x)과 열마다 값. 표본이 없으면 None"""
    rows = []
    try:
        with _file(run_path).open(encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return None
    if not rows:
        return None
    t0 = rows[0]["t"]
    cols = {k: [r.get(k) for r in rows] for k in ("gpu", "gmem", "cpu", "mem", "gtemp", "temp", "fan") if any(k in r for r in rows)}
    avg = lambda k: (sum(v for v in cols[k] if v is not None) / max(1, sum(v is not None for v in cols[k]))) if k in cols else None
    return {"minutes": [round((r["t"] - t0) / 60, 2) for r in rows], "columns": cols, "samples": len(rows),
            "shared": any(r.get("n", 1) > 1 for r in rows),
            "avg": {k: round(avg(k), 1) for k in cols}}


# GPU가 놀 때 해 볼 것. 프레임워크마다 설정 이름이 다르다.
# ★Hugging Face·Keras·Lightning 학습에도 울트라리틱스 인자(workers, cache=ram)를 권했다
_IDLE_TIPS = {
    "ultralytics": "The GPU may be waiting for data. Try more workers, cache=ram, or a larger batch.",
    "huggingface": "The GPU may be waiting for data. Try a higher dataloader_num_workers or per_device_train_batch_size in TrainingArguments.",
    "lightning": "The GPU may be waiting for data. Try num_workers and pin_memory=True in your DataLoader, or a larger batch size.",
    "keras": "The GPU may be waiting for data. Try a tf.data pipeline with .cache() and .prefetch(tf.data.AUTOTUNE), or a larger batch size.",
}
_IDLE_TIP_OTHER = "The GPU may be waiting for data. Try more data loading workers, keeping the data in memory, or a larger batch size."


def note(rec: dict | None, framework: str = "ultralytics") -> tuple[str, str] | None:
    """해설 한 줄: GPU를 절반도 못 썼다. 표본이 적거나 GPU 값이 없으면 None"""
    if not rec or rec["samples"] < MIN_SAMPLES or rec["avg"].get("gpu") is None or rec["avg"]["gpu"] >= LOW_GPU:
        return None
    from .msg import tr
    return (tr("The GPU was busy only {pct}% of the time on average while this run trained.", pct=f"{rec['avg']['gpu']:.0f}"),
            tr(_IDLE_TIPS.get(framework, _IDLE_TIP_OTHER)))
