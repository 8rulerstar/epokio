"""사용자가 고르는 기준값. ~/.epokio/config.json 하나. 앱 설정 → 알림에서 바꾼다(POST /config).

    stall_min      이만큼(분) 새 에폭이 없으면 "멈춘 것 같다"
    disk_low_gb    디스크 여유가 이보다 적으면 경고
    gpu_hot_c      GPU 온도가 이보다 높으면 경고
    gpu_mem_pct    GPU 메모리가 이만큼(%) 차면 경고
    quiet_from/to  이 시간 사이(0~23시)에는 폰 푸시를 보내지 않는다. 같으면 끔
    scan_mode      auto(기본) · saver(절전, 알림이 몇 분 늦을 수 있다) · manual(누를 때만, 알림 없음). pace.py
    saver_on_battery  배터리로 돌면 저절로 절전
    reads_token    보기(GET)에도 토큰을 요구할까: auto(이 기계 밖에 열었을 때만) · always(늘) · never(안 함)
                   ★여러 사람이 SSH로 쓰는 리눅스 서버에서는 "루프백 = 나"가 아니다. 같은 서버의 다른 계정이
                     curl 한 줄로 학습 목록·로그를 읽는다. 그런 기계에서는 always로 둘 것
    launch_runs    도우미로 학습·대기열·스윕·검사 작업을 시작할까(웹 페이지의 Train·Queue·Sweeps, MCP의 학습 도구). 기본 끔.
                   켜는 법: `epokio config launch_runs on`. 웹(POST /config)으로는 못 바꾼다(이 기계에서 일부러 켜는 것)
                   ★Epokio의 자리는 "이미 있는 기록을 읽고 폰에 알린다"다. 학습을 띄우는 화면이 기본으로 보이면 무엇을 하는
                     도구인지 흐려지고, 토큰 하나로 코드를 돌리는 길이 늘 열려 있었다
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

FILE = Path.home() / ".epokio" / "config.json"
DEFAULTS = {"stall_min": 3, "disk_low_gb": 5.0, "gpu_hot_c": 85, "gpu_mem_pct": 97, "quiet_from": 0, "quiet_to": 0,
            "scan_mode": "auto", "saver_on_battery": True, "reads_token": "auto", "launch_runs": False}
CHOICES = {"scan_mode": ("auto", "saver", "manual"), "reads_token": ("auto", "always", "never")}
LIMITS = {"stall_min": (2, 240), "disk_low_gb": (0.5, 500), "gpu_hot_c": (60, 105), "gpu_mem_pct": (50, 100),
          "quiet_from": (0, 23), "quiet_to": (0, 23)}


def load() -> dict:
    try:
        return {**DEFAULTS, **{k: v for k, v in json.loads(FILE.read_text(encoding="utf-8")).items() if k in DEFAULTS}}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def update(changes: dict) -> dict:
    """알려진 값만, 허용 범위 안으로 잘라서 저장한다"""
    from . import jsonfile
    # 깨진 파일은 옆에 남기고(.broken-…) 기본값에서 시작한다. ★예전엔 조용히 기본값으로 덮어써 기준값이 사라졌다
    try:
        saved = jsonfile.read(FILE, {})
    except jsonfile.BrokenFile:
        saved = {}
    c = {**DEFAULTS, **{k: v for k, v in (saved if isinstance(saved, dict) else {}).items() if k in DEFAULTS}}
    for k, v in changes.items():
        if k in CHOICES:
            if v in CHOICES[k]:
                c[k] = v
        elif k in DEFAULTS and isinstance(DEFAULTS[k], bool):
            if isinstance(v, bool):
                c[k] = v
        elif k in DEFAULTS and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            lo, hi = LIMITS[k]
            c[k] = type(DEFAULTS[k])(min(max(v, lo), hi))
    jsonfile.write(FILE, c)                  # 원자적으로(쓰다 끊겨도 반쯤 쓴 파일이 안 남는다)
    return c


LAUNCH_CMD = "config launch_runs on"


def launch_runs(flag: bool = False) -> bool:
    """도우미가 작업(학습·스크립트·스윕·검사)을 시작해도 되나. --launch-runs(맥 앱이 띄운 도우미)·EPOKIO_LAUNCH_RUNS=1·설정 중 하나.
    요청마다 파일을 읽으므로 `epokio config launch_runs on` 뒤 도우미를 다시 켤 필요가 없다"""
    import os
    return bool(flag) or os.environ.get("EPOKIO_LAUNCH_RUNS") == "1" or load().get("launch_runs") is True


def apply(c: dict | None = None):
    """멈춤 판정 시간을 스캐너에 반영한다(끝남 판정은 멈춤의 10배, 최소 30분)"""
    from . import scan
    c = c or load()
    scan.STALE_SEC = c["stall_min"] * 60
    scan.ENDED_SEC = max(30 * 60, scan.STALE_SEC * 10)


def quiet_now(c: dict | None = None, now: datetime | None = None) -> bool:
    c = c or load()
    a, b, h = c["quiet_from"], c["quiet_to"], (now or datetime.now()).hour
    if a == b:
        return False
    return a <= h < b if a < b else (h >= a or h < b)       # 23→7처럼 자정을 넘는 경우
