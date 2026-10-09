"""맥 CPU 사용률. 활성 상태 보기와 같은 길: 커널의 CPU 시간 눈금(tick) 차이.

왜 이 방법인가
  예전엔 `ps -Ao %cpu=` 의 합을 코어 수로 나눴다. macOS ps(1) 의 %cpu 는 "최대 1분에 걸친
  감쇠 평균"이다(수명 누적 평균은 아니다). 지금 구간의 사용률이 아니라서 부하를 늦게 따라오고,
  man 이 적어 두었듯 프로세스마다 시간 기준이 달라 다 더한 값에는 정해진 뜻이 없다.
  M4 Pro 실측(12코어 중 4코어 고정 부하, 6표본 평균): top 66.0% 일 때 이 방식 67.0%,
  옛 ps 방식 61.3%. 부하가 걷힐 때도 ps 쪽이 몇 초 늦게 내려온다.

  `host_processor_info(PROCESSOR_CPU_LOAD_INFO)` 는 코어마다 user/system/idle/nice 에
  쓴 시간 눈금 누계를 준다. 두 번 읽어 차이를 내면 그 구간의 실제 사용률이 나온다.
  top 과 활성 상태 보기가 쓰는 것과 같은 값이고, 관리자 권한도 필요 없다.

  P코어·E코어를 같이 세도 되나? 된다. 눈금은 "코어가 일한 시간"이지 처리량이 아니라서,
  전체 눈금 대비 idle 눈금의 비율이 곧 "전체 코어-시간 중 얼마를 썼나"다. top 과 같은 정의다.

첫 호출은 비교할 직전 값이 없으니 None 이다(0% 로 위장하지 않는다).
"""
from __future__ import annotations

import ctypes as C
import ctypes.util
import threading

PROCESSOR_CPU_LOAD_INFO = 2
CPU_STATE_MAX = 4           # user, system, idle, nice
CPU_STATE_IDLE = 2

_lock = threading.Lock()
_state: dict = {"lib": None, "failed": False, "prev": None, "last": None}


def _lib():
    lib = C.CDLL(C.util.find_library("c") or "libc.dylib", use_errno=True)
    V, U = C.c_void_p, C.c_uint
    lib.mach_host_self.restype = U
    lib.mach_host_self.argtypes = []
    lib.host_processor_info.restype = C.c_int
    lib.host_processor_info.argtypes = [U, C.c_int, C.POINTER(U),
                                        C.POINTER(C.POINTER(U)), C.POINTER(U)]
    lib.vm_deallocate.restype = C.c_int
    lib.vm_deallocate.argtypes = [U, V, C.c_size_t]
    return lib


def _ticks(lib) -> list[int] | None:
    """코어마다 [user, system, idle, nice] 누계를 이어 붙인 목록."""
    n, cnt = C.c_uint(), C.c_uint()
    arr = C.POINTER(C.c_uint)()
    if lib.host_processor_info(lib.mach_host_self(), PROCESSOR_CPU_LOAD_INFO,
                               C.byref(n), C.byref(arr), C.byref(cnt)) != 0:
        return None
    try:
        return [arr[i] for i in range(cnt.value)]
    finally:
        task = C.c_uint.in_dll(lib, "mach_task_self_").value
        lib.vm_deallocate(task, C.cast(arr, C.c_void_p), cnt.value * C.sizeof(C.c_uint))


def busy_pct(prev: list[int] | None, cur: list[int] | None) -> float | None:
    """두 눈금 누계 사이의 사용률 %. 비교할 것이 없거나 되감겼으면 None.

    눈금은 32비트라 한 바퀴 돌 수 있다. 음수 차이가 보이면 그 구간은 버린다.
    """
    if not prev or not cur or len(prev) != len(cur) or len(cur) % CPU_STATE_MAX:
        return None
    d = [c - p for c, p in zip(cur, prev)]
    if any(x < 0 for x in d):
        return None
    total = sum(d)
    if total <= 0:                      # 두 번 읽는 사이에 눈금이 안 올랐다(너무 빨리 읽음)
        return None
    idle = sum(d[i] for i in range(CPU_STATE_IDLE, len(d), CPU_STATE_MAX))
    return max(0.0, min(100.0, 100.0 * (total - idle) / total))


def cpu_percent() -> float | None:
    """직전 호출 이후 구간의 CPU 사용률 %. 첫 호출과 실패는 None.
    ★눈금은 100Hz라, 다른 호출이 같은 눈금 안에서 바로 앞에 읽었으면 차이가 0이라 None이 났다.
      그때는 기준을 그대로 두고 직전 값을 준다"""
    with _lock:
        if _state["failed"]:
            return None
        try:
            if _state["lib"] is None:
                _state["lib"] = _lib()
            cur = _ticks(_state["lib"])
        except Exception:
            _state["failed"] = True
            return None
        if cur is None:
            return None
        prev = _state["prev"]
        if prev == cur:
            return _state["last"]
        _state["prev"] = cur
        _state["last"] = pct = busy_pct(prev, cur)
        return pct


def reset():
    """테스트용: 직전 눈금을 잊는다(다음 호출이 다시 첫 호출이 된다)."""
    with _lock:
        _state["prev"] = _state["last"] = None
