"""results.csv를 읽어 학습 상태를 만든다. 순수 계산, 화면·네트워크와 무관."""
from __future__ import annotations

import logging
import os
import time
import unicodedata
from dataclasses import dataclass, field, fields
from pathlib import Path

from . import adapters, schema
from .schema import is_loss_column

STALE_SEC = 180       # 이 시간 넘게 안 변하면 진행 중이 아니다
COPY_SPREAD_SEC = 0.05   # 시간 열 없이 폴더 시각으로 잰 학습 전체가 이보다 짧으면 잰 게 아니라 복사된 것이다(파일이 한 순간에 생김)
ENDED_SEC = 30 * 60   # 이 시간 넘으면 '멎은 것'이 아니라 '끝난 것'
#   ⚠둘을 나눈 이유: 조기종료(patience)로 끝난 run은 total보다 적은 에폭에서 멈춘다.
#   시간 기준이 없으면 몇 달 전에 정상 종료된 학습까지 전부 "멈춤 경고"로 뜬다.

MAX_DEPTH = 4         # runs 폴더 아래로 이만큼만 내려간다. ⚠없으면 프로젝트 루트를 가리켰을 때 데이터셋 수만 장까지 훑는다

SKIP_DIRS = {         # 학습 폴더 안에 있지만 results.csv가 있을 리 없는 곳
    "images", "labels", "weights", "dataset", "datasets", ".git", ".venv", "node_modules", "__pycache__",
}
# 지켜보는 폴더 → 윈도우 경로 260자 제한에 걸려 못 읽은 폴더. /runs가 slow_roots로 알린다(LongPathsEnabled가 꺼진 기본 윈도우)
TOO_LONG: dict[str, list[str]] = {}


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
    idle: float             # 마지막 기록 이후 지난 초. ★원격 run은 저쪽 시계로 잰 값이라 이쪽 시계와 빼면 안 된다
    history: list[float] = field(default_factory=list)   # 지표 추이 (스파크라인용)
    source: str = "local"
    framework: str = "ultralytics"      # 어느 어댑터가 읽었나 (ultralytics·huggingface·lightning·keras)
    meta: dict = field(default_factory=dict)   # 사람이 붙인 별표·태그·메모 (agent가 /runs에 실어 보낸다)
    lower: bool | None = None     # None이면 metric_higher·열 이름으로 정한다(__post_init__). best가 '낮을수록 좋은' 점수인가. 목표 알림·순위·화면이 이것을 본다(저장된 설정이 아니라 실제로 쓴 방향)
    updated: float = 0.0    # 정렬용. 원격은 저쪽 시각이라 표시에 쓰지 않는다
    format_warnings: list[str] = field(default_factory=list)   # 못 알아본 열·버전(adapters). 화면은 작은 배지로
    metric_higher: bool = True     # 대표 점수가 높을수록 좋은가. ★화면이 열 이름을 다시 해석하지 않게 실어 보낸다.
    #   기본 True: 이 필드가 없던 옛 agent(원격·SSH) 응답을 from_dict로 읽을 때 예전 가정("높을수록 좋다") 그대로.
    x_axis: str = "epoch"          # "step"이면 epoch·total·best_epoch가 step 번호다(W&B·TensorBoard·CSV의 step 기록). 화면은 단위만 바꾼다
    error: str = ""                # 실패 이유("RuntimeError: CUDA out of memory"). epokio.start()가 예외로 죽었을 때
    resumed_from: str = ""         # 이 학습이 이어 한 앞 학습 폴더(Lightning version_1 ← version_0). 앞 것은 알림을 안 낸다
    fraction: float | None = None  # 에폭보다 잘게 아는 끝낸 몫(HF global_step/max_steps). 진행 막대가 쓴다

    def __post_init__(self):
        if self.lower is None:     # 방향을 안 준 Run(시험·옛 코드): metric_higher가 False면 그대로, 아니면 열 이름으로
            self.lower = (not self.metric_higher) or (
                not schema.higher_is_better(self.metric_name) if self.metric_name else False)
        self.metric_higher = not self.lower

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["path"] = str(self.path)
        d["display"] = display_name(self)       # 모든 화면이 같은 이름을 쓰게(★폰 알림·트레이·맥 알림은 'train'만 보였다)
        for k in ("metric", "best"):            # ★API가 0.8200000000000001 같은 부동소수 찌꺼기를 그대로 냈다
            if isinstance(d.get(k), float):
                d[k] = round(d[k], 6)
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
        done = min(self.epoch / self.total, 1.0) if self.total else None
        f = self.fraction                  # ★HF 첫 에폭 내내 0%인데 남은 시간은 나왔다
        return max(done, f) if done is not None and done < 1 and f is not None and 0 < f < 1 else done


# ── 파일 읽기 ──────────────────────────────────────

from .scan_names import STATE_ORDER, alias_of_sibling, crash_reason, display_name, find_override, fmt_dur, sort_runs, too_long, unique  # noqa: E402,F401  (옛 import 경로 유지)
from .scan_timing import _read_total_epochs, _to_float, args_rewritten, fitness_epoch, patience_stop, longest_gap_sec, recent_epoch_sec, recent_unit_sec  # noqa: E402,F401,E501

_pick_metric = schema.pick_metric      # 옛 이름(윈도우 쪽 코드·시험이 부른다)


@dataclass
class _Parsed:
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
    epoch_sec: float | None = None     # 최근 기록 한 줄 사이의 시간(중앙값). 멈춤 판정이 쓴다
    unit_sec: float | None = None      # 최근 에폭(step 축이면 step) 하나에 걸린 시간(중앙값). ETA가 쓴다
    gap_sec: float | None = None       # 최근 줄 사이 가장 긴 간격(긴 평가·저장). 멎음 문턱이 쓴다
    frac: float | None = None          # 끝낸 몫(0~1, HF global_step/max_steps). 첫 에폭이 안 끝나도 남은 시간을 낸다
    fit_epoch: int | None = None       # best.pt 에폭(patience 판정. 사람이 고른 대표 점수와 무관)


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
    """요약에 필요한 것만. ★어댑터가 읽은 행을 통째로 캐시에 들고 있어 학습 2,000개에서 agent 메모리가 583MB였다"""
    source: Path
    framework: str
    total: int | None          # args.yaml의 epochs(없으면 어댑터가 찾은 값). step 축이면 계획 step 수
    updated: float             # 기록 파일의 수정 시각
    x_axis: str = "epoch"
    resumed_from: str = ""     # 이어 한 앞 학습 폴더 이름(Lightning version_N)


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
    # ★기록 파일의 시각·크기부터 본다(파일을 다 읽은 뒤 비교해 폴링마다 모든 CSV를 다시 읽었다, 학습 200개에 370ms)
    # 폴더 자체의 수정 시각도 본다. ★Hugging Face는 새 체크포인트를 새 폴더(checkpoint-N)에 써서, 읽은 파일만 보면
    #   첫 체크포인트에서 멈춘 것처럼 보이다가 3분 뒤 '멎음' 알림(폰까지)을 보냈다. 폴더에 항목이 생기면 폴더 시각이 바뀐다
    try:
        dir_mtime = run_dir.stat().st_mtime
    except OSError:
        dir_mtime = None
    from .runmeta import key as meta_key
    ov = find_override(_overrides(), run_dir, meta_key)   # 그 학습, 없으면 위 폴더에 정한 기본값
    hit = _cache.get(run_dir)
    if hit:
        try:
            st = hit[0].stat()
            if (st.st_mtime, st.st_size, dir_mtime, ov) == hit[1] and time.time() - st.st_mtime > 2.0:   # ★방금 바뀐 파일은 시각·크기가 같아도 다시(아래 _read_csv)
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
    axis = "step" if (loaded.args or {}).get("x_axis") == "step" else "epoch"
    rows = [r for r in loaded.rows if r.get("epoch")]
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
    # 방향: 고른 점수면 사람이 정한 방향, 자동이면 학습이 적은 방향이나 열 이름(schema.lower_for). lower와 metric_higher는 늘 반대
    lower = bool(ov[1]) if chosen else schema.lower_for(mname, loaded.args)
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
        fi = None if chosen else schema.fitness_index(rows, mname)    # ★분할·포즈·분류는 best.pt를 고른 값(박스 점수와 더함)으로
        if fi is not None:
            best, best_epoch = _to_float(rows[fi].get(mname)), int(float(rows[fi]["epoch"]))

    # 발산 판정: 손실 계열 열 중 하나라도 NaN/inf면 실패로 본다
    diverged = any(
        _to_float(v) is None
        for k, v in last.items()
        if is_loss_column(k) and v not in ("", None)
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
        best=best, best_epoch=best_epoch, diverged=diverged, fit_epoch=fitness_epoch(rows, schema.pick_metric(cols)) if chosen else best_epoch,
        epoch_sec=recent_epoch_sec(rows), unit_sec=recent_unit_sec(rows), gap_sec=longest_gap_sec(rows), frac=loaded.fraction,
    )
    if not parsed.elapsed:                     # 시간 열이 없는 프레임워크: 폴더가 생긴 뒤 흐른 시간
        try:
            born = getattr(run_dir.stat(), "st_birthtime", None) or min(p.stat().st_mtime for p in run_dir.iterdir())
            parsed.elapsed = max(st.st_mtime - born, 0.0) if st.st_mtime < time.time() + 3600 else 0.0   # ★미래 시각 파일(시계가 뒤로 감)이 "3285d left"
        except (OSError, ValueError):
            pass
        # ★복사본은 파일이 한 순간에 생겨 0초로 보였다(모름으로). '에폭 x 1초'로 가르면 빠른 진짜 학습도 시간이 비었다.
        #   step 축도 같다: HF 폴더와 trainer_state.json이 거의 같이 생기면 진행 중인 학습이 "0s left"였다(2026-10-10)
        if parsed.epoch and parsed.elapsed < COPY_SPREAD_SEC:
            parsed.elapsed = 0.0
    # args.yaml은 기록 파일이 바뀔 때만 다시 읽는다. step 축이면 args.yaml의 epochs는 단위가 달라 안 본다
    meta = _Meta(csv_path, loaded.framework, loaded.total if axis == "step" else (_read_total_epochs(run_dir) or loaded.total), st.st_mtime, axis,
                 str((loaded.args or {}).get("resumed_from") or ""))
    _cache[run_dir] = (csv_path, key, parsed, meta)
    return parsed, meta


def _stale_after(p: "_Parsed", total: int | None) -> float:
    """'멎음'으로 볼 조용한 시간. 한 에폭에 걸리는 시간에 맞춘다.
    ★고정 3분이라, 에폭(또는 HF 체크포인트) 사이가 3분 넘는 학습은 매 에폭 '멎음'(급한 소리·폰 알림)과 '다시 돎'이 번갈아 떴다.
      계획 에폭을 모르면(Keras·Lightning) 끝난 것과 멎은 것을 구별할 수 없어 더 넉넉히 기다린다"""
    per_epoch = p.epoch_sec or (p.elapsed / p.epoch if p.epoch and p.elapsed else 0.0)   # 최근 에폭 중앙값이 있으면 그것
    gap = (p.gap_sec or 0.0) * 1.25                  # 주기적인 긴 평가·저장보다는 길게
    if total:
        return max(STALE_SEC, per_epoch * 1.5, gap)
    # 계획 에폭을 모르면 stall_limits(최근 에폭의 3배+1분)와 누적 평균의 3배 중 큰 쪽
    return max(stall_limits(p.epoch_sec)[0], per_epoch * 3, gap)


def read_run(run_dir: Path, now: float | None = None) -> Run | None:
    now = time.time() if now is None else now
    got = _parse(run_dir)
    p, loaded = got if got else (None, None)

    if p is None:
        # ★results.csv는 1에폭이 끝나야 생긴다. 그 전에도 '시작했다'를 보여 준다(args.yaml은 뜨자마자 생긴다)
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

    updated = max(loaded.updated, args_rewritten(run_dir, loaded.updated) if loaded.framework == "ultralytics" else 0.0)   # 수정 시각(_parse가 잼) 또는 이어 하기로 다시 쓴 args.yaml
    idle = max(now - updated, 0.0)
    total = loaded.total

    per = p.unit_sec or ((p.elapsed / p.epoch) if p.epoch and p.elapsed else None)
    stale = _stale_after(p, total)
    ended = max(stall_limits(p.epoch_sec)[1], stale * 3)   # 끝남: 최근 에폭의 10배와 멎음 문턱의 3배 중 큰 쪽
    error = crash_reason(run_dir)               # epokio.start()가 예외로 죽으며 남긴 이유(★3분 뒤 '멎음'으로만 보였다)
    if p.diverged or error:
        state = "failed"
    elif (total and p.epoch >= total) or (run_dir / "epokio_done").exists():
        # epokio_done: epokio.start()가 끝날 때 남긴다(★총 에폭을 모르는 직접 짠 학습이 끝나고 3분 뒤 '멎음' 알림을 받았다)
        state = "done"
    elif idle > stale and loaded.framework == "ultralytics" and patience_stop(run_dir, p.epoch, p.fit_epoch, total):
        state = "done"        # patience로 정상 조기 종료(멎음 경고가 아니다)
    elif idle > ended:
        state = "stopped"     # 조기종료했거나 사람이 껐다
    elif idle > stale:
        state = "stalled"     # 방금까지 돌다 멎었다, 이게 진짜 경고다
    else:
        state = "running"

    eta = None
    if state == "running" and total and per:
        eta = per * max(total - p.epoch, 0)                  # 최근 칸 기준(초반 느린 에폭에 끌려가지 않게)
    elif state == "running" and p.frac and 0 < p.frac < 1 and p.elapsed >= 30:   # 막 생긴 폴더(경과 0초)면 '0초 남음'이 됐다   # ★3에폭 LLM 미세 조정이 첫 에폭 내내 '0/3, – 남음'
        eta = p.elapsed * (1 - p.frac) / p.frac

    return Run(
        name=unicodedata.normalize("NFC", run_dir.name),
        path=run_dir, epoch=p.epoch, total=total, elapsed=p.elapsed, eta=eta,
        metric=p.metric, metric_name=p.metric_name, metric_higher=p.metric_higher, lower=p.lower,
        best=p.best, best_epoch=p.best_epoch,
        state=state, idle=idle, updated=updated, history=p.history, framework=loaded.framework,
        format_warnings=list(getattr(loaded, "warnings", []) or []), x_axis=loaded.x_axis, error=error or "",
               resumed_from=loaded.resumed_from, fraction=p.frac)


def _walk(root: Path, depth: int, long: list | None = None):
    if depth < 0:
        return
    try:
        with os.scandir(root) as it:           # scandir은 폴더인지를 목록과 같이 준다(★is_dir()이 항목마다 stat을 했다)
            entries = list(it)
    except OSError:
        if long is not None and too_long(root):
            long.append(str(root))         # ★WinError 3을 삼켜 260자를 넘는 학습 폴더가 말없이 사라졌다
        return
    names = {e.name for e in entries}
    found = adapters.detect(root, names)
    if found and found.name != "custom":
        yield root
        return                      # run 폴더 안으로는 더 안 들어간다
    kids = []
    for e in entries:
        try:
            is_dir = e.is_dir()
        except OSError:
            continue
        if is_dir and e.name not in SKIP_DIRS and not e.name.startswith(".") and not (e.is_symlink() and alias_of_sibling(Path(e.path), root)):
            kids.extend(_walk(Path(e.path), depth - 1, long))
    # ★이름 무관 CSV만 있는 폴더는 아래에 학습이 없을 때만 학습(runs/loss_summary.csv가 아래 학습 8개를 1개로 만들었다)
    yield from (kids or ([root] if found else []))


_broken: set[Path] = set()      # 읽다 예외가 난 학습 폴더(경고는 한 번만)


def scan(root: Path, now: float | None = None, max_depth: int = MAX_DEPTH) -> list[Run]:
    runs, long = [], []
    # 이 폴더 아래에서 사라진 학습의 요약은 버린다(★지운 학습이 캐시에 영원히 남았다)
    seen = set()
    for d in _walk(root, max_depth, long):
        seen.add(d)
        try:
            r = read_run(d, now=now)
        except Exception as ex:   # ★기록 하나가 깨지면 예외가 폴더 전체로 올라가 정상 학습까지 다 사라지고 "느림"으로 보였다
            if d not in _broken:
                _broken.add(d)
                logging.getLogger("epokio").warning("skipped %s: %s: %s", d, type(ex).__name__, ex)
            continue
        _broken.discard(d)
        if r:
            runs.append(r)
        elif too_long(d):
            long.append(str(d))                 # 폴더는 열리는데 그 안 파일 경로가 260자를 넘는다
    TOO_LONG[str(root)] = long
    for gone in [d for d in _cache if d not in seen and root in d.parents]:
        _cache.pop(gone, None)
    return sort_runs(runs)

