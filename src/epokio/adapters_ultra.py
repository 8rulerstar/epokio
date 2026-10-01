"""Ultralytics(results.csv + args.yaml, 옛 YOLOv5 이름 포함)와 epokio.log()의 epokio_log.csv 어댑터."""
from __future__ import annotations

import re

from .adapters_base import Adapter, Loaded, _csv_header, _int, _num, _read_csv, _yaml_value
from .schema import TASK2METRIC, YOLOV5_ALIASES


# Ultralytics가 results.csv에 쓰는 열 이름(8.4.150 소스 기준: utils/loss.py loss_names, utils/metrics.py keys,
# engine/trainer.py save_metrics). 여기 없는 열이 나오면 버전이 바뀐 것일 수 있어 경고를 채운다
ULTRA_TASKS = {"detect", "segment", "semantic", "depth", "classify", "pose", "obb"}
ULTRA_TASK_METRIC = TASK2METRIC               # 정본은 schema.TASK2METRIC. 이 열이 없으면 핵심 점수를 못 읽는다
ULTRA_LOSSES = {"box", "cls", "dfl", "l1", "seg", "sem", "pose", "kobj", "rle", "angle", "dlog", "dgrad",
                "ce", "dice", "aux", "obj"}     # obj: 옛 YOLOv5
_ULTRA_COL = re.compile(
    r"^(epoch|time|lr/pg\d+|(train|val)/loss"
    r"|metrics/(precision|recall|mAP50|mAP50-95)\([BMP]\)"
    r"|metrics/(accuracy_top1|accuracy_top5|mIoU|pixel_acc|delta[123]|abs_rel|rmse|silog))$")


def ultralytics_warnings(header: list[str], task: str | None) -> list[str]:
    """results.csv 머리줄(옛 YOLOv5 이름은 바꾼 뒤)과 args.yaml task로 모르는 형식인지 본다"""
    out = []
    unknown = [c for c in header if not (_ULTRA_COL.match(c) or (
        c.startswith(("train/", "val/")) and c.endswith("_loss") and c.split("/", 1)[1][:-5] in ULTRA_LOSSES))]
    if unknown:
        out.append("unknown format/version: unrecognized columns " + ", ".join(unknown))
    if not any(c.startswith("metrics/") for c in header):
        out.append("unknown format/version: no metrics/ columns")
    if task and task not in ULTRA_TASKS:
        out.append(f"unknown format/version: unknown task '{task}'")
    elif task and ULTRA_TASK_METRIC[task] not in header:
        out.append(f"unknown format/version: task '{task}' is missing {ULTRA_TASK_METRIC[task]}")
    return out


class Ultralytics(Adapter):
    """results.csv + args.yaml. 열 이름이 이미 규칙과 같다(train/box_loss, metrics/mAP50(B)). 옛 YOLOv5 이름은 바꿔 읽는다."""
    name = "ultralytics"

    def detect(self, d, names):
        # args.yaml만 있는 폴더(1에폭 전)도 울트라리틱스로 본다. 단 울트라리틱스 args.yaml에는 늘 task·mode가 있다(timm엔 둘 다 없다).
        # ★timm도 args.yaml을 남겨서, summary.csv가 있는 timm 학습을 여기서 가져간 뒤 못 읽어 목록에서 사라졌다
        if "results.csv" in names:
            return True
        if "args.yaml" not in names:
            return False
        text = (d / "args.yaml").read_text(encoding="utf-8", errors="ignore")[:20000]
        return _yaml_value(text, "task") is not None or _yaml_value(text, "mode") is not None

    def load(self, d):
        p = d / "results.csv"
        if not p.exists():
            return None
        all_rows = _read_csv(p)
        header = list(all_rows[0]) if all_rows else _csv_header(p)
        rows = [r for r in all_rows if r.get("epoch")]
        if any(k in YOLOV5_ALIASES for k in header):
            header = [YOLOV5_ALIASES.get(k, k) for k in header]
        if rows and any(k in YOLOV5_ALIASES for k in rows[0]):       # 옛 YOLOv5: 이름을 지금 규칙으로, 에폭은 0부터라 +1
            rows = [{YOLOV5_ALIASES.get(k, k): v for k, v in r.items()} for r in rows]
            if rows[0]["epoch"] == "0":
                for r in rows:
                    r["epoch"] = _num(float(r["epoch"]) + 1) if r["epoch"] else r["epoch"]
        extra = d / "epokio_log.csv"                             # epokio.log()로 더 남긴 값: 같은 에폭에 붙인다
        if extra.exists():
            more = {_num(r["epoch"]): _log_row(r) for r in _read_csv(extra) if r.get("epoch")}
            rows = [{**more.get(_num(r["epoch"]) or r["epoch"], {}), **r} for r in rows]
        a = d / "args.yaml"
        try:
            atext = a.read_text(encoding="utf-8", errors="ignore") if a.exists() else ""
        except OSError:
            atext = ""
        # epokio.start()로 기록한 직접 짠 학습은 'custom'. ★ultralytics로 보여서 "다시 학습" 등 YOLO 전용 기능이 붙었다
        custom = "task: custom" in atext.splitlines()[:1]
        task = None if custom else _yaml_value(atext, "task") if atext else None
        return Loaded("custom" if custom else self.name, rows, p, warnings=ultralytics_warnings(header, task))




class EpokioLog(Adapter):
    """epokio.log()가 남긴 epokio_log.csv(학습 코드 한 줄 기록). 손실은 train/·val/ 규칙으로, 나머지는 이름 그대로(schema가 점수를 알아본다)"""
    name = "epokio"

    def detect(self, d, names):
        return "epokio_log.csv" in names and "results.csv" not in names

    def load(self, d):
        p = d / "epokio_log.csv"
        if not p.exists():
            return None
        return Loaded(self.name, [_log_row(r) for r in _read_csv(p) if r.get("epoch")], p,
                      total=_int(_yaml_value((d / "args.yaml").read_text(encoding="utf-8", errors="ignore"), "epochs"))
                      if (d / "args.yaml").exists() else None)


def _log_row(r: dict) -> dict:
    out = {"epoch": r["epoch"]}
    for k, v in r.items():
        if k == "epoch" or v == "":
            continue
        if k.endswith("loss") and "/" not in k:
            out[("val/" if k.startswith(("val_", "val")) and k != "loss" else "train/") + (k if k.endswith("_loss") else k + "_loss" if k != "loss" else "loss")] = v
        else:
            out[k] = v
    return out

