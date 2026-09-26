"""학습에 쓸 파이썬 환경을 찾고, 그 환경의 ultralytics 설정표를 읽는다.

설정표(schema)는 ultralytics의 cfg/default.yaml을 그대로 읽어 만든다.
  → 전문가 화면의 파라미터 100여 개를 손으로 만들지 않는다
  → ultralytics가 버전을 올리면 화면도 저절로 따라간다
yaml 라이브러리에 기대지 않도록 'key: value # comment' 한 줄씩 직접 읽는다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()


def candidates() -> list[str]:
    found = []
    # ★윈도우는 conda 본체가 anaconda3\python.exe, env가 envs\<이름>\python.exe 다(bin 층이 없다).
    #   맥 모양 경로만 보다가 윈도우에서는 agent 자신의 파이썬 하나만 찾았다(2026-09-25 실측)
    conda = [HOME / "anaconda3", HOME / "miniconda3", HOME / "miniforge3", Path("/opt/anaconda3"),
             Path("/opt/miniconda3"), Path("C:/ProgramData/anaconda3"), Path("C:/ProgramData/miniconda3")]
    for b in [c / "envs" for c in conda] + [HOME / ".pyenv/versions"]:
        if b.is_dir():
            for e in sorted(b.iterdir()):
                for rel in ("bin/python", "python.exe"):
                    p = e / rel
                    if p.exists():
                        found.append(str(p))
    # ★exe 로 구우면 sys.executable 이 Epokio.exe 다. 거기에 -c 를 붙이면 런처가 트레이를 또 띄운다
    me = [] if getattr(sys, "frozen", False) else [Path(sys.executable)]
    for p in [c / rel for c in conda for rel in ("bin/python", "python.exe")] + me:
        if p.exists():
            found.append(str(p))
    # python.org 설치본 (윈도우). 사용자별 기본 위치와 모든 사용자용 위치
    for base in (HOME / "AppData/Local/Programs/Python", Path(os.environ.get("ProgramFiles", "C:/Program Files"))):
        if base.is_dir():
            found += [str(p) for p in sorted(base.glob("Python3*/python.exe"))]
    found += _on_path()
    # Epokio가 자동 설치한 환경
    for v in sorted((HOME / ".epokio" / "envs").glob("*")):
        for rel in ("bin/python", "Scripts/python.exe"):
            if (v / rel).exists():
                found.append(str(v / rel))
    # 프로젝트 폴더의 .venv (윈도우는 Scripts\python.exe)
    for root in (HOME / "Projects", HOME / "Desktop"):
        if root.is_dir():
            for pat in ("*/.venv/bin/python", "*/.venv/Scripts/python.exe"):   # 윈도우 venv는 Scripts
                for v in root.glob(pat):
                    found.append(str(v))
    seen, out = set(), []
    for f in found:
        k = os.path.realpath(f)
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def probe(python: str) -> dict:
    """그 파이썬에 ultralytics·torch가 있는지, 어떤 가속기를 쓸 수 있는지."""
    code = r'''
import json, sys
out = {"python": sys.version.split()[0]}
try:
    import ultralytics; out["ultralytics"] = ultralytics.__version__
    from pathlib import Path
    out["cfg"] = str(Path(ultralytics.__file__).parent / "cfg" / "default.yaml")
except Exception: pass
try:
    import torch; out["torch"] = torch.__version__
    out["cuda"] = torch.cuda.is_available()
    out["mps"] = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
except Exception: pass
print(json.dumps(out))
'''
    hit = _probed.get(python)
    if hit and (hit[1] is None or time.time() < hit[1]):
        return hit[0]
    try:
        r = subprocess.run([python, "-c", code], capture_output=True, text=True, timeout=25,
                           encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))   # 창 없는 agent에서 검은 창이 번쩍이지 않게
        info = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        info = {}
    # 다 갖춘 환경은 계속 기억하고, 모자란 것·실패는 1분만. ★예전엔 실패도 영원히 기억해서(lru_cache),
    #   첫 torch import가 25초를 넘었거나 설치 도중에 본 환경이 agent를 다시 켤 때까지 '안 됨'으로 남았다
    _probed[python] = (info, None if "ultralytics" in info and "torch" in info else time.time() + 60)
    return info


_probed: dict[str, tuple[dict, float | None]] = {}


def forget():
    """설치가 끝나면 부른다. 다음 목록 요청에서 다시 떠본다."""
    _probed.clear()


def _on_path() -> list[str]:
    """PATH·py 런처·Microsoft Store 파이썬. ★윈도우가 권하는 방식(스토어, 'py')으로 깐 파이썬을 못 찾아
    exe 사용자가 파이썬을 깔고도 '파이썬이 없습니다'에서 막혔다"""
    import shutil
    import subprocess
    out = []
    for name in ("python3", "python"):
        w = shutil.which(name)
        # WindowsApps\python.exe 는 안 깔았을 때 스토어를 여는 가짜다. 실행하면 스토어 창이 뜬다
        if w and not ("WindowsApps" in w and Path(w).name.lower() in ("python.exe", "python3.exe")):
            out.append(w)
    if sys.platform == "win32":
        apps = Path(os.environ.get("LOCALAPPDATA", str(HOME / "AppData/Local"))) / "Microsoft" / "WindowsApps"
        out += [str(p) for p in sorted(apps.glob("python3.*.exe"))]      # 스토어로 깔았을 때만 생긴다
        launcher = shutil.which("py")
        if launcher:
            try:
                r = subprocess.run([launcher, "-0p"], capture_output=True, text=True, timeout=5,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                for line in r.stdout.splitlines():
                    i = line.lower().find(":\\")
                    path = line[i - 1:].strip() if i > 0 else ""
                    if path.lower().endswith("python.exe") and Path(path).exists():
                        out.append(path)
            except (OSError, subprocess.SubprocessError):
                pass
    return out


def base_python() -> str | None:
    """학습용 가상환경을 만들 파이썬. 보통은 agent 자신.
    ★exe 로 구웠으면 sys.executable 이 Epokio.exe 라 venv 를 못 만들고, -u 를 붙이면 트레이가 또 뜬다.
      그때는 이 기계에서 찾은 진짜 파이썬을 쓴다. 하나도 없으면 None"""
    if not getattr(sys, "frozen", False):
        return sys.executable
    return next(iter(candidates()), None)


def env_name(python: str) -> str:
    """화면에 보일 환경 이름. 파이썬이 든 폴더, 그게 bin·Scripts면 한 칸 위.
    ★예전 규칙은 bin 층을 가정해 윈도우에서 conda env가 'envs', conda 본체가 사용자 폴더 이름으로 나왔다"""
    d = Path(python).parent
    if d.name.lower() in ("bin", "scripts"):
        d = d.parent
    return d.name


def list_envs() -> list[dict]:
    out = []
    for p in candidates():
        info = probe(p)
        if not info:
            continue
        out.append({"path": p, "name": env_name(p), **info,
                    "ready": "ultralytics" in info and "torch" in info})
    out.sort(key=lambda e: (not e["ready"], e["name"]))
    return out


# ── 설정표 ─────────────────────────────────────────

# 초보자 화면에 보일 것만. 나머지는 전문가 모드에서.
BASIC = {"train": ["data", "model", "epochs", "imgsz", "batch", "device"],
         "predict": ["model", "source", "conf", "imgsz", "device"]}

# 어떤 모드에서 의미 있는 키인가 (default.yaml의 구역 제목으로 나눈다)
SECTIONS = {"Train settings": "train", "Val/Test settings": "val", "Predict settings": "predict",
            "Visualize settings": "predict", "Export settings": "export",
            "Hyperparameters": "train", "Custom config.yaml": "all", "Tracker settings": "track"}


def _cast(v: str):
    v = v.strip()
    if v in ("", "null", "None"):
        return None
    if v in ("True", "true"):
        return True
    if v in ("False", "false"):
        return False
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v.strip("'\"")


def parse_default_yaml(text: str) -> list[dict]:
    items, section = [], "general"
    for raw in text.splitlines():
        line = raw.rstrip()
        # 구역 제목: '# Train settings ------' 처럼 긴 줄. ★길이로 거르면 전부 놓친다(실제로 놓쳤다)
        if line.startswith("# ") and line.rstrip().endswith("---"):
            title = line[2:].strip(" -")
            section = next((v for k, v in SECTIONS.items() if title.startswith(k)), "other")
            continue
        if not line or line.startswith("#") or line.startswith(" ") or ":" not in line:
            continue
        key, rest = line.split(":", 1)
        value, _, comment = rest.partition("#")
        v = _cast(value)
        typ = ("bool" if isinstance(v, bool) else "int" if isinstance(v, int)
               else "float" if isinstance(v, float) else "str")
        items.append({"key": key.strip(), "default": v, "type": typ,
                      "help": comment.strip(), "section": section})
    return items


def schema(python: str, mode: str = "train") -> dict:
    info = probe(python)
    cfg = info.get("cfg")
    if not cfg or not Path(cfg).exists():
        return {"ok": False, "reason": "ultralytics is not installed in this Python"}
    items = parse_default_yaml(Path(cfg).read_text(encoding="utf-8"))
    keep = {mode, "all", "general"}
    if mode == "train":
        keep |= {"val"}
    fields = [i for i in items if i["section"] in keep]
    # 다른 구역에 적혀 있지만 이 모드에서도 꼭 필요한 값 (예: 추론에도 model·imgsz·device가 필요)
    cross = {"predict": ["model", "imgsz", "device", "batch", "half", "conf", "iou"]}.get(mode, [])
    have = {f["key"] for f in fields}
    fields = [i for i in items if i["key"] in cross and i["key"] not in have] + fields
    basic = BASIC.get(mode, [])
    for f in fields:
        f["basic"] = f["key"] in basic
    return {"ok": True, "ultralytics": info.get("ultralytics"), "mode": mode, "fields": fields}
