"""TensorBoard tfevents 읽기 (표준 라이브러리만, tensorboard·protobuf 없이).

Lightning의 기본 기록기, Hugging Face Trainer, torch SummaryWriter, Keras TensorBoard 콜백이 이 파일을 쓴다.
파일 형식(TFRecord): 레코드마다 [길이 uint64 LE][길이의 masked crc32c uint32][데이터][데이터의 masked crc32c].
데이터는 protobuf Event. 필요한 필드만 직접 푼다(tensorflow/core/util/event.proto, framework/summary.proto·tensor.proto):
    Event    1 wall_time(double) 2 step(int64) 5 summary(Summary)
    Summary  1 value(repeated Value)
    Value    1 tag(string) 2 simple_value(float) 8 tensor(TensorProto)   (이미지·히스토그램 등은 건너뛴다)
    Tensor   1 dtype 2 tensor_shape 4 tensor_content 5 float_val 6 double_val 7 int_val 10 int64_val 13 half_val
tensor는 스칼라(차원 없음)일 때만 값으로 본다(torch SummaryWriter·TF2 tf.summary.scalar가 이렇게 쓴다).

읽는 길이 둘이다.
  read_scalars(p): (wall, step, tag, value) 전부와 깨진 레코드 수. 파일별 오프셋을 기억해 커진 끝부분만 더 읽는다.
  read(p): {step: {tag: 값}}, {step: 시각}. 쓰는 것만 담아 메모리가 작다(검증 걸음 + 줄인 학습 걸음).
둘 다 쓰는 중인 반쪽 레코드는 다음에 읽고, 한 시간 안 읽은 파일은 잊는다.
태그 → 열 규칙과 어댑터(TensorBoard)는 tfevents_adapter.py(여기서 다시 내보낸다).
"""
from __future__ import annotations

import struct
import time
from pathlib import Path

MAX_RECORD = 64 * 1024 * 1024          # 이보다 긴 레코드 길이는 말이 안 된다: 깨진 파일
BIG_RECORD = 1024 * 1024               # 그림·히스토그램 같은 큰 기록은 풀지 않고 건너뛴다


# ---------- crc32c (Castagnoli) ----------
_T = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0x82F63B78 if _c & 1 else _c >> 1
    _T.append(_c)


def crc32c(data: bytes) -> int:
    c = 0xFFFFFFFF
    for b in data:
        c = _T[(c ^ b) & 0xFF] ^ (c >> 8)
    return c ^ 0xFFFFFFFF


def masked_crc(data: bytes) -> int:
    c = crc32c(data)
    return (((c >> 15) | (c << 17)) + 0xA282EAD8) & 0xFFFFFFFF


# ---------- protobuf wire ----------
def _varint(b: bytes, i: int) -> tuple[int, int]:
    """최대 10바이트(64비트). ★길이 제한이 없어, 0xFF로 채운 깨진 파일에서 큰 정수를 계속 키워
    수 KB에 몇 초, 수백 KB에 몇 분이 걸려 감시 스레드(알림·웹후크까지)가 멈췄다"""
    x = s = 0
    while True:
        c = b[i]
        i += 1
        x |= (c & 0x7F) << s
        if c < 0x80:
            return x, i
        s += 7
        if s >= 70:
            raise ValueError("varint too long")


def fields(b: bytes):
    """(번호, wire 형식, 값) 차례로. 값: varint는 int, 64/32비트는 bytes(8/4), 길이 구분은 bytes"""
    i, n = 0, len(b)
    while i < n:
        key, i = _varint(b, i)
        no, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 1:
            v, i = b[i:i + 8], i + 8
        elif wt == 2:
            ln, i = _varint(b, i)
            v, i = b[i:i + ln], i + ln
        elif wt == 5:
            v, i = b[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported wire type {wt}")
        yield no, wt, v


_fields = fields


def _signed(x: int) -> int:
    return x - (1 << 64) if x >= 1 << 63 else x


def _packed_varints(v: bytes) -> list[int]:
    out, j = [], 0
    while j < len(v):
        x, j = _varint(v, j)
        out.append(x)
    return out


def _tensor_scalar(b: bytes) -> float | None:
    """모양이 없는(0차원) 숫자 하나만. ★모양을 안 봐서 PR 곡선(6×127) 같은 텐서의 첫 값이 '점수'로 뽑혔다"""
    dtype, content, vals, hv = 1, b"", [], []
    for no, wt, v in fields(b):
        if no == 1 and wt == 0:
            dtype = v
        elif no == 2 and wt == 2:                           # tensor_shape: 차원이 하나라도 있으면 숫자 하나가 아니다
            if any(sno == 2 for sno, _, _ in fields(v)):
                return None
        elif no == 4 and wt == 2:
            content = v
        elif no == 5:                                       # float_val (packed 또는 하나)
            vals += struct.unpack("<%df" % (len(v) // 4), v) if wt == 2 else [struct.unpack("<f", v)[0]]
        elif no == 6:                                       # double_val
            vals += struct.unpack("<%dd" % (len(v) // 8), v) if wt == 2 else [struct.unpack("<d", v)[0]]
        elif no in (7, 10):                                 # int_val / int64_val
            vals += [_signed(x) for x in _packed_varints(v)] if wt == 2 else [_signed(v)] if wt == 0 else []
        elif no == 13:                                      # half_val (float16을 int로 담는다)
            hv += _packed_varints(v) if wt == 2 else [v] if wt == 0 else []
    if vals:
        return float(vals[0]) if len(vals) == 1 else None
    if len(hv) == 1:
        return float(struct.unpack("<e", struct.pack("<H", hv[0] & 0xFFFF))[0])
    if content:
        fmt = {1: "<f", 2: "<d", 3: "<i", 9: "<q", 19: "<e"}.get(dtype)
        if fmt and len(content) == struct.calcsize(fmt):
            return float(struct.unpack(fmt, content)[0])
    return None


def _event(b: bytes) -> tuple[float | None, int, list[tuple[str, float]]]:
    """(wall_time 또는 None, step, [(tag, 값)])"""
    wall, step, out = None, 0, []
    for no, wt, v in fields(b):
        if no == 1 and wt == 1:
            wall = struct.unpack("<d", v)[0]
        elif no == 2 and wt == 0:
            step = _signed(v)
        elif no == 5 and wt == 2:
            for sno, swt, sv in fields(v):
                if sno != 1 or swt != 2:
                    continue
                tag, val = "", None
                for vno, vwt, vv in fields(sv):
                    if vno == 1 and vwt == 2:
                        tag = vv.decode("utf-8", "replace")
                    elif vno == 2 and vwt == 5:
                        val = struct.unpack("<f", vv)[0]
                    elif vno == 8 and vwt == 2 and val is None:
                        val = _tensor_scalar(vv)
                if tag and val is not None:
                    out.append((tag, val))
    return wall, step, out


def parse_event(b: bytes) -> tuple[float, int, list[tuple[str, float]]]:
    wall, step, out = _event(b)
    return (0.0 if wall is None else wall), step, out


# ---------- 레코드 훑기 (두 읽기 길이 같이 쓴다) ----------
def _records(p: Path, off: int, size: int, check_crc: bool):
    """(다음 오프셋, 데이터 또는 None=건너뜀, 깨짐 여부). 반쪽 레코드·말이 안 되는 길이에서 멈춘다.
    ★통째로 메모리에 올리지 않고 레코드마다 읽는다(큰 기록은 seek로 건너뛴다)"""
    with p.open("rb") as f:
        f.seek(off)
        while True:
            head = f.read(12)
            if len(head) < 12:
                return
            ln = struct.unpack("<Q", head[:8])[0]
            if check_crc and struct.unpack("<I", head[8:])[0] != masked_crc(head[:8]):
                yield None, None, True                      # 길이를 못 믿으면 더 나아갈 수 없다
                return
            if ln > MAX_RECORD:
                yield None, None, True
                return
            if off + 16 + ln > size:
                return                                      # 쓰는 중인 반쪽 레코드: 다음에 읽는다
            if ln > BIG_RECORD:
                f.seek(ln + 4, 1)
                off += 16 + ln
                yield off, None, False
                continue
            data, tail = f.read(ln), f.read(4)
            if len(data) < ln or len(tail) < 4:
                return
            off += 16 + ln
            bad = check_crc and struct.unpack("<I", tail)[0] != masked_crc(data)
            yield off, (None if bad else data), bad


_seen: dict[str, float] = {}
_pruned = 0.0


def _forget_stale(key: str) -> None:
    """한 시간 넘게 안 읽은 파일(지운 학습)의 기억을 버린다. 두 캐시 모두"""
    global _pruned
    now = time.time()
    _seen[key] = now
    if now - _pruned > 600:
        _pruned = now
        for k in [k for k, t in _seen.items() if now - t > 3600]:
            _seen.pop(k, None)
            _cache.pop(k, None)
            for pk in [pk for pk in _CACHE if str(pk) == k]:
                _CACHE.pop(pk, None)


# ---------- read_scalars: 모든 스칼라 ----------
class _ScalarState:
    __slots__ = ("offset", "size", "events", "bad")

    def __init__(self):
        self.offset, self.size, self.events, self.bad = 0, 0, [], 0


_CACHE: dict[Path, _ScalarState] = {}


def read_scalars(p: Path, check_crc: bool = True) -> tuple[list[tuple[float, int, str, float]], int]:
    """(wall_time, step, tag, value) 목록과 깨진 레코드 수. 파일이 커졌으면 지난번 오프셋부터만 읽는다"""
    _forget_stale(str(p))
    size = p.stat().st_size
    st = _CACHE.get(p)
    if st is None or size < st.size:                        # 처음이거나 파일이 줄었다(새로 쓰임): 처음부터
        st = _CACHE[p] = _ScalarState()
    if size > st.offset:
        for off, data, bad in _records(p, st.offset, size, check_crc):
            if bad:
                st.bad += 1
            elif data is not None:
                try:
                    wall, step, vals = parse_event(data)
                    st.events += [(wall, step, t, v) for t, v in vals]
                except (ValueError, IndexError, struct.error):
                    st.bad += 1
            if off is not None:
                st.offset = off
    st.size = size
    return st.events, st.bad


# ---------- read: 쓰는 것만 담는 가벼운 읽기 ----------
VAL_PREFIX = ("val", "eval", "valid", "test")
KEEP_TRAIN = 4000                 # 검증 값이 없는 걸음은 이만큼만(넘으면 하나 걸러 버린다)


class _State:
    """파일 하나를 읽은 결과. ★모든 걸음×태그를 들고 있어 30만 걸음 파일 하나에 268MB였고,
    파일이 자랄 때마다 통째로 복사·재조립해 훑기마다 몇 초씩 걸렸다. 이제 쓰는 것만 담는다:
      marks  검증 값이 찍힌 걸음 → 그때까지의 모든 태그 최신값(학습 값을 함께 싣는 데 쓴다)
      train  검증 없는 걸음 → 그 걸음의 값(검증이 아예 없는 학습의 곡선용, 최대 KEEP_TRAIN개)"""
    __slots__ = ("off", "marks", "train", "walls", "latest")

    def __init__(self):
        self.off, self.marks, self.train, self.walls, self.latest = 0, {}, {}, {}, {}


_cache: dict[str, _State] = {}


def read(path: Path) -> tuple[dict[int, dict[str, float]], dict[int, float]]:
    """{step: {tag: 값}}, {step: 시각}. 새로 붙은 부분만 읽는다. 깨진 꼬리(쓰는 중)는 다음에 다시.
    검증 걸음에는 그때까지의 학습 값도 함께 담겨 있다"""
    key = str(path)
    _forget_stale(key)
    try:
        size = path.stat().st_size
    except OSError:
        return {}, {}
    st = _cache.get(key)
    if st is None or size < st.off:                          # 처음이거나 파일이 새로 쓰였다
        st = _cache[key] = _State()
    try:
        for off, data, _bad in _records(path, st.off, size, check_crc=False):
            if off is None:
                break
            st.off = off
            if data is None:
                continue
            try:
                wall, step, values = _event(data)
            except (IndexError, ValueError, struct.error):
                continue
            if not values:
                continue
            st.latest.update(values)
            if any(t.lower().startswith(VAL_PREFIX) for t, _ in values):
                st.marks[step] = dict(st.latest)
            else:
                st.train.setdefault(step, {}).update(values)
                if len(st.train) > KEEP_TRAIN:               # 고르게 절반만 남긴다(마지막 걸음은 남긴다)
                    for k in sorted(st.train)[:-1:2]:
                        st.train.pop(k, None)
                        st.walls.pop(k, None)
            if wall is not None:
                st.walls[step] = wall
    except OSError:
        pass
    out = dict(st.train)
    out.update(st.marks)
    return out, st.walls


# 어댑터 쪽(열 이름 규칙·TensorBoard). ★기존 `from epokio.tfevents import column, TensorBoard`가 깨지지 않게 다시 내보낸다
from .tfevents_adapter import (PREFIX, SIDE_DIRS, TensorBoard, _EPOCH_TAGS, _files, column,  # noqa: E402,F401
                               _SKIP, _SUFFIX, _TRAIN_PRE, _VAL_PRE)
