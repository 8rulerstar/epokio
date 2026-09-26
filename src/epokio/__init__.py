"""Epokio agent. 예전 이름은 TrainBar였다."""
from __future__ import annotations

from pathlib import Path

# 판 번호는 여기 한 곳(pyproject가 이것을 읽는다). ★설치 정보로 읽어, 맥 앱(PYTHONPATH로 소스를 돌린다)과
#   exe에서는 'unknown'이거나 따로 깔린 다른 epokio의 판이 나왔다
__version__ = "0.4.0"


def _migrate_home() -> None:
    """옛 데이터 폴더 ~/.trainbar 를 ~/.epokio 로 한 번 옮긴다(새 폴더가 없을 때만).
    기록 파일 안의 옛 경로도 새 경로로 고친다(대기열 결과 폴더, 알림함의 학습 위치)."""
    old, new = Path.home() / ".trainbar", Path.home() / ".epokio"
    if not old.is_dir() or new.exists():
        return
    try:
        old.rename(new)
        for f in new.glob("*.json"):
            text = f.read_text(encoding="utf-8")
            if "/.trainbar/" in text or "\\\\.trainbar\\\\" in text:
                f.write_text(text.replace("/.trainbar/", "/.epokio/").replace("\\\\.trainbar\\\\", "\\\\.epokio\\\\"),
                             encoding="utf-8")
    except OSError:
        pass            # 옮기지 못하면 새로 시작한다. 옛 폴더는 그대로 남는다


_migrate_home()


def log(epoch, **values):
    """학습 코드에서 값을 남긴다(선택). 자세한 설명은 epokio/logger.py"""
    from .logger import log as _log
    return _log(epoch, **values)


def image(name, path_or_image, epoch=None):
    from .logger import image as _image
    return _image(name, path_or_image, epoch)


def params(**settings):
    """설정을 남긴다(args.yaml). ★이름이 config면 epokio.config 모듈(알림 설정)을 가려 깨졌다"""
    from .logger import params as _params
    return _params(**settings)


def init(run_dir=None):
    from .logger import init as _init
    return _init(run_dir)


def version() -> str:
    """이 코드의 판(맥 앱 판 build_app.sh와 같은 숫자로 맞춘다)"""
    return __version__


def start(folder, epochs=None, **params):
    """직접 짠 학습 코드용 기록기: `run = epokio.start("runs/exp", epochs=50, lr=1e-4)` 후 `run.log(val_loss=..., acc=...)`"""
    from .logger import start as _start
    return _start(folder, epochs, **params)
