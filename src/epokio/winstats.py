"""윈도우 CPU·메모리(psutil 없이 ctypes). sysinfo._generic_cpu_mem의 윈도우 폴백."""
from __future__ import annotations


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
    import ctypes
    from ctypes import wintypes
    i, k, u = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u)):
        return None
    cur = tuple((t.dwHighDateTime << 32) | t.dwLowDateTime for t in (i, k, u))
    prev, _TIMES["v"] = _TIMES.get("v"), cur
    return cpu_from_times(prev, cur)
