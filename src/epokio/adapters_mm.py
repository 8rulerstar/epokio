"""OpenMMLab(mmengine 기반: MMDetection 3.x, MMPretrain, MMSegmentation 등)의 기록.

폴더: work_dirs/<설정>/<시각>/vis_data/scalars.json  ← 이 <시각> 폴더를 학습 하나로 본다.
한 줄 = JSON 하나. mmengine LoggerHook + LocalVisBackend가 쓴다(근거: mmengine/visualization/vis_backend.py,
mmengine/hooks/logger_hook.py):
  학습 줄: {"lr": .., "loss": .., "loss_cls": .., "time": .., "epoch": 3, "iter": 150, "memory": .., "step": 150}
  검증 줄: {"coco/bbox_mAP": .., "coco/bbox_mAP_50": .., "data_time": .., "time": .., "step": 3}
검증 줄에는 epoch가 없고, 에폭 단위 학습이면 step이 곧 에폭이다. 학습 줄은 에폭마다 여러 줄이라 마지막 값을 쓴다.
반복 단위 학습(IterBasedTrainLoop, epoch 없음)은 에폭으로 셀 수 없어 읽지 않는다.
계획 에폭: 같은 폴더의 설정 사본(<설정>.py)에서 max_epochs.
원본 대조(2026-09-30, mmengine main): logger_hook.py 199행 학습 step=runner.iter+1, 266행 검증 step=epoch(에폭 단위),
273행 검증 step=iter(반복 단위). vis_backend.py 277행 {태그..., "step": step} 을 scalars.json 에 한 줄씩.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .adapters_base import Adapter, Loaded, metric_column

_SKIP = {"lr", "base_lr", "time", "data_time", "memory", "iter", "step", "epoch", "grad_norm"}
_MAX_EPOCHS = re.compile(r"max_epochs\s*=\s*(\d+)")


class MMEngine(Adapter):
    name = "openmmlab"

    def detect(self, d, names):
        return "vis_data" in names and (d / "vis_data" / "scalars.json").is_file()

    def load(self, d):
        f = d / "vis_data" / "scalars.json"
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return None
        by: dict[int, dict] = {}
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:                                     # 쓰는 중인 마지막 줄
                continue
            if not isinstance(r, dict):
                continue
            if "iter" in r and "epoch" not in r:                  # 반복 단위 학습: step이 에폭이 아니다
                return None
            train = "epoch" in r
            ep = r.get("epoch") if train else r.get("step")
            if not isinstance(ep, (int, float)):
                continue
            row = by.setdefault(int(ep), {"epoch": str(int(ep))})
            for k, v in r.items():
                if k in _SKIP or not isinstance(v, (int, float)) or isinstance(v, bool):
                    continue
                key = k.replace("/", "_")
                if key.startswith("loss_"):                           # loss_cls → cls_loss(YOLO와 같은 모양, 손실 열은 _loss로 끝난다)
                    key = key[5:] + "_loss"
                if "loss" in key:
                    side = "train" if train else "val"
                    row[f"{side}/{key if key.endswith('loss') else key + '_loss'}"] = str(v)
                elif train:
                    row[metric_column(key, False)] = str(v)                # 학습 줄의 loss 아닌 값(드묾)
                else:
                    row[f"metrics/{key}"] = str(v)                          # coco/bbox_mAP → metrics/coco_bbox_mAP
        rows = [by[k] for k in sorted(by)]
        if not any(k.startswith("train/") for r in rows for k in r):
            return None
        return Loaded(self.name, rows, f, total=_total(d))


def _total(d: Path) -> int | None:
    # 설정 사본: <시각>/vis_data/config.py(mmengine이 늘 쓴다), 없으면 한 단계 위 work_dir/<설정>.py
    for p in [*sorted((d / "vis_data").glob("*.py")), *sorted(d.parent.glob("*.py"))]:
        m = _MAX_EPOCHS.search(p.read_text(encoding="utf-8", errors="ignore"))
        if m:
            return int(m.group(1))
    return None
