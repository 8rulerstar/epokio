"""학습 이름·시간 표기처럼 여러 화면이 같이 쓰는 작은 규칙. scan에서 재수출한다(from .scan import display_name 그대로)."""
from __future__ import annotations

import os
import re
import unicodedata

# version_N: Lightning(★여러 학습이 전부 version_0으로 떴다). 날짜_시각: OpenMMLab work_dirs/<설정>/<시각>(★시각만 보였다)
_GENERIC = re.compile(r"^(train|exp|val|predict|run|detect|segment|pose|classify)\d*$|^version_\d+$|^\d{8}_\d{6}$")
_WANDB = re.compile(r"^(?:offline-)?run-\d{8}_\d{6}-([a-z0-9]+)$")   # W&B: wandb/offline-run-<시각>-<id>
_SKIP_PARENT = ("runs", "detect", "segment", "pose", "classify", "obb", "lightning_logs", "wandb")


def display_name(r) -> str:
    """'train'처럼 흔한 이름이면 위 폴더를 붙인다: defect_det/train. 한 곳에서만 정한다.
    ★웹·터미널·트레이·맥이 따로 만들어, 맥은 윈도우 경로(\\)를 못 나눠 'train'만 보였다.
    맥에서 온 한글 이름(NFD)은 NFC로(칸 수가 두 배로 세어져 표가 어긋났다)"""
    name = unicodedata.normalize("NFC", r.name)
    if (w := _WANDB.match(name)):
        name = w.group(1)                                   # ★offline-run-20260930_145135-h32dkwxl 이 그대로 보였다
    elif not _GENERIC.match(name):
        return name
    parts = [p for p in re.split(r"[\\/]", str(r.path)) if p]
    parent = next((p for p in reversed(parts[:-1]) if p not in _SKIP_PARENT), None)
    return unicodedata.normalize("NFC", f"{parent}/{name}") if parent else name


def unique(runs: list) -> list:
    """같은 학습은 한 번만(먼저 온 것). ★한 감시 폴더가 다른 감시 폴더 안에 있으면(직접 더한 ~/proj와 찾은
    ~/proj/runs) 목록·보고서에 같은 학습이 두 번 나왔다"""
    seen, out = set(), []
    for r in runs:
        k = (r.source, os.path.normcase(os.path.normpath(str(r.path))))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def fmt_dur(sec: float | None, sep: str = " ") -> str:
    """걸린·남은 시간. 내림하고, 하루가 넘으면 시간까지(웹과 같은 규칙). 단위는 i18n(한국어면 일·시간·분·초).
    ★터미널·트레이가 따로 만들어 47시간 남은 학습이 '1d'로 보였다"""
    from .i18n import t
    if sec is None:
        return "-"
    s = int(sec)
    if s < 60:
        return f"{s}{t('unit.s')}"
    if s < 3600:
        return f"{s // 60}{t('unit.m')}"
    if s < 86400:
        return f"{s // 3600}{t('unit.h')}{sep}{s % 3600 // 60}{t('unit.m')}"
    return f"{s // 86400}{t('unit.d')}{sep}{s % 86400 // 3600}{t('unit.h')}"


def alias_of_sibling(link, parent) -> bool:
    """옆 폴더를 가리키는 바로가기인가(W&B latest-run 등). ★scan._walk가 따라가서 같은 학습이 두 번 보였다"""
    try:
        return link.resolve().parent == parent.resolve()
    except OSError:
        return False


def x_count(r) -> str:
    """진행 칸 '12/100'. step 축(x_axis=step) 학습은 '12,000/100,000'처럼 천 단위 쉼표(모든 화면이 같은 모양)"""
    total = getattr(r, "total", None)
    if getattr(r, "x_axis", "epoch") == "step":
        return f"{r.epoch:,}/{f'{total:,}' if total else '?'}"
    return f"{r.epoch}/{total or '?'}"
