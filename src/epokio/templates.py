"""작업(job)이 실행할 파이썬 스크립트 틀. 사용자가 고른 파이썬(ultralytics가 깔린 환경)에서 돈다.

★이 틀들은 epokio를 import하지 않는다. 학습용 파이썬에 epokio가 없을 수 있다.
  평가 틀은 원자료(정답·예측·마스크 IoU)만 모은다. 채점 규칙은 review.py 한 곳(예전엔 둘에 따로 있었다).
틀 안의 중괄호는 str.format 때문에 두 겹({{ }})으로 쓴다.
"""

TRAIN_TEMPLATE = '''\
import json, sys
from ultralytics import YOLO
p = json.loads({params!r})
model = p.pop("model")
YOLO(model).train(**p)
'''

AUTOLABEL_TEMPLATE = '''\
import json, sys, collections
from pathlib import Path
from ultralytics import YOLO
p = json.loads({params!r})
model = YOLO(p.pop("model"))
out = Path(p.pop("project")) / p.pop("name")
low = p.pop("low_conf", 0.5)
summary = {{"images": 0, "empty": [], "low": [], "per_class": collections.Counter(), "conf_hist": [0]*10}}
for r in model.predict(stream=True, save_txt=True, save_conf=True,
                       project=str(out.parent), name=out.name, exist_ok=True, **p):
    summary["images"] += 1
    name = Path(r.path).name
    boxes = r.boxes
    if boxes is None or len(boxes) == 0:
        summary["empty"].append(name)
        continue
    confs = boxes.conf.tolist()
    for c, k in zip(confs, boxes.cls.tolist()):
        summary["per_class"][r.names[int(k)]] += 1
        summary["conf_hist"][min(int(c * 10), 9)] += 1
    if min(confs) < low:
        summary["low"].append({{"image": name, "min_conf": round(min(confs), 3)}})
summary["per_class"] = dict(summary["per_class"])
(out / "epokio_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print("EPOKIO_DONE", out)
'''


EVAL_TEMPLATE = '''\
# 평가: 모델을 한 번 돌려 이미지마다 정답과 예측 원자료만 모은다. 채점(문턱·매칭·점수)은 agent의 epokio/review.py가 한다.
#   검출·자세: 박스(+키포인트)   분할: 다각형 + 정답×예측 마스크 IoU 표   분류: 정답 클래스(폴더 이름) + 상위 5개
import json
from pathlib import Path
from ultralytics import YOLO
p = json.loads({params!r})
model = YOLO(p.pop("model"))
src = Path(p.pop("source"))
out = Path(p.pop("project")) / p.pop("name")
out.mkdir(parents=True, exist_ok=True)
iou_thr = p.pop("iou_match", 0.5)
view_conf = float(p.get("conf", 0.25))            # 화면 기본 문턱
p["conf"] = min(view_conf, 0.05)                  # ★낮게 저장해 두면 앱에서 문턱을 다시 돌리지 않고 바꿀 수 있다
task = getattr(model, "task", "detect")
names = {{int(k): v for k, v in (model.names or {{}}).items()}}
EXT = {{".jpg", ".jpeg", ".png", ".bmp", ".webp"}}
imgs = sorted(x for x in src.rglob("*") if x.suffix.lower() in EXT)

def label_for(img):
    parts = list(img.parts)
    if "images" in parts:
        i = len(parts) - 1 - parts[::-1].index("images")
        cand = Path(*parts[:i], "labels", *parts[i + 1:]).with_suffix(".txt")
        if cand.exists(): return cand
    c = img.with_suffix(".txt")
    return c if c.exists() else None

def read_gt(f):
    rows = []
    if f is None: return rows
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        v = [float(x) for x in line.split()]
        if len(v) < 5: continue
        if task == "segment":                     # cls x1 y1 x2 y2 … (다각형)
            xs, ys = v[1::2], v[2::2]
            poly = list(zip(xs, ys))
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            rows.append({{"cls": int(v[0]), "box": [(x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0], "kpts": [], "poly": poly}})
        else:
            kp = v[5:]
            rows.append({{"cls": int(v[0]), "box": v[1:5], "kpts": [kp[k:k + 3] for k in range(0, len(kp) - len(kp) % 3, 3)]}})
    return rows

def mask_ious(gt, pred, shape):
    import numpy as np, cv2
    h, w = shape
    s = 256 / max(h, w)                            # 작게 그려 겹침만 잰다(정확도보다 속도)
    H, W = max(1, int(h * s)), max(1, int(w * s))
    def raster(poly):
        m = np.zeros((H, W), np.uint8)
        if len(poly) >= 3:
            cv2.fillPoly(m, [np.array([[x * W, y * H] for x, y in poly], np.int32)], 1)
        return m
    G, P = [raster(g["poly"]) for g in gt], [raster(q["poly"]) for q in pred]
    return [[round(float((a & b).sum()) / max(float((a | b).sum()), 1.0), 3) for b in P] for a in G]

rows = []
for r in model.predict(source=[str(x) for x in imgs], stream=True, verbose=False, **p):
    img = Path(r.path)
    if task == "classify":
        top = r.probs.top5 if r.probs is not None else []
        conf = r.probs.top5conf.tolist() if r.probs is not None else []
        truth = next((k for k, v in names.items() if v == img.parent.name), None)
        rows.append({{"image": str(img), "label": img.parent.name, "truth": truth,
                     "top": [[int(c), round(float(x), 4)] for c, x in zip(top, conf)]}})
        continue
    gt = read_gt(label_for(img))
    pred = []
    if r.boxes is not None:
        xywhn = r.boxes.xywhn.tolist(); cls = r.boxes.cls.tolist(); conf = r.boxes.conf.tolist()
        kps = r.keypoints.xyn.tolist() if getattr(r, "keypoints", None) is not None and r.keypoints is not None else [None] * len(cls)
        polys = [pl.tolist() for pl in r.masks.xyn] if getattr(r, "masks", None) is not None and r.masks is not None else [None] * len(cls)
        for b, c, cf, k, pl in zip(xywhn, cls, conf, kps, polys):
            q = {{"cls": int(c), "box": b, "conf": round(cf, 4), "kpts": k or []}}
            if pl is not None: q["poly"] = [[round(x, 4), round(y, 4)] for x, y in pl]
            pred.append(q)
    row = {{"image": str(img), "label": str(label_for(img) or ""), "gt": gt, "pred": pred}}
    if task == "segment" and gt and pred:
        row["ious"] = mask_ious(gt, pred, r.orig_shape)
    rows.append(row)

summary = {{"task": task, "metric": {{"classify": "top-1 correct", "pose": "keypoint score", "segment": "per-image F1 (mask)"}}.get(task, "per-image F1"),
           "images": len(rows), "mean": 0, "conf": view_conf, "conf_floor": p["conf"], "iou": iou_thr,
           "names": {{str(k): v for k, v in names.items()}}, "rows": rows}}
(out / "epokio_eval.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
print("EPOKIO_DONE", out, task, len(rows), "images")
'''


# 자동 설치가 까는 ultralytics 판. 이 맥 yolo5_env에서 실제로 검증한 버전(2026-09-22 확인)으로 고정한다.
# 고정하지 않으면 새 판이 나올 때마다 결과 열·인자가 바뀔 수 있다. 다른 판을 원하면 agent 환경 변수
# EPOKIO_ULTRALYTICS_SPEC(예: "ultralytics==8.3.0" 또는 "ultralytics")로 덮어쓴다
ULTRALYTICS_SPEC = "ultralytics==8.4.150"

SETUP_TEMPLATE = '''\
# Epokio: 학습용 파이썬 환경 자동 설치 (초보자가 아무것도 없을 때)
import subprocess, sys, os
from pathlib import Path
target = Path({target!r})
py = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
def run(cmd):
    print("$", " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), check=True)
if not py.exists():
    print("Creating a Python environment at", target, flush=True)
    run([sys.executable, "-m", "venv", target])
print("Installing ultralytics and torch. This downloads about 1 to 3 GB and can take 5 to 15 minutes.", flush=True)
run([py, "-m", "pip", "install", "--upgrade", "pip"])
run([py, "-m", "pip", "install", os.environ.get("EPOKIO_ULTRALYTICS_SPEC") or "@@SPEC@@"])
print("Done. Choose \\"epokio\\" in the Python list.", flush=True)
'''.replace("@@SPEC@@", ULTRALYTICS_SPEC)

EXPORT_TEMPLATE = '''\
# Epokio: 학습한 모델을 다른 형식으로 내보낸다 (앱·서버·폰에서 쓰려고)
import json
from pathlib import Path
from ultralytics import YOLO
p = json.loads({params!r})


def run_imgsz(model):
    # 모델이 속한 run 폴더(weights/best.pt면 한 칸 위)의 args.yaml에서 학습 imgsz. 못 읽으면 None
    m = Path(model)
    for d in (m.parent, m.parent.parent):
        try:
            for line in (d / "args.yaml").read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("imgsz:"):
                    v = line.split(":", 1)[1].split(" #")[0].strip()
                    return int(v) if v.isdigit() else json.loads(v)
        except (OSError, ValueError):
            continue
    return None


imgsz = p.get("imgsz") or run_imgsz(p["model"]) or 640
extra = {{k: p[k] for k in ("half", "int8", "dynamic") if p.get(k) is not None}}
print("Exporting", p["model"], "to", p["format"], "imgsz", imgsz, extra or "", flush=True)
out = YOLO(p["model"]).export(format=p["format"], imgsz=imgsz, **extra)
print("Saved:", out, flush=True)
'''
