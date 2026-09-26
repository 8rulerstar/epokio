""""같은 설정으로 다시 학습"과 "멈춘 곳에서 재개"의 요청 본문(params)을 만든다. 파일만 읽는다.

★예전에는 앱이 10개 키만 옮겨 증강·freeze·device가 조용히 빠졌고 모델도 yolo11{크기}로 바뀌었다.
여기서는 args.yaml 전체를 타입 그대로(null·리스트·숫자·불리언) 가져오고, 빼는 키는 이유와 함께 알린다.
"""
from __future__ import annotations

from pathlib import Path

from . import yamlish

# 저장 위치·실행 식별 키: 새 학습이 새 폴더에 써야 한다
DROP = ("project", "name", "save_dir", "exist_ok", "resume", "mode")
# 이 기계의 파일을 가리킬 수 있는 키. 경로처럼 생겼는데 없으면 뺀다(model은 따로)
PATH_KEYS = ("data", "cfg", "pretrained", "tracker", "source")


def _looks_path(v) -> bool:
    return isinstance(v, str) and ("/" in v or "\\" in v)


def _exists(v: str, run_dir: Path) -> bool:
    p = Path(v).expanduser()
    return p.exists() or (not p.is_absolute() and (run_dir / p).exists())


def read_args(run_dir: Path) -> dict:
    f = run_dir / "args.yaml"
    if not f.exists():
        return {}
    got, _ = yamlish.load(f.read_text(encoding="utf-8", errors="ignore"))
    return got if isinstance(got, dict) else {}


def same(run_dir: Path) -> dict:
    """원래 run의 설정 전체. model은 원래 값 그대로, 없으면 model_ok=False(사용자가 고른다)."""
    args = read_args(run_dir)
    params, dropped = {}, {}
    for k, v in args.items():
        k = str(k)
        if k in DROP:
            dropped[k] = "run location"
        elif k in PATH_KEYS and _looks_path(v) and not _exists(v, run_dir):
            dropped[k] = "missing path"
        elif k != "model":
            params[k] = v
    model = args.get("model")
    model = model if isinstance(model, str) and model.strip() else ""
    # 이름만 있는 모델(yolov8s.pt)은 ultralytics가 내려받으니 있는 것으로 친다
    model_ok = bool(model) and (not _looks_path(model) or _exists(model, run_dir))
    if model_ok:
        params["model"] = model
    return {"params": params, "kept": sorted(params), "dropped": dropped,
            "model": model, "model_ok": model_ok, **resume_state(run_dir, args)}


def resume_state(run_dir: Path, args: dict | None = None) -> dict:
    """진짜 재개(resume=True, last.pt) 가능 여부. 멈춘(stopped·stalled·failed) run이고 last.pt가 있을 때만."""
    from .scan import read_run
    last = run_dir / "weights" / "last.pt"
    r = read_run(run_dir)
    state = r.state if r else ""
    why = ""
    if not last.exists():
        why = "no last.pt"
    elif state in ("running", "starting"):
        why = "still running"
    elif state == "done":
        why = "already finished"
    elif state not in ("stopped", "stalled", "failed"):
        why = "unknown state"
    return {"resumable": not why, "resume_why": why, "last": str(last) if last.exists() else "", "state": state}


def resume(run_dir: Path) -> dict:
    """재개 요청 본문. ultralytics는 체크포인트 안의 설정·옵티마이저·에폭을 되살리고 원래 폴더에 이어 쓴다."""
    st = resume_state(run_dir)
    if not st["resumable"]:
        raise ValueError(st["resume_why"])
    return {"params": {"model": st["last"], "resume": True}, **st}
