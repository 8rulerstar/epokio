"""작업 스크립트 틀 중 jobs.py가 쓰는 것. 공통 틀은 templates.py에 있고 여기서 다시 내보낸다.

여기 있는 것
  TRAIN_TEMPLATE: 학습 + 실행 환경 기록(epokio_env.json, ENV_HELPERS의 write_env)
  SETUP_TEMPLATE: 자동 설치. ultralytics 판 고정(templates.ULTRALYTICS_SPEC) + 윈도우 NVIDIA면 CUDA torch 먼저
  EVAL_HELPERS: 평가의 순수 계산(라벨 읽기·IoU·신뢰도 순 짝짓기). 지금 평가 틀은 원자료만 모으고
    채점은 review.py가 한다. 이 글자는 테스트와 다른 곳에서 exec해 쓰도록 남긴다
"""
from .templates import AUTOLABEL_TEMPLATE, EVAL_TEMPLATE, EXPORT_TEMPLATE, ULTRALYTICS_SPEC  # noqa: F401

TRAIN_TEMPLATE = '''\
import json, sys
from ultralytics import YOLO
p = json.loads({params!r})
model = p.pop("model")
yolo = YOLO(model)
yolo.add_callback("on_pretrain_routine_start", lambda trainer: write_env(trainer.save_dir, p, {git}))
every = int(p.pop("epokio_snapshots", 0) or 0)       # 켰으면 몇 에폭마다 검증 이미지 4장을 예측해 남긴다
if every > 0:
    add_snapshots(yolo, every)
yolo.train(**p)
# 여러 GPU 학습은 판에 따라 콜백이 따로 뜬 프로세스에 안 넘어간다. 끝나고 없으면 그때 쓴다
if getattr(yolo, "trainer", None) is not None:
    write_env(yolo.trainer.save_dir, p, {git}, only_if_missing=True)
    # 마지막 검증의 클래스별 성능. 이미 계산된 값을 적기만 한다(GPU를 더 안 쓴다)
    write_classes(yolo.trainer.save_dir, getattr(getattr(yolo.trainer, "validator", None), "metrics", None), "train")
'''

# 학습마다 어떤 환경에서 돌았는지 남긴다(epokio_env.json). "왜 14번 학습이 재현이 안 되지"의 답.
# 결과 폴더는 ultralytics가 만든다(미리 만들면 이름 뒤에 2가 붙는다). 그래서 폴더가 생긴 직후의 콜백에서 쓴다.
# 실패해도 학습은 계속한다. 표준 라이브러리만(사용자 파이썬에서 돈다)
ENV_HELPERS = '''\
def write_env(save_dir, params=None, git=False, only_if_missing=False):
    try:
        import json, os, platform, subprocess, sys, hashlib
        from importlib import metadata
        from pathlib import Path
        out = Path(save_dir, "epokio_env.json")
        params = params or {}
        # 이어 하기(resume)는 처음 기록을 덮지 않는다
        if out.exists() and (only_if_missing or params.get("resume")):
            return
        env = {"python": sys.version.split()[0], "platform": platform.platform()}
        for pkg in ("ultralytics", "torch", "torchvision", "numpy"):
            try:
                env[pkg] = metadata.version(pkg)
            except Exception:
                pass
        try:
            import torch
            env["cuda"] = torch.version.cuda if torch.cuda.is_available() else None
            if torch.cuda.is_available():
                env["gpus"] = ", ".join(torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count()))
            env["device"] = str(params.get("device", "auto"))       # 어느 장치로 돌렸나(★GPU 0 이름만 적어 cpu·device=1 학습도 GPU 0으로 보였다)
        except Exception:
            pass
        # git은 작업 폴더를 준 학습만(★아니면 agent를 띄운 폴더의 커밋, 예를 들어 epokio 자신의 것이 적혔다)
        try:
            head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5) if git else None
            if head is not None and head.returncode == 0:
                env["git_commit"] = head.stdout.strip()[:12]
                dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5)
                env["git_dirty"] = bool(dirty.stdout.strip())
        except Exception:
            pass
        pkgs = []
        for d in metadata.distributions():                     # 메타데이터는 한 번만 읽는다(★세 번 읽어 큰 환경에서 5초)
            m = d.metadata
            if m["Name"]:
                pkgs.append(m["Name"] + "==" + (m["Version"] or ""))
        pkgs.sort()
        env["packages_hash"] = hashlib.sha1("\\n".join(pkgs).encode()).hexdigest()[:12]
        out.write_text(json.dumps(env, indent=1), encoding="utf-8")
    except Exception as e:
        print("epokio: could not record the environment:", e, flush=True)


def add_snapshots(yolo, every, n=4, side=480):
    """에폭별 예측 사진(epokio_snapshots/e0005_0.jpg). 같은 검증 이미지 n장을 every 에폭마다 last.pt로 예측해 그린다.
    학습 프로세스 안에서 CPU로 돈다(GPU 메모리를 건드리지 않는다). last.pt는 이 콜백 직전에 저장된다(trainer._do_train).
    학습 끝의 마지막 검증도 이 콜백을 부르는데(epoch+1) 그때는 건너뛴다"""
    picked = []

    def cb(tr):
        try:
            from ultralytics.utils import RANK
            e = tr.epoch + 1
            if RANK not in (-1, 0) or e > tr.epochs or (e % every and e != tr.epochs):
                return
            if not picked:
                ims = sorted(tr.validator.dataloader.dataset.im_files)
                picked.extend(ims[i * len(ims) // n] for i in range(min(n, len(ims))))
            import cv2
            from pathlib import Path
            from ultralytics import YOLO
            out = Path(tr.save_dir, "epokio_snapshots")
            out.mkdir(exist_ok=True)
            for i, r in enumerate(YOLO(str(tr.last)).predict(picked, device="cpu", imgsz=tr.args.imgsz, verbose=False)):
                im = r.plot()
                h, w = im.shape[:2]
                if max(h, w) > side:
                    im = cv2.resize(im, (int(w * side / max(h, w)), int(h * side / max(h, w))))
                cv2.imwrite(str(out / f"e{e:04d}_{i}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 80])
        except Exception as ex:
            print("epokio: prediction snapshot skipped:", ex, flush=True)
    yolo.add_callback("on_fit_epoch_end", cb)


def write_classes(save_dir, m, source):
    """클래스별 성능(epokio_classes.json). ultralytics는 이걸 로그에 찍기만 하고 파일로 남기지 않는다.
    값의 이름은 results.csv 열 이름(metrics/mAP50-95(B) 등)과 같다. 머리(box·pose·mask)가 여럿이면 전부"""
    try:
        import json, time
        from pathlib import Path
        keys, idx = list(getattr(m, "keys", None) or []), list(getattr(m, "ap_class_index", None) if m is not None else [])
        if not keys or not idx:
            return
        nc, ni = getattr(m, "nt_per_class", None), getattr(m, "nt_per_image", None)
        rows = []
        for i, c in enumerate(idx):
            c = int(c)
            vals = [float(v) for v in m.class_result(i)]
            rows.append({"name": str(m.names[c]), "instances": int(nc[c]) if nc is not None else None,
                         "images": int(ni[c]) if ni is not None else None, **dict(zip(keys, vals))})
        out = {"source": source, "at": time.time(), "keys": keys, "rows": rows}
        Path(save_dir, "epokio_classes.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    except Exception as e:
        print("epokio: could not save per-class scores:", e, flush=True)

'''

# 이미 끝난 학습(밖에서 돌렸거나 예전 판)의 클래스별 성능: best.pt로 검증을 한 번 돌려 그 학습 폴더에 적는다
CLASSES_TEMPLATE = '''\
import json
from ultralytics import YOLO
p = json.loads({params!r})
m = YOLO(p["model"]).val(data=p["data"], split=p.get("split", "val"), plots=False, save_json=False,
                         project=p["tmp"], name="val", exist_ok=True, verbose=True)
write_classes(p["run"], m, "val")
'''

# 평가의 순수 계산 부분(라벨 읽기·IoU·짝짓기). 사용자 파이썬에서 돌아서 epokio를 import할 수 없으니 글자로 붙인다.
# 틀(.format) 밖에 따로 둬서 테스트가 그대로 exec해 본다(tests/test_eval_helpers.py)
EVAL_HELPERS = '''\
import math

def read_gt(f, seg=False):
    """YOLO 라벨. 검출: cls cx cy w h, 포즈: 그 뒤에 키포인트(x y v), 분할: cls 뒤에 폴리곤(x y ...).
    ★분할 폴리곤의 앞 숫자 4개를 박스로 읽어서, 분할 모델의 이미지별 점수가 의미 없었다. 폴리곤은 감싸는 박스로 바꾼다"""
    rows = []
    if f is None: return rows
    for line in f.read_text(encoding="utf-8").splitlines():
        v = [float(x) for x in line.split()]
        if len(v) < 5: continue
        if seg and len(v) > 5 and (len(v) - 1) % 2 == 0:
            xs, ys = v[1::2], v[2::2]
            x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
            rows.append({"cls": int(v[0]), "box": [(x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1], "kpts": []})
        else:
            kp = v[5:]
            rows.append({"cls": int(v[0]), "box": v[1:5], "kpts": [kp[k:k + 3] for k in range(0, len(kp) - len(kp) % 3, 3)]})
    return rows

def iou(a, b):
    ax1, ay1, ax2, ay2 = a[0]-a[2]/2, a[1]-a[3]/2, a[0]+a[2]/2, a[1]+a[3]/2
    bx1, by1, bx2, by2 = b[0]-b[2]/2, b[1]-b[3]/2, b[0]+b[2]/2, b[1]+b[3]/2
    iw, ih = max(0, min(ax2, bx2) - max(ax1, bx1)), max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    u = a[2]*a[3] + b[2]*b[3] - inter
    return inter / u if u > 0 else 0

def match(gt, pred, thr):
    """(맞춘 수, 키포인트 점수들). 신뢰도 높은 예측부터 가장 많이 겹치는 정답과 짝짓는다(COCO·ultralytics와 같은 순서).
    ★정답 순서대로 고르면 앞 정답이 뒤 정답의 유일한 짝을 가져가 맞출 수 있는 것을 놓쳤다"""
    used, tp, ks = set(), 0, []
    for qi in sorted(range(len(pred)), key=lambda i: -pred[i]["conf"]):
        q, best, gi = pred[qi], thr, -1
        for i, g in enumerate(gt):
            if i in used or g["cls"] != q["cls"]: continue
            v = iou(g["box"], q["box"])
            if v >= best: best, gi = v, i
        if gi < 0: continue
        used.add(gi); tp += 1
        g = gt[gi]
        if g["kpts"] and q["kpts"]:
            diag = math.hypot(g["box"][2], g["box"][3]) or 1
            ds = [math.hypot(a[0] - b[0], a[1] - b[1]) / diag for a, b in zip(g["kpts"], q["kpts"]) if a[2] > 0]
            if ds: ks.append(max(0.0, 1 - sum(ds) / len(ds)))
    return tp, ks
'''

# CUDA 12.8 판. RTX 50 까지 되고 드라이버 570 이상이면 된다(2026-09-25, torch 2.11+cu128 이 이 PC에서 실제로 돈다)
CUDA_INDEX = "https://download.pytorch.org/whl/cu128"

SETUP_TEMPLATE = '''\
# Epokio: 학습용 파이썬 환경 자동 설치 (초보자가 아무것도 없을 때)
import subprocess, sys, os, shutil
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
# ★윈도우의 PyPI torch 는 CPU 전용이다. NVIDIA 가 있으면 CUDA 판을 먼저 깐다(리눅스 PyPI 판은 CUDA 포함).
#   ultralytics 는 이미 깔린 torch 를 그대로 쓴다. CUDA 판이 안 되면 CPU 판으로라도 끝낸다
if os.name == "nt" and shutil.which("nvidia-smi"):
    print("NVIDIA GPU found. Installing PyTorch with CUDA.", flush=True)
    try:
        run([py, "-m", "pip", "install", "torch", "torchvision", "--index-url", {cuda_index!r}])
    except subprocess.CalledProcessError:
        print("CUDA PyTorch did not install. Continuing with the CPU version.", flush=True)
# 판 고정(templates.ULTRALYTICS_SPEC). 다른 판은 agent 환경 변수 EPOKIO_ULTRALYTICS_SPEC로
run([py, "-m", "pip", "install", os.environ.get("EPOKIO_ULTRALYTICS_SPEC") or "@@SPEC@@"])
print("Done. Choose \\"epokio\\" in the Python list.", flush=True)
'''.replace("@@SPEC@@", ULTRALYTICS_SPEC)
