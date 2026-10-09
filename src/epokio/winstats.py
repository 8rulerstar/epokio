"""윈도우 CPU·메모리(psutil 없이 ctypes). sysinfo._generic_cpu_mem의 윈도우 폴백."""
from __future__ import annotations

import threading


def mem() -> tuple[float, float]:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        raise OSError("GlobalMemoryStatusEx failed")
    return (m.ullTotalPhys - m.ullAvailPhys) / 2**30, m.ullTotalPhys / 2**30


_TIMES: dict = {}
_LOCK = threading.Lock()


def cpu_from_times(prev, cur) -> float | None:
    """GetSystemTimes 두 번의 차이로 CPU %. (idle, kernel, user), kernel에 idle이 들어 있다."""
    if not prev:
        return None
    di, dk, du = (c - p for c, p in zip(cur, prev))
    total = dk + du
    if total <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * (total - di) / total))


def cpu() -> float | None:
    """직전 호출 이후 구간의 CPU %. 첫 호출은 None.
    ★GetSystemTimes는 시계 눈금(약 15.6ms)마다만 오른다. 다른 호출이 같은 눈금 안에서 바로 앞에 읽었으면 차이가 0이라
      None이 났다(0.8.0 윈도우 CI: 다른 시험이 띄운 기계 표본 스레드). 그때는 기준을 그대로 두고 직전 값을 준다"""
    import ctypes
    from ctypes import wintypes
    i, k, u = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u)):
        return None
    return _since_last(tuple((t.dwHighDateTime << 32) | t.dwLowDateTime for t in (i, k, u)))


def _since_last(cur: tuple) -> float | None:
    """지난 표본과의 차이. 시계가 안 움직였으면 기준을 두고 직전 값"""
    with _LOCK:
        prev = _TIMES.get("v")
        if prev == cur:
            return _TIMES.get("pct")
        pct = cpu_from_times(prev, cur)
        _TIMES["v"], _TIMES["pct"] = cur, pct
        return pct
