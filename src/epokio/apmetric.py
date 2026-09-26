"""Detection metrics, independent implementation (MIT). No third-party metric code was read or copied.

Target: produce the same numbers as Ultralytics 8.4.150 validation. The behavior below was inferred
by calling that library as a black box with chosen inputs and observing only its outputs
(e.g. one class, a single correct detection -> AP 0.995; two truths, one correct detection -> 0.495;
hit, miss, hit on two truths -> 0.828333...), then written down here in our own words and
checked in a separate process: AP50/P/R on ~2,270 random cases and matching on 4,000 random IoU tables,
no difference above 1e-6 (numpy present; see Ties).

Observed behavior (specification for this module):
  Matching   Candidate (truth, prediction) pairs of the same class with IoU >= threshold, listed
             truth-major, are ranked by descending IoU. Each prediction keeps only its highest-IoU
             truth. Among predictions left pointing at the same truth, the one with the lowest
             prediction index (input order, i.e. highest confidence when predictions arrive sorted)
             wins, not the one with the higher IoU. A prediction that loses does not fall back to
             another truth. Observed: one truth, predictions with IoU [0.6, 0.9] -> the first matches;
             truths x predictions [[0.9, 0.8], [0.7, 0.6]] -> only prediction 0 matches.
  Curve      Per class, detections ranked by confidence, cumulative precision and recall after each.
  AP         Add a starting point (recall 0, precision 1) and a closing point at the final recall with
             precision 0. Replace each precision by the best precision at that point or later
             (non-increasing envelope). Sample the resulting piecewise-linear curve at recall
             0.00, 0.01, ..., 1.00, where a sample falling exactly on repeated recall values takes the
             last of them, and past the final recall takes the last value. AP is the trapezoid area
             under those 101 samples. So a perfect class scores 0.995, not 1.0.
  P, R       Each class's precision and recall are read as functions of the confidence threshold on
             1000 evenly spaced thresholds 0..1 (linear interpolation between detections; recall 0 and
             precision 1 above the top confidence). Class F1 values are averaged over classes, the
             averaged F1 is smoothed with a 101-sample moving average (ends padded by repeating the edge
             value), and the threshold with the highest smoothed value (first on ties) is chosen.
             Reported P and R are class means at that threshold.
  Ties       Equal confidences keep the order numpy's default argsort gives over all predictions;
             without numpy, input order (results can then differ when many confidences tie).
  Classes    Only classes that have at least one truth box are scored.
"""
from __future__ import annotations

from bisect import bisect_right

RECALL_LEVELS = [i / 100 for i in range(101)]
CONF_GRID = [i / 999 for i in range(1000)]
F1_WINDOW = 101


def _rank_desc_reversed(vals: list[float]) -> list[int]:
    """Descending ranking whose tie order is the reverse of numpy's default ascending argsort
    (observed to decide equal-IoU ties in the reference). Without numpy: reverse of a stable ascending sort."""
    try:
        import numpy as np
        asc = [int(k) for k in np.argsort(np.asarray(vals, dtype=float))]
    except ImportError:
        asc = sorted(range(len(vals)), key=lambda k: vals[k])
    return asc[::-1]


def greedy_overlap_match(gt_cls: list[int], pred_cls: list[int], overlap, thr: float) -> list[bool]:
    """True for each prediction paired with a truth box. overlap(gi, pi) -> IoU. See "Matching" above."""
    cand = []
    for gi, gc in enumerate(gt_cls):
        for pi, pc in enumerate(pred_cls):
            v = overlap(gi, pi) if gc == pc else 0.0
            if gc == pc and v >= thr:
                cand.append((v, gi, pi))
    cand = [cand[k] for k in _rank_desc_reversed([c[0] for c in cand])]
    first_per_pred, seen_p = [], set()
    for c in cand:
        if c[2] not in seen_p:
            seen_p.add(c[2])
            first_per_pred.append(c)
    first_per_pred.sort(key=lambda c: c[2])                             # then by prediction index
    hit, seen_g = [False] * len(pred_cls), set()
    for _, gi, pi in first_per_pred:
        if gi not in seen_g:
            seen_g.add(gi)
            hit[pi] = True
    return hit


def _piecewise(x: float, xs: list[float], ys: list[float], below: float) -> float:
    """Piecewise-linear lookup on ascending xs. Exactly on repeated xs -> the last one. Past the end -> last y."""
    if not xs or x < xs[0]:
        return below if xs else below
    j = bisect_right(xs, x) - 1
    if j >= len(xs) - 1:
        return ys[-1]
    x0, x1 = xs[j], xs[j + 1]
    if x1 == x0:
        return ys[j]
    return ys[j] + (ys[j + 1] - ys[j]) * (x - x0) / (x1 - x0)


def rank_by_confidence(confs: list[float]) -> list[int]:
    """Indices, highest confidence first. Equal confidences: numpy's default argsort order on the whole
    prediction list when numpy is available (observed to decide tie order in the reference), else input order."""
    try:
        import numpy as np
    except ImportError:
        return sorted(range(len(confs)), key=lambda k: -confs[k])
    return [int(k) for k in np.argsort(-np.asarray(confs, dtype=float))]


def pr_curve(confs: list[float], hits: list[bool], n_gt: int, order: list[int] | None = None) -> tuple[list[float], list[float], list[float]]:
    """(confidences high to low, recall after each, precision after each). order: ranking to use (default: stable)."""
    if order is None:
        order = sorted(range(len(confs)), key=lambda k: -confs[k])
    tp = fp = 0
    cs, rec, prec = [], [], []
    for k in order:
        tp += 1 if hits[k] else 0
        fp += 0 if hits[k] else 1
        cs.append(confs[k])
        rec.append(tp / n_gt if n_gt else 0.0)
        prec.append(tp / (tp + fp))
    return cs, rec, prec


def ap101(rec: list[float], prec: list[float]) -> float:
    """101-sample trapezoid AP over the precision envelope (see module docstring)."""
    if not rec:
        return 0.0
    rs = [0.0] + list(rec) + [rec[-1]]
    ps = [1.0] + list(prec) + [0.0]
    for k in range(len(ps) - 2, -1, -1):
        ps[k] = max(ps[k], ps[k + 1])
    ys = [_piecewise(r, rs, ps, 1.0) for r in RECALL_LEVELS]
    step = RECALL_LEVELS[1] - RECALL_LEVELS[0]
    return sum((ys[k] + ys[k + 1]) * step / 2 for k in range(len(ys) - 1))


def _moving_average(vals: list[float], width: int) -> list[float]:
    half = width // 2
    padded = [vals[0]] * half + vals + [vals[-1]] * half
    out, run = [], sum(padded[:width])
    for k in range(len(vals)):
        out.append(run / width)
        if k + width < len(padded):
            run += padded[k + width] - padded[k]
    return out


def class_mean_scores(stats: list[tuple[float, int, bool]], targets: list[int]) -> dict:
    """stats = (conf, cls, is_tp) per prediction; targets = class of each truth box."""
    classes = sorted(set(targets))
    ranked = [stats[k] for k in rank_by_confidence([s[0] for s in stats])]
    aps, p_rows, r_rows = [], [], []
    for c in classes:
        dets = [(s[0], s[2]) for s in ranked if s[1] == c]
        cs, rec, prec = pr_curve([d[0] for d in dets], [d[1] for d in dets], targets.count(c), list(range(len(dets))))
        aps.append(ap101(rec, prec))
        neg = [-v for v in cs]                         # ascending axis for the lookup
        r_rows.append([_piecewise(-t, neg, rec, 0.0) if cs else 0.0 for t in CONF_GRID])
        p_rows.append([_piecewise(-t, neg, prec, 1.0) if cs else 0.0 for t in CONF_GRID])
    n = len(classes)
    f1 = []
    for i in range(len(CONF_GRID)):
        s = 0.0
        for c in range(n):
            p, r = p_rows[c][i], r_rows[c][i]
            s += 2 * p * r / (p + r) if p + r else 0.0
        f1.append(s / n)
    sm = _moving_average(f1, F1_WINDOW)
    i = max(range(len(sm)), key=lambda k: (sm[k], -k))
    return {"precision": sum(p[i] for p in p_rows) / n, "recall": sum(r[i] for r in r_rows) / n,
            "map50": sum(aps) / n, "conf": round(CONF_GRID[i], 3)}
