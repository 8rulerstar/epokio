"""요청 값 검사. agent.py가 커져서 나눴다."""
from __future__ import annotations

import os

from . import envs


def python_ok(py: str) -> bool:
    """학습·오토라벨로 띄울 실행 파일. 찾아 둔 환경이거나, 이름이 python인 실행 파일만.
    ★토큰이 새어도 아무 프로그램이나 대기열로 돌리지 못하게(보안 점검 2026-09-22). 이름 규칙을 남긴 이유는
      사용자가 설정에서 직접 적은 환경(목록에 안 잡히는 conda·컨테이너 경로)도 써야 하기 때문"""
    if not py:
        return True                                        # 비우면 대기열이 기본 파이썬을 고른다
    # 파일이 있는지는 보지 않는다: 원격 기계의 경로를 여기서 받아 그 기계로 넘기기도 한다(스윕). 실행은 그쪽에서 다시 검사한다
    # 이름 규칙을 먼저 본다. ★환경 목록(list_envs)은 파이썬마다 띄워 보느라 conda 환경이 여럿이면 수 초가 걸려,
    #   POST /jobs가 원격 스윕의 5초 제한(sweep_remote.TIMEOUT)을 넘겨 시도가 그 기계에 안 들어갔다
    if os.path.basename(py).lower().startswith("python"):
        return True
    return py in {e.get("path") for e in envs.list_envs()}
