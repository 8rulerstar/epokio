"""어댑터 공통 부품: 한 모양(Loaded), 값 문자열화, CSV·yaml 읽기, 열 이름 규칙(metric_column).
adapters.py가 여기 것을 다시 내보낸다(from .adapters import Loaded 등은 그대로 된다)."""
from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Loaded:
    framework: str
    rows: list[dict]
    source: Path                  # 갱신 시각을 잴 파일
    total: int | None = None      # 계획 에폭
    args: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)   # 형식을 못 알아본 곳(조용히 틀리지 않게). 비면 문제 없음
    epoch: int | None = None      # 끝낸 에폭 수를 따로 아는 프레임워크(HF: 줄의 에폭은 평가 시점이라 다를 수 있다)
    fraction: float | None = None  # 끝낸 몫 0~1을 에폭보다 잘게 아는 프레임워크(HF: global_step/max_steps)


def _num(v) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return ""
    if math.isnan(x):
        return "nan"
    return str(int(x)) if x.is_integer() and abs(x) < 1e15 else repr(x)


@dataclass
class _CsvHit:
    key: tuple                    # (mtime_ns, 크기, 10초 안에 바뀜)
    used: int                     # 파싱한 바이트 수(쓰는 중인 끝 줄을 버린 뒤)
    digest: bytes                 # 그 바이트들의 해시
    fields: list | None           # 머리줄
    quotes: bool                  # 따옴표가 있었나(줄을 넘는 칸이 있을 수 있어 덧붙여 읽기를 안 한다)
    rows: list[dict]


_CSV_CACHE: dict[Path, _CsvHit] = {}
_CSV_KEEP = 96                    # 기억하는 파일 수. ★학습 1,000개면 모든 행을 들고 있어 agent가 270MB였다


def _dict_rows(fields, rows) -> list[dict]:
    """csv.DictReader와 같은 규칙: 빈 줄은 건너뛰고, 모자란 칸은 "", 넘친 값은 버린다(None 열쇠).
    ★헤더보다 열이 많은 줄은 DictReader가 넘친 값을 None 열쇠에 리스트로 담는다. 그걸 strip하다 죽어서
    그 폴더의 학습이 전부 화면에서 사라졌다"""
    out = []
    for r in rows:
        if r:
            out.append({(k or "").strip(): (r[i] if i < len(r) else "").strip() for i, k in enumerate(fields) if k is not None})
    return out


def _read_csv(p: Path) -> list[dict]:
    """utf-8-sig: 엑셀 등이 붙이는 BOM을 떼야 첫 열(epoch)이 읽힌다(BOM이 붙으면 통째로 빈 학습이 됐다).
    ★학습 중에 파일 끝 줄이 반쯤 쓰인 채로 읽히면("2,0.") 0.0이 점수로 들어갔다: 방금(10초 안) 바뀐 파일이 줄바꿈으로
    안 끝났으면 마지막 줄은 쓰는 중으로 보고 버린다. 오래된 파일은 버리지 않는다(끝 줄바꿈 없이 저장하는 도구도 있다)
    ★파일이 그대로면(mtime_ns·크기·"10초 안" 여부) 다시 파싱하지 않는다. 호출자가 행을 고쳐도 캐시가 안 변하게 행은 복사해서 준다
    ★2초 안에 바뀐 파일은 시각·크기를 믿지 않는다(윈도우 시계 단위로 같은 크기 다시 쓰기를 놓쳤다). 그때는 내용의 해시로 본다.
      예전엔 그때마다 통째로 다시 파싱해, 2만 줄 학습이 도는 동안 /run 한 번에 아홉 번(1.6초) 읽고 agent가 쉬어도 CPU 9%였다.
      앞부분이 그대로이고 뒤에 줄만 붙었으면(학습 중의 보통 모양) 붙은 줄만 읽는다"""
    import hashlib
    import time
    st = p.stat()
    recent = time.time() - st.st_mtime
    key = (st.st_mtime_ns, st.st_size, recent < 10)
    hit = _CSV_CACHE.get(p)
    if hit is not None and hit.key == key and recent >= 2.0:
        _CSV_CACHE[p] = _CSV_CACHE.pop(p)               # 최근에 쓴 것으로
        return [dict(r) for r in hit.rows]
    raw = p.read_bytes()
    if raw and not raw.endswith((b"\n", b"\r")) and key[2]:
        raw = raw[: raw.rfind(b"\n") + 1]               # 바이트로 잘라도 같다(\n은 UTF-8 여러 바이트 글자 안에 안 나온다)
    view = memoryview(raw)
    quotes = b'"' in raw
    # 덧붙여 읽기는 지난번 끝이 줄바꿈이었을 때만(끝 줄을 이어 쓴 것을 새 줄로 읽지 않게)
    if (hit is not None and hit.fields and not quotes and not hit.quotes and len(raw) >= hit.used > 0
            and raw[hit.used - 1:hit.used] in (b"\n", b"\r")
            and hashlib.blake2b(view[: hit.used], digest_size=16).digest() == hit.digest):
        tail = raw[hit.used:].decode("utf-8", errors="ignore")
        rows = hit.rows + _dict_rows(hit.fields, csv.reader(io.StringIO(tail, newline=""))) if tail else hit.rows
        fields = hit.fields
    else:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig", errors="ignore"), newline=""))
        fields = next((r for r in reader if r), None)
        rows = _dict_rows(fields, reader) if fields else []
    _CSV_CACHE.pop(p, None)
    _CSV_CACHE[p] = hit = _CsvHit(key, len(raw), hashlib.blake2b(view, digest_size=16).digest(), fields, quotes, rows)
    while len(_CSV_CACHE) > _CSV_KEEP:                  # 가장 오래 안 쓴 것부터(dict는 넣은 순서)
        _CSV_CACHE.pop(next(iter(_CSV_CACHE)))
    return [dict(r) for r in rows]


def _yaml_value(text: str, key: str) -> str | None:
    """한 줄짜리 'key: value'만 읽는다(yaml 의존성 없이)"""
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*([^#\n]+)", text, re.M)
    return m.group(1).strip() if m else None


class Adapter:
    name = ""

    def detect(self, d: Path, names: set[str]) -> bool:
        raise NotImplementedError

    def load(self, d: Path) -> Loaded | None:
        raise NotImplementedError



def _int(v):
    try:
        return int(float(v)) if v is not None else None
    except ValueError:
        return None


def _csv_header(p: Path) -> list[str]:
    """행이 없는(머리줄만 있는) results.csv의 열 이름"""
    try:
        line = p.read_text(encoding="utf-8-sig", errors="ignore").splitlines()[:1]
    except OSError:
        return []
    return [c.strip() for c in next(csv.reader(line), [])] if line else []


# 손실류는 train/·val/…_loss 열로 보낸다(점수가 아니다).
# ★crossentropy 같은 손실을 metrics로 받은 Keras에서 가장 나쁜 에폭을 best로 골랐다
# 오차 지표(mae·mse·rmse·msle·mape·error·err·wer·cer·perplexity)는 '낮을수록 좋은 점수'로 metrics/에 둔다.
# HF eval_rmse와 같은 길이고 방향은 schema.higher_is_better(LOWER_IS_BETTER)가 정한다.
# ★처음엔 metrics/에 두고 높을수록 좋다고 봐서 가장 나쁜 에폭이 best였고, 그 뒤엔 손실 쪽으로 보내서
#   Keras·CSV 회귀 학습(val_mae)은 최고 점수가 "–"였다
# 낱말 경계는 _ / - . 공백. ★loss/train·loss/val·val-loss처럼 _가 아닌 구분자면 점수(metrics/, 높을수록 좋음)로 가서
#   가장 나쁜 에폭(1.2 @ 1)이 best였다
_SEP = r"[_/\-. ]"
_LOWER = re.compile(rf"(^|{_SEP})(loss|losses|crossentropy|hinge|kl|kld|divergence|poisson|logcosh|nll)($|{_SEP})", re.IGNORECASE)
_VAL_WORD = re.compile(rf"(^|{_SEP})(val|valid|validation|eval|test)($|{_SEP})", re.IGNORECASE)


def is_val_key(key: str) -> bool:
    """검증 쪽 열인가(val_loss·loss/val·val-loss·eval_acc·test_acc1)"""
    return bool(_VAL_WORD.search(key))


def loss_name(key: str) -> str:
    """열 이름 안의 구분자를 _로(열 이름의 /는 'train/·val/' 앞머리만 쓴다). loss/val → loss_val_loss"""
    k = re.sub(r"[/\-. ]+", "_", key).strip("_")
    return k if k.endswith("_loss") else k + "_loss"


def metric_column(key: str, val_side: bool) -> str:
    return f"{'val' if val_side else 'train'}/{loss_name(key)}" if _LOWER.search(key) else f"metrics/{key}"


_EPOCH_KEYS = ("epochs", "max_epochs", "num_epochs", "num_train_epochs", "n_epochs")
# step으로 적는 학습(x_axis=step)의 계획 step 수. 에폭 수를 step 학습의 총량으로 쓰면 진행률이 거짓말을 한다
STEP_KEYS = ("total_steps", "max_steps", "num_training_steps", "max_iters", "max_iter", "iterations", "num_steps")
_CONFIG_FILES = ("args.yaml", "args.json", "config.yaml", "config.json", "hparams.yaml", "opt.yaml")


def epochs_nearby(d: Path, keys: tuple = _EPOCH_KEYS) -> int | None:
    """같은 폴더의 설정 파일에서 계획 에폭. 없으면 None(진행률·남은 시간을 못 낸다).
    ★MAE·DeiT log.txt, Lightning TensorBoard 기록은 에폭 수를 스스로 남기지 않아 진행률이 늘 비었다.
    keys=STEP_KEYS면 step 학습의 계획 step 수"""
    import json
    for n in _CONFIG_FILES:
        f = d / n
        try:
            if not f.is_file() or f.stat().st_size > 2_000_000:
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if n.endswith(".json"):
            try:
                obj = json.loads(text)
            except ValueError:
                continue
            vals = [obj.get(k) for k in keys] if isinstance(obj, dict) else []
        else:
            vals = [_yaml_value(text, k) for k in keys]
        for v in vals:
            try:
                if v is not None and float(v) > 0:
                    return int(float(v))
            except (TypeError, ValueError):
                continue
    return None

