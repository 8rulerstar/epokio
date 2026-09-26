"""GPU 목록 세기. 여러 장이면 대기열이 빈 GPU마다 하나씩 돌린다.

원칙
  1. nvidia-smi가 없거나 실패하면 GPU 0장으로 본다 -> 대기열은 예전 그대로 한 번에 하나
     (맥은 GPU가 하나뿐이고 CUDA_VISIBLE_DEVICES도 뜻이 없다. 여기서 셀 이유가 없다)
  2. 배정은 CUDA_VISIBLE_DEVICES로만 한다. 학습 코드를 고치지 않는 것이 이 앱의 약속이고,
     ultralytics/torch는 이 변수를 먼저 읽는다. 자식 안에서 보이는 번호는 늘 0번 한 장이다
  3. 점유 상태를 파일에 따로 적지 않는다. 죽은 작업이 GPU를 영영 잡는 자물쇠 파일이 제일 흔한 사고라서,
     '누가 쓰는가'는 대기열의 running 작업에서만 읽는다(작업이 끝나면 그 자리는 자동으로 빈다)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

AUTO = "auto"
CPU = "cpu"

_CACHE: dict = {}
CACHE_SECONDS = 60.0


def smi_path() -> str | None:
    from .sysinfo import nvidia_smi_path
    return nvidia_smi_path()


def parse_index_names(out: str) -> list[dict]:
    """nvidia-smi --query-gpu=index,name --format=csv,noheader 의 출력."""
    gpus = []
    for line in (out or "").strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        gpus.append({"index": int(parts[0]), "name": parts[1]})
    return gpus


def detect() -> list[dict]:
    """[{"index": 0, "name": "RTX 4090"}, ...]. nvidia-smi가 없거나 깨지면 빈 목록."""
    smi = smi_path()
    if not smi:
        return []
    try:
        r = subprocess.run([smi, "--query-gpu=index,name", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=5,
                           encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return []                       # 드라이버가 없거나 멈춤: GPU 0장으로 본다
    if r.returncode != 0:
        return []
    return parse_index_names(r.stdout)


def listed(refresh: bool = False) -> list[dict]:
    """detect()를 60초 기억한다(대기열 일꾼이 계속 물어본다)."""
    hit = _CACHE.get("v")
    if refresh or not hit or time.time() - hit[0] > CACHE_SECONDS:
        _CACHE["v"] = (time.time(), detect())
    return _CACHE["v"][1]


def count(refresh: bool = False) -> int:
    return len(listed(refresh))


def forget():
    _CACHE.pop("v", None)


def lanes() -> list[int | None]:
    """동시에 돌릴 자리. GPU가 2장 이상일 때만 여러 자리가 되고, 그 밖에는 예전처럼 한 자리."""
    idx = [g["index"] for g in listed()]
    return list(idx) if len(idx) >= 2 else [None]


def normalize(want) -> str:
    """작업이 요청한 GPU. 'auto' | 'cpu' | '0','1',... 그 밖은 auto로 본다."""
    s = str(want or AUTO).strip().lower()
    if s in (AUTO, "", "none"):
        return AUTO
    if s == CPU:
        return CPU
    return s if s.isdigit() else AUTO


def fits(want: str, lane: int | None) -> bool:
    """이 자리에서 돌려도 되는 요청인가. 자리가 하나뿐이면(lane None) 무엇이든 받는다."""
    if lane is None:
        return True
    if want in (AUTO, CPU):
        return True
    return want == str(lane)


def assigned(want: str, lane: int | None) -> int | None:
    """실제로 쓸 GPU 번호. cpu는 None, 자리가 하나면 요청한 번호를 그대로 존중한다."""
    if want == CPU:
        return None
    if lane is not None:
        return lane if want == AUTO else int(want)
    return int(want) if want.isdigit() else None


def known(want: str) -> bool:
    """요청한 GPU 번호가 이 기계에 있나. GPU를 못 셌으면(nvidia-smi 없음) 막지 않는다.
    ★번호를 못 막으면 그 작업은 자리를 못 잡고 대기열에 영원히 남는다"""
    if want in (AUTO, CPU) or not want.isdigit():
        return True
    idx = [g["index"] for g in listed()]
    return not idx or int(want) in idx


def env_for(want: str, index: int | None, base: dict | None = None) -> dict:
    """CUDA_VISIBLE_DEVICES를 넣은 환경. auto + GPU 한 장(또는 못 셈)이면 아무것도 건드리지 않는다."""
    env = dict(os.environ if base is None else base)
    if want == CPU:
        env["CUDA_VISIBLE_DEVICES"] = ""        # 빈 값 = GPU를 안 쓴다(torch가 cpu로 떨어진다)
    elif index is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(index)
    return env


def fix_device(params: dict, want: str, index: int | None, has_cuda: bool) -> str | None:
    """넘어온 device가 이 자리에서 뜻이 없으면 고친다. 고친 까닭을 돌려준다(안 고쳤으면 None).
    ★"다시 학습"은 args.yaml의 device를 그대로 옮긴다(같은 기계에선 맞다). 그런데
      ① CUDA 기계의 학습을 맥에서 다시 돌리면 device=0이 와서 실패했고
      ② 대기열이 CUDA_VISIBLE_DEVICES로 한 장만 보이게 해도 device=1이 남아 없는 GPU를 찾았다.
    cpu·mps처럼 GPU 번호가 아닌 값은 건드리지 않는다."""
    d = params.get("device")
    if d is None or str(d).strip() == "":
        return None
    s = str(d).strip().lower().replace("cuda:", "").replace("cuda", "0")
    if not all(p.strip().isdigit() for p in s.split(",")):
        return None
    if not has_cuda:
        params.pop("device")
        return f"device={d} dropped: this machine has no CUDA GPU"
    if want == CPU:
        params["device"] = "cpu"
        return f"device={d} -> cpu: this job was queued for the CPU"
    if index is not None:
        params["device"] = 0
        return f"device={d} -> 0: this job sees only GPU {index}"
    return None


def describe() -> dict:
    """화면·API용 요약."""
    gs = listed()
    return {"gpus": gs, "count": len(gs), "multi": len(gs) >= 2,
            "smi": bool(smi_path()), "platform": sys.platform}
