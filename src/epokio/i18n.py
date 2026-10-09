"""트레이·폰 알림처럼 앱이 언어를 보내 주지 않는 곳의 짧은 문구. 기본은 영어, 시스템 언어나 설정한 앱의 언어를 따른다.

키는 짧은 이름("notify.done")이고, 번역은 msg.py와 같은 `locales/<코드>.json` 한 벌에서 영어 원문으로 찾는다.
★예전엔 이 파일에 19개 언어 표가 따로 있어 알림 제목이 세 곳에 흩어졌다(맥 작업이 지웠고, 윈도우 작업이 다시 만들었다).
  합치면서 표는 locales로 옮기고 이 파일은 짧은 키 → 영어 원문 대응과 언어 고르기만 남겼다.
새 문구: 아래 PHRASES에 키와 영어를 넣고, locales/en.json에 영어를 그대로, 각 언어 파일에 번역을 더한다.
"""
from __future__ import annotations

from . import msg

# 짧은 키 → 영어 원문(= locales의 키)
PHRASES = {
    "unit.d": "d", "unit.s": "s",
    "unit.m": "m", "unit.h": "h",
    "notify.stalled": "Training may have stopped", "notify.stopped_early": "Stopped before the last epoch",
    "notify.quiet": "Training stopped logging",
    "notify.recovered": "Training resumed", "notify.started": "Training started",
    "notify.goal": "Goal reached", "notify.pruned": "Sweep stopped a run that fell behind",
    "notify.job_done": "Job finished", "notify.job_failed": "Job failed",
    "notify.disk_low": "Disk almost full", "notify.gpu_hot": "GPU is very hot",
    "notify.gpu_mem": "GPU memory is full", "notify.fan_max": "Fans at full speed", "menu.notify": "Notifications",
    "epoch": "epoch", "step": "step", "best": "best",
    "notify.test": "Test alert", "notify.test_body": "Phone alerts from {machine} work.",
    "menu.quit": "Quit Epokio", "notify.done": "Training finished",
    "notify.failed": "Training failed", "notify.diverged": "loss became NaN", "tray.training": "Epokio · {n} training",
    "tray.nothing": "Epokio · nothing training", "tray.down": "Epokio · cannot reach the helper at {agent}",
    "tray.dashboard": "Open dashboard", "tray.tooltip": "Show in tooltip",
    "tray.which": "Which run", "tray.which.live": "The newest running one",
    "tray.which.star": "The starred one", "tray.which.cycle": "Take turns",
    "tray.login": "Start when I log in", "info.pct": "Progress %",
    "info.eta": "Time left", "info.clock": "Finish time",
    "info.epoch": "Epoch", "info.best": "Best score",
    "info.gpu": "GPU %",
}
EN = PHRASES            # 옛 이름. tests/test_tray.py가 키 목록으로 쓴다

_current = "en"


def _table(code: str) -> dict[str, str]:
    """이 언어에서 번역이 있는 키만(없는 키는 영어로 떨어진다)"""
    words = msg.TABLE.get(code, {})
    return {k: words[en] for k, en in PHRASES.items() if en in words}


# 알림 제목 몇 개만 번역된 언어(윈도우 0.3.0에 있던 기계 번역 초안). 에이전트 문장 전체가 없어
# msg.LANGS(모든 키를 갖춰야 하는 언어)에는 넣지 않는다. 파일은 같은 locales/ 에 있고 빠진 키는 영어로 떨어진다
TRAY_ONLY = ("ru", "it", "hi", "tr", "id", "pl", "ar")

TABLE = {c: _table(c) for c in msg.LANGS}
for _c in TRAY_ONLY:
    msg.TABLE.setdefault(_c, msg._load(_c))
    TABLE[_c] = _table(_c)


def use(code: str | None) -> str:
    """언어 코드(ko_KR · zh-TW · pt 등)를 받아 표를 고른다. 모르면 영어. 고른 코드를 돌려준다"""
    global _current
    tag = (code or "").replace("_", "-")
    base = tag.split("-")[0].lower()
    _current = base if base in TRAY_ONLY else msg.resolve(tag)
    return _current


def system_language() -> str | None:
    """이 컴퓨터의 표시 언어(ko_KR 등). 트레이처럼 앱이 언어를 보내 주지 않는 곳에서 쓴다"""
    import locale
    import os
    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            return locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage())
        except (AttributeError, OSError):
            pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var, "").split(".")[0]
        if v and v not in ("C", "POSIX"):
            return v
    return None


def t(key: str, **kw) -> str:
    en = PHRASES.get(key, key)
    s = msg.TABLE.get(_current, {}).get(en) or en
    return s.format(**kw) if kw else s
