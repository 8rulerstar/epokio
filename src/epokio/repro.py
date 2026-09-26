"""재현성 스냅샷: 학습을 시작할 때 "무엇으로 돌렸나"를 epokio_repro.json 한 장에 남긴다.

기록: 코드(git SHA·브랜치·dirty·diff 해시) · 파이썬(경로·버전·주요 패키지) · 시드 · 데이터 지문 · OS·GPU.
원칙: 표준 라이브러리만 · 밖으로 보내지 않음 · 학습 코드 안 건드림 · 홈 경로는 "~"로 가린다.
한 항목이 실패해도 나머지는 쓴다(실패는 그 칸에 "error"로).

★git은 항상 GIT_* 환경변수를 지운 env로 부른다. pre-commit 훅 밑에서 GIT_DIR이 새어 들어와
  남의 저장소(Epokio 자신)를 읽거나 설정을 망가뜨린 적이 있다.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

FILE = "epokio_repro.json"
LOCK_FILE = "requirements.lock.txt"
SCHEMA = 1
KEY_PACKAGES = ("ultralytics", "torch", "torchvision", "numpy", "transformers", "lightning",
                "pytorch-lightning", "tensorflow", "keras", "opencv-python", "pillow", "timm",
                "accelerate", "datasets", "scikit-learn")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
TIMEOUT = 10


# ── 공통 ─────────────────────────────────────────

def _clean_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _run(cmd: list[str], cwd: str | None = None) -> str | None:
    try:
        p = subprocess.run(cmd, cwd=cwd, env=_clean_env(), capture_output=True, text=True,
                           timeout=TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def tilde(value):
    """홈 경로를 ~로. 문자열·목록·사전 안까지.
    ★단순 치환이라 윈도우(C:\\Users\\이름, 대소문자 차이)에서 사용자 이름이 재현 기록에 남았고,
      홈이 /Users/a 면 /Users/ab 까지 먹었다. 오류 보고와 같은 errlog.scrub 을 쓴다"""
    if isinstance(value, str):
        from .errlog import scrub
        return scrub(value)
    if isinstance(value, list):
        return [tilde(v) for v in value]
    if isinstance(value, dict):
        return {k: tilde(v) for k, v in value.items()}
    return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── 코드 ─────────────────────────────────────────

def git_info(path: str | Path) -> dict:
    """path가 든 git 저장소의 커밋·브랜치·dirty. 저장소가 아니면 {"repo": False}."""
    p = Path(path)
    cwd = str(p if p.is_dir() else p.parent)
    if not Path(cwd).exists():
        return {"repo": False}
    top = _run(["git", "rev-parse", "--show-toplevel"], cwd)
    if top is None:
        return {"repo": False}
    sha = (_run(["git", "rev-parse", "HEAD"], cwd) or "").strip() or None
    branch = (_run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd) or "").strip() or None
    status = _run(["git", "status", "--porcelain", "--untracked-files=normal"], cwd) or ""
    out = {"repo": True, "root": tilde(top.strip()), "commit": sha,
           "branch": None if branch == "HEAD" else branch, "dirty": bool(status.strip())}
    if out["dirty"]:
        diff = _run(["git", "diff", "HEAD", "--no-color", "--no-ext-diff"], cwd) or ""
        lines = status.splitlines()
        out["diff_sha256"] = _sha((diff + status).encode("utf-8", "replace"))
        out["changed_files"] = len(lines)
        out["untracked_files"] = sum(1 for ln in lines if ln.startswith("??"))
    return out


# ── 파이썬 ────────────────────────────────────────

_PROBE = r"""
import json, sys, platform
from importlib import metadata as md
want = json.loads(sys.argv[1])
pk = {}
for n in want:
    try: pk[n] = md.version(n)
    except Exception: pass
print(json.dumps({"version": platform.python_version(), "implementation": platform.python_implementation(),
                  "executable": sys.executable, "packages": pk}))
"""


def python_info(python: str | None = None, packages=KEY_PACKAGES) -> dict:
    """그 파이썬으로 importlib.metadata를 물어 설치된 주요 패키지만. 학습용 파이썬이 agent와 다를 수 있어서."""
    exe = python or sys.executable
    raw = _run([exe, "-c", _PROBE, json.dumps(list(packages))])
    if raw is None:
        return {"executable": tilde(exe), "error": "python did not answer"}
    try:
        info = json.loads(raw.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"executable": tilde(exe), "error": "unreadable answer"}
    return tilde(info)


def pip_freeze(python: str | None = None) -> str | None:
    return _run([python or sys.executable, "-m", "pip", "freeze", "--disable-pip-version-check"])


# ── 시드 ─────────────────────────────────────────

def _read_flat_yaml(path: Path) -> dict:
    """args.yaml처럼 한 줄에 key: value인 파일만. PyYAML 없이."""
    out = {}
    try:
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not ln or ln[0] in " #-" or ":" not in ln:
                continue
            k, v = ln.split(":", 1)
            out[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return out


def seed_info(params: dict | None = None, args_yaml: Path | None = None) -> dict:
    src = dict(params or {})
    if args_yaml and args_yaml.exists():
        src = {**_read_flat_yaml(args_yaml), **src}
    out = {k: src[k] for k in ("seed", "deterministic") if k in src}
    if params is not None and "seed" not in out:
        out["seed_default"] = True      # 대기열 작업인데 seed를 안 줌 = 프레임워크 기본값(ultralytics 0)
    return out


# ── 데이터 ────────────────────────────────────────

def _dataset_dirs(data_yaml: Path, cfg: dict) -> list[Path]:
    base = Path(cfg.get("path") or data_yaml.parent)
    if not base.is_absolute():
        base = (data_yaml.parent / base).resolve()
    dirs = []
    for key in ("train", "val", "test"):
        v = cfg.get(key)
        if v and not v.startswith("["):
            d = Path(v) if Path(v).is_absolute() else base / v
            if d.is_dir() and d not in dirs:
                dirs.append(d)
    if not dirs and base.is_dir():
        dirs.append(base)
    return dirs


def data_info(data: str | Path | None, full_hash: bool = False) -> dict:
    """data.yaml 내용 해시 + 이미지 수·총 크기(가벼운 지문). full_hash면 이미지 내용까지 해시."""
    if not data:
        return {}
    p = Path(data)
    out: dict = {"path": tilde(str(p))}
    if not p.exists():
        out["missing"] = True
        return out
    dirs = [p] if p.is_dir() else []
    if p.is_file():
        raw = p.read_bytes()
        out["yaml_sha256"] = _sha(raw)
        dirs = _dataset_dirs(p, _read_flat_yaml(p))
    count, size, listing, content = 0, 0, hashlib.sha256(), hashlib.sha256()
    files = sorted(f for d in dirs for f in d.rglob("*") if f.suffix.lower() in IMAGE_EXT and f.is_file())
    for f in files:
        st = f.stat()
        count, size = count + 1, size + st.st_size
        rel = f.name if not dirs else os.path.relpath(f, dirs[0].parent)
        listing.update(f"{rel}\0{st.st_size}\n".encode("utf-8", "replace"))
        if full_hash:
            content.update(f.read_bytes())
    out.update(images=count, bytes=size, listing_sha256=listing.hexdigest(),
               dirs=[tilde(str(d)) for d in dirs])
    if full_hash:
        out["content_sha256"] = content.hexdigest()
    return out


# ── 기계 ─────────────────────────────────────────

def system_info() -> dict:
    out = {"os": platform.system(), "os_release": platform.release(), "machine": platform.machine()}
    if sys.platform == "darwin":
        chip = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        out["os_version"] = platform.mac_ver()[0]
        if chip:
            out["chip"] = chip.strip()
    smi = _run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    if smi:
        out["gpus"] = [dict(zip(("name", "driver"), [x.strip() for x in ln.split(",")]))
                       for ln in smi.strip().splitlines()]
        head = _run(["nvidia-smi"]) or ""
        if "CUDA Version:" in head:
            out["cuda"] = head.split("CUDA Version:")[1].split()[0]
    return out


# ── 스냅샷 ────────────────────────────────────────

def snapshot(code: str | Path | None = None, python: str | None = None, params: dict | None = None,
             data: str | Path | None = None, args_yaml: Path | None = None,
             full_data_hash: bool = False, partial: bool = False) -> dict:
    """모든 칸을 모은다. 한 칸이 터져도 나머지는 남긴다."""
    snap: dict = {"schema": SCHEMA, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "partial": partial}
    steps = {"code": lambda: git_info(code) if code else {},
             "python": lambda: python_info(python) if (python or not partial) else {},
             "seed": lambda: seed_info(params, args_yaml),
             "data": lambda: data_info(data, full_data_hash),
             "system": system_info}
    for key, fn in steps.items():
        try:
            snap[key] = fn()
        except Exception as e:           # noqa: BLE001, 스냅샷 때문에 학습이 멈추면 안 된다
            snap[key] = {"error": type(e).__name__}
    if params:
        snap["params"] = tilde({k: v for k, v in params.items() if isinstance(v, (str, int, float, bool))})
    return snap


def write(dest_dir: str | Path, snap: dict, freeze: str | None = None) -> Path:
    d = Path(dest_dir)
    d.mkdir(parents=True, exist_ok=True)
    if freeze:
        (d / LOCK_FILE).write_text(tilde(freeze), encoding="utf-8")
        snap = {**snap, "lock_file": LOCK_FILE, "lock_sha256": _sha(freeze.encode())}
    out = d / FILE
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, out)
    return out


def read(run_dir: str | Path) -> dict | None:
    try:
        return json.loads((Path(run_dir) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
