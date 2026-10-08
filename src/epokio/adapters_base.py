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


def _num(v) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return ""
    if math.isnan(x):
        return "nan"
    return str(int(x)) if x.is_integer() and abs(x) < 1e15 else repr(x)


_CSV_CACHE: dict[Path, tuple[tuple, list[dict]]] = {}


def _read_csv(p: Path) -> list[dict]:
    """utf-8-sig: 엑셀 등이 붙이는 BOM을 떼야 첫 열(epoch)이 읽힌다(BOM이 붙으면 통째로 빈 학습이 됐다).
    ★학습 중에 파일 끝 줄이 반쯤 쓰인 채로 읽히면("2,0.") 0.0이 점수로 들어갔다: 방금(10초 안) 바뀐 파일이 줄바꿈으로
    안 끝났으면 마지막 줄은 쓰는 중으로 보고 버린다. 오래된 파일은 버리지 않는다(끝 줄바꿈 없이 저장하는 도구도 있다)
    ★파일이 그대로면(mtime_ns·크기·"10초 안" 여부) 다시 파싱하지 않는다. scan은 요약을 캐시해도 그 앞에서 매번 전체를
    다시 읽었고, 상세 화면은 한 번에 세 번 읽었다. 호출자가 행을 고쳐도 캐시가 안 변하게 행은 복사해서 준다"""
    import time
    st = p.stat()
    key = (st.st_mtime_ns, st.st_size, time.time() - st.st_mtime < 10)
    hit = _CSV_CACHE.get(p)
    if hit is None or hit[0] != key:
        text = p.read_text(encoding="utf-8-sig", errors="ignore")
        if text and not text.endswith(("\n", "\r")) and key[2]:
            text = text[: text.rfind("\n") + 1] if "\n" in text else ""
        # ★헤더보다 열이 많은 줄은 DictReader가 넘친 값을 None 열쇠에 리스트로 담는다. 그걸 strip하다 죽어서
        #   그 폴더의 학습이 전부 화면에서 사라졌다. 넘친 값은 버린다
        rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None}
                for r in csv.DictReader(io.StringIO(text, newline=""))]
        _CSV_CACHE[p] = hit = (key, rows)
    return [dict(r) for r in hit[1]]


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


# 낮을수록 좋은 지표. metrics/ 는 '높을수록 좋은 것만'이라는 규칙이라 손실 쪽으로 보낸다.
# ★mae·rmse를 metrics/ 로 두었더니 최고점 고르기가 가장 나쁜 에폭을 'best'로 골랐다(Keras 회귀 모델)
# ★crossentropy 같은 손실을 metrics로 받은 Keras에서 가장 나쁜 에폭을 best로 골랐다
_LOWER = re.compile(r"(^|_)(mae|mse|rmse|msle|mape|error|err|perplexity|wer|cer|loss|crossentropy|hinge|kl|"
                    r"kld|divergence|poisson|logcosh|nll)($|_)", re.IGNORECASE)


def metric_column(key: str, val_side: bool) -> str:
    return f"{'val' if val_side else 'train'}/{key}_loss" if _LOWER.search(key) else f"metrics/{key}"


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

