"""이미지 한 장 바로 예측(POST /predict). 대기열을 거치지 않는다"""
from __future__ import annotations

import json

from ..textnorm import resolve
from . import NOT_MINE

SCRIPT = '''
import json, sys
from ultralytics import YOLO
p = json.loads(sys.argv[1])
r = next(iter(YOLO(p["model"]).predict(source=p["image"], conf=p["conf"], device=p["device"], verbose=False, stream=True)))
out = {"names": r.names, "size": list(r.orig_shape[::-1]), "boxes": []}
if r.boxes is not None:
kps = r.keypoints.xyn.tolist() if getattr(r, "keypoints", None) is not None and r.keypoints is not None else [None] * len(r.boxes)
for b, c, cf, k in zip(r.boxes.xywhn.tolist(), r.boxes.cls.tolist(), r.boxes.conf.tolist(), kps):
    out["boxes"].append({"cls": int(c), "box": b, "conf": round(cf, 4), "kpts": k or []})
print("EPOKIO_JSON" + json.dumps(out))
'''

def _predict(agent, body):
    """이미지 한 장을 바로 예측한다 (미리 보기). 대기열을 거치지 않는다.
    ★학습이 돌고 있으면 GPU를 다투지 않도록 CPU로 돌린다 (예전에 병행 학습이 GPU 경합으로 날아갔다)"""
    import subprocess
    busy = any(j.state == "running" for j in agent.queue.jobs)
    device = "cpu" if busy else body.get("device", "")
    args = {"model": resolve(body.get("model", "")), "image": resolve(body.get("image", "")),
            "conf": float(body.get("conf", 0.25)), "device": device or None}
    try:
        r = subprocess.run([body.get("python", ""), "-c", SCRIPT, json.dumps(args)],
                           capture_output=True, text=True, errors="replace", timeout=180,   # 오류 메시지의 못 푸는 글자에 요청이 죽지 않게
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))   # 윈도우에서 검은 창 안 뜨게
    except (OSError, subprocess.TimeoutExpired) as e:
        return 500, {"error": str(e)}
    line = next((l for l in r.stdout.splitlines() if l.startswith("EPOKIO_JSON")), None)
    if not line:
        return 500, {"error": (r.stderr.strip().splitlines() or ["prediction failed"])[-1][:300]}
    out = json.loads(line[len("EPOKIO_JSON"):])
    out["device"] = device or "auto"
    out["cpu_because_training"] = busy
    return 200, out


def get(agent, route: str, q: dict):
    return NOT_MINE


def post(agent, route: str, body: dict):
    return _predict(agent, body) if route == "/predict" else NOT_MINE
