"""기록 줄의 시간으로 한 칸(에폭, step 축이면 step)에 걸린 시간을 잰다. scan에서 재수출한다(400줄 규칙으로 나눔)."""
from __future__ import annotations

import math


def _to_float(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def recent_epoch_sec(rows: list[dict], n: int = 10) -> float | None:
    """최근 n에폭의 에폭당 시간 중앙값(누적 time 열의 차이). 시간 열이 없거나 2행 미만이면 None"""
    ts = [t for t in (_to_float(r.get("time")) for r in rows[-(n + 1):]) if t is not None]
    d = sorted(b - a for a, b in zip(ts, ts[1:]) if b > a)
    return d[len(d) // 2] if d else None


def longest_gap_sec(rows: list[dict]) -> float | None:
    """기록 전체에서 두 번 이상 나온 긴 간격(두 번째로 긴 간격). ★중앙값만 보면 5에폭마다 6분씩 평가하는 학습(에폭은 1분)이
    평가할 때마다 '멎음'(급한 폰 알림)이 됐다(2026-10-10 외부 검토). 최근 20줄의 최댓값을 썼더니 25에폭마다 하는 평가는
    창 밖으로 밀려 다시 울렸고, 한 번뿐인 40분 지연(NFS 멈춤)이 다음 20에폭 동안 멎음 감지를 50분으로 늦췄다.
    두 번째로 긴 간격은 되풀이되는 평가만 잡고 한 번뿐인 이상치는 건너뛴다"""
    ts = [t for t in (_to_float(r.get("time")) for r in rows) if t is not None]
    d = sorted(b - a for a, b in zip(ts, ts[1:]) if b > a)
    return d[-2] if len(d) >= 2 else None


def recent_unit_sec(rows: list[dict], n: int = 10) -> float | None:
    """최근 n줄에서 진행 한 칸(에폭, step 축이면 step)에 걸린 시간의 중앙값: 시간 차이 / epoch 열 차이.
    ★ETA가 줄 사이 시간에 남은 칸 수를 곱해서, 100 step마다 기록하는 step 학습은 남은 시간이 100배로 나왔다
      (15분이 "1d 1h")."""
    pts = [(_to_float(r.get("time")), _to_float(r.get("epoch"))) for r in rows[-(n + 1):]]
    pts = [(t, x) for t, x in pts if t is not None and x is not None]
    d = sorted((t2 - t1) / (x2 - x1) for (t1, x1), (t2, x2) in zip(pts, pts[1:]) if t2 > t1 and x2 > x1)
    return d[len(d) // 2] if d else None


def _read_total_epochs(run_dir) -> int | None:
    """args.yaml에서 epochs만. yamlish(PyYAML 있으면 그것, 없으면 표준 라이브러리 파서)"""
    return _arg_int(run_dir, "epochs")


def _arg_int(run_dir, key: str) -> int | None:
    from . import yamlish
    try:
        text = (run_dir / "args.yaml").read_text(encoding="utf-8", errors="ignore")
        data, _ = yamlish.load(text)
        return int(float(data.get(key))) if isinstance(data, dict) and data.get(key) not in (None, "") else None
    except (OSError, ValueError, TypeError):
        return None


def args_rewritten(run_dir, since: float) -> float:
    """Ultralytics가 이어 하기로 다시 뜰 때 args.yaml을 새로 쓴다(resume: <last.pt>). 기록 파일(since)보다 새것이고
    resume이 적혀 있으면 그 시각, 아니면 0. resume을 보는 까닭: 폴더를 복사하면 args.yaml이 늦게 생겨도 이어 한 게 아니다.
    ★터미널에서 이어 한 학습이 첫 에폭이 끝날 때까지 '중단됨'으로 보였고 '이어 하기' 단추가 두 번째 학습을 같은 폴더에 붙였다"""
    try:
        t = (run_dir / "args.yaml").stat().st_mtime
    except OSError:
        return 0.0
    if t <= since + 5:
        return 0.0
    from . import yamlish
    try:
        data, _ = yamlish.load((run_dir / "args.yaml").read_text(encoding="utf-8", errors="ignore"))
    except (OSError, ValueError):
        return 0.0
    r = data.get("resume") if isinstance(data, dict) else None
    return t if r not in (None, False, "", "False", "false", "None", "null") else 0.0


def patience_stop(run_dir, epoch: int, best_epoch: int | None, total: int | None) -> bool:
    """Ultralytics patience 조기 종료로 끝났나(EarlyStopping: 지금 에폭 - 최고 에폭 >= patience면 멈춘다).
    기록이 멎은 뒤에만 부른다. ★정상 조기 종료가 '멎음'(급함)과 '마지막 에폭 전에 멈춤' 두 알림으로 갔다"""
    if not (total and best_epoch and epoch < total):
        return False
    patience = _arg_int(run_dir, "patience")
    return bool(patience and patience > 0 and epoch - best_epoch >= patience)


def fitness_epoch(rows: list[dict], auto: str | None) -> int | None:
    """Ultralytics가 best.pt·patience에 쓰는 최고 에폭(사람이 고른 대표 점수와 무관하게 자동 점수로).
    ★고른 열(val/box_loss 등)의 최고 에폭으로 patience를 재서, 멈춘 학습이 '끝남'으로 알려졌다"""
    from . import schema
    if not auto:
        return None
    fi = schema.fitness_index(rows, auto)
    try:
        if fi is not None:
            return int(float(rows[fi]["epoch"]))
        vals = [(v, int(float(r["epoch"]))) for r in rows if (v := _to_float(r.get(auto))) is not None]
    except (KeyError, TypeError, ValueError):
        return None
    return (max if schema.higher_is_better(auto) else min)(vals, key=lambda t: t[0])[1] if vals else None
