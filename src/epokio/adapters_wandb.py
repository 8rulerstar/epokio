"""W&B(Weights & Biases) 로컬 기록: wandb/run-<시각>-<id>/run-<id>.wandb (온라인·오프라인 둘 다 남는다).

wandb 없이, 표준 라이브러리로 읽는다. 형식(wandb 0.30.0으로 만든 실제 파일과 그 판의 proto 정의로 확인):
  파일 머리말 7바이트  b":W&B" + 식별값 0xBEE1(작은 끝) + 판 번호 0
  그 뒤 LevelDB 로그 형식: 32KiB 블록, 레코드마다 [crc32 4][길이 2][종류 1] + 내용. 종류 1=통째 2=처음 3=가운데 4=끝.
  내용은 protobuf Record: history=2(HistoryRecord: item=1[key=1, nested_key=2, value_json=16]),
  config=5(ConfigRecord: update=1[같은 모양]), run=17(RunRecord: config=4), exit=18.
W&B는 에폭이 아니라 step으로 적는다. 사용자가 "epoch"도 같이 적은 학습만 에폭으로 모아 읽는다(에폭 줄이 나올 때,
그 사이에 적힌 값들의 마지막 것을 그 에폭 몫으로). epoch를 안 적은 학습은 step 축으로 읽는다(args x_axis=step,
행의 "epoch" 자리에 step 번호). ★예전엔 이런 학습(LLM 미세조정 대부분)이 목록에서 통째로 빠졌다.
"""
from __future__ import annotations

import json
from pathlib import Path

from .adapters_base import STEP_KEYS, Adapter, Loaded
from .adapters_csvlog import _epoch_rows

_BLOCK, _HDR = 32768, 7
_MAX_BYTES = 300_000_000              # 사진·표를 잔뜩 올린 학습의 큰 파일은 읽지 않는다(15초마다 다시 읽는다)
_EPOCHS = ("epochs", "max_epochs", "num_epochs", "num_train_epochs", "n_epochs")
_MAX_POINTS = 2000                    # step 축 학습의 점 수 상한(마지막 점은 늘 남긴다). 곡선과 /runs가 가볍게


def _varint(b: bytes, i: int) -> tuple[int, int]:
    n = shift = 0
    while True:
        c = b[i]
        i += 1
        n |= (c & 0x7F) << shift
        if c < 0x80:
            return n, i
        shift += 7


def _fields(b: bytes):
    """protobuf 한 겹: (필드 번호, 값). 길이 붙은 값은 bytes, 나머지는 int. 32·64비트 고정값은 건너뛴다"""
    i = 0
    while i < len(b):
        key, i = _varint(b, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
            yield num, v
        elif wt == 2:
            n, i = _varint(b, i)
            yield num, b[i:i + n]
            i += n
        elif wt == 1:
            i += 8
        elif wt == 5:
            i += 4
        else:                         # 모르는 형식: 이 레코드는 더 읽지 않는다
            return


def _items(b: bytes) -> dict:
    """HistoryRecord·ConfigRecord의 항목들 → {열쇠: 값}. nested_key는 '/'로 잇는다"""
    out = {}
    for num, v in _fields(b):
        if num != 1 or not isinstance(v, bytes):
            continue
        key, nested, raw = "", [], None
        for n2, v2 in _fields(v):
            if n2 == 1:
                key = v2.decode("utf-8", "replace")
            elif n2 == 2:
                nested.append(v2.decode("utf-8", "replace"))
            elif n2 == 16:
                raw = v2
        name = "/".join(nested) if nested else key
        try:
            out[name] = json.loads(raw) if raw is not None else None
        except ValueError:
            continue
    return out


def records(path: Path):
    """.wandb 파일의 Record 내용(bytes)을 차례로. 쓰는 중인 끝은 조용히 멈춘다"""
    data = path.read_bytes()
    if not data.startswith(b":W&B"):
        return
    i, buf = _HDR, b""
    while i + _HDR <= len(data):
        left = _BLOCK - i % _BLOCK
        if left < _HDR:                                            # 블록 끝의 남는 자리(0으로 채워져 있다)
            i += left
            continue
        n = int.from_bytes(data[i + 4:i + 6], "little")
        kind = data[i + 6]
        body = data[i + _HDR:i + _HDR + n]
        if len(body) < n or kind not in (1, 2, 3, 4):
            return
        i += _HDR + n
        if kind == 1:
            yield body
        elif kind == 2:
            buf = body
        elif kind == 3:
            buf += body
        else:
            yield buf + body
            buf = b""


class WandB(Adapter):
    name = "wandb"

    def _file(self, d: Path, names: set[str]) -> Path | None:
        return next((d / n for n in sorted(names) if n.startswith("run-") and n.endswith(".wandb")), None)

    def detect(self, d, names):
        return self._file(d, names) is not None

    def load(self, d):
        f = self._file(d, {p.name for p in d.iterdir()})
        try:
            if not f or f.stat().st_size > _MAX_BYTES:
                return None
            recs = list(records(f))
        except OSError:
            return None
        config: dict = {}
        raw: list[dict] = []
        pending: dict = {}
        steps: dict[int, dict] = {}                                # epoch를 안 적은 학습용: step → 그 step의 값들
        for r in recs:
            for num, v in _fields(r):
                if num == 5 and isinstance(v, bytes):
                    config.update(_items(v))
                elif num == 17 and isinstance(v, bytes):
                    for n2, v2 in _fields(v):
                        if n2 == 4 and isinstance(v2, bytes):
                            config.update(_items(v2))
                elif num == 2 and isinstance(v, bytes):
                    items = _items(v)
                    h = {k.replace("/", "_"): x for k, x in items.items()
                         if not k.startswith("_") and isinstance(x, (int, float)) and not isinstance(x, bool)}
                    if isinstance(items.get("_step"), int) and h:
                        steps.setdefault(items["_step"], {}).update(h)
                    pending.update(h)
                    if "epoch" in h:                                # 에폭 줄: 그 사이 값들의 마지막 것을 이 에폭 몫으로
                        raw.append({k: str(x) for k, x in pending.items()})
                        pending = {}
        cfg = {k: (v.get("value") if isinstance(v, dict) and "value" in v else v) for k, v in config.items()}
        args = {k: str(v) for k, v in cfg.items() if isinstance(v, (int, float, str, bool)) and not k.startswith("_")}
        if raw:
            eps = [int(float(r["epoch"])) for r in raw]
            rows = _epoch_rows(raw, 1 if min(eps) == 0 else 0)
            keys = _EPOCHS
        elif steps:
            rows = _epoch_rows([{**{k: str(x) for k, x in steps[s].items()}, "epoch": str(s)} for s in _thin(sorted(steps))], 0)
            args["x_axis"] = "step"
            keys = STEP_KEYS
        else:
            return None
        total = next((int(cfg[k]) for k in keys if isinstance(cfg.get(k), (int, float)) and cfg[k] > 0), None)
        return Loaded(self.name, rows, f, total=total, args=args)


def _thin(xs: list[int], cap: int = _MAX_POINTS) -> list[int]:
    """고르게 cap개 이하로 줄인다. 마지막 점(지금 step)은 늘 남긴다"""
    if len(xs) <= cap:
        return xs
    stride = len(xs) / (cap - 1)
    return sorted({xs[int(i * stride)] for i in range(cap - 1)} | {xs[-1]})
