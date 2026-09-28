"""학습 결과를 숫자와 사람 말로 요약한다. 기록 파일만 읽는다 (가벼움, 어댑터를 거친다).

자동 해설의 원칙
  1. 근거가 된 숫자를 같이 적는다. "과적합 같다"가 아니라 "17에폭 이후 val loss 0.8→1.1"
  2. 확실하지 않으면 '~일 수 있다'로. 틀린 단정이 제일 해롭다
  3. 해설마다 무엇을 해 보면 좋은지 한 줄을 붙인다
"""
from __future__ import annotations

from .msg import tr

import math
from dataclasses import dataclass, field
from pathlib import Path

from .schema import HEADS, IMAGE_FILES, head_col, higher_is_better, kind, pick_metric


def _f(v):
    try:
        x = float(v)
        return None if math.isnan(x) or math.isinf(x) else x
    except (TypeError, ValueError):
        return None


def f1(p, r):
    if p is None or r is None or (p + r) == 0:
        return None
    return 2 * p * r / (p + r)


@dataclass
class HeadStats:
    head: str                     # "B" | "P" | "M"
    best_epoch: int
    precision: float | None
    recall: float | None
    f1: float | None
    map50: float | None
    map5095: float | None


@dataclass
class Analysis:
    run_dir: Path
    epochs: int
    heads: list[HeadStats]
    notes: list[tuple[str, str]]      # (관찰, 해 볼 것)
    images: dict[str, Path]           # 곡선·혼동행렬 등 이미 있는 그림
    kinds: list[dict] = field(default_factory=list)   # notes와 같은 순서: 어떤 규칙인지 + 다음 학습 제안에 쓸 값(next_run)
    score: dict | None = None         # 대표 점수 {"metric", "value", "best_epoch"}. YOLO 밖(HF·Lightning·Keras)도 채운다


def _load(run_dir: Path) -> list[dict]:
    """에폭별 행. 프레임워크마다 다른 기록 파일을 어댑터가 같은 모양으로 바꿔 준다."""
    from . import adapters
    got = adapters.load(run_dir)
    return got.rows if got else []


def _col(rows, name):
    return [_f(r.get(name)) for r in rows]


def head_stats(rows, head) -> HeadStats | None:
    P = _col(rows, head_col("precision", head))
    R = _col(rows, head_col("recall", head))
    M50 = _col(rows, head_col("mAP50", head))
    M = _col(rows, head_col("mAP50-95", head))
    if not any(v is not None for v in M + M50):
        return None
    score = [m if m is not None else -1 for m in (M if any(M) else M50)]
    i = max(range(len(score)), key=lambda k: score[k])
    F = [f1(p, r) for p, r in zip(P, R)]
    ep = int(float(rows[i].get("epoch", i + 1)))
    return HeadStats(head, ep, P[i], R[i], F[i], M50[i], M[i])


# 과적합으로 볼 대표 점수 하락 폭(최고점 대비 상대). 이보다 작은 흔들림은 잡음으로 본다
OVERFIT_DROP = 0.05


def _score(rows) -> tuple[str, list[float | None], bool] | None:
    """대표 점수 열과 그 값들. schema.pick_metric이 고른다(YOLO는 공식 TASK2METRIC 열 = best.pt 저장 기준 fitness와
    같은 열. 설치된 ultralytics 8.4.150의 DetMetrics.fitness는 mAP50-95 가중치 1.0이다).
    HF eval_*, Lightning·Keras val_*도 어댑터가 metrics/로 옮겨 주므로 같은 길로 고른다. 손실 열은 대표 점수로 쓰지 않는다"""
    names = []
    for r in rows:
        names += [k for k in r if k not in names]
    name = pick_metric(names)
    if not name or kind(name) == "loss":
        return None
    vals = [_f(r.get(name)) for r in rows]
    if sum(v is not None for v in vals) < 2:
        return None
    return name, vals, higher_is_better(name)


def _best(vals, up) -> int:
    ok = [k for k in range(len(vals)) if vals[k] is not None]
    return (max if up else min)(ok, key=lambda k: vals[k])


def _epoch(rows, i) -> int:
    try:
        return int(float(rows[i].get("epoch", i + 1)))
    except (TypeError, ValueError):
        return i + 1


def _val_loss(rows):
    """검증 손실 합 시계열과 최저점. 과적합 판정에는 참고로만 쓴다"""
    n = len(rows)
    vl = [c for c in rows[0].keys() if c.startswith("val/") and c.endswith("_loss")]
    if not vl or n < 8:
        return None, None
    # ★YOLO는 검증을 건너뛴 초반 에폭의 검증 손실을 0으로 적는다. 그대로 쓰면 그 에폭이 "가장 낮은 손실"이 되어
    #   엉뚱한 과적합 해설이 나왔다(0.000). 전부 0이거나 빈 에폭은 뺀다
    vals = [[_f(r.get(c)) for c in vl] for r in rows]
    series = [sum(v) if all(x is not None for x in v) and any(x > 0 for x in v) else None for v in vals]
    ok = [k for k in range(n) if series[k] is not None]
    if len(ok) < 8:
        return None, None
    return series, min(ok, key=lambda k: series[k])


# Ultralytics 학습 인자 기본값. 설치본 cfg/default.yaml(8.4.150)에서 값만 확인했다(코드는 보지 않음).
#   close_mosaic 10: 마지막 10에폭은 모자이크 증강을 끈다 · lrf 0.01: 학습률이 lr0의 1%까지 줄어든다
#   둘 다 끝 무렵 점수를 끌어올려서, 최고점이 마지막 에폭인 것만으로는 "더 학습하면 는다"의 근거가 안 된다
ULTRA_CLOSE_MOSAIC = 10
ULTRA_LRF = 0.01


def read_args(run_dir: Path) -> dict:
    """args.yaml의 맨 윗단 'key: value'만. 없으면 빈 dict(울트라리틱스 run이 아님)"""
    out = {}
    try:
        text = (run_dir / "args.yaml").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return out
    for line in text.splitlines():
        if ":" in line and not line.startswith((" ", "-", "#")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.split(" #")[0].strip().strip("'\"")
    return out


def _num(args: dict, k: str, d: float) -> float:
    try:
        return float(args.get(k, d))
    except (TypeError, ValueError):
        return d


def _tail(args: dict | None, n: int) -> int:
    """끝 무렵 점수를 끌어올리는 구간의 에폭 수. 0이면 그런 구간이 없다(예전 규칙 그대로).
    close_mosaic이 켜져 있고 학습이 그 구간에 들어갔으면 그 길이. close_mosaic=0이어도 학습률이 lrf까지
    줄어드는 끝난 학습이면 마지막 10%를 같은 구간으로 본다"""
    if not args or not ({"close_mosaic", "task", "mode"} & set(args)):     # 울트라리틱스 args.yaml만(logger도 args.yaml을 쓴다)
        return 0
    epochs = int(_num(args, "epochs", n))
    cm = int(_num(args, "close_mosaic", ULTRA_CLOSE_MOSAIC))
    if 0 < cm < epochs and n > epochs - cm:
        return min(cm, n - 1)
    if cm <= 0 and n >= epochs and _num(args, "lrf", ULTRA_LRF) < 0.5:
        return max(1, round(n * 0.1))
    return 0


def _still_rising(pre: list, up: bool) -> tuple[float, float] | None:
    """구간 앞쪽 점수가 끝까지 오르고 있었나. 마지막 1/5의 최고가 그 전 최고보다 1% 넘게 좋으면 (전, 후)"""
    pre = [v for v in pre if v is not None]
    if len(pre) < 5:
        return None
    k = max(2, len(pre) // 5)
    a, b = (max, max) if up else (min, min)
    before, after = a(pre[:-k]), b(pre[-k:])
    gain = (after - before) if up else (before - after)
    return (before, after) if gain > abs(before) * 0.01 else None


def _keep_best(framework: str) -> str:
    """"가장 좋은 에폭을 쓰라"를 그 프레임워크의 말로. ★Keras·Lightning 학습에도 'best.pt를 쓰라'고 했다(그런 파일이 없다)"""
    return {"ultralytics": tr("Keep using best.pt, which is saved by the score, not by the loss."),
            "huggingface": tr("Set load_best_model_at_end=True and metric_for_best_model to your score, so the saved model is the best epoch, not the last."),
            "lightning": tr("Save with ModelCheckpoint(monitor=your score, mode=\"max\") and load that checkpoint, not the last one."),
            "keras": tr("Use ModelCheckpoint(save_best_only=True) or EarlyStopping(restore_best_weights=True), so you keep the best epoch, not the last."),
            }.get(framework, tr("Keep the checkpoint from the best epoch, not the last one."))


def _early_stop(framework: str) -> str:
    return {"ultralytics": tr("Next time set patience (for example 10) so training stops by itself, or use fewer epochs."),
            "huggingface": tr("Next time add EarlyStoppingCallback(early_stopping_patience=3) with load_best_model_at_end=True."),
            "lightning": tr("Next time add the EarlyStopping callback on your score, or use fewer epochs."),
            "keras": tr("Next time add EarlyStopping(patience=5, restore_best_weights=True), or use fewer epochs."),
            }.get(framework, tr("Next time stop earlier, or use fewer epochs."))


def _train_loss_blowup(rows) -> tuple[float, int, float] | None:
    """학습 손실이 바닥을 찍은 뒤 두 배 넘게 불어났다(NaN이 아니어도 학습이 무너진 것). (바닥 값, 바닥 에폭 자리, 끝 값)"""
    tl = [c for c in rows[0].keys() if c.startswith("train/") and c.endswith("loss")]
    n = len(rows)
    if not tl or n < 6:
        return None
    s = [sum(v) if all(x is not None for x in v) else None for v in ([_f(r.get(c)) for c in tl] for r in rows)]
    ok = [k for k in range(n) if s[k] is not None]
    if len(ok) < 6:
        return None
    lo = min(ok, key=lambda k: s[k])
    tail = [s[k] for k in ok[-3:]]
    end = sum(tail) / len(tail)
    return (s[lo], lo, end) if lo < n - 3 and s[lo] > 0 and end > s[lo] * 2 else None


def _notes(rows, heads, args: dict | None = None, framework: str = "ultralytics") -> list[tuple[str, str, dict]]:
    out = []
    n = len(rows)
    main = heads[0] if heads else None
    sc = _score(rows)

    # 1) 과적합: 대표 점수(best.pt 저장 기준)가 최고점 이후 뚜렷이 떨어졌다. 검증 손실 상승은 참고 문장으로만.
    #    YOLO는 mAP가 오르는 중에도 cls loss가 오르는 일이 흔하다. 점수가 안 떨어졌으면 "에폭 줄이기"를 말하지 않는다
    series, lo = _val_loss(rows)
    # 끝 값은 마지막 3에폭 평균(한 에폭만 보면 흔들린다)
    tail3 = [series[k] for k in range(max(0, n - 3), n) if series[k] is not None] if series else []
    last_loss = sum(tail3) / len(tail3) if tail3 else None
    loss_rose = lo is not None and lo < n - 3 and last_loss is not None and last_loss > series[lo] * 1.10
    loss_note = tr(" Validation loss also rose from {a:.3f} (epoch {lo}) to {b:.3f}.", lo=_epoch(rows, lo),
                   a=series[lo], b=last_loss) if loss_rose else ""
    if sc and n >= 8:
        name, vals, up = sc
        b = _best(vals, up)
        last = next(v for v in reversed(vals) if v is not None)
        drop = (vals[b] - last) if up else (last - vals[b])
        early = n >= 10 and _epoch(rows, b) <= max(2, n * 0.15)    # 2에폭 최고점은 과적합보다 '너무 이른 최고점'(4번)이 맞다
        if b < n - 3 and not early and drop > abs(vals[b]) * OVERFIT_DROP:
            out.append((tr("{m} peaked at epoch {e} ({a:.3f}) and fell to {b:.3f} by the end. "
                           "The model may be overfitting.", m=name.split("/", 1)[-1], e=_epoch(rows, b), a=vals[b], b=last)
                        + loss_note,
                        tr("Use the best checkpoint, lower epochs, or add augmentation."),
                        {"kind": "overfit", "best_epoch": _epoch(rows, b)}))
        elif loss_rose and not (early and drop > abs(vals[b]) * OVERFIT_DROP):
            # ★최고점이 너무 이르면 위 과적합 판정을 건너뛰는데, 여기서 점수가 떨어졌는지 다시 보지 않고 "떨어지지 않았다"고 했다
            out.append((tr("Validation loss rose from {a:.3f} (epoch {lo}) to {b:.3f}, but {m} did not drop. "
                           "This alone is not overfitting.", lo=_epoch(rows, lo), a=series[lo], b=last_loss,
                           m=name.split("/", 1)[-1]),
                        _keep_best(framework), {"kind": "loss_rise"}))
    elif loss_rose:
        # 대표 점수가 없는 기록(손실만): 손실만이 근거다. 그래서 '~일 수 있다'로 말한다
        out.append((tr("Validation loss bottomed at epoch {lo} ({a:.3f}) and rose to {b:.3f} by the end. "
                       "The model may be overfitting.", lo=_epoch(rows, lo), a=series[lo], b=last_loss),
                    tr("Use the best checkpoint, lower epochs, or add augmentation."),
                    {"kind": "overfit", "best_epoch": _epoch(rows, lo)}))

    # 2) 정밀도와 재현율의 불균형
    if main and main.precision is not None and main.recall is not None:
        gap = main.precision - main.recall
        if gap > 0.12:
            out.append((tr("Precision {p:.2f} is much higher than recall {r:.2f}. "
                           "It misses objects more often than it raises false alarms.", p=main.precision, r=main.recall),
                        tr("These numbers are at the confidence threshold with the best F1, not your own. When deploying, try a lower confidence threshold and check it on the review screen, or add examples of missed cases."), {"kind": "misses"}))
        elif gap < -0.12:
            out.append((tr("Recall {r:.2f} is much higher than precision {p:.2f}. "
                           "It finds most objects but raises many false alarms.", p=main.precision, r=main.recall),
                        tr("These numbers are at the confidence threshold with the best F1, not your own. When deploying, try a higher confidence threshold and check it on the review screen, or add hard negative images."), {"kind": "false_alarms"}))

    # 3)·4) 최고점 위치. 대표 점수 기준이라 YOLO 밖 프레임워크도 판정한다.
    #    '이어 하기'가 아니라 '에폭을 늘려 새로'라고 말한다(이어 하면 이미 줄어든 학습률에서 시작한다)
    best_ep = _epoch(rows, _best(sc[1], sc[2])) if sc else (main.best_epoch if main else None)
    if best_ep is not None and best_ep >= n - 1 and n >= 5:
        tail = _tail(args, n)
        if not tail:
            out.append((tr("The best score came in the last epochs ({e} of {n}). It was still improving.", e=best_ep, n=n),
                        tr("A new run with more epochs will probably score higher. Resuming this one will not help much, "
                           "because its learning rate has already wound down."), {"kind": "still_improving", "epochs": n}))
        elif sc and (alive := _still_rising(sc[1][:n - tail], sc[2])):
            out.append((tr("The score was still rising before the final {t} epochs ({a:.3f} to {b:.3f}), "
                           "so the best score at the end is not only the end-of-training effect.", t=tail, a=alive[0], b=alive[1]),
                        tr("A new run with more epochs will probably score higher. Resuming this one will not help much, "
                           "because its learning rate has already wound down."), {"kind": "still_improving", "epochs": n}))
    # 4b) 정체: 점수가 중간에 멈췄고(떨어지지도 않았다) 뒤 에폭은 보탠 게 없다. 조기 종료를 그 프레임워크의 말로
    if sc and n >= 10 and best_ep is not None and max(2, n * 0.15) < best_ep <= n * 0.6:
        b = _best(sc[1], sc[2])
        last = next(v for v in reversed(sc[1]) if v is not None)
        if abs(sc[1][b] - last) <= abs(sc[1][b]) * OVERFIT_DROP:
            out.append((tr("The score stopped improving after epoch {e} of {n}. The last {k} epochs added nothing.",
                           e=best_ep, n=n, k=n - best_ep),
                        _early_stop(framework), {"kind": "plateau", "best_epoch": best_ep}))
    if best_ep is not None and n >= 10 and best_ep <= max(2, n * 0.15):
        out.append((tr("The best score came very early (epoch {e} of {n}).", e=best_ep, n=n),
                    tr("The learning rate may be too high, or the start weights already fit the data."), {"kind": "early_best"}))

    # 5a) 폭주: NaN은 아니지만 학습 손실이 바닥 뒤 두 배 넘게 불어났다(프레임워크 무관)
    if (blow := _train_loss_blowup(rows)):
        out.append((tr("Training loss fell to {a:.3f} (epoch {e}) and then grew to {b:.3f}. Training became unstable.",
                       a=blow[0], e=_epoch(rows, blow[1]), b=blow[2]),
                    tr("Lower the learning rate, or add gradient clipping or warmup."), {"kind": "diverged"}))

    # 5) 발산: 모든 행에서 손실이 처음 NaN이 된 에폭. 끝까지 NaN이면 발산, 뒤에 돌아왔으면 따로 알린다
    first = None
    for i, r in enumerate(rows):
        c = next((c for c in r if c.endswith("_loss") and _f(r.get(c)) is None and r.get(c) not in ("", None)), None)
        if c:
            first = (i, c)
            break
    if first:
        i, c = first
        last_nan = any(k.endswith("_loss") and _f(rows[-1].get(k)) is None and rows[-1].get(k) not in ("", None)
                       for k in rows[-1])
        if last_nan:
            out.append((tr("{c} first became NaN at epoch {e} and stayed broken to the end. Training diverged.",
                           c=c, e=_epoch(rows, i)),
                        tr("Lower the learning rate or check for broken labels."), {"kind": "diverged"}))
        else:
            out.append((tr("{c} became NaN at epoch {e} but recovered later. Results after that point may be unreliable.",
                           c=c, e=_epoch(rows, i)),
                        tr("Lower the learning rate or check for broken labels."), {"kind": "nan_recovered"}))
    return out


def analyze(run_dir: Path) -> Analysis | None:
    rows = [r for r in _load(run_dir) if r.get("epoch")]
    if not rows:
        return None
    heads = [h for h in (head_stats(rows, x) for x in HEADS) if h]
    imgs = {k: run_dir / v for k, v in IMAGE_FILES.items() if (run_dir / v).exists()}
    from . import adapters
    got = adapters.load(run_dir)
    found = _notes(rows, heads, read_args(run_dir), got.framework if got else "ultralytics")
    sc = _score(rows)
    score = None
    if sc:
        b = _best(sc[1], sc[2])
        score = {"metric": sc[0].split("/", 1)[-1], "value": sc[1][b], "best_epoch": _epoch(rows, b)}
    return Analysis(run_dir, len(rows), heads, [(o, t) for o, t, _ in found], imgs, [k for _, _, k in found], score)


def next_run(kind: dict, args: dict, weights: str | None) -> dict | None:
    """해설 하나 → 바꿔 볼 설정 하나(울트라리틱스 학습 인자). 모르면 None. 화면은 이걸 학습 양식에 채운다
    (Ultralytics Platform의 "다음 학습 제안"을 규칙으로, 인터넷 없이)"""
    def num(k, d):
        try:
            return float(args.get(k, d))
        except (TypeError, ValueError):
            return d
    k = kind.get("kind")
    if k == "plateau":                                    # 멈춘 뒤로는 헛돈다: 그만큼 줄이고 스스로 멈추게
        return {"epochs": max(10, round(kind["best_epoch"] * 1.3)), "patience": 10}
    if k == "overfit":
        return {"epochs": max(10, round(kind["best_epoch"] * 1.2))}
    if k == "still_improving" and weights:
        return {"epochs": int(max(num("epochs", kind.get("epochs", 50)), kind.get("epochs", 0)) * 2), "weights": weights}
    if k == "early_best":
        return {"lr0": round(num("lr0", 0.01) / 3, 6)}
    if k in ("diverged", "nan_recovered"):
        return {"lr0": round(num("lr0", 0.01) / 10, 6)}
    return None
