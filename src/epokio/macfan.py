"""맥 팬 속도. 관리자 권한 없이 AppleSMC 에서 읽는다(Stats 앱과 같은 길).

키: FNum(팬 수) · F{n}Ac(지금 rpm) · F{n}Mx(최대 rpm). 애플 실리콘은 값이 flt(4바이트 float)다.
  실측(M4 Pro MacBook Pro): 팬 2개, 최소 2317 · 최대 7826 rpm. 학습 없이도 3200~5100 rpm 사이를 오갔다.
팬 없는 기기(MacBook Air 등)는 FNum 이 0 이라 None. 인텔 맥은 값 형식(fpe2)이 달라 보지 않는다.

★SMC 구조체(SMCKeyData_t)는 C 정렬을 그대로 맞춰야 한다. keyInfo 뒤 패딩 3바이트를 빼먹으면
  크기는 80으로 같아도 필드가 밀려 모든 호출이 kIOReturnBadArgument(e00002c2)로 실패했다.
실패(인텔, 권한, 인터페이스 변경)는 전부 None. 한 번 실패하면 다시 시도하지 않는다(mactemp.py 와 같은 규칙).
"""
from __future__ import annotations

import ctypes as C
import platform
import struct
import threading
import time

CACHE_SEC = 5.0
_READ_BYTES, _READ_INFO = 5, 9          # SMC 명령: 값 읽기 · 키 정보 읽기
_FLT = int.from_bytes(b"flt ", "big")


class _Vers(C.Structure):
    _fields_ = [("major", C.c_uint8), ("minor", C.c_uint8), ("build", C.c_uint8),
                ("reserved", C.c_uint8), ("release", C.c_uint16)]


class _PLimit(C.Structure):
    _fields_ = [("version", C.c_uint16), ("length", C.c_uint16), ("cpu", C.c_uint32),
                ("gpu", C.c_uint32), ("mem", C.c_uint32)]


class _KeyInfo(C.Structure):
    _fields_ = [("size", C.c_uint32), ("type", C.c_uint32), ("attr", C.c_uint8)]


class _KeyData(C.Structure):
    _fields_ = [("key", C.c_uint32), ("vers", _Vers), ("plimit", _PLimit), ("info", _KeyInfo),
                ("result", C.c_uint8), ("status", C.c_uint8), ("data8", C.c_uint8),
                ("data32", C.c_uint32), ("bytes", C.c_uint8 * 32)]


def _key(s: str) -> int:
    return int.from_bytes(s.encode("ascii"), "big")


def fan_pct(fans) -> tuple[float, int] | None:
    """[(지금 rpm, 최대 rpm)] → (가장 빠른 팬의 최대 대비 %, 그 팬의 rpm). 읽을 게 없으면 None."""
    vals = [(ac / mx * 100, ac) for ac, mx in fans if mx and mx > 0 and 0 <= ac <= mx * 1.2]
    if not vals:
        return None
    pct, rpm = max(vals)
    return round(min(pct, 100.0), 1), int(round(rpm))


class _Reader:
    def __init__(self):
        io = C.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
        V, U = C.c_void_p, C.c_uint32
        for fn, res, args in (
            (io.IOServiceMatching, V, [C.c_char_p]),
            (io.IOServiceGetMatchingService, U, [U, V]),
            (io.IOServiceOpen, C.c_int, [U, U, U, C.POINTER(U)]),
            (io.IOConnectCallStructMethod, C.c_int, [U, U, V, C.c_size_t, V, C.POINTER(C.c_size_t)]),
        ):
            fn.restype, fn.argtypes = res, args
        assert C.sizeof(_KeyData) == 80, C.sizeof(_KeyData)
        self.io = io
        svc = io.IOServiceGetMatchingService(0, io.IOServiceMatching(b"AppleSMC"))
        if not svc:
            raise OSError("AppleSMC 없음")
        task = U.in_dll(C.CDLL(None), "mach_task_self_")
        self.conn = U()
        if io.IOServiceOpen(svc, task, 0, C.byref(self.conn)) != 0:
            raise OSError("AppleSMC 열기 실패")
        n = self._read("FNum")
        self.count = n[1][0] if n and n[1] else 0

    def _call(self, d: _KeyData) -> _KeyData | None:
        out, size = _KeyData(), C.c_size_t(C.sizeof(_KeyData))
        r = self.io.IOConnectCallStructMethod(self.conn.value, 2, C.byref(d), C.sizeof(d), C.byref(out), C.byref(size))
        return out if r == 0 and out.result == 0 else None

    def _read(self, k: str):
        info = self._call(_KeyData(key=_key(k), data8=_READ_INFO))
        if info is None:
            return None
        d = _KeyData(key=_key(k), data8=_READ_BYTES)
        d.info.size = info.info.size
        got = self._call(d)
        return (info.info.type, bytes(got.bytes[:info.info.size])) if got else None

    def _flt(self, k: str) -> float | None:
        v = self._read(k)
        return struct.unpack("<f", v[1])[0] if v and v[0] == _FLT and len(v[1]) == 4 else None

    def read(self):
        return [(self._flt(f"F{i}Ac"), self._flt(f"F{i}Mx")) for i in range(min(self.count, 4))]


_lock = threading.Lock()
_state: dict = {"reader": None, "failed": False, "at": 0.0, "value": None}


def fan(now: float | None = None) -> tuple[float, int] | None:
    """(가장 빠른 팬의 최대 대비 %, rpm) 또는 None(팬 없음·못 읽음). 예외를 내지 않는다."""
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return None
    now = time.monotonic() if now is None else now
    with _lock:
        if _state["failed"]:
            return None
        if _state["at"] and now - _state["at"] < CACHE_SEC:
            return _state["value"]
        try:
            if _state["reader"] is None:
                _state["reader"] = _Reader()
            r = _state["reader"]
            _state["value"] = fan_pct([(a, m) for a, m in r.read() if a is not None and m is not None]) if r.count else None
            if not r.count:
                _state["failed"] = True          # 팬 없는 기기: 다시 물을 것이 없다
        except Exception:
            _state["failed"] = True
            _state["value"] = None
        _state["at"] = now
        return _state["value"]
