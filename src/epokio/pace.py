"""얼마나 자주 훑을까(쉬는 상태 전력). 설정 → 일반 "기록 읽기"(config.scan_mode)를 따른다.

* auto(기본): 도는 학습이 있으면 8초. 없으면 8 → 15 → 30 → 60초로 늘린다. 무엇이 바뀌거나 파일 알림이 오면 바로 8초로
* saver: 도는 학습 30초, 없으면 120초. 알림이 몇 분 늦을 수 있다
* manual: 폴더를 훑지 않는다(누를 때만, POST /refresh). 완료·실패·멈춤·목표 알림이 오지 않는다. 대기열·스윕은 계속 돈다
* 배터리로 돌면(saver_on_battery) auto를 saver로
파일 알림은 watchdog가 깔려 있을 때만(선택 의존성). 네트워크 드라이브는 알림이 불안정해 주기 훑기가 늘 받쳐 준다
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from . import config

AUTO_STEPS = (8, 15, 30, 60)
SAVER = (30, 120)


class Pace:
    def __init__(self, battery=None):
        self.step = 0                         # auto에서 쉬는 동안 몇 번째 칸인가
        self.wake = threading.Event()         # 파일 알림·새로 고침 요청이 오면 바로 깬다
        self._battery = battery               # () -> (퍼센트, 충전 중). 시험에서 바꾼다
        self._batt_at, self._on_battery = 0.0, False
        self._observer = None

    def mode(self) -> str:
        c = config.load()
        m = c.get("scan_mode", "auto")
        if m == "auto" and c.get("saver_on_battery", True) and self.on_battery():
            return "saver"
        return m

    def on_battery(self) -> bool:
        if time.time() - self._batt_at > 60:                     # pmset은 1분에 한 번만
            # ★읽기 전에 시각부터 적으면, 읽는 동안(수십 ms) 다른 스레드가 '방금 읽음'으로 보고 채워지지 않은
            #   기본값(전원 연결)을 받았다. 배터리로 켠 직후 첫 /runs가 auto, 다음이 saver가 되어 한 번 더 훑었다.
            #   다 읽은 뒤에 값과 시각을 함께 적는다(겹치면 pmset을 두 번 부를 뿐 틀린 값은 안 나간다)
            try:
                if self._battery is None:
                    from .sysinfo import _battery
                    self._battery = _battery
                pct, charging = self._battery()
                on = pct is not None and charging is False
            except Exception:
                on = False
            self._on_battery, self._batt_at = on, time.time()
        return self._on_battery

    def interval(self, live: bool, changed: bool) -> float:
        """다음 훑기까지 기다릴 초. manual은 훑지 않고 대기열만 챙기는 간격"""
        m = self.mode()
        if m == "manual":
            return 8
        if m == "saver":
            return SAVER[0] if live else SAVER[1]
        if live or changed:
            self.step = 0
        else:
            self.step = min(self.step + 1, len(AUTO_STEPS) - 1)
        return AUTO_STEPS[self.step]

    def should_scan(self) -> bool:
        return self.mode() != "manual"

    def sleep(self, seconds: float) -> bool:
        """기다린다. 중간에 깨면 True"""
        woke = self.wake.wait(seconds)
        self.wake.clear()
        if woke:
            self.step = 0
        return woke

    def watch(self, roots: list[Path]) -> bool:
        """파일 알림(watchdog 있으면). 로컬 폴더만. 되면 True"""
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            return False
        if self._observer:
            self._observer.stop()
        pace = self

        class H(FileSystemEventHandler):
            def on_any_event(self, e):
                if not e.is_directory and str(e.src_path).endswith((".csv", ".json", ".yaml", ".log")):
                    pace.wake.set()
        obs = Observer()
        for r in roots:
            if r.exists() and not str(r).startswith("/Volumes/"):   # 네트워크·외장 드라이브는 주기 훑기로
                try:
                    obs.schedule(H(), str(r), recursive=True)
                except OSError:
                    pass
        obs.daemon = True
        obs.start()
        self._observer = obs
        return True
