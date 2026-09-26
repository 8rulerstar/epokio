"""PyTorch Lightning CSVLogger(metrics.csv)와 Keras CSVLogger 어댑터."""
from __future__ import annotations

from pathlib import Path

from .adapters_base import Adapter, Loaded, _num, _read_csv, _yaml_value, metric_column


class Lightning(Adapter):
    """PyTorch Lightning CSVLogger: lightning_logs/version_N/metrics.csv (+ hparams.yaml).
    근거(Lightning master csv_logs.py·logger_connector·result.py, 설치본 없음): 열은 정렬, step·epoch 열, 학습 step 줄·
    에폭 줄·검증 줄이 따로. on_step+on_epoch 값은 <이름>_step/_epoch로 갈린다. hparams.yaml엔 max_epochs가 보통 없다.
    ★예전엔 _step 값이 _epoch 값을 덮고("train_loss_step_loss") lr-Adam이 점수로 들어갔다."""
    name = "lightning"

    def detect(self, d, names):
        return "metrics.csv" in names and ("hparams.yaml" in names or d.name.startswith("version_"))

    def load(self, d):
        p = d / "metrics.csv"
        try:
            raw = _read_csv(p)
        except OSError:
            return None
        warns = []
        if raw and "epoch" not in raw[0]:
            warns.append("unknown format/version: metrics.csv has no epoch column")
        cols = set(raw[0]) if raw else set()
        by: dict[int, dict] = {}
        for r in raw:
            try:
                ep = int(float(r.get("epoch", "")))
            except ValueError:
                continue
            row = by.setdefault(ep, {"epoch": str(ep + 1)})       # Lightning 에폭은 0부터
            for k, v in r.items():
                if k in ("epoch", "step") or v == "" or self._skip(k, cols):
                    continue
                row[self._name(k)] = v
        rows = [by[k] for k in sorted(by)]
        total = None
        if (d / "hparams.yaml").exists():
            t = (d / "hparams.yaml").read_text(encoding="utf-8", errors="ignore")
            v = _yaml_value(t, "max_epochs") or _yaml_value(t, "epochs")
            total = int(float(v)) if v and v.replace(".", "").isdigit() else None
        return Loaded(self.name, rows, p, total, warnings=warns)

    @staticmethod
    def _skip(k: str, cols: set[str]) -> bool:
        low = k.lower()
        if low.startswith(("lr-", "lr_")) or low in ("lr", "learning_rate") or low.endswith("/lr"):
            return True                                            # 학습률은 점수가 아니다
        return k.endswith("_step") and (k[:-5] + "_epoch") in cols   # 에폭 값이 있으면 step 값은 버린다

    @staticmethod
    def _name(k: str) -> str:
        for suf in ("_epoch", "_step"):
            if k.endswith(suf):
                k = k[: -len(suf)]
        k = k.replace("/", "_")
        if "loss" in k:
            side = "val" if k.startswith(("val", "valid")) else "train"
            return f"{side}/{k if k.endswith('_loss') else k + '_loss'}"
        return metric_column(k, k.startswith(("val", "valid")))


class Keras(Adapter):
    """Keras CSVLogger. 파일 이름은 사용자가 정하므로 흔한 이름만 본다(training.log, history.csv, *keras*.csv).
    근거(keras master csv_logger.py, 설치본 없음): epoch(0부터) + 정렬된 키, sep 기본 쉼표, append 재개면 같은 에폭이 또 나온다."""
    name = "keras"
    FILES = ("training.log", "history.csv", "training.csv", "keras_log.csv")

    def _file(self, d: Path, names: set[str]) -> Path | None:
        for n in self.FILES:
            if n in names:
                return d / n
        for n in names:
            if n.endswith(".csv") and "keras" in n.lower():
                return d / n
        return None

    def detect(self, d, names):
        f = self._file(d, names)
        if not f:
            return False
        try:
            head = f.open(encoding="utf-8", errors="ignore").readline().lower()
        except OSError:
            return False
        return head.startswith("epoch") and "loss" in head

    def load(self, d):
        f = self._file(d, {p.name for p in d.iterdir()})
        if not f:
            return None
        raw = _read_csv(f)
        warns = []
        if raw and len(raw[0]) == 1:
            warns.append("unknown format/version: single column, non-comma separator (CSVLogger sep=) is not supported")
        by: dict[int, dict] = {}
        for r in raw:
            try:
                ep = int(float(r["epoch"])) + 1                    # Keras 에폭은 0부터
            except (KeyError, ValueError):
                continue
            row = {"epoch": str(ep)}
            for k, v in r.items():
                if k == "epoch" or _num(v) == "":                  # 리스트 값("[..]")·빈 값은 곡선이 못 그린다
                    continue
                if k in ("loss", "val_loss"):
                    row["val/val_loss" if k == "val_loss" else "train/train_loss"] = v
                elif k.endswith("loss"):
                    row[("val/" if k.startswith("val_") else "train/") + k] = v
                elif k in ("lr", "learning_rate"):         # Keras 2는 lr, Keras 3은 learning_rate
                    continue
                else:
                    row[metric_column(k, k.startswith("val_"))] = v
            by[ep] = row                                           # append 재개로 같은 에폭이 또 나오면 나중 것
        return Loaded(self.name, [by[k] for k in sorted(by)], f, warnings=warns)
