"""PyTorch Lightning CSVLogger(metrics.csv)와 Keras CSVLogger 어댑터."""
from __future__ import annotations

import json
from pathlib import Path

import csv
import io

from .adapters_base import STEP_KEYS, Adapter, Loaded, _num, _read_csv, _yaml_value, epochs_nearby, is_val_key, metric_column


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
        args = {"resumed_from": prev} if (prev := _resumed_from(d, rows)) else {}
        return Loaded(self.name, rows, p, total, args, warnings=warns)

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
            side = "val" if k.startswith(("val", "valid")) or is_val_key(k) else "train"
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
            return _epoch_loss_header(f, strict=False)
        except OSError:
            return False

    def load(self, d):
        f = self._file(d, {p.name for p in d.iterdir()})
        if not f:
            return None
        got = self._load_file(f, offset=1)                         # Keras 에폭은 0부터
        got.total = got.total or epochs_nearby(d)          # ★옆 config.json의 epochs를 안 봐서 README와 달리 진행률이 비었다
        return got

    def _load_file(self, f: Path, offset: int):
        raw = _read_csv(f)
        warns = []
        if raw and len(raw[0]) == 1:
            warns.append("unknown format/version: single column, non-comma separator (CSVLogger sep=) is not supported")
        return Loaded(self.name, _epoch_rows(raw, offset), f, warnings=warns)


def _epoch_rows(raw: list[dict], offset: int) -> list[dict]:
    """에폭별 {열: 값} 목록을 공통 모양(train/·val/·metrics/)으로. CSV 로그와 JSON 줄 로그가 같이 쓴다"""
    by: dict[int, dict] = {}
    for r in raw:
        try:
            ep = int(float(r["epoch"])) + offset
        except (KeyError, ValueError):
            continue
        row = {"epoch": str(ep)}
        for k, v in r.items():
            if k == "epoch" or _num(v) == "":                  # 리스트 값("[..]")·빈 값은 곡선이 못 그린다
                continue
            if k in ("loss", "val_loss"):
                row["val/val_loss" if k == "val_loss" else "train/train_loss"] = v
            elif k.endswith("loss"):
                row[("val/" if is_val_key(k) else "train/") + (k if "/" not in k else k.replace("/", "_"))] = v
            elif k in ("lr", "learning_rate") or k.endswith("_lr"):   # Keras 2는 lr, Keras 3은 learning_rate, MAE는 train_lr
                continue
            elif k.lower() in _TIME_COLS:                      # 걸린 시간은 점수가 아니다
                continue
            else:
                row[metric_column(k, is_val_key(k))] = v
        by[ep] = row                                           # append 재개로 같은 에폭이 또 나오면 나중 것
    return [by[k] for k in sorted(by)]


# 검증 쪽 이름은 adapters_base.is_val_key(val·valid·eval·test가 낱말로 어디에 있든).
# ★timm은 eval_loss·eval_top1, MAE·DeiT는 test_loss·test_acc1이라 학습 손실로 잘못 분류됐고, loss/val은 학습 손실이었다
_TIME_COLS = {"sec", "secs", "seconds", "time", "elapsed", "duration", "epoch_time", "time_s"}
_OWNED = {"results.csv", "metrics.csv", "epokio_log.csv"}         # 다른 어댑터 몫. 여기서 가로채면 모양이 틀어진다
_MAX_PROBE = 8                                                     # 폴더마다 첫 줄만 보는 CSV 수(자동 탐색이 Desktop을 훑는다)


def _epoch_loss_header(f: Path, strict: bool = True) -> bool:
    """첫 열이 epoch이고 loss 열이 있는 쉼표 CSV인가. utf-8-sig: 윈도우·엑셀·pandas(encoding="utf-8-sig")가 붙이는
    BOM 때문에 startswith("epoch")가 실패해 이름이 맞아도 놓쳤다(2026-09-28 EI 학습 train_log.csv).
    strict=False(Keras 이름 파일): 쉼표가 아닌 구분자(sep=";")도 잡아서 load가 "지원 안 함" 경고를 내게 한다"""
    with f.open(encoding="utf-8-sig", errors="ignore") as fh:
        head = fh.readline()
    if not strict:
        return head.lower().startswith("epoch") and "loss" in head.lower()
    return _x_column(head, ("epoch",)) is not None


_STEP_COLS = ("step", "iter", "iteration")       # step으로 적는 직접 짠 루프. 축만 다르고 모양은 같다


def _x_column(head: str, allowed: tuple) -> str | None:
    """첫 줄의 첫 열 이름(원래 철자)이 allowed 중 하나이고 loss 열이 있으면 그 이름"""
    raw = next(csv.reader(io.StringIO(head)), [])
    cols = [c.strip().lower() for c in raw]
    ok = bool(cols) and cols[0] in allowed and any("loss" in c for c in cols[1:])
    if ok and cols[0] != "epoch" and "epoch" in cols:   # step 열 뒤에 epoch 열도 있으면 우리가 아는 모양이 아니다(가로채지 않는다)
        ok = False
    return raw[0].strip() if ok else None


def _head(f: Path) -> str:
    with f.open(encoding="utf-8-sig", errors="ignore") as fh:
        return fh.readline()


class CsvLog(Keras):
    """직접 짠 학습 루프가 남긴 에폭 CSV(train_log.csv·log.csv 등, 이름 무관). 형식은 Keras CSVLogger와 같다고 보고
    읽되 에폭은 0부터면 +1, 1부터면 그대로. 다른 어댑터가 다 못 알아본 폴더에서만 마지막으로 본다(ADAPTERS 맨 끝).
    ★코드 수정 없이 보이게: 예전엔 epokio.start()를 넣거나 파일 이름을 history.csv로 바꿔야만 잡혔다"""
    name = "custom"

    def _probe(self, f: Path) -> bool:
        try:
            return _x_column(_head(f), ("epoch",) + _STEP_COLS) is not None
        except OSError:
            return False

    def detect(self, d, names):
        return self._file(d, names) is not None

    def _file(self, d: Path, names: set[str]) -> Path | None:
        n_seen = 0
        for n in sorted(names):
            if not n.lower().endswith(".csv") or n in _OWNED:
                continue
            n_seen += 1
            if n_seen > _MAX_PROBE:
                return None
            if self._probe(d / n):
                return d / n
        return None

    def load(self, d):
        f = self._file(d, {p.name for p in d.iterdir()})
        if not f:
            return None
        try:
            xcol = _x_column(_head(f), _STEP_COLS)
        except OSError:
            return None
        if xcol:                                        # step 축: 행 모양은 그대로, "epoch" 자리에 step 번호(x_axis=step)
            raw = [{**{k: v for k, v in r.items() if k != xcol}, "epoch": r[xcol]} for r in _read_csv(f) if _num(r.get(xcol, "")) != ""]
            return Loaded(self.name, _epoch_rows(raw, 0), f, total=epochs_nearby(d, STEP_KEYS), args={"x_axis": "step"})
        try:
            eps = [int(float(r["epoch"])) for r in _read_csv(f) if _num(r.get("epoch", "")) != ""]
        except (KeyError, ValueError):
            eps = []
        got = self._load_file(f, offset=1 if eps and min(eps) == 0 else 0)
        # timm train.py 가 남기는 두 파일. utils/summary.py update_summary: epoch, train_*, eval_*, lr(원본 대조 2026-09-30)
        if f.name == "summary.csv" and (d / "args.yaml").exists():
            got.framework = "timm"
        got.total = got.total or epochs_nearby(d)          # ★README엔 '옆 설정에서 찾는다'고 써 놓고 CSV에는 빠져 있었다
        return got


class JsonLines(Adapter):
    """에폭마다 JSON 한 줄(log.txt). MAE·DeiT·DINO·BEiT·ConvNeXt 공식 코드가 이렇게 쓴다:
    {"train_lr": .., "train_loss": .., "test_loss": .., "test_acc1": .., "epoch": 0, "n_parameters": ..}
    ★이 형식을 몰라서 비전 연구 코드의 학습이 목록에 아예 안 떴다. 첫 줄이 epoch 있는 JSON일 때만 본다(흔한 이름이라)
    원본 대조(2026-09-30): facebookresearch/mae main_finetune.py 335행·main_pretrain.py 202행, deit main.py 467행의
    log_stats = {train_*, test_*, "epoch", "n_parameters"} → output_dir/log.txt 에 json.dumps 한 줄씩"""
    name = "jsonlog"
    FILE = "log.txt"
    SKIP = ("n_parameters",)

    def detect(self, d, names):
        if self.FILE not in names:
            return False
        with (d / self.FILE).open(encoding="utf-8-sig", errors="ignore") as fh:
            head = fh.readline(20000).strip()
        try:
            return head.startswith("{") and "epoch" in json.loads(head)
        except ValueError:
            return False

    def load(self, d):
        f = d / self.FILE
        raw = []
        try:
            lines = f.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
        except OSError:
            return None
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:                                     # 쓰는 중인 마지막 줄·다른 출력은 건너뛴다
                continue
            if isinstance(r, dict) and "epoch" in r:
                raw.append({k: str(v) for k, v in r.items() if k not in self.SKIP and isinstance(v, (int, float))})
        if not raw:
            return None
        eps = [int(float(r["epoch"])) for r in raw if "epoch" in r]
        return Loaded(self.name, _epoch_rows(raw, 1 if eps and min(eps) == 0 else 0), f, total=epochs_nearby(d))


def _resumed_from(d: Path, rows: list[dict]) -> str | None:
    """같은 lightning_logs 안에서 이 version_N이 앞 version_M(M<N 중 가장 큰 것)을 이어 하는가(체크포인트에서 재개하면
    에폭 번호가 그대로 이어진다). 이으면 앞 폴더 이름. 첫 에폭이 1이면 새 학습이다.
    ★재개할 때마다 새 version_N이 생겨 같은 학습이 따로 보였고, 앞 것은 멈춘 채 '멎음'·'끝남' 알림을 냈다"""
    import re
    m = re.fullmatch(r"version_(\d+)", d.name)
    if not m or not rows or int(m.group(1)) == 0:
        return None
    try:
        first = int(rows[0]["epoch"])
    except (KeyError, ValueError):
        return None
    if first <= 1:
        return None
    sib = sorted((int(x.name[8:]), x) for x in d.parent.glob("version_*")
                 if x.name[8:].isdigit() and int(x.name[8:]) < int(m.group(1)) and (x / "metrics.csv").is_file())
    if not sib:
        return None
    prev = sib[-1][1]
    try:
        eps = [int(float(r["epoch"])) for r in _read_csv(prev / "metrics.csv") if _num(r.get("epoch", "")) != ""]
    except (OSError, KeyError, ValueError):
        return None
    last = max(eps) + 1 if eps else 0                   # Lightning 에폭은 0부터, 화면은 1부터
    return prev.name if eps and first <= last + 1 else None
