"""대기열이 띄운 프로세스 다루기: 트리째 끄기, 살아 있나, 언제 시작했나. jobs.py가 다시 내보낸다."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# ★agent는 창 없이 돈다. 콘솔 프로그램을 그냥 띄우면 윈도우가 그때마다 검은 창을 새로 연다
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def kill_tree(proc_or_pid) -> None:
    """자식·손자까지 같이 끈다. 학습을 취소했는데 dataloader 워커가 남으면 GPU 메모리를 계속 쥔다.

    윈도우에는 프로세스 그룹이 없어 terminate()는 직접 자식 하나만 죽인다(2026-09-23 실측: 손자가 살아 있었다).
    taskkill /T 가 트리를 따라 내려간다. 그게 실패하면 terminate()로라도 끈다.
    Popen 대신 pid만 줘도 된다(agent를 다시 켜기 전에 띄운 학습).
    """
    pid = getattr(proc_or_pid, "pid", proc_or_pid)
    try:
        if sys.platform == "win32":
            r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, creationflags=NO_WINDOW)
            if r.returncode == 0:
                return
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            return
    except (ProcessLookupError, AttributeError, OSError):
        pass
    try:
        if hasattr(proc_or_pid, "terminate"):
            proc_or_pid.terminate()
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def proc_start(pid: int | None) -> float | None:
    """그 프로세스가 시작된 시각(유닉스 초). 모르면 None."""
    if not pid:
        return None
    try:
        if sys.platform == "win32":
            import ctypes
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x1000, False, pid)
            if not h:
                return None
            t = [ctypes.c_ulonglong() for _ in range(4)]          # 만든 때·끝난 때·커널·사용자 (FILETIME)
            ok = k.GetProcessTimes(h, *[ctypes.byref(x) for x in t])
            k.CloseHandle(h)
            return (t[0].value - 116444736000000000) / 1e7 if ok else None
        if sys.platform.startswith("linux"):
            ticks = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])
            btime = next(int(l.split()[1]) for l in Path("/proc/stat").read_text().splitlines() if l.startswith("btime"))
            return btime + ticks / os.sysconf("SC_CLK_TCK")
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout.strip()
        return time.mktime(time.strptime(out, "%a %b %d %H:%M:%S %Y")) if out else None
    except (OSError, ValueError, IndexError, StopIteration, subprocess.SubprocessError):
        return None


def pid_alive(pid: int | None, started: float | None = None) -> bool:
    """그 프로세스가 아직 살아 있나. agent를 다시 켰을 때 전에 띄운 학습이 도는지 본다.
    started(띄울 때 적어 둔 시작 시각)를 주면 그 시각도 맞아야 한다. ★재부팅 뒤엔 같은 번호를 다른 프로그램이
    받는다. 번호만 보면 대기열이 남의 프로그램이 끝나길 영원히 기다리고, 멈춤을 누르면 그 프로그램을 죽였다"""
    if not pid:
        return False
    if started is not None:
        now = proc_start(pid)
        if now is not None and abs(now - started) > 2:
            return False
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259          # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
