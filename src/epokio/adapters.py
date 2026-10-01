"""프레임워크별 학습 기록을 한 모양으로 바꾼다(어댑터).

Epokio의 나머지 부분(목록·상태·곡선·해설·비교)은 "에폭별 행" 하나만 본다:
    [{"epoch": "1", "time": "12.3", "train/xxx_loss": "...", "val/xxx_loss": "...", "metrics/xxx": "..."}, ...]
값은 문자열이다(results.csv를 읽을 때와 같게). 열 이름 규칙:
    손실  train/<이름>_loss · val/<이름>_loss      점수  metrics/<이름>   (높을수록 좋은 것만)

새 프레임워크를 넣으려면 Adapter를 하나 더 만들어 ADAPTERS에 넣으면 된다.
★코드를 고치지 않는다는 원칙: 프레임워크가 원래 남기는 파일만 읽는다.

파일 나눔(400줄 상한): adapters_base(공통 부품) · adapters_ultra(Ultralytics·epokio.log) ·
adapters_hf(Hugging Face) · adapters_csvlog(Lightning·Keras·이름 무관 에폭 CSV) · tfevents(TensorBoard).
옛 import(from .adapters import Loaded, metric_column …)가 그대로 되도록 여기서 다시 내보낸다.
"""
from __future__ import annotations

from pathlib import Path

from .adapters_base import (Adapter, Loaded, _CSV_CACHE, _LOWER, _csv_header, _int, _num,  # noqa: F401
                            _read_csv, _yaml_value, metric_column)
from .adapters_csvlog import CsvLog, JsonLines, Keras, Lightning  # noqa: F401
from .adapters_hf import HuggingFace  # noqa: F401
from .adapters_mm import MMEngine  # noqa: F401
from .adapters_wandb import WandB  # noqa: F401
from .adapters_ultra import (ULTRA_LOSSES, ULTRA_TASK_METRIC, ULTRA_TASKS, EpokioLog, Ultralytics,  # noqa: F401
                             _log_row, ultralytics_warnings)
from .tfevents import TensorBoard  # noqa: E402  파서가 커서 따로 둔다. 다른 형식과 같이 있으면 그쪽이 먼저

ADAPTERS: list[Adapter] = [EpokioLog(), Ultralytics(), HuggingFace(), Lightning(), Keras(), JsonLines(), MMEngine(), WandB(), TensorBoard(), CsvLog()]   # CsvLog는 이름 무관 CSV라 맨 끝


def detect(d: Path, names: set[str] | None = None) -> Adapter | None:
    if names is None:
        try:
            names = {p.name for p in d.iterdir()}
        except OSError:
            return None
    for a in ADAPTERS:
        try:
            if a.detect(d, names):
                return a
        except OSError:
            continue
    return None


def load(d: Path) -> Loaded | None:
    a = detect(d)
    return a.load(d) if a else None
