"""작업 넣기(POST /jobs): 입력 검사, 이어 하기, GPU 고르기. 대기열 자체는 jobs.py"""
from __future__ import annotations

import sys
from pathlib import Path

from .. import envs, msg, rundetail, runmeta
from ..inputs import python_ok
from ..jobs import EXPORT_FORMATS
from ..textnorm import resolve
from . import NOT_MINE

TEXT_KEYS = {"data", "model", "source", "project", "name", "cfg", "tracker", "format", "device", "classes"}


def typed_value(v):
    """"30"→30, "0.01"→0.01, "true"→True, "null"→None. 경로·이름(TEXT_KEYS)은 부르지 않는다"""
    if not isinstance(v, str):
        return v
    s = v.strip()
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", "~"):
        return None
    for t in (int, float):
        try:
            return t(s)
        except ValueError:
            pass
    return s



def resume_check(agent, params: dict, body: dict):
    """이어 해도 되는지. 안 되면 (코드, 본문)"""
    import time
    from ..scan import ENDED_SEC
    ckpt = Path(str(params["model"]))
    # last.pt만. ★best.pt도 받아서, 되감긴 에폭부터 다시 돌며 results.csv에 같은 에폭이 두 번 들어갔다
    if ckpt.name != "last.pt" or ckpt.parent.name != "weights" or not ckpt.is_file():
        return 400, {"error": msg.tr("To resume, pick a run's weights/last.pt")}
    run = ckpt.parents[1]
    # ultralytics 학습만(args.yaml이 있고 epokio.start()가 쓴 것이 아닌 것). ★직접 짠 학습·YOLOv5의 last.pt는 YOLO()가 못 읽는다
    args = run / "args.yaml"
    try:
        ours = args.read_text(encoding="utf-8", errors="ignore").startswith("task: custom")
    except OSError:
        ours = True
    if ours:
        return 400, {"error": msg.tr("Only ultralytics runs can be resumed.")}
    # 옮긴 학습은 안 된다. ultralytics는 체크포인트에 적힌 save_dir(새 판은 절대 경로)에 이어 쓴다.
    # ★폴더를 옮기거나 다른 PC에서 복사한 학습을 이어 하면 옛 경로에 새 폴더를 만들거나 권한 오류가 났고,
    #   대기열은 새 폴더를 보고 있었다
    saved = rundetail._args(run, None).get("save_dir", "").strip("'\"")
    if saved and Path(saved).is_absolute() and runmeta.key(saved) != runmeta.key(str(run)):
        return 409, {"error": msg.tr("This run was moved after training (it was saved at {old}). "
                                     "Ultralytics would continue there, so use Train again instead.", old=saved)}
    # 최근에 바뀌었으면 아직 돌고 있을 수 있다(에폭이 3분보다 긴 학습은 '멎음'으로 보인다).
    # ★터미널에서 띄운 학습에 두 번째 학습을 붙여 같은 GPU·같은 파일에 둘이 썼다
    newest = max((f.stat().st_mtime for f in (ckpt, run / "results.csv") if f.exists()), default=0)
    if time.time() - newest < ENDED_SEC and not body.get("force"):
        return 409, {"error": msg.tr("This run changed in the last 30 minutes and may still be training.")}
    # ★대기 중인 작업은 output이 아직 비어 있어 두 번 눌러도 둘 다 들어갔다. 체크포인트로 비교한다
    for j in agent.queue.jobs:
        if j.state in ("queued", "running") and (j.output == str(run) or (
                j.params.get("resume") and Path(str(j.params.get("model", ""))) == ckpt)):
            return 409, {"error": msg.tr("This run is already queued or training")}
    return None

def resume_where(agent, ckpt: Path, body: dict) -> dict:
    """어느 파이썬으로, 어느 폴더에서 띄울지.
    ultralytics는 체크포인트에 적힌 save_dir에 이어 쓴다. 상대 경로(runs/detect/train)면 처음 띄운 폴더 기준이라
    그 폴더에서 띄워야 한다. ★agent 폴더(exe면 설치 폴더)에서 띄워 엉뚱한 곳에 쓰거나 권한 오류가 났다"""
    run = ckpt.parents[1]
    out = {}
    saved = rundetail._args(run, None).get("save_dir", "").strip("'\"")
    if saved and not Path(saved).is_absolute() and not body.get("cwd"):
        parts = Path(saved).parts
        if tuple(run.parts[-len(parts):]) == parts:
            out["cwd"] = str(Path(*run.parts[:-len(parts)]))
    if not body.get("python"):                 # 처음 이 학습을 띄운 파이썬, 없으면 준비된 첫 파이썬
        first = next((j.python for j in reversed(agent.queue.jobs) if j.output == str(run) and j.python), None)
        first = first or next((e["path"] for e in envs.list_envs() if e["ready"]), None)
        if first:
            out["python"] = first
    return out

# 보기

def get(agent, route: str, q: dict):
    return NOT_MINE


def post(agent, route: str, body: dict):
    if route != "/jobs":
        return NOT_MINE
    if getattr(getattr(agent, "queue", None), "locked_out", False):
        return 409, {"error": msg.tr("Another Epokio helper on this machine runs the queue. Stop it first (epokio agent --stop).")}
    kind = body.get("kind")
    if kind not in ("train", "autolabel", "evaluate", "script", "setup", "export", "practice"):
        return 400, {"error": "kind must be train, autolabel, evaluate, script, setup, export or practice"}
    if kind == "setup":                              # 설치는 agent 자신의 파이썬으로 가상환경을 만든다
        base = envs.base_python()                    # exe 로 구웠으면 이 기계의 진짜 파이썬
        if not base:
            return 400, {"error": msg.tr("No Python found on this machine. Install Python 3.10 or newer "
                                         "from python.org, then try again.")}
        j = agent.queue.add("setup", msg.tr("Set up Python"), base, {})
        return 200, {"id": j.id}
    if not isinstance(body.get("params") or {}, dict):
        return 400, {"error": "params must be an object"}
    if kind == "practice":                           # 연습 학습도 agent 자신의 파이썬(표준 라이브러리만)
        j = agent.queue.add("practice", body.get("name") or "practice", sys.executable, dict(body.get("params") or {}))
        return 200, {"id": j.id}
    params = dict(body.get("params") or {})
    if not all(isinstance(body.get(k, ""), str) for k in ("python", "name", "cwd")):
        return 400, {"error": "python, name and cwd must be text"}
    if kind == "script" and not (isinstance(params.get("args", []), list)
                                 and all(isinstance(a, str) for a in params.get("args", []))):
        return 400, {"error": "args must be a list of text"}     # ★숫자가 섞이면 대기열 스레드에서 터졌다
    # ★train은 model도 있어야 한다. 없이 받으면 대기열에서 KeyError로 죽었다
    need = {"train": ["data", "model"], "evaluate": ["model", "source"], "autolabel": ["model", "source"],
            "export": ["model", "format"]}.get(kind, [])
    if kind == "train" and params.get("resume"):   # 이어 하기: 학습 폴더의 weights/last.pt 하나면 된다
        need = ["model"]
    missing = [k for k in need if not params.get(k)]
    if kind == "script" and not params.get("args"):
        return 400, {"error": "script needs a file to run (params.args)"}
    if missing:                                   # ★예전엔 받아 놓고 대기열에서 실패했다
        return 400, {"error": msg.tr("Missing: {what}", what=", ".join(missing))}
    if kind == "export" and params.get("format") not in EXPORT_FORMATS:
        return 400, {"error": "format must be one of " + ", ".join(sorted(EXPORT_FORMATS))}
    if kind in ("train", "evaluate", "autolabel", "export"):   # ★웹은 args.yaml 값을 글자("0.01")로 보냈다: 숫자·참거짓으로
        params = {k: (v if k in TEXT_KEYS else typed_value(v)) for k, v in params.items()}
    if not python_ok(str(body.get("python") or "")):
        return 400, {"error": "python must be a Python interpreter on this machine"}
    for k in ("data", "model", "source"):          # 맥↔윈도우 한글 경로 맞추기
        if isinstance(params.get(k), str):
            params[k] = resolve(params[k])
    if kind == "train" and params.get("resume"):
        err = resume_check(agent, params, body)
        if err:
            return err
        body = {**body, **resume_where(agent, Path(str(params["model"])), body)}
        if not body.get("python"):
            return 400, {"error": msg.tr("No Python with ultralytics found. Set one up in Train first.")}
        if not python_ok(str(body.get("python") or "")):
            return 400, {"error": "python must be a Python interpreter on this machine"}
    from .. import gpus
    want = gpus.normalize(body.get("gpu"))
    if not gpus.known(want):                       # "3"인데 GPU가 2장: 받아 놓고 영영 안 돌면 안 된다
        return 400, {"error": f"this machine has no GPU {want}"}
    extra = {} if want == gpus.AUTO else {"gpu": want}    # 기본(auto)이면 대기열의 기본값에 맡긴다
    j = agent.queue.add(kind, body.get("name") or kind, body.get("python", ""),
                        params, body.get("cwd", ""), **extra)
    return 200, {"id": j.id, "gpu": getattr(j, "gpu", want)}
