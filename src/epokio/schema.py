"""기록 열 이름에 대한 지식을 한 곳에 모은다.

★프레임워크 형식이 바뀌면 여기와 adapters.py만 고친다. 앱·웹·터미널·트레이는 agent가 보내는
`column_info`(이름·종류·방향)를 그대로 쓰고, 열 이름을 직접 해석하지 않는다.

열 이름 규칙(어댑터가 맞춰 준다):
    손실  train/<이름>_loss · val/<이름>_loss      점수  metrics/<이름>      학습률  lr/<이름>
근거: Ultralytics 8.4 `utils/metrics.py`의 keys, `engine/trainer.py`의 save_metrics(epoch,time,손실,점수,검증손실,lr)
"""
from __future__ import annotations

import re

# Ultralytics 머리(head) 접미사. OBB도 (B)를 쓴다
HEADS = {"B": "Box", "P": "Pose", "M": "Mask"}          # 순서 = 대표 머리 우선순위

# Ultralytics 공식 대표 점수(8.4.150 cfg/__init__.py TASK2METRIC). best.pt 저장 기준(fitness)과 같은 열
TASK2METRIC = {
    "detect": "metrics/mAP50-95(B)", "segment": "metrics/mAP50-95(M)", "semantic": "metrics/mIoU",
    "depth": "metrics/delta1", "classify": "metrics/accuracy_top1", "pose": "metrics/mAP50-95(P)",
    "obb": "metrics/mAP50-95(B)",
}

# 대표 점수 고르는 순서. 없으면 pick_metric의 규칙으로.
# task를 모를 때 열로 추정한다: 마스크(M)가 있으면 segment, 키포인트(P)가 있으면 pose라 (B)보다 먼저.
# (M)·(P)가 없는 옛 파일은 기존처럼 (B)
METRIC_PREFERENCE = (
    "metrics/mAP50-95(M)", "metrics/mAP50-95(P)",
    "metrics/mAP50-95(B)", "metrics/mAP50-95",
    "metrics/mAP50(B)", "metrics/mAP50",
    "metrics/accuracy_top1",
    "metrics/mIoU",                                  # 8.4 semantic segmentation
    "metrics/delta1",                                # 8.4 depth
)

# 낮을수록 좋은 점수. ★"metrics/*는 높을수록 좋다"는 가정이 깊이 추정(8.4)에서 깨진다
LOWER_IS_BETTER = re.compile(r"(rmse|mae|mse|abs_rel|sq_rel|silog|wer|cer|perplexity|error)", re.I)

# 옛 YOLOv5 results.csv → 지금 규칙. (v5는 에폭이 0부터, 머리 접미사가 없다)
YOLOV5_ALIASES = {
    "metrics/precision": "metrics/precision(B)",
    "metrics/recall": "metrics/recall(B)",
    "metrics/mAP_0.5": "metrics/mAP50(B)",
    "metrics/mAP_0.5:0.95": "metrics/mAP50-95(B)",
    "x/lr0": "lr/pg0", "x/lr1": "lr/pg1", "x/lr2": "lr/pg2",
}

# Ultralytics가 남기는 그림 (분석 화면에서 이름으로 찾는다)
IMAGE_FILES = {
    "results": "results.png",
    "confusion": "confusion_matrix_normalized.png",
    "box_pr": "BoxPR_curve.png", "box_f1": "BoxF1_curve.png",
    "pose_pr": "PosePR_curve.png", "pose_f1": "PoseF1_curve.png",
    "mask_pr": "MaskPR_curve.png", "mask_f1": "MaskF1_curve.png",
    "pr": "PR_curve.png", "f1": "F1_curve.png",
    "val_pred": "val_batch0_pred.jpg", "val_labels": "val_batch0_labels.jpg",
}

_HEAD_RE = re.compile(r"\(([A-Z])\)$")


def head_col(kind: str, head: str) -> str:
    """head_col("mAP50-95", "B") → "metrics/mAP50-95(B)" """
    return f"metrics/{kind}({head})"


# 접두사 없는 점수 이름(직접 짠 학습 스크립트의 CSV: val_acc, val_macro_f1, test_auc …)
# ★"metrics/"로 시작하는 것만 점수로 쳐서, 이런 학습은 점수 탭이 비고 최고 점수가 "–"였다(2026-09-22)
SCORE_WORDS = re.compile(r"(^|[_/.-])(acc|accuracy|f1|macro_f1|micro_f1|recall|precision|auc|auroc|map|map50|iou|miou|dice|top1|top5|r2|bleu|rouge)"
                         r"($|[_/.-])", re.I)


def kind(key: str) -> str:
    if key.endswith("_loss") or key.endswith("/loss") or key in ("loss", "val_loss", "train_loss"):
        return "loss"
    if key.startswith("metrics/"):
        return "score"
    if key.startswith("lr/") or key in ("lr", "learning_rate"):
        return "lr"
    if SCORE_WORDS.search(key) or (LOWER_IS_BETTER.search(key) and key != "epoch"):
        return "score"
    return "other"


def higher_is_better(key: str) -> bool:
    k = kind(key)
    if k == "loss":
        return False
    return not LOWER_IS_BETTER.search(key.split("/", 1)[-1])


def info(key: str) -> dict:
    """열 하나의 설명. name은 영어 기본 이름, head는 번역할 수 있게 따로 보낸다."""
    k = kind(key)
    m = _HEAD_RE.search(key)
    head = HEADS.get(m.group(1)) if m else None
    base = _HEAD_RE.sub("", key)
    side = base.split("/", 1)[0] if k == "loss" else None
    name = base.split("/", 1)[-1]
    if k == "loss":
        name = name.removesuffix("_loss") or "loss"
    return {"kind": k, "name": name, "head": head, "side": side, "higher": higher_is_better(key)}


def pretty(key: str) -> str:
    """"metrics/mAP50-95(B)" → "mAP50-95 · Box", "val/box_loss" → "val box" """
    i = info(key)
    s = f"{i['side']} {i['name']}" if i["side"] else i["name"]
    return f"{s} · {i['head']}" if i["head"] else s


def column_info(keys) -> dict[str, dict]:
    return {k: info(k) for k in keys}


def pick_metric(fieldnames, task: str | None = None) -> str | None:
    """대표 점수 열. task(args.yaml)를 알면 공식 TASK2METRIC 열을 먼저, 없으면 열 이름으로 추정"""
    names = list(fieldnames)
    if TASK2METRIC.get(task or "") in names:
        return TASK2METRIC[task]
    for want in METRIC_PREFERENCE:
        if want in names:
            return want
    ms = [f for f in names if f.startswith("metrics/")] or [f for f in names if kind(f) == "score"]   # 접두사 없는 점수도
    val = [f for f in ms if "val" in f or "eval" in f]
    for pref in ("map", "f1", "acc", "iou", "dice"):         # 흔한 "대표 점수" 먼저
        for f in val + ms:
            if pref in f.lower():
                return f
    return (val or ms or [None])[0]

