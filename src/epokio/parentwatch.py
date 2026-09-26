"""부모(맥 앱)가 죽으면 agent도 스스로 끝낸다. 앱이 띄울 때만 --parent-pid로 켠다.
앱이 비정상 종료돼도 agent만 남아 계속 도는 일이 없게 한다(사용자가 직접 띄운 agent는 해당 없음)."""
from __future__ import annotations

import os
import threading
import time
from typing import Callable


def alive(pid: int) -> bool:
    """pid 프로세스가 살아 있나. 윈도우에서 os.kill(pid, 0)은 프로세스를 죽이므로 쓰지 않는다."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259            # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:                              # 있지만 남의 것
        return True
    return True


def watch(pid: int, on_gone: Callable[[], None] | None = None, interval: float = 2.0) -> threading.Thread:
    """pid가 사라지거나 내가 고아가 되면(부모가 바뀌면) on_gone(기본: 즉시 종료)을 부른다."""
    start_ppid = os.getppid()

    def loop():
        while True:
            time.sleep(interval)
            orphaned = os.name != "nt" and start_ppid == pid and os.getppid() != pid
            if orphaned or not alive(pid):
                (on_gone or (lambda: os._exit(0)))()
                return

    t = threading.Thread(target=loop, name="parent-watch", daemon=True)
    t.start()
    return t
