"""작업 대기열. 학습·오토라벨링·임의 스크립트를 줄 세워 차례로 돌린다.

원칙
  1. 직접 구현하지 않는다. 실행은 전부 그 프레임워크(ultralytics 등)에 넘긴다
  2. 한 GPU에서는 한 번에 하나만 돈다 (예전에 병행 학습이 GPU를 다퉈 날아간 적이 있다).
     GPU가 여러 장이면(nvidia-smi로 셈) 장마다 한 줄씩, 빈 GPU에 다음 작업을 넣는다.
     nvidia-smi가 없거나 GPU가 한 장이면 예전처럼 한 줄이다 (gpus.py)
  3. 대기열은 파일에 남긴다. 앱이나 agent를 껐다 켜도 이어진다
  4. 각 작업은 사용자가 고른 파이썬 환경에서 돈다. Epokio가 그 환경에 설치돼 있을 필요가 없다
     → 작은 실행 스크립트를 만들어 그 파이썬으로 돌린다

나눈 곳: 스크립트 틀 jobs_templates.py, 프로세스 다루기 jobs_proc.py, 대기열 jobs_queue.py.
★경로 상수(HOME·STATE·LOGS·SCRIPTS·SETUP_DIR)는 이 모듈에만 있다. 다른 모듈은 부를 때마다 여기서 읽는다
  (테스트가 jobs.LOGS 등을 바꿔 끼운다)
"""
from __future__ import annotations

import json
import os  # noqa: F401  (jobs.os: 테스트가 갈아 끼운다)
import signal  # noqa: F401  (jobs.signal: 테스트가 본다)
import subprocess  # noqa: F401  (jobs.subprocess: 테스트가 갈아 끼운다)
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
    python: str                   # 실행할 파이썬
    params: dict = field(default_factory=dict)
    cwd: str = ""
    state: str = "queued"         # queued | running | done | failed | cancelled
    created: float = 0.0
    started: float | None = None
    ended: float | None = None
    returncode: int | None = None
    log: str = ""
    output: str = ""              # 결과 폴더 (run 폴더 또는 라벨 폴더)
    pid: int | None = None
    pid_start: float | None = None  # 그 프로세스가 시작된 시각(번호 재사용을 가려낸다)
    sweep: str = ""            # 스윕에 속한 학습이면 스윕 id (epokio.sweep)
    gpu: str = "auto"          # 요청: auto | cpu | "0","1",...  (gpus.normalize)
    gpu_index: int | None = None   # 실제로 배정된 GPU 번호 (cpu·GPU 없음이면 None)


EXPORT_FORMATS = {"onnx", "coreml", "tflite", "openvino", "engine", "torchscript", "ncnn"}
# 이어 하기 때 체크포인트 설정 대신 넘겨도 되는 것(나머지는 체크포인트에 적힌 원래 설정을 쓴다)
RESUME_KEYS = ("model", "resume", "device", "batch", "workers")


def safe_name(name: str) -> str:
    """결과 폴더 이름으로 쓰는 작업 이름. ★"../../x"면 project 밖에 결과를 썼다. 경로 구분자·줄바꿈·앞뒤 점을 뺀다"""
    import re
    s = re.sub(r"[\\/\r\n\t\x00:]+", "_", str(name)).strip().strip(".")
    return s[:120]


def _free_name(params: dict):
    """같은 이름 폴더가 있으면 name2, name3... ultralytics의 increment_path와 같은 이름을 여기서 미리 정한다"""
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
        if why:                                       # 로그 첫머리에 남겨 왜 바뀌었는지 보이게
            from .jobs_run import note
            note(job, f"epokio: {why}\n")
    if job.kind == "train" and params.get("resume") and params.get("model"):
        # 이어 하기: ultralytics는 체크포인트(weights/last.pt)에 적힌 원래 폴더에 이어 쓴다. 대기열도 그 폴더를 가리킨다.
        # ★이름을 새로 정하면(name2) 대기열은 빈 새 폴더를, 학습은 옛 폴더를 봤다. 다른 설정은 체크포인트 것을 쓴다
        job.output = str(Path(params["model"]).parents[1])
        params = {k: v for k, v in params.items() if k in RESUME_KEYS}
        params["resume"] = True
        src = ENV_HELPERS + TRAIN_TEMPLATE.format(params=json.dumps(params), git=bool(job.cwd))
    elif job.kind == "train":
        params.setdefault("project", str(HOME / "runs"))
        params.setdefault("name", job.name)
        params.setdefault("exist_ok", False)
        # ★안 그러면 같은 데이터로 두 번째 학습할 때 작업은 옛 폴더를 가리켜, 대기열이 끝난 옛 학습의 진행(50/50)을 보였다
        if not params.get("exist_ok"):
            _free_name(params)
        job.output = str(Path(params["project"]) / params["name"])
        src = ENV_HELPERS + TRAIN_TEMPLATE.format(params=json.dumps(params), git=bool(job.cwd))
    elif job.kind == "evaluate":
        params.setdefault("project", str(HOME / "evals"))
        params.setdefault("name", job.name)
        job.output = str(Path(params["project"]) / params["name"])
        src = EVAL_TEMPLATE.format(params=json.dumps(params))       # 원자료만 모은다. 채점은 review.py
    elif job.kind == "classes":                          # 끝난 학습의 클래스별 성능: 결과는 그 학습 폴더에(jobs_templates.write_classes)
        from .jobs_templates import CLASSES_TEMPLATE
        params.setdefault("tmp", str(HOME / "evals" / f"classes_{job.id}"))
        job.output = str(params["run"])
        src = ENV_HELPERS + CLASSES_TEMPLATE.format(params=json.dumps(params))
    elif job.kind == "autolabel":
        # ★기존 라벨을 절대 덮어쓰지 않는다. 결과는 항상 별도 폴더
        params.setdefault("project", str(Path(params["source"]).parent / "labels_auto"))
        params.setdefault("name", job.name)
        # ★같은 폴더에 다시 돌리면 ultralytics가 라벨 파일에 이어 써서 박스가 두 번씩 들어갔고,
        #   이번에 아무것도 못 찾은 이미지는 지난번 라벨이 그대로 남았다. 그래서 늘 새 폴더
        _free_name(params)
        job.output = str(Path(params["project"]) / params["name"])
        src = AUTOLABEL_TEMPLATE.format(params=json.dumps(params))
    elif job.kind == "export":
        if params.get("format") not in EXPORT_FORMATS:
            raise ValueError("unknown export format")
        job.output = str(Path(params["model"]).parent)
        src = EXPORT_TEMPLATE.format(params=json.dumps(params))
    elif job.kind == "practice":                         # 연습 학습: GPU 없이 곡선만 (epokio.practice)
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


from .jobs_queue import Queue  # noqa: E402,F401  (맨 끝: jobs_queue가 이 모듈의 Job·상수를 쓴다)
