"""검수 요청: 다시 채점(GET /jobs/<id>/eval), 판정 저장·라벨 고치기·재학습 세트(POST /review/*). 계산은 review.py"""
from __future__ import annotations

import json
from pathlib import Path

import threading

from .. import msg, retrain, review
from . import NOT_MINE, result_file as _result

_VERDICT_LOCK = threading.Lock()


def get(agent, route: str, q: dict):
    if route == "/review/state":                      # 저장된 판정·고친 라벨 목록(웹 화면이 읽는다. 보기라 토큰 없이)
        j = agent.queue.get(q.get("job", [""])[0])
        if not j or j.kind != "evaluate" or not j.output:
            return 400, {"error": "job must be a finished check"}
        return {"verdicts": retrain.verdicts(Path(j.output)), "fixed": sorted(retrain.fixed_labels(Path(j.output)))}
    if route.startswith("/jobs/") and route.endswith("/eval"):
        j = agent.queue.get(route.split("/")[2])
        f = _result(j, "eval")
        if not (f and f.exists()):
            return {"ready": False}
        try:
            conf = float(q["conf"][0]) if "conf" in q else None
            iou_thr = float(q.get("iou", ["0.5"])[0])
        except ValueError:
            return 400, {"error": "conf and iou must be numbers"}
        if not (0 < iou_thr < 1) or (conf is not None and not 0 <= conf <= 1):
            return 400, {"error": "conf must be 0..1 and iou between 0 and 1"}
        out = review.rescore(json.loads(f.read_text(encoding="utf-8")), conf, iou_thr)
        t = trained(j.params.get("model"), out.get("task"))
        return {**out, "trained": t} if t else out
    return NOT_MINE


def trained(model, task) -> dict | None:
    """모델이 학습 폴더(…/weights/best.pt)에서 왔으면 그 results.csv가 적은 공식 값(학습 검증셋 기준).
    best.pt면 최고 에폭, last.pt면 마지막 에폭"""
    if not model:
        return None
    from .. import analysis
    w = Path(str(model))
    run = w.parent.parent if w.parent.name == "weights" else None
    if run is None or not (run / "results.csv").exists():
        return None
    try:
        rows = analysis._load(run)
    except Exception:
        return None
    if not rows:
        return None
    # 검수 채점(review.py)과 같은 기준끼리: 분할은 마스크, 포즈는 박스 IoU로 맞춘다. ★포즈는 키포인트(OKS) 점수를 박스 점수 옆에 같은 'mAP50'으로 보였다
    head = {"segment": "M"}.get(task or "", "B")
    at = None
    if w.stem == "last":
        rows = rows[-1:]
    elif w.stem == "best":                  # best.pt가 저장된 줄(fitness). ★마스크 최고 에폭을 따로 골라 best.pt와 다른 에폭 점수를 보였다
        from .. import schema
        at = schema.fitness_index(rows, schema.pick_metric(list(rows[-1].keys())))
    h = analysis.head_stats(rows, head, at) or analysis.head_stats(rows, "B", at)
    if not h:
        return None
    return {"precision": h.precision, "recall": h.recall, "map50": h.map50, "map50_95": h.map5095,
            "epoch": h.best_epoch, "file": str(run / "results.csv")}


def post(agent, route: str, body: dict):
    if not route.startswith("/review/"):
        return NOT_MINE
    if route == "/review/import":                     # 다른 프레임워크의 예측 파일(JSONL) → 검수 결과
        return _import(agent, body)
    j = agent.queue.get(str(body.get("job", "")))
    if not j or j.kind != "evaluate" or not j.output or not Path(j.output).is_dir():
        return 400, {"error": "job must be a finished check"}
    out = Path(j.output)
    rows = {r["image"] for r in json.loads((out / "epokio_eval.json").read_text(encoding="utf-8")).get("rows", [])} \
        if (out / "epokio_eval.json").exists() else set()
    if route == "/review/verdicts":
        v = body.get("verdicts") if body.get("patch") is None else body.get("patch")
        ok = {"model_wrong", "label_wrong", "unsure", "ok"}
        # patch: 바뀐 이미지만(null = 지우기). 저장된 판정에 섞는다. ★늘 화면의 판정 전체를 보내 파일을 통째로 바꿔,
        #   열어 둔 다른 탭(또는 맥 앱)이 그사이 매긴 판정을 말없이 지웠다
        patch = body.get("patch") is not None
        if not isinstance(v, dict) or any(k not in rows or not (x in ok or (patch and x is None)) for k, x in v.items()):
            return 400, {"error": "verdicts must map images of this check to model_wrong, label_wrong, unsure or ok"}
        try:                                          # ★어떤 문턱에서 매긴 판정인지 CSV에 남긴다(첫 줄 메타)
            conf = float(body["conf"]) if body.get("conf") is not None else None
            iou_thr = float(body["iou"]) if body.get("iou") is not None else None
        except (TypeError, ValueError):
            return 400, {"error": "conf and iou must be numbers"}
        if (conf is not None and not 0 <= conf <= 1) or (iou_thr is not None and not 0 < iou_thr < 1):
            return 400, {"error": "conf must be 0..1 and iou between 0 and 1"}
        with _VERDICT_LOCK:
            if patch:
                v = {**retrain.verdicts(out), **v}
                v = {k: x for k, x in v.items() if x is not None}
            return 200, {"saved": retrain.save_verdicts(out, v, conf, iou_thr), "verdicts": v}
    if route == "/review/fix":
        image, boxes = body.get("image"), body.get("boxes")
        if image not in rows or not isinstance(boxes, list):
            return 400, {"error": "image must be from this check and boxes a list"}
        # 고친 라벨은 'cls x y w h' 한 줄이다. 포즈(키포인트)·분할(다각형) 라벨을 이것으로 바꾸면 Ultralytics가 그 이미지를
        # 깨진 라벨로 보고 빼거나(포즈) 분할을 통째로 버린다(분할). ★맥 앱이 포즈 고치기를 열어 두어 고친 이미지가 조용히 빠졌다
        task = json.loads((out / "epokio_eval.json").read_text(encoding="utf-8")).get("task") if (out / "epokio_eval.json").exists() else None
        if task in ("pose", "segment"):
            return 400, {"error": msg.tr("Fixing labels here works for boxes and classes only. Fix pose and mask labels in your labelling tool.")}
        try:
            f = retrain.fix_label(out, image, boxes)
        except (KeyError, TypeError, ValueError) as e:
            return 400, {"error": f"bad box: {e}"}
        return 200, {"path": str(f)}
    if route == "/review/fixed":
        return 200, {"fixed": retrain.fixed_labels(out)}
    if route == "/review/export":                     # 점수 + 판정 CSV (앱의 "내보내기"가 그대로 저장한다)
        f = _result(j, "eval")
        if not (f and f.exists()):
            return 400, {"error": "this check has no results yet"}
        try:
            conf = float(body["conf"]) if body.get("conf") is not None else None
            iou_thr = float(body.get("iou", 0.5))
        except (TypeError, ValueError):
            return 400, {"error": "conf and iou must be numbers"}
        if not (0 < iou_thr < 1) or (conf is not None and not 0 <= conf <= 1):
            return 400, {"error": "conf must be 0..1 and iou between 0 and 1"}
        data = review.rescore(json.loads(f.read_text(encoding="utf-8")), conf, iou_thr)
        text = retrain.export_csv(data, retrain.verdicts(out))
        return 200, {"csv": text, "rows": len(data.get("rows", [])), "name": "epokio-review.csv"}
    if route == "/review/retrain":
        want = body.get("want", ["model_wrong", "label_wrong"])
        if not isinstance(want, list):
            return 400, {"error": "want must be a list"}
        try:
            return 200, retrain.build_retrain(out, j.params.get("model", ""), want, int(body.get("repeat", 2)))
        except ValueError as e:
            return 400, {"error": str(e)}
    return 404, {"error": "unknown review action"}


def _import(agent, body: dict):
    import re
    from .. import predictions
    from ..jobs import HOME
    from ..textnorm import resolve
    f = Path(resolve(str(body.get("path", ""))))
    if not str(body.get("path", "")).strip() or not f.is_file() or f.suffix.lower() not in (".jsonl", ".json", ".ndjson"):
        return 400, {"error": "path must be a .jsonl or .json file on this machine"}     # ★/etc/passwd도 열어 읽었다
    try:
        data = predictions.load(f)
    except (OSError, ValueError) as e:
        return 400, {"error": f"could not read predictions: {e}"}
    name = re.sub(r"[^\w.-]+", "_", str(body.get("name") or f.stem))[:60] or "imported"
    out, n = HOME / "evals" / f"import_{name}", 2
    while out.exists():                               # ★같은 이름의 예측 파일을 또 가져오면 앞 결과(판정·고친 라벨)를 덮었다
        out, n = HOME / "evals" / f"import_{name}{n}", n + 1
    out.mkdir(parents=True)
    (out / "epokio_eval.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    j = agent.queue.record_done("evaluate", out.name, str(out), {"source": str(f), "imported": True})
    return 200, {"id": j.id, "task": data["task"], "images": data["images"]}


_img_cache: dict[str, tuple[float, set]] = {}


def eval_images(agent) -> set[str]:
    """끝난 평가 결과들에 적힌 이미지 경로(웹 검수 화면이 /file로 받는다). 결과 파일 시각이 그대로면 다시 안 읽는다"""
    out: set[str] = set()
    for j in agent.queue.jobs:
        if j.kind != "evaluate" or j.state != "done":
            continue
        f = _result(j, "eval")
        if not f:
            continue
        t = f.stat().st_mtime
        hit = _img_cache.get(str(f))
        if not hit or hit[0] != t:
            try:
                rows = json.loads(f.read_text(encoding="utf-8")).get("rows", [])
            except (OSError, ValueError):
                rows = []
            hit = (t, {str(Path(r["image"])) for r in rows if r.get("image")})
            _img_cache[str(f)] = hit
        out |= hit[1]
    return out
