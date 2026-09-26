"""검수 채점: 평가 결과(epokio_eval.json)를 문턱·IoU를 바꿔 다시 채점한다. 모델을 다시 돌리지 않는다.
★채점 규칙은 여기 한 곳. 평가 스크립트(templates.py)와 예측 가져오기(predictions.py)는 원자료만 만든다.

과제(task)마다 원자료:
  detect·pose  이미지마다 정답(gt)·예측(pred, 신뢰도) 박스 (+키포인트)
  segment      위와 같고 + 다각형(poly), 정답×예측 마스크 IoU 표(ious). 매칭은 박스 대신 마스크 겹침으로
  classify     정답 클래스(truth) + 상위 예측(top: [[클래스, 신뢰도], …]). 1위만 예측으로 쓰고, 문턱 밑이면 "애매함"
               화면이 한 모양으로 그리도록 이미지 전체 박스로 바꿔 같은 계산을 탄다(자리 = 늘 맞음)

계산: 이미지별 맞춤·헛검출·놓침과 박스마다의 상태(tp · fp · fn · cls = 자리는 맞고 클래스 틀림),
      전체·클래스별 정밀도·재현율·F1, 혼동 행렬(마지막 칸 = 배경: 놓침·헛검출), 문턱별 F1 곡선과 추천 문턱.
★Ultralytics 검증(mAP)과 규칙이 다르다. 그래서 같은 예측으로 Ultralytics val과 같은 방식의 값(official)도 따로 낸다(apmetric.py, 독자 구현).
  차이: ①P·R을 고른 문턱 하나에서 센다(공식은 클래스 평균 F1이 가장 높은 문턱) ②박스를 모두 합쳐 센다(공식은 클래스별 평균)
       ③매칭이 신뢰도 순 탐욕(공식은 예측마다 IoU 큰 정답을 고르고, 겹치면 앞선 예측이 가짐) ④IoU 문턱을 바꿀 수 있다(공식 P·R·mAP50은 0.5)
       ⑤분류: 문턱 밑 1위는 '애매함'(공식 top1은 문턱 없음) ⑥저장된 예측이 conf_floor(0.05)까지라 공식(0.001)보다 mAP가 약간 낮을 수 있다
파일을 쓰는 쪽(라벨 고치기·재학습 세트)은 retrain.py.
"""
from __future__ import annotations

import math

from epokio.apmetric import class_mean_scores, greedy_overlap_match

CONF_STEPS = [round(0.05 * i, 2) for i in range(1, 20)]      # 0.05 ~ 0.95
FULL = [0.5, 0.5, 1.0, 1.0]                                  # 분류: 이미지 전체


def _conf(q: dict) -> float:
    """신뢰도가 없는 예측(점수 없이 가져온 파일)은 확신 1.0으로 본다. ★없으면 0으로 쳐서 채점에서 통째로 빠졌다"""
    c = q.get("conf")
    return 1.0 if c is None else float(c)


def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx1, by1, bx2, by2 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    iw, ih = max(0.0, min(ax2, bx2) - max(ax1, bx1)), max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    u = a[2] * a[3] + b[2] * b[3] - inter
    return inter / u if u > 0 else 0.0


def match(gt: list[dict], pred: list[dict], iou_thr: float, ious: list[list[float]] | None = None):
    """탐욕 매칭(신뢰도 높은 예측부터). 같은 클래스 먼저, 남은 것끼리 자리만 맞으면 '클래스 틀림'.
    ious가 있으면(분할) 박스 대신 그 표를 쓴다. pred의 "_i"가 원래 순번.
    돌려주는 것: gt 상태 목록, pred 상태 목록, 짝 [(gi, pi)] (혼동 행렬용, 클래스 달라도 포함)"""
    def overlap(gi, pi):
        if ious is not None:
            row = ious[gi] if gi < len(ious) else []
            k = pred[pi].get("_i", pi)
            return row[k] if k < len(row) else 0.0
        return iou(gt[gi]["box"], pred[pi]["box"])
    order = sorted(range(len(pred)), key=lambda i: -_conf(pred[i]))
    gs, ps = ["fn"] * len(gt), ["fp"] * len(pred)
    pairs = []
    for same in (True, False):
        for pi in order:
            if ps[pi] != "fp":
                continue
            best, bg = iou_thr, -1
            for gi, g in enumerate(gt):
                if gs[gi] != "fn" or (g["cls"] == pred[pi]["cls"]) != same:
                    continue
                v = overlap(gi, pi)
                if v >= best:
                    best, bg = v, gi
            if bg >= 0:
                gs[bg] = ps[pi] = "tp" if same else "cls"
                pairs.append((bg, pi))
    return gs, ps, pairs


def keypoint_closeness(gt: list[dict], pred: list[dict], pairs) -> float | None:
    """키포인트 근접도(Epokio 자체 지표, OKS 아님. pose mAP와 비교 불가): 맞춘 짝마다 1 - (평균 거리 / 정답 박스 대각선), 그 평균.
    응답에는 호환을 위해 기존 키 'kpt'로 실린다"""
    sc = []
    for gi, pi in pairs:
        g, q = gt[gi], pred[pi]
        if g["cls"] != q["cls"] or not g.get("kpts") or not q.get("kpts"):
            continue
        diag = math.hypot(g["box"][2], g["box"][3]) or 1
        ds = [math.hypot(a[0] - b[0], a[1] - b[1]) / diag for a, b in zip(g["kpts"], q["kpts"]) if len(a) < 3 or a[2] > 0]
        if ds:
            sc.append(max(0.0, 1 - sum(ds) / len(ds)))
    return sum(sc) / len(sc) if sc else None


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f}


def _as_boxes(r: dict) -> dict:
    """분류 한 줄 → 이미지 전체 박스 모양 (정답 1개, 예측은 1위 1개)"""
    top = r.get("top") or []
    gt = [{"cls": r["truth"], "box": FULL, "kpts": []}] if r.get("truth") is not None else []
    pred = [{"cls": int(top[0][0]), "box": FULL, "conf": float(top[0][1]), "kpts": []}] if top else []
    return {**r, "gt": gt, "pred": pred}


def _count(rows: list[dict], conf: float, iou_thr: float):
    """문턱 하나에서 전체·클래스별 개수 + 이미지별 상태"""
    per: dict[int, list[int]] = {}
    out = []
    conf_pairs: dict[tuple, int] = {}
    for r in rows:
        pred = [{**q, "_i": i} for i, q in enumerate(r.get("pred", [])) if _conf(q) >= conf]
        gt = r.get("gt", [])
        gs, ps, pairs = match(gt, pred, iou_thr, r.get("ious"))
        tp = gs.count("tp")
        fp = sum(1 for s in ps if s in ("fp", "cls"))
        fn = sum(1 for s in gs if s in ("fn", "cls"))
        for g, s in zip(gt, gs):
            c = per.setdefault(g["cls"], [0, 0, 0])
            c[0 if s == "tp" else 2] += 1
        for q, s in zip(pred, ps):
            if s != "tp":
                per.setdefault(q["cls"], [0, 0, 0])[1] += 1
        for gi, pi in pairs:
            k = (gt[gi]["cls"], pred[pi]["cls"])
            conf_pairs[k] = conf_pairs.get(k, 0) + 1
        for g, s in zip(gt, gs):
            if s == "fn":
                conf_pairs[(g["cls"], -1)] = conf_pairs.get((g["cls"], -1), 0) + 1
        for q, s in zip(pred, ps):
            if s == "fp":
                conf_pairs[(-1, q["cls"])] = conf_pairs.get((-1, q["cls"]), 0) + 1
        out.append((r, [{k: v for k, v in q.items() if k != "_i"} for q in pred], gs, ps, pairs, tp, fp, fn))
    return per, out, conf_pairs


def rescore(data: dict, conf: float | None = None, iou_thr: float = 0.5, names: dict | None = None) -> dict:
    """평가 결과 전체를 다시 채점한다. 옛 결과(gt·pred 없음)는 그대로 돌려준다."""
    rows = data.get("rows", [])
    task = data.get("task") or ("classify" if rows and "top" in rows[0] else
                                "pose" if "keypoint" in str(data.get("metric", "")).lower() else "detect")
    if task == "classify":
        rows = [_as_boxes(r) for r in rows]
    if not rows or "pred" not in rows[0]:
        return data
    floor = data.get("conf_floor", 0.25)                       # 평가 때 저장한 가장 낮은 신뢰도
    conf = min(max(float(conf if conf is not None else data.get("conf", 0.25)), floor), 1.0)
    names = {int(k): v for k, v in (names or data.get("names") or {}).items()}

    per, scored, pairs = _count(rows, conf, iou_thr)
    new_rows = []
    T = FP = FN = 0
    for r, pred, gs, ps, prs, tp, fp, fn in scored:
        T, FP, FN = T + tp, FP + fp, FN + fn
        f1 = 1.0 if not r["gt"] and not pred else 2 * tp / (2 * tp + fp + fn)
        kpt = keypoint_closeness(r["gt"], pred, prs) if task == "pose" else r.get("kpt")   # 키포인트 근접도(자체, OKS 아님)
        if task == "classify":                                 # 정답 클래스에 준 확률(낮을수록 어려운 이미지)
            score = next((float(c) for k, c in r.get("top", []) if k == r.get("truth")), 0.0)
        elif task == "pose":
            score = kpt if kpt is not None else f1 * 0.5
        else:
            score = f1
        new_rows.append({**r, "pred": pred, "tp": tp, "fp": fp, "fn": fn, "f1": round(f1, 4), "score": round(score, 4),
                         "kpt": round(kpt, 4) if kpt is not None else None, "gt_status": gs, "pred_status": ps,
                         "classes": sorted({b["cls"] for b in r["gt"]} | {b["cls"] for b in pred})})
    new_rows.sort(key=lambda x: x["score"])

    classes = sorted(per)
    per_class = [{"cls": c, "name": names.get(c, str(c)), "support": per[c][0] + per[c][2], **_prf(*per[c])} for c in classes]
    labels = classes + [-1]
    matrix = [[pairs.get((g, p), 0) for p in labels] for g in labels]

    curve = []
    for c in CONF_STEPS:
        if c < floor - 1e-9:
            continue
        pc = per if c == conf else _count(rows, c, iou_thr)[0]
        t = sum(v[0] for v in pc.values()); f = sum(v[1] for v in pc.values()); n = sum(v[2] for v in pc.values())
        curve.append({"conf": c, **_prf(t, f, n)})
    best = max((x for x in curve if x["f1"] is not None), key=lambda x: x["f1"], default=None)

    return {**data, "task": task, "rows": new_rows, "images": len(new_rows), "conf": conf, "iou": iou_thr, "conf_floor": floor,
            "mean": round(sum(x["score"] for x in new_rows) / max(len(new_rows), 1), 4),
            "overall": _prf(T, FP, FN), "per_class": per_class,
            "confusion": {"labels": [names.get(c, str(c)) if c >= 0 else "background" for c in labels],
                          "classes": labels, "matrix": matrix},
            "curve": curve, "best_conf": best["conf"] if best else None,
            "names": {str(k): v for k, v in names.items()}, "official": official(data)}


# ---- 공식 규칙 값: Ultralytics val과 같은 수치를 내는 독자 구현(apmetric.py, 블랙박스 관찰로 정한 명세) ----

def overlap_tp(gt: list[dict], pred: list[dict], thr: float, ious) -> list[bool]:
    """예측마다 맞춤 여부(같은 클래스, IoU >= thr). 규칙은 apmetric.greedy_overlap_match. ious가 있으면 마스크 겹침"""
    ov = (lambda gi, pi: ious[gi][pi]) if ious else (lambda gi, pi: iou(pred[pi]["box"], gt[gi]["box"]))
    return greedy_overlap_match([g["cls"] for g in gt], [q["cls"] for q in pred], ov, thr)


def official(data: dict) -> dict | None:
    """Ultralytics val과 같은 방식으로 같은 예측을 채점: P·R(클래스 평균, 평활한 평균 F1 최고 문턱) · mAP50. 분류는 top1 정확도.
    ★여기 값은 저장된 예측(conf_floor 이상)으로 낸 것. 공식 val은 0.001까지 보므로 mAP가 조금 다를 수 있다"""
    rows = data.get("rows", [])
    if not rows:
        return None
    if data.get("task") == "classify" or "top" in rows[0]:
        judged = [r for r in rows if r.get("truth") is not None and r.get("top")]
        if not judged:
            return None
        return {"top1": sum(int(r["top"][0][0]) == r["truth"] for r in judged) / len(judged), "iou": None}
    if "pred" not in rows[0]:
        return None
    stats, targets = [], []                          # (conf, cls, tp)
    for r in rows:
        gt, pred = r.get("gt", []), r.get("pred", [])
        targets += [g["cls"] for g in gt]
        stats += [(_conf(q), q["cls"], t) for q, t in zip(pred, overlap_tp(gt, pred, 0.5, r.get("ious")))]
    if not targets:
        return None
    return {**class_mean_scores(stats, targets), "iou": 0.5}
