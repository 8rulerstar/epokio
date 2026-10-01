"""TensorBoard tfevents 어댑터: 태그 → 열 이름 규칙과 폴더 읽기. 파일 파서는 tfevents.py.
tfevents.py가 이 모듈의 이름을 다시 내보내므로 `from epokio.tfevents import column, TensorBoard`가 그대로 된다."""
from __future__ import annotations

import math
import re
from pathlib import Path


PREFIX = "events.out.tfevents."
SIDE_DIRS = {"train": "train", "training": "train", "validation": "val", "val": "val", "valid": "val",
             "eval": "val", "test": "val"}
_TRAIN_PRE = re.compile(r"^(train|training)[/_]", re.I)
_VAL_PRE = re.compile(r"^(val|valid|validation|eval|test)[/_]", re.I)
_SKIP = re.compile(r"(^|[/_])(lr|learning_rate|lr-\w+|grad_norm|epoch|step|global_step|samples|steps_per_second"
                   r"|samples_per_second|runtime|flos|total_flos|train_runtime|hp_metric|time|num_tokens)$|lr[-_]|momentum"
                   r"|per_second|_step$",
                   re.I)
_SUFFIX = re.compile(r"/(train|training|val|valid|validation|eval|test)$", re.I)
_EPOCH_TAGS = ("epoch", "train/epoch", "epochs", "trainer/epoch")


def column(tag: str, side: str | None = None) -> str | None:
    """태그 -> 열 이름(train/*_loss, val/*_loss, metrics/*). None이면 곡선에 안 쓴다(학습률·속도 등).
    규칙(다른 어댑터와 같은 이름이 나오게):
      "train/x"·"val/x"·"eval/x"(슬래시 접두) -> 접두를 떼고 쪽을 정한다. "eval/accuracy" -> metrics/accuracy
      "val_loss"·"train_loss"(밑줄 접두) -> Keras CSV처럼 이름을 그대로 둔다. 단 HF식 eval_<지표>는 metrics/<지표>
      Keras TensorBoard 콜백의 epoch_<이름>은 train/·validation/ 폴더가 쪽을 정한다
      "Loss/train"·"Accuracy/test"(슬래시 접미)도 쪽으로 읽는다. "metrics/..."는 그대로
      train 쪽 점수는 metrics/train_<이름> (검증 점수와 안 섞이게)"""
    t = tag.strip()
    if len(t) > 6 and t.lower().endswith("_epoch") and "/" not in t[-7:]:
        t = t[:-6]                                               # Lightning 에폭 평균 train_loss_epoch → train_loss (_step은 아래에서 뺀다)
        if t.lower() in SIDE_DIRS:                               # train_epoch·val_epoch는 에폭 번호다
            return None
    if _SKIP.search(t):
        return None
    if t.lower().startswith("epoch_"):
        t = t[6:]
    if t.startswith("metrics/"):
        return t                                                 # 이미 규칙대로(Ultralytics 콜백 등)
    sm = _SUFFIX.search(t)                                       # 파이토치 튜토리얼식 "Loss/train", "Accuracy/test"
    if sm:
        side, t = ("train" if sm.group(1).lower() in ("train", "training") else "val"), t[:sm.start()]
    low = t.lower()
    m = _TRAIN_PRE.match(t) or _VAL_PRE.match(t)
    keep = ""
    if m:
        side = "train" if _TRAIN_PRE.match(t) else "val"
        if t[m.end() - 1] == "_" and not (low.startswith("eval_") and "loss" not in low):
            keep = t[:m.end()]                                   # 밑줄 접두는 이름에 남긴다
        t = t[m.end():]
    rest = keep + re.sub(r"[/\s]+", "_", t).strip("_")
    if not rest or rest == keep:
        return None
    if "loss" in rest.lower():
        return f"{side or 'train'}/{rest if rest.lower().endswith('loss') else rest + '_loss'}"
    if side == "train" and not keep:
        rest = "train_" + rest
    return f"metrics/{rest}"


def _files(d: Path, names: set[str]) -> list[tuple[Path, str | None]]:
    out = [(d / n, None) for n in sorted(names) if n.startswith(PREFIX)]
    for n in sorted(names):
        side = SIDE_DIRS.get(n.lower())
        if side and (d / n).is_dir():
            out += [(f, side) for f in sorted((d / n).iterdir()) if f.name.startswith(PREFIX)]
    return out


class TensorBoard:                      # adapters.Adapter 모양(서로 import하면 순환이라 상속 안 함)
    """events.out.tfevents.* (폴더 안, 또는 Keras식 train/·validation/ 아래). 스칼라만 읽는다.
    x축: epoch 태그가 있으면 그 에폭(올림), Keras식 epoch_* 태그는 step이 0부터 에폭, 둘 다 아니면 step(args x_axis=step)."""
    name = "tensorboard"

    def detect(self, d, names):
        if not _files(d, names):
            return False
        # HF 출력 폴더(<out>/runs/<날짜_기계>)에 trainer_state.json이 있으면 그쪽(HuggingFace)이 읽는다. 같은 학습이 두 번 보이지 않게
        out = d.parent.parent if d.parent.name == "runs" else None
        return not (out and ((out / "trainer_state.json").exists() or any(out.glob("checkpoint-*/trainer_state.json"))))

    def load(self, d):
        from . import tfevents as _tf   # 안에서 import: 어느 쪽을 먼저 불러도 순환이 안 깨지게
        from .adapters_base import STEP_KEYS, Loaded, _num, epochs_nearby
        try:
            files = _files(d, {p.name for p in d.iterdir()})
        except OSError:
            return None
        if not files:
            return None
        warns, evs, bad = [], [], 0
        for f, side in files:
            try:
                e, b = _tf.read_scalars(f)
            except OSError:
                continue
            bad += b
            evs += [(w, s, t, v, side) for w, s, t, v in e]
        if bad:
            warns.append(f"unknown format/version: {bad} unreadable tfevents records skipped")
        tags = {t for _, _, t, _, _ in evs}
        epoch_tag = next((t for t in _EPOCH_TAGS if t in tags), None)
        keras = any(t.lower().startswith("epoch_") for t in tags)
        epochs = sorted((s, v) for _, s, t, v, _ in evs if t == epoch_tag) if epoch_tag else []
        mode = "epoch" if epoch_tag or keras else "step"
        # Lightning은 epoch를 0부터 적는다. 직접 1부터 적은 기록에 +1을 하면 '20에폭 중 21에폭'이 됐다
        zero_based = bool(epochs) and min(v for _, v in epochs) == 0

        def x_of(step: int) -> int:
            if keras and not epoch_tag:
                return step + 1
            if epoch_tag:
                last = None
                for s, v in epochs:                          # step 이하에서 가장 최근의 epoch 값
                    if s > step:
                        break
                    last = v
                if last is None:
                    return 1
                if epoch_tag == "epoch" and float(last).is_integer():
                    return int(last) + 1 if zero_based else max(1, int(last))   # Lightning: 0부터 세는 '지금 도는 에폭'
                return max(1, math.ceil(last))               # HF train/epoch: 0.5·1.0 → 1
            return step

        rows: dict[int, dict] = {}
        t0 = min((w for w, *_ in evs if w > 0), default=0.0)
        for w, s, t, v, side in sorted(evs, key=lambda e: (e[1], e[0])):
            col = column(t, side)
            if col is None:
                continue
            x = x_of(s)
            row = rows.setdefault(x, {"epoch": str(x)})
            row[col] = _num(float(f"{v:.7g}"))               # float32라 7자리로(0.3이 0.30000001로 안 보이게). 같은 x면 나중 값
            if w > 0:
                row["time"] = _num(round(w - t0, 3))
        if evs and not rows:
            warns.append("unknown format/version: no usable scalar tags in tfevents")
        if not evs and not bad:
            warns.append("unknown format/version: tfevents file has no scalar values yet")
        src = max((f for f, _ in files), key=lambda f: f.stat().st_mtime)
        args = {"x_axis": mode}
        if epoch_tag:
            args["epoch_tag"] = epoch_tag
        # Lightning hparams.yaml, 또는 같은 폴더의 args·config. step 축이면 계획 step 수(에폭 수를 쓰면 진행률이 틀린다)
        total = epochs_nearby(d, STEP_KEYS) if mode == "step" else epochs_nearby(d)
        done = None                                          # HF: 소수 에폭이라 줄의 에폭(올림)과 끝낸 에폭(내림)이 다르다
        if epoch_tag == "train/epoch" and epochs:
            done = int(math.floor(max(v for _, v in epochs) + 1e-6))
        # 학습 쪽 점수(metrics/train_*)는 뒤로. ★대표 점수 고르기가 열 순서를 보고 train 정확도를 골랐다(Keras train/·validation/)
        out = [dict(sorted(rows[k].items(), key=lambda kv: kv[0].startswith("metrics/train_"))) for k in sorted(rows)]
        return Loaded(self.name, out, src, total, args, warns, epoch=done)

