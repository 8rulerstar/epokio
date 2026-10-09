"""Job queue. Lines up training, autolabeling and arbitrary scripts and runs them in turn.

Principles
  1. Don't reimplement anything. All execution is handed to the framework (ultralytics etc.)
  2. Only one job at a time per GPU (parallel training once fought over the GPU and both runs were lost).
     With several GPUs (counted via nvidia-smi), one lane per GPU; the next job goes to a free GPU.
     Without nvidia-smi or with a single GPU, it is one lane as before (gpus.py)
  3. The queue is kept in a file. It survives restarting the app or the agent
  4. Each job runs in the Python environment the user picked. Epokio need not be installed there
     -> a small launcher script is generated and run with that Python

Split into: script templates jobs_templates.py, process handling jobs_proc.py, queue jobs_queue.py.
Path constants (HOME, STATE, LOGS, SCRIPTS, SETUP_DIR) live only in this module. Other modules read them from here on each call
  (tests swap jobs.LOGS etc.)
"""
from __future__ import annotations

import json
import os  # noqa: F401  (jobs.os: tests swap it)
import signal  # noqa: F401  (jobs.signal: tests inspect it)
import subprocess  # noqa: F401  (jobs.subprocess: tests swap it)
import sys  # noqa: F401
from dataclasses import dataclass, field
from pathlib import Path

HOME = Path.home() / ".epokio"
STATE = HOME / "jobs.json"
LOGS = HOME / "logs"
SCRIPTS = HOME / "scripts"
SETUP_DIR = HOME / "envs" / "epokio"

from . import gpus  # noqa: E402,F401
from .jobs_proc import NO_WINDOW, kill_tree, pid_alive, proc_start  # noqa: E402,F401
from .jobs_templates import (  # noqa: E402,F401
    AUTOLABEL_TEMPLATE, CUDA_INDEX, ENV_HELPERS, EVAL_HELPERS, EVAL_TEMPLATE, EXPORT_TEMPLATE, SETUP_TEMPLATE,
    TRAIN_TEMPLATE)

_NO_WINDOW = NO_WINDOW


@dataclass
class Job:
    id: str
    kind: str                     # train | autolabel | evaluate | export | setup | script | practice | classes
    name: str
    python: str                   # Python to run with
    params: dict = field(default_factory=dict)
    cwd: str = ""
    state: str = "queued"         # queued | running | done | failed | cancelled
    created: float = 0.0
    started: float | None = None
    ended: float | None = None
    returncode: int | None = None
    log: str = ""
    output: str = ""              # result folder (run folder or label folder)
    pid: int | None = None
    pid_start: float | None = None  # when that process started (detects PID reuse)
    sweep: str = ""            # sweep id if this training belongs to a sweep (epokio.sweep)
    gpu: str = "auto"          # requested: auto | cpu | "0","1",...  (gpus.normalize)
    gpu_index: int | None = None   # GPU actually assigned (None for cpu or no GPU)


EXPORT_FORMATS = {"onnx", "coreml", "tflite", "openvino", "engine", "torchscript", "ncnn"}
# On resume, these may override the checkpoint settings (everything else uses the original settings stored in the checkpoint)
RESUME_KEYS = ("model", "resume", "device", "batch", "workers")


def safe_name(name: str) -> str:
    """Job name used as the result folder name. Previously "../../x" wrote outside project. Strips separators, newlines, edge dots"""
    import re
    s = re.sub(r"[\\/\r\n\t\x00:]+", "_", str(name)).strip().strip(".")
    return s[:120]


def _free_name(params: dict):
    """If a folder with that name exists, use name2, name3... Picks up front the name ultralytics' increment_path would"""
    base, n = params["name"], 2
    while (Path(params["project"]) / params["name"]).exists():
        params["name"] = f"{base}{n}"
        n += 1


def build_command(job: Job) -> list[str]:
    SCRIPTS.mkdir(parents=True, exist_ok=True)
    if job.kind == "script":
        return [job.python, *job.params.get("args", [])]
    params = dict(job.params)
    if job.kind in ("train", "evaluate", "classes"):
        from . import gpus
        why = gpus.fix_device(params, job.gpu, job.gpu_index, bool(gpus.listed()))
        if why:                                       # put it at the top of the log so the reason for the change is visible
            from .jobs_run import note
            note(job, f"epokio: {why}\n")
    if job.kind == "train" and params.get("resume") and params.get("model"):
        # Resume: ultralytics keeps writing to the original folder in the checkpoint (weights/last.pt). The queue points there too.
        # Previously a new name (name2) made the queue watch an empty folder while training used the old one. Other settings: checkpoint's
        job.output = str(Path(params["model"]).parents[1])
        params = {k: v for k, v in params.items() if k in RESUME_KEYS}
        params["resume"] = True
        src = ENV_HELPERS + TRAIN_TEMPLATE.format(params=json.dumps(params), git=bool(job.cwd))
    elif job.kind == "train":
        params.setdefault("project", str(HOME / "runs"))
        params.setdefault("name", job.name)
        params.setdefault("exist_ok", False)
        # Without this, a 2nd training on the same data pointed at the old folder, and the queue showed the old run's progress (50/50)
        if not params.get("exist_ok"):
            _free_name(params)
        job.output = str(Path(params["project"]) / params["name"])
        src = ENV_HELPERS + TRAIN_TEMPLATE.format(params=json.dumps(params), git=bool(job.cwd))
    elif job.kind == "evaluate":
        params.setdefault("project", str(HOME / "evals"))
        params.setdefault("name", job.name)
        # ★같은 폴더(이름이 val인 폴더 등)를 다른 모델로 또 평가하면 앞 평가의 결과를 덮어써, 그 평가의 판정·고친 라벨이 새 결과에 붙었다
        _free_name(params)
        job.output = str(Path(params["project"]) / params["name"])
        src = EVAL_TEMPLATE.format(params=json.dumps(params))       # only collects raw data. Scoring is in review.py
    elif job.kind == "classes":                          # per-class metrics of a finished run, saved in its folder (jobs_templates.write_classes)
        from .jobs_templates import CLASSES_TEMPLATE
        params.setdefault("tmp", str(HOME / "evals" / f"classes_{job.id}"))
        job.output = str(params["run"])
        src = ENV_HELPERS + CLASSES_TEMPLATE.format(params=json.dumps(params))
    elif job.kind == "autolabel":
        # Never overwrite existing labels. Results always go to a separate folder
        params.setdefault("project", str(Path(params["source"]).parent / "labels_auto"))
        params.setdefault("name", job.name)
        # Previously rerunning into the same folder made ultralytics append to label files, doubling boxes,
        #   and images with no detections this time kept last run's labels. Hence always a new folder
        _free_name(params)
        job.output = str(Path(params["project"]) / params["name"])
        src = AUTOLABEL_TEMPLATE.format(params=json.dumps(params))
    elif job.kind == "export":
        if params.get("format") not in EXPORT_FORMATS:
            raise ValueError("unknown export format")
        job.output = str(Path(params["model"]).parent)
        src = EXPORT_TEMPLATE.format(params=json.dumps(params))
    elif job.kind == "practice":                         # practice training: curves only, no GPU (epokio.practice)
        from . import practice
        src, job.output = practice.script({**params, "name": params.get("name") or job.name})
    elif job.kind == "setup":
        job.output = str(SETUP_DIR)
        src = SETUP_TEMPLATE.format(target=str(SETUP_DIR), cuda_index=CUDA_INDEX)
    else:
        raise ValueError(f"unknown job kind: {job.kind}")
    script = SCRIPTS / f"{job.id}.py"
    script.write_text(src, encoding="utf-8")
    return [job.python, "-u", str(script)]


from .jobs_queue import Queue  # noqa: E402,F401  (at the end: jobs_queue uses this module's Job and constants)
