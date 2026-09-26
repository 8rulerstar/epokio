"""맥 SoC(칩) 다이 온도. 관리자 권한 없이, Stats 앱과 같은 길.

★이름 주의: CPU 코어만의 온도가 아니다. M2~M4 에서 실제로 잡히는 센서는 "PMU tdie*"
  (M4 Pro 실측 42개)뿐이고, tdie 는 다이 위 "위치"별 온도라 기능(CPU·GPU·NPU) 구분이 없다.
  실측(M4 Pro, 0.4초 간격 20초, 최고점 센서가 누구인지 세어 봄):
    CPU 부하 12코어 → tdie1 이 100%.  GPU 부하(MPS 행렬곱) → tdie8 60% · tdie1 40%.
  부하 종류에 따라 최고점이 다른 센서로 옮겨 간다. 즉 센서마다 다른 블록 위에 있고,
  최댓값을 쓰는 이 함수는 CPU 가 아닌 블록의 온도를 낼 수 있다.
  그래서 화면 이름표는 "SoC temperature" 다.
  함수·필드 이름 cpu_temp 는 앱·agent 사이 약속(Snapshot)이라 그대로 둔다.

공식 API가 없어서 IOKit의 비공개 인터페이스 IOHIDEventSystemClient 로 온도 센서
(PrimaryUsagePage 0xff00, PrimaryUsage 5)를 ctypes 로 읽는다. 칩마다 센서 이름이 달라
CPU_PREFIXES 에 맞는 센서의 최댓값만 쓴다(칩에서 제일 뜨거운 지점).

비용: 첫 호출에서 센서 목록을 만들고(수십 ms), 뒤로는 고른 센서만 다시 읽는다.
그래도 한 번에 수십 ms라 CACHE_SEC 동안은 직전 값을 돌려준다.
실패(인텔, 권한, 인터페이스 변경)는 전부 None. 한 번 실패하면 다시 시도하지 않는다.
"""
from __future__ import annotations

import ctypes as C
import platform
import threading
import time

# M1 계열: "pACC MTR Temp Sensor*", "eACC MTR Temp Sensor*", "SOC MTR Temp Sensor*"
# M2~M4 계열: "PMU tdie*" (M4 Pro 실측). "PMU tdev*"는 -9000대 쓰레기값, "tcal"은 보정값이라 뺀다.
CPU_PREFIXES = ("PMU tdie", "PMU2 tdie", "pACC MTR Temp", "eACC MTR Temp", "SOC MTR Temp")
MIN_C, MAX_C = 0.0, 150.0
CACHE_SEC = 5.0

_TEMP_EVENT = 15                    # kIOHIDEventTypeTemperature
_TEMP_FIELD = _TEMP_EVENT << 16
_UTF8 = 0x08000100


def pick_cpu_temp(readings) -> float | None:
    """(센서 이름, °C) 목록에서 다이 센서의 현실적인 값 중 최댓값. 없으면 None."""
    vals = [v for n, v in readings
            if isinstance(n, str) and n.startswith(CPU_PREFIXES)
            and isinstance(v, (int, float)) and MIN_C < v < MAX_C]
    return round(max(vals), 1) if vals else None


class _Reader:
    def __init__(self):
        V = C.c_void_p
        cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        io = C.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
        for fn, res, args in (
            (cf.CFStringCreateWithCString, V, [V, C.c_char_p, C.c_uint32]),
            (cf.CFNumberCreate, V, [V, C.c_int, V]),
            (cf.CFDictionaryCreate, V, [V, V, V, C.c_long, V, V]),
            (cf.CFArrayGetCount, C.c_long, [V]),
            (cf.CFArrayGetValueAtIndex, V, [V, C.c_long]),
            (cf.CFStringGetCString, C.c_bool, [V, C.c_char_p, C.c_long, C.c_uint32]),
            (cf.CFRelease, None, [V]),
            (io.IOHIDEventSystemClientCreate, V, [V]),
            (io.IOHIDEventSystemClientSetMatching, C.c_int, [V, V]),
            (io.IOHIDEventSystemClientCopyServices, V, [V]),
            (io.IOHIDServiceClientCopyProperty, V, [V, V]),
            (io.IOHIDServiceClientCopyEvent, V, [V, C.c_int64, C.c_int32, C.c_int64]),
            (io.IOHIDEventGetFloatValue, C.c_double, [V, C.c_int32]),
        ):
            fn.restype, fn.argtypes = res, args
        self.cf, self.io = cf, io

        def cfstr(b):
            return cf.CFStringCreateWithCString(None, b, _UTF8)

        def num(v):
            x = C.c_int32(v)
            return cf.CFNumberCreate(None, 3, C.byref(x))   # kCFNumberSInt32Type

        kcb = V.in_dll(cf, "kCFTypeDictionaryKeyCallBacks")
        vcb = V.in_dll(cf, "kCFTypeDictionaryValueCallBacks")
        keys = (V * 2)(cfstr(b"PrimaryUsagePage"), cfstr(b"PrimaryUsage"))
        vals = (V * 2)(num(0xFF00), num(5))
        match = cf.CFDictionaryCreate(None, keys, vals, 2, C.addressof(kcb), C.addressof(vcb))
        self.client = io.IOHIDEventSystemClientCreate(None)
        if not self.client or not match:
            raise OSError("IOHIDEventSystemClient 없음")
        io.IOHIDEventSystemClientSetMatching(self.client, match)
        # 센서 목록은 한 번만. 배열을 들고 있어야 안의 서비스도 살아 있다.
        self.services = io.IOHIDEventSystemClientCopyServices(self.client)
        if not self.services:
            raise OSError("온도 센서 없음")
        product = cfstr(b"Product")
        self.cpu = []
        for i in range(cf.CFArrayGetCount(self.services)):
            svc = cf.CFArrayGetValueAtIndex(self.services, i)
            p = io.IOHIDServiceClientCopyProperty(svc, product)
            if not p:
                continue
            buf = C.create_string_buffer(128)
            ok = cf.CFStringGetCString(p, buf, 128, _UTF8)
            cf.CFRelease(p)
            name = buf.value.decode("utf-8", "replace") if ok else ""
            if name.startswith(CPU_PREFIXES):
                self.cpu.append((name, svc))
        if not self.cpu:
            raise OSError("CPU 온도 센서 없음")

    def read(self):
        out = []
        for name, svc in self.cpu:
            ev = self.io.IOHIDServiceClientCopyEvent(svc, _TEMP_EVENT, 0, 0)
            if ev:
                out.append((name, self.io.IOHIDEventGetFloatValue(ev, _TEMP_FIELD)))
                self.cf.CFRelease(ev)
        return out


_lock = threading.Lock()
_state: dict = {"reader": None, "failed": False, "at": 0.0, "value": None}


def cpu_temp(now: float | None = None) -> float | None:
    """SoC 다이 최고 온도 °C 또는 None. 예외를 내지 않는다."""
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
            _state["value"] = pick_cpu_temp(_state["reader"].read())
        except Exception:
            _state["failed"] = True
            _state["value"] = None
        _state["at"] = now
        return _state["value"]
