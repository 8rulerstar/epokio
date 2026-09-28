"""GPU·CPU·메모리 사용률. 활성 상태 보기처럼, 런캣처럼.

측정 방법 (전부 관리자 권한 없이)
  맥 GPU   : ioreg IOAccelerator 의 "Device Utilization %"  (Apple Silicon, 약 16ms)
  맥 CPU   : host_processor_info 눈금 차이 (maccpu.py)      (약 0.1ms, 첫 표본은 None)
  맥 AI 몫 : ps 의 %cpu (실행 파일 경로만 본다. aiuse.py)    (약 15ms)
  맥 메모리: vm_stat + sysctl hw.memsize                     (약 6ms)
  윈도우   : GetSystemTimes + GlobalMemoryStatusEx (ctypes)
  리눅스   : /proc/stat + /proc/meminfo
  NVIDIA   : nvidia-smi --query-gpu                          (원격 agent가 읽어 보낸다)
  맥 온도 : IOHIDEventSystemClient 온도 센서 (mactemp.py, 5초 캐시, 다시 읽기 30~70ms)
  맥 팬   : AppleSMC FNum·F{n}Ac·F{n}Mx (macfan.py, 5초 캐시, 약 1ms)
  ⚠powermetrics는 sudo가 필요해서 쓰지 않는다.
한 번 읽는 데 35ms쯤 든다. 60fps 화면을 막지 않게 Sampler가 별도 스레드에서 읽는다.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field

from . import aiuse, macfan, maccpu, mactemp
from .sysinfo_os import (_cpu_delta, _cpu_prev, _linux_cpu_mem, _windows_cpu_mem,  # noqa: F401  다시 내보낸다
                         parse_pmset_batt, parse_power_supply, parse_proc_net_dev)


@dataclass
class GPU:
    name: str
    util: float | None            # %
    mem_used: float | None        # GB
    mem_total: float | None       # GB
    temp: float | None = None     # °C (NVIDIA만)


@dataclass
class Snapshot:
    host: str
    cpu: float | None
    mem_used: float | None        # GB
    mem_total: float | None
    gpus: list[GPU] = field(default_factory=list)
    at: float = 0.0
    disk_free: float | None = None     # GB (sample(path=) 의 볼륨, 없으면 홈)
    disk_total: float | None = None    # GB
    net_up: float | None = None        # 바이트/초 (직전 샘플과의 차이, 첫 샘플은 None)
    net_down: float | None = None      # 바이트/초
    battery: float | None = None       # % (배터리 없는 기기는 None)
    charging: bool | None = None
    cpu_temp: float | None = None      # °C (애플 실리콘 맥만, mactemp.py)
    fan: float | None = None           # % 가장 빠른 팬의 최대 대비 (팬 있는 애플 실리콘 맥만, macfan.py)
    fan_rpm: int | None = None
    ai: float | None = None            # % AI 도구 사용량 (aiuse.py). 메뉴바 캐릭터 속도용
    ai_from: str | None = None         # 그 값이 어디서 왔나: "reported" · "process" · "none"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        d["gpus"] = [GPU(**g) for g in d.get("gpus", [])]
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})

    @property
    def gpu(self) -> float | None:
        vals = [g.util for g in self.gpus if g.util is not None]
        return max(vals) if vals else None


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)     # 윈도우: 창 없는 agent 밑에서 nvidia-smi 창이 깜빡이지 않게


def _run(cmd, timeout=3):
    try:
        # ★창 없는 agent가 nvidia-smi 같은 콘솔 프로그램을 그냥 띄우면 윈도우가 몇 초마다 검은 창을 연다
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace", creationflags=_NO_WINDOW).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


_STATIC: dict = {}


def _static(key, make):
    """안 바뀌는 값(CPU 이름·전체 메모리)은 한 번만 잰다(★예전엔 1.5초마다 sysctl을 띄웠다)"""
    if key not in _STATIC:
        _STATIC[key] = make()
    return _STATIC[key]


def _mac_gpu() -> list[GPU]:
    # ★이름은 GPU 노드의 "model". 예전엔 machdep.cpu.brand_string(CPU 이름)이 들어갔다.
    # ★mem_total 은 물리 메모리. 예전 "Alloc system memory"(약 4 GB)는 쓸수록 분모가 커졌다.
    out = _run(["ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"])
    util = re.search(r'"Device Utilization %"=(\d+)', out)
    used = re.search(r'"In use system memory"=(\d+)', out)
    model = re.search(r'"model"\s*=\s*"([^"]+)"', out)
    if not util:
        return []
    total = _static("memsize", lambda: _run(["sysctl", "-n", "hw.memsize"]).strip())
    return [GPU(name=(model.group(1).strip() if model else "Apple GPU"), util=float(util.group(1)),
                mem_used=int(used.group(1)) / 2**30 if used else None,
                mem_total=int(total) / 2**30 if total else None)]


def _mac_cpu_ai() -> tuple[float | None, float | None]:
    """(전체 CPU %, AI 도구 %).

    ★전체 CPU 는 maccpu(커널 눈금 차이). ps 의 %cpu 는 최대 1분 감쇠 평균이라 지금 구간 값이 아니다.
    AI 몫만 ps 로 남긴다. "그 도구가 대체로 일하는 중인가"라는 대리 지표엔 감쇠 평균이 오히려 맞고,
    프로세스별로 갈라 볼 수단이 ps 말고 없다. comm= 은 실행 파일 경로만이다(aiuse.py).
    """
    out = _run(["ps", "-Ao", "%cpu=,comm="])
    return maccpu.cpu_percent(), aiuse.scan_ps(out)


def _mac_mem() -> tuple[float | None, float | None]:
    total = _static("memsize", lambda: _run(["sysctl", "-n", "hw.memsize"]).strip())
    vm = _run(["vm_stat"])
    page = re.search(r"page size of (\d+)", vm)
    if not (total and page):
        return None, None
    ps = int(page.group(1))
    get = lambda k: int(re.search(rf"{k}:\s+(\d+)", vm).group(1)) if re.search(rf"{k}:\s+(\d+)", vm) else 0
    used = (get("Pages active") + get("Pages wired down") + get("Pages occupied by compressor")) * ps
    return used / 2**30, int(total) / 2**30


def nvidia_smi_path() -> str | None:
    """PATH에 없으면 윈도우 옛 드라이버 자리(NVSMI)도 본다."""
    p = shutil.which("nvidia-smi")
    if p or sys.platform != "win32":
        return p
    for base in (os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles"), r"C:\Program Files"):
        if base:
            cand = os.path.join(base, "NVIDIA Corporation", "NVSMI", "nvidia-smi.exe")
            if os.path.isfile(cand):
                return cand
    return None


def _nvidia() -> list[GPU]:
    smi = nvidia_smi_path()
    if not smi:
        return []
    out = _run([smi, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits"])
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        f = lambda v: float(v) if v not in ("", "[N/A]", "N/A") else None
        gb = lambda v: (f(v) / 1024) if f(v) is not None else None      # ★[N/A]를 0.0 GB로 바꾸지 않는다
        gpus.append(GPU(name=parts[0], util=f(parts[1]),
                        mem_used=gb(parts[2]), mem_total=gb(parts[3]),
                        temp=f(parts[4])))
    return gpus

_PSUTIL: dict = {}      # psutil 첫 표본을 버렸는지


def _generic_cpu_mem():
    """윈도우·리눅스. psutil이 깔려 있으면 그걸 쓰고, 없으면 OS에 직접 묻는다.

    psutil을 의존성으로 넣지 않는 건 agent가 학습 기계의 파이썬 환경에 들어가기 때문이다.
    남의 환경에 패키지를 더 얹지 않는다.
    """
    try:
        import psutil
        vm = psutil.virtual_memory()
        pct = psutil.cpu_percent(interval=None)     # ★첫 호출은 0.0 이다(화면에 "0%"로 나갔다)
        primed, _PSUTIL["primed"] = _PSUTIL.get("primed"), True
        return (pct if primed else None), vm.used / 2**30, vm.total / 2**30   # _cpu_delta 처럼 첫 표본은 버린다
    except ImportError:
        pass
    try:
        if sys.platform == "win32":             # psutil은 필수 의존성이 아니다. 윈도우는 ctypes로 읽는다
            try:
                from . import winstats
                return winstats.cpu(), *winstats.mem()
            except Exception:
                return _windows_cpu_mem()       # 두 번째 길(sysinfo_os)
        if platform.system() == "Linux":
            return _linux_cpu_mem()
    except Exception:                           # 값 하나 못 읽었다고 agent가 죽으면 안 된다
        pass
    return None, None, None


def disk(path: str | None = None) -> tuple[float | None, float | None]:
    """(여유 GB, 전체 GB). 학습 폴더가 있는 볼륨을 보려면 path를 넘긴다."""
    try:
        u = shutil.disk_usage(path or os.path.expanduser("~"))
        return u.free / 2**30, u.total / 2**30
    except (OSError, ValueError):
        return None, None


def parse_netstat_ib(out: str) -> tuple[int, int] | None:
    """맥 `netstat -ib`: 인터페이스마다 <Link#> 줄 하나만 센다(주소 줄은 같은 숫자를 되풀이). lo 제외."""
    lines = out.strip().splitlines()
    if not lines:
        return None
    head = lines[0].split()
    try:
        ib, ob = head.index("Ibytes"), head.index("Obytes")
    except ValueError:
        return None
    rx = tx = 0
    seen = set()
    found = False
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 7 or not parts[2].startswith("<Link#"):
            continue
        name = parts[0].rstrip("*")
        if name.startswith("lo") or name in seen:
            continue
        # Address 칸이 비면 뒤 칸이 하나 당겨진다: 오른쪽 끝에서 센다
        off = len(head) - len(parts)
        try:
            rx += int(parts[ib - off])
            tx += int(parts[ob - off])
        except (ValueError, IndexError):
            continue
        seen.add(name)
        found = True
    return (rx, tx) if found else None


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _net_bytes() -> tuple[int, int] | None:
    system = platform.system()
    if system == "Darwin":
        return parse_netstat_ib(_run(["netstat", "-ib", "-n"]))
    if system == "Linux":
        out = _read("/proc/net/dev")
        return parse_proc_net_dev(out) if out else None
    try:
        import psutil
        c = psutil.net_io_counters()
        return c.bytes_recv, c.bytes_sent
    except Exception:
        return None


def _battery() -> tuple[float | None, bool | None]:
    system = platform.system()
    if system == "Darwin":
        return parse_pmset_batt(_run(["pmset", "-g", "batt"]))
    if system == "Linux":
        base = "/sys/class/power_supply"
        try:
            names = sorted(n for n in os.listdir(base) if n.startswith("BAT"))
        except OSError:
            return None, None
        for n in names:
            pct, ch = parse_power_supply(_read(f"{base}/{n}/capacity"), _read(f"{base}/{n}/status"))
            if pct is not None:
                return pct, ch
        return None, None
    try:
        import psutil
        b = psutil.sensors_battery()
        return (float(b.percent), bool(b.power_plugged)) if b else (None, None)
    except Exception:
        return None, None


_NET_LAST: dict = {}


def net_rate(now: float | None = None, counters=None) -> tuple[float | None, float | None]:
    """(업, 다운) 바이트/초. 직전 호출과의 차이. 첫 호출·카운터 되감김은 None."""
    now = time.time() if now is None else now
    cur = _net_bytes() if counters is None else counters
    prev = _NET_LAST.get("v")
    if cur is None:
        return None, None
    _NET_LAST["v"] = (now, cur)
    if not prev:
        return None, None
    dt = now - prev[0]
    drx, dtx = cur[0] - prev[1][0], cur[1] - prev[1][1]
    if dt <= 0 or drx < 0 or dtx < 0:
        return None, None
    return dtx / dt, drx / dt


def _extras(snap: Snapshot, path: str | None) -> Snapshot:
    """디스크·네트워크·배터리. 어느 하나가 깨져도 나머지 값은 그대로."""
    for fn in (lambda: disk(path), net_rate, _battery):
        try:
            vals = fn()
        except Exception:
            continue
        if fn is net_rate:
            snap.net_up, snap.net_down = vals
        elif fn is _battery:
            snap.battery, snap.charging = vals
        else:
            snap.disk_free, snap.disk_total = vals
    return snap


def sample(host: str | None = None, path: str | None = None) -> Snapshot:
    host = host or platform.node()
    if platform.system() == "Darwin":
        used, total = _mac_mem()
        gpus = _nvidia() or _mac_gpu()
        cpu, ai = _mac_cpu_ai()
        snap = Snapshot(host, cpu, used, total, gpus, time.time())
        snap.cpu_temp, (snap.fan, snap.fan_rpm) = mactemp.cpu_temp(), macfan.fan() or (None, None)
        snap.ai, snap.ai_from = aiuse.combine(ai)
        return _extras(snap, path)
    cpu, used, total = _generic_cpu_mem()
    snap = Snapshot(host, cpu, used, total, _nvidia(), time.time())
    snap.ai, snap.ai_from = aiuse.combine(None)      # 맥 아닌 기계는 프로세스 훑기 없음. 보고가 오면 그 값
    return _extras(snap, path)


class Sampler:
    """백그라운드에서 주기적으로 읽는다. 화면 쪽은 latest/history만 본다."""

    IDLE_PERIOD = 15.0          # 아무 화면도 안 볼 때
    WATCHED_FOR = 20.0          # 마지막으로 누가 본 뒤 이만큼은 빠르게

    def __init__(self, fetch=sample, period: float = 1.5, keep: int = 120):
        self.fetch = fetch
        self.period = period
        self.last_seen = 0.0     # 앱·웹·터미널이 /system을 물은 시각
        self.latest: Snapshot | None = None
        self.history: deque[Snapshot] = deque(maxlen=keep)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._t.start()
        return self

    def stop(self):
        self._stop.set()

    def touch(self):
        """누가 보고 있다: 다음 샘플을 바로, 그 뒤로 빠르게. (★아무도 안 볼 때도 1.5초마다 프로그램 5개를 띄워 CPU 5%를 먹었다)"""
        idle = time.time() - self.last_seen > self.WATCHED_FOR
        self.last_seen = time.time()
        if idle:
            self._wake.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                s = self.fetch()
                if s is not None:
                    self.latest = s
                    self.history.append(s)
            except Exception:
                pass                # 한 번 실패해도 다음 주기에 다시 읽는다
            watched = time.time() - self.last_seen < self.WATCHED_FOR
            self._wake.clear()
            self._wake.wait(self.period if watched else self.IDLE_PERIOD)
            if self._stop.is_set():
                return
