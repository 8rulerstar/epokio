"""results.csv를 읽어 학습 상태를 만든다. 순수 계산, 화면·네트워크와 무관."""
from __future__ import annotations

import math
import os
import time
import unicodedata
from dataclasses import dataclass, field, fields
from pathlib import Path

from . import adapters, schema

STALE_SEC = 180       # 이 시간 넘게 안 변하면 진행 중이 아니다
MIN_EPOCH_SEC = 1.0   # 시간 열 없이 폴더 시각으로 잰 에폭이 이보다 빠르면 잰 게 아니라 복사된 것이다
ENDED_SEC = 30 * 60   # 이 시간 넘으면 '멎은 것'이 아니라 '끝난 것'
#   ⚠둘을 나눈 이유: 조기종료(patience)로 끝난 run은 total보다 적은 에폭에서 멈춘다.
#   시간 기준이 없으면 몇 달 전에 정상 종료된 학습까지 전부 "멈춤 경고"로 뜬다.

MAX_DEPTH = 4         # runs 폴더 아래로 이만큼만 내려간다
#   ⚠없으면 사용자가 프로젝트 루트를 가리켰을 때 데이터셋 수만 장까지 훑는다.

SKIP_DIRS = {         # 학습 폴더 안에 있지만 results.csv가 있을 리 없는 곳
    "images", "labels", "weights", "dataset", "datasets",
    ".git", ".venv", "node_modules", "__pycache__",
}



@dataclass
class Run:
    name: str
    path: Path
    epoch: int              # 완료된 에폭 수
    total: int | None       # args.yaml의 epochs
    elapsed: float          # 누적 초
    eta: float | None       # 남은 초 (도는 중일 때만)
    metric: float | None
    metric_name: str
    best: float | None
    best_epoch: int | None
    state: str              # starting | running | stalled | failed | stopped | done
    idle: float             # 마지막 기록 이후 지난 초
    #   ★원격 run은 저쪽 기계 시계로 잰 값이다. 이쪽 시계와 빼면 안 된다
    #   (두 기계 시각이 몇 초만 어긋나도 상태가 엉뚱하게 나온다).
    history: list[float] = field(default_factory=list)   # 지표 추이 (스파크라인용)
    source: str = "local"
    framework: str = "ultralytics"      # 어느 어댑터가 읽었나 (ultralytics·huggingface·lightning·keras)
    meta: dict = field(default_factory=dict)   # 사람이 붙인 별표·태그·메모 (agent가 /runs에 실어 보낸다)
    lower: bool | None = None     # None이면 metric_higher·열 이름으로 정한다(__post_init__). best가 '낮을수록 좋은' 점수인가. 목표 알림·순위·화면이 이것을 본다(저장된 설정이 아니라 실제로 쓴 방향)
    updated: float = 0.0    # 정렬용. 원격은 저쪽 시각이라 표시에 쓰지 않는다
    format_warnings: list[str] = field(default_factory=list)   # 못 알아본 열·버전(adapters). 화면은 작은 배지로
    metric_higher: bool = True     # 대표 점수가 높을수록 좋은가(schema.higher_is_better).
    #   ★화면이 열 이름을 다시 해석하지 않게 여기서 실어 보낸다. 기본 True: 이 필드가 없던 옛 agent(원격·SSH)의
    #   응답을 from_dict로 읽을 때, 지금까지 화면이 쓰던 "높을수록 좋다" 가정을 그대로 유지한다.

    def __post_init__(self):
        if self.lower is None:     # 방향을 안 준 Run(시험·옛 코드): metric_higher가 False면 그대로, 아니면 열 이름으로
            self.lower = (not self.metric_higher) or (
                not schema.higher_is_better(self.metric_name) if self.metric_name else False)
        self.metric_higher = not self.lower

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["path"] = str(self.path)
        d["display"] = display_name(self)       # 모든 화면이 같은 이름을 쓰게(★폰 알림·트레이·맥 알림은 'train'만 보였다)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Run":
        known = {f.name for f in fields(cls)}
        d = {k: v for k, v in d.items() if k in known}   # agent 버전이 달라도 견딘다
        d["path"] = Path(d.get("path", ""))
        # 방향은 두 이름(lower·metric_higher)으로 오간다. 한쪽만 보낸 옛 agent면 다른 쪽을 맞춘다
        if "lower" in d and "metric_higher" not in d:
            d["metric_higher"] = not d["lower"]
        elif "metric_higher" in d and "lower" not in d:
            d["lower"] = not d["metric_higher"]
        return cls(**d)

    @property
    def progress(self) -> float | None:
        if not self.total:
            return None
        return min(self.epoch / self.total, 1.0)


# ── 파일 읽기 ──────────────────────────────────────

def _read_total_epochs(run_dir: Path) -> int | None:
    """args.yaml에서 epochs만. yamlish(PyYAML 있으면 그것, 없으면 표준 라이브러리 파서)"""
    from . import yamlish
    try:
        text = (run_dir / "args.yaml").read_text(encoding="utf-8", errors="ignore")
        data, _ = yamlish.load(text)
        return int(float(data.get("epochs"))) if isinstance(data, dict) and data.get("epochs") not in (None, "") else None
    except (OSError, ValueError, TypeError):
        return None


from .scan_names import display_name, fmt_dur, unique  # noqa: E402,F401  (옛 import 경로 유지)

_pick_metric = schema.pick_metric      # 옛 이름(윈도우 쪽 코드·시험이 부른다)


def _to_float(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


@dataclass
class _Parsed:
    """results.csv 한 번 읽은 결과. mtime이 그대로면 재사용한다."""
    epoch: int
    elapsed: float
    metric: float | None
    metric_name: str
    metric_higher: bool
    best: float | None
    best_epoch: int | None
    diverged: bool
    history: list[float]
    lower: bool = False            # 대표 점수가 낮을수록 좋은가(= not metric_higher. 사람이 고른 방향 또는 열 이름으로 추정)
    epoch_sec: float | None = None     # 최근 에폭 한 번에 걸린 시간(중앙값). 멈춤 판정·ETA가 쓴다


def recent_epoch_sec(rows: list[dict], n: int = 10) -> float | None:
    """최근 n에폭의 에폭당 시간 중앙값(누적 time 열의 차이). 시간 열이 없거나 2행 미만이면 None"""
    ts = [t for t in (_to_float(r.get("time")) for r in rows[-(n + 1):]) if t is not None]
    d = sorted(b - a for a, b in zip(ts, ts[1:]) if b > a)
    return d[len(d) // 2] if d else None


def stall_limits(epoch_sec: float | None) -> tuple[float, float]:
    """(멈춤, 끝남) 문턱 초. ★예전엔 모두 3분 고정이라 에폭이 3분 넘는 보통 학습이 매 에폭 "멈춤" 알림을 냈다.
    이제 그 학습의 최근 에폭 시간의 3배(끝남은 10배). 사용자 설정(stall_min)은 바닥값으로 남는다"""
    stale, ended = STALE_SEC, ENDED_SEC
    if epoch_sec:
        stale = max(stale, 3 * epoch_sec + 60)
        ended = max(ended, 10 * epoch_sec)
    return stale, ended


@dataclass
class _Meta:
    """요약에 필요한 것만. ★예전엔 어댑터가 읽은 것(모든 에폭의 모든 행)을 통째로 캐시에 들고 있어서
    학습 2,000개에서 agent 메모리가 583MB였다(그중 497MB가 CSV 행). 쓰는 건 이 넷뿐이다"""
    source: Path
    framework: str
    total: int | None          # args.yaml의 epochs(없으면 어댑터가 찾은 값)
    updated: float             # 기록 파일의 수정 시각


# 학습 폴더 → (기록 파일, (mtime, size), 요약, 메타)
_cache: dict[Path, tuple[Path, tuple, _Parsed, _Meta]] = {}      # (기록 파일, (mtime, size, 폴더 mtime), 요약, 메타)


_ov: tuple[float, tuple, dict[str, tuple[str, bool]]] = (0.0, (), {})     # (확인 시각, 서명, 키 → (열, 낮을수록))


def _overrides() -> dict[str, tuple[str, bool]]:
    """사람이 고른 대표 점수(runmeta의 metric·lower). agent가 저장하면 바로(runmeta.VERSION),
    손으로 파일을 고친 것은 1초 안에(파일 시각) 다시 읽는다. ★학습마다 파일을 stat하지 않게"""
    global _ov
    from . import runmeta
    now = time.time()
    path = str(runmeta.FILE)
    if _ov[1][:2] == (path, runmeta.VERSION) and now - _ov[0] < 1.0:
        return _ov[2]
    try:
        mt = runmeta.FILE.stat().st_mtime_ns
    except OSError:
        mt = 0
    sig = (path, runmeta.VERSION, mt)
    data = _ov[2] if sig == _ov[1] else {
        k: (m["metric"], bool(m.get("lower"))) for k, m in runmeta.load().items() if m.get("metric")}
    _ov = (now, sig, data)
    return data


def _parse(run_dir: Path) -> tuple[_Parsed, _Meta] | None:
    """프레임워크 어댑터로 에폭별 행을 받아 요약한다. 원본 파일이 그대로면 다시 안 읽는다."""
    # ★기록 파일의 시각·크기부터 본다. 예전엔 파일을 통째로 읽은 뒤에 비교해서, 캐시가 있어도
    #   폴링마다 모든 학습의 CSV를 다시 읽었다(학습 200개·300에폭에서 한 번 훑는 데 370ms)
    # 폴더 자체의 수정 시각도 본다. ★Hugging Face는 새 체크포인트를 새 폴더(checkpoint-N)에 써서, 읽은 파일만 보면
    #   첫 체크포인트에서 멈춘 것처럼 보이다가 3분 뒤 '멎음' 알림(폰까지)을 보냈다. 폴더에 항목이 생기면 폴더 시각이 바뀐다
    try:
        dir_mtime = run_dir.stat().st_mtime
    except OSError:
        dir_mtime = None
    from .runmeta import key as meta_key
    ov = _overrides().get(meta_key(str(run_dir)))
    hit = _cache.get(run_dir)
    if hit:
        try:
            st = hit[0].stat()
            if (st.st_mtime, st.st_size, dir_mtime, ov) == hit[1]:
                return hit[2], hit[3]
        except OSError:
            pass
    a = adapters.detect(run_dir)
    if a is None:
        return None
    try:
        loaded = a.load(run_dir)
    except OSError:
        return None
    if loaded is None:
        return None
    csv_path = loaded.source
    try:
        st = csv_path.stat()
    except OSError:
        return None
    key = (st.st_mtime, st.st_size, dir_mtime, ov)
    rows =[r for r in loaded.rows if r.get("epoch")]
    if not rows:
        return None

    last = rows[-1]
    try:
        epoch = loaded.epoch if loaded.epoch is not None else int(float(last["epoch"]))
    except (ValueError, KeyError):
        return None

    # 사람이 고른 대표 점수가 있으면 그것(★손실·오류율처럼 낮을수록 좋은 것도 대표로 쓸 수 없었다).
    # 마지막 줄만 보지 않는다. ★Lightning·HF는 새 에폭의 첫 줄에 학습 값만 있어, 검증 전까지 점수가 사라지고 목표 알림이 멈췄다
    cols = list(last.keys()) + sorted({k for r in rows for k in r} - set(last.keys()))
    chosen = bool(ov and ov[0] in cols)
    mname = ov[0] if chosen else schema.pick_metric(cols)
    # 방향은 하나로 정한다: 고른 점수면 사람이 정한 방향, 자동이면 열 이름으로(schema.higher_is_better).
    # Run.lower(윈도우 쪽 이름)와 Run.metric_higher(맥 쪽 이름)는 늘 서로 반대값이다
    lower = bool(ov[1]) if chosen else (not schema.higher_is_better(mname) if mname else False)
    best = best_epoch = None
    if mname:
        vals = []
        for r in rows:
            v = _to_float(r.get(mname))
            if v is None:
                continue
            try:
                vals.append((v, int(float(r["epoch"]))))
            except (ValueError, KeyError):
                continue
        if vals:
            best, best_epoch = (min if lower else max)(vals, key=lambda t: t[0])

    # 발산 판정: 손실 계열 열 중 하나라도 NaN/inf면 실패로 본다
    diverged = any(
        _to_float(v) is None
        for k, v in last.items()
        if k.endswith("_loss") and v not in ("", None)
    )

    hist = []
    if mname:
        hist = [v for v in (_to_float(r.get(mname)) for r in rows[-60:]) if v is not None]

    parsed = _Parsed(
        epoch=epoch,
        history=hist,
        elapsed=_to_float(last.get("time")) or 0.0,
        metric=next((v for v in (_to_float(r.get(mname)) for r in reversed(rows)) if v is not None), None) if mname else None,
        metric_name=mname or "",
        metric_higher=not lower, lower=lower,
        best=best, best_epoch=best_epoch, diverged=diverged,
        epoch_sec=recent_epoch_sec(rows),
    )
    if not parsed.elapsed:                     # 시간 열이 없는 프레임워크: 폴더가 생긴 뒤 흐른 시간
        try:
            born = getattr(run_dir.stat(), "st_birthtime", None) or min(p.stat().st_mtime for p in run_dir.iterdir())
            parsed.elapsed = max(st.st_mtime - born, 0.0)
        except (OSError, ValueError):
            pass
        # ★다른 기계에서 복사해 온 폴더는 모든 파일이 한 순간에 생겨 에폭당 0초·남은 시간 0초로 보였다. 모름으로 둔다
        if parsed.epoch and parsed.elapsed < parsed.epoch * MIN_EPOCH_SEC:
            parsed.elapsed = 0.0
    # args.yaml은 학습 중에 안 바뀐다. 기록 파일이 바뀔 때만 다시 읽는다(★예전엔 폴링마다 전부 다시 읽었다)
    meta = _Meta(csv_path, loaded.framework, _read_total_epochs(run_dir) or loaded.total, st.st_mtime)
    _cache[run_dir] = (csv_path, key, parsed, meta)
    return parsed, meta


def _stale_after(p: "_Parsed", total: int | None) -> float:
    """'멎음'으로 볼 조용한 시간. 한 에폭에 걸리는 시간에 맞춘다.
    ★고정 3분이라, 에폭(또는 HF 체크포인트) 사이가 3분 넘는 학습은 매 에폭 '멎음'(급한 소리·폰 알림)과 '다시 돎'이 번갈아 떴다.
      계획 에폭을 모르면(Keras·Lightning) 끝난 것과 멎은 것을 구별할 수 없어 더 넉넉히 기다린다"""
    per_epoch = p.epoch_sec or (p.elapsed / p.epoch if p.epoch and p.elapsed else 0.0)   # 최근 에폭 중앙값이 있으면 그것
    if total:
        return max(STALE_SEC, per_epoch * 1.5)
    # 계획 에폭을 모르면 stall_limits(최근 에폭의 3배+1분)와 누적 평균의 3배 중 큰 쪽
    return max(stall_limits(p.epoch_sec)[0], per_epoch * 3)


def read_run(run_dir: Path, now: float | None = None) -> Run | None:
    now = time.time() if now is None else now
    got = _parse(run_dir)
    p, loaded = got if got else (None, None)

    if p is None:
        # ★results.csv는 1에폭이 끝나야 생긴다. 그 전에도 '시작했다'를 보여 준다.
        #   args.yaml은 학습이 뜨는 즉시 만들어진다.
        args = run_dir / "args.yaml"
        if not args.exists():
            return None
        try:
            born = args.stat().st_mtime
        except OSError:
            return None
        idle = max(now - born, 0.0)
        if idle > ENDED_SEC:
            return None          # 옛날에 죽은 껍데기 폴더는 무시
        return Run(
            name=unicodedata.normalize("NFC", run_dir.name), path=run_dir,
            epoch=0, total=_read_total_epochs(run_dir), elapsed=idle, eta=None,
            metric=None, metric_name="", metric_higher=True, best=None, best_epoch=None,
            state="starting", idle=idle, updated=born, history=[],
        )

    updated = loaded.updated                    # _parse가 이미 잰 수정 시각(★같은 파일을 두 번 stat했다)
    idle = max(now - updated, 0.0)
    total = loaded.total

    per = p.epoch_sec or ((p.elapsed / p.epoch) if p.epoch and p.elapsed else None)
    stale = _stale_after(p, total)
    ended = max(stall_limits(p.epoch_sec)[1], stale * 3)   # 끝남: 최근 에폭의 10배와 멎음 문턱의 3배 중 큰 쪽
    if p.diverged:
        state = "failed"
    elif (total and p.epoch >= total) or (run_dir / "epokio_done").exists():
        # epokio_done: epokio.start() 기록기가 끝날 때 남긴다. ★총 에폭을 모르거나 일찍 멈춘 직접 짠 학습이
        #   끝나고 3분 뒤 '멎음' 알림(폰까지)을 받았다
        state = "done"
    elif idle > ended:
        state = "stopped"     # 조기종료했거나 사람이 껐다
    elif idle > stale:
        state = "stalled"     # 방금까지 돌다 멎었다, 이게 진짜 경고다
    else:
        state = "running"

    eta = None
    if state == "running" and total and per:
        eta = per * max(total - p.epoch, 0)                  # 최근 에폭 기준(초반 느린 에폭에 끌려가지 않게)

    return Run(
        name=unicodedata.normalize("NFC", run_dir.name),
        path=run_dir, epoch=p.epoch, total=total, elapsed=p.elapsed, eta=eta,
        metric=p.metric, metric_name=p.metric_name, metric_higher=p.metric_higher, lower=p.lower,
        best=p.best, best_epoch=p.best_epoch,
        state=state, idle=idle, updated=updated, history=p.history, framework=loaded.framework,
        format_warnings=list(getattr(loaded, "warnings", []) or []),
    )


def _walk(root: Path, depth: int):
    """results.csv를 가진 폴더만 찾는다. 데이터셋 폴더로 내려가지 않는다."""
    if depth < 0:
        return
    try:
        with os.scandir(root) as it:           # scandir은 폴더인지를 목록과 같이 준다(★is_dir()이 항목마다 stat을 했다)
            entries = list(it)
    except OSError:
        return
    names = {e.name for e in entries}
    if adapters.detect(root, names):
        yield root
        return                      # run 폴더 안으로는 더 안 들어간다
    for e in entries:
        try:
            is_dir = e.is_dir()
        except OSError:
            continue
        if is_dir and e.name not in SKIP_DIRS and not e.name.startswith("."):
            yield from _walk(Path(e.path), depth - 1)


STATE_ORDER = {"running": 0, "starting": 1, "stalled": 2, "failed": 3, "stopped": 4, "done": 5}


def sort_runs(runs: list[Run]) -> list[Run]:
    return sorted(runs, key=lambda r: (STATE_ORDER.get(r.state, 9), r.idle))


def scan(root: Path, now: float | None = None, max_depth: int = MAX_DEPTH) -> list[Run]:
    runs = []
    # 이 폴더 아래에서 사라진 학습의 요약은 버린다(★지운 학습이 캐시에 영원히 남았다)
    seen = set()
    for d in _walk(root, max_depth):
        seen.add(d)
        r = read_run(d, now=now)
        if r:
            runs.append(r)
    for gone in [d for d in _cache if d not in seen and root in d.parents]:
        _cache.pop(gone, None)
    return sort_runs(runs)

