"""윈도우·리눅스 CPU·메모리를 psutil 없이 OS에 직접 묻는다. sysinfo._generic_cpu_mem의 폴백.
sysinfo가 이 이름들을 다시 내보낸다(sysinfo._cpu_delta 등 기존 호출·monkeypatch가 그대로 된다).
윈도우는 winstats가 먼저, 여기 _windows_cpu_mem은 그게 실패할 때의 두 번째 길이다."""
from __future__ import annotations

import re
import threading

_cpu_prev: dict[str, tuple[float, float]] = {}
_cpu_last: dict[str, float | None] = {}
_cpu_lock = threading.Lock()


def _cpu_delta(who: str, busy: float, total: float) -> float | None:
    """CPU 사용률은 한 순간에 잴 수 없다. 지난번에 읽은 값과의 차이로 낸다.

    그래서 첫 호출은 None이다(psutil.cpu_percent(interval=None)과 같은 방식).
    Sampler가 주기적으로 부르므로 두 번째부터 값이 나온다.
    ★카운터는 눈금(리눅스 10ms, 윈도우 약 15.6ms)마다만 오른다. 다른 호출이 같은 눈금 안에서 바로 앞에 읽었으면
      차이가 0이라 None이 났다. 그때는 기준을 그대로 두고 직전 값을 준다(0으로 나누지도 않는다)
    """
    with _cpu_lock:
        prev = _cpu_prev.get(who)
        if prev is not None and total == prev[1]:
            return _cpu_last.get(who)
        _cpu_prev[who] = (busy, total)
        db, dt = (busy - prev[0], total - prev[1]) if prev else (0.0, 0.0)
        pct = max(0.0, min(100.0, 100.0 * db / dt)) if dt > 0 else None     # 첫 호출, 되감긴 카운터는 새 기준
        _cpu_last[who] = pct
        return pct


def _windows_cpu_mem():
    """GetSystemTimes + GlobalMemoryStatusEx. 관리자 권한도, 외부 패키지도 필요 없다."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    cpu = None
    idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
        n = lambda t: (t.dwHighDateTime << 32) | t.dwLowDateTime
        total = n(kern) + n(user)           # kernel 시간에는 idle이 들어 있다
        cpu = _cpu_delta("win", total - n(idle), total)

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not k32.GlobalMemoryStatusEx(ctypes.byref(m)):
        return cpu, None, None
    return cpu, (m.ullTotalPhys - m.ullAvailPhys) / 2**30, m.ullTotalPhys / 2**30


def _linux_cpu_mem():
    """/proc/stat 과 /proc/meminfo. 리눅스 GPU 서버에 아무것도 안 깔고 쓴다."""
    cpu = None
    try:
        with open("/proc/stat") as f:
            parts = [float(x) for x in f.readline().split()[1:]]
        total = sum(parts)
        cpu = _cpu_delta("linux", total - parts[3], total)      # 4번째가 idle
    except (OSError, ValueError, IndexError):
        pass
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                info[k] = float(v.split()[0]) * 1024            # kB 로 적혀 있다
        total, avail = info["MemTotal"], info.get("MemAvailable", info.get("MemFree", 0.0))
        return cpu, (total - avail) / 2**30, total / 2**30
    except (OSError, ValueError, KeyError, IndexError):
        return cpu, None, None


# ---- 배터리 출력 파서(명령 출력 문자열만 받는다) ----
def parse_pmset_batt(out: str) -> tuple[float | None, bool | None]:
    """맥 `pmset -g batt`: "-InternalBattery-0 ...	87%; charging; ..." 배터리 줄이 없으면 (None, None)."""
    m = re.search(r"InternalBattery.*?(\d+)%;\s*([^;]+);", out)
    if not m:
        return None, None
    state = m.group(2).strip().lower()
    if state == "discharging":
        charging = False
    else:
        charging = state in ("charging", "charged", "finishing charge") or "'AC Power'" in out
    return float(m.group(1)), charging


def parse_power_supply(capacity: str | None, status: str | None) -> tuple[float | None, bool | None]:
    """리눅스 /sys/class/power_supply/BAT*/capacity, status."""
    try:
        pct = float(capacity.strip()) if capacity else None
    except ValueError:
        pct = None
    if pct is None:
        return None, None
    st = (status or "").strip().lower()
    return pct, (st in ("charging", "full", "not charging") if st else None)


def parse_proc_net_dev(out: str) -> tuple[int, int] | None:
    """리눅스 /proc/net/dev: 받은 바이트 = 콜론 뒤 1번째, 보낸 바이트 = 9번째. lo 제외."""
    rx = tx = 0
    found = False
    for line in out.splitlines():
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        f = rest.split()
        if name.strip() == "lo" or len(f) < 9:
            continue
        try:
            rx += int(f[0])
            tx += int(f[8])
            found = True
        except ValueError:
            continue
    return (rx, tx) if found else None
