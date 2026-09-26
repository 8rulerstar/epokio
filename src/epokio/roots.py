"""지켜보는 폴더를 동시에, 시간 한도 안에서 훑는다.

한 폴더가 막혀도(macOS 권한 대기·거절, 끊긴 네트워크 드라이브) /runs 전체가 멈추지 않게 한다.
★2026-09-22: 재설치 뒤 바탕화면 폴더 권한이 막혀 /runs가 25초 걸리고, 거절된 폴더는 "학습 0개"로 조용히 보였다.
못 끝냈거나 못 읽은 폴더는 지난번 결과를 쓰고 이름을 돌려준다(→ 응답의 slow_roots → 앱 팝오버 안내).
"""
from __future__ import annotations

import concurrent.futures as cf
import os
from pathlib import Path

from .scan import scan


def scan_one(root: Path) -> list:
    """폴더 하나. 권한이 막혀 있으면 빈 목록이 아니라 PermissionError를 올린다."""
    if not root.exists():
        return []
    os.listdir(root)
    return scan(root)


class RootScanner:
    def __init__(self, budget: float = 3.0, workers: int = 8, scan_fn=scan_one):
        self.budget = budget
        self.scan_fn = scan_fn
        self._pool = cf.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scan")
        self._last: dict[str, list] = {}
        self._pending: dict[str, cf.Future] = {}      # 아직 안 끝난 훑기는 다시 띄우지 않는다

    def scan(self, roots: list[Path]) -> tuple[list, list[str]]:
        futs = {}
        for root in roots:
            key = str(root)
            f = self._pending.get(key)                # 지난번에 못 끝낸 훑기가 있으면 그 결과를 쓴다
            if f is None:                             # ★끝난 것을 버리고 새로 띄우면 늘 3초를 넘는 폴더는 영영 안 보였다
                f = self._pool.submit(self.scan_fn, root)
            futs[key] = f
        cf.wait(list(futs.values()), timeout=self.budget)
        runs, slow = [], []
        for key, f in futs.items():
            if f.done() and f.exception() is None:
                self._last[key] = f.result()
                self._pending.pop(key, None)
            else:
                if not f.done():
                    self._pending[key] = f
                slow.append(key)                      # 아직 못 끝냈거나(대기) 못 읽었거나(거절)
            runs += self._last.get(key, [])
        return runs, slow
