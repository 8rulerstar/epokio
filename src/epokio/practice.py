"""연습 학습: GPU도 데이터도 없이 "학습하는 척"하는 작업. 처음 쓰는 사람이 곡선·알림·메뉴바가 어떻게 움직이는지 보게.

진짜 학습과 같은 모양(Ultralytics results.csv + args.yaml)을 에폭마다 한 줄씩 쓴다. 가중치는 만들지 않는다.
결과는 ~/.epokio/runs/practice/<이름> (agent가 이미 보는 폴더라 목록에 저절로 뜬다). args.yaml에 practice: true.
곡선 모양: good(잘 됨) · overfit(과적합) · plateau(정체) · fail(중간에 실패)
"""
from __future__ import annotations

from pathlib import Path

DIR = Path.home() / ".epokio" / "runs" / "practice"
SHAPES = ("good", "overfit", "plateau", "fail")

# 선택한 파이썬 대신 agent 자신의 파이썬으로 돈다. 표준 라이브러리만
TEMPLATE = r'''
import json, math, random, sys, time
from pathlib import Path
P = json.loads({params!r})
out = Path(P["out"]); out.mkdir(parents=True, exist_ok=True)
n, shape, sec = int(P["epochs"]), P["shape"], float(P["seconds"])
rnd = random.Random(P.get("seed", 0))
(out / "args.yaml").write_text("task: detect\nmodel: yolo11n.pt\ndata: practice/coco8.yaml\nepochs: %d\nimgsz: 640\nbatch: 16\nname: %s\npractice: true\n" % (n, out.name))
head = "epoch,time,train/box_loss,train/cls_loss,train/dfl_loss,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B),val/box_loss,val/cls_loss,val/dfl_loss"
rows = [head]
top = {{"good": 0.62, "overfit": 0.5, "plateau": 0.28, "fail": 0.4}}[shape]
for e in range(1, n + 1):
    time.sleep(sec)
    t = e / n
    g = top * (1 - math.exp(-5 * t)) if shape != "plateau" else top * (1 - math.exp(-14 * t))
    if shape == "overfit" and t > 0.55: g -= 0.1 * (t - 0.55)
    g = max(0.0, g + rnd.uniform(-0.012, 0.012))
    tr = 1.6 * math.exp(-2.2 * t) + 0.35 + rnd.uniform(-0.02, 0.02)
    va = tr + (1.6 * max(0, t - 0.4) if shape == "overfit" else 0.05)
    rows.append("%d,%.1f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f" % (
        e, e * sec, tr, tr * 1.3, tr * 0.9, min(g + 0.08, 1), g * 0.95, min(g * 1.35, 1), g, va, va * 1.3, va * 0.9))
    tmp = out / "results.csv.tmp"; tmp.write_text("\n".join(rows) + "\n"); tmp.replace(out / "results.csv")
    print("epoch %d/%d  mAP50-95 %.3f  (practice, no GPU)" % (e, n, g), flush=True)
    if shape == "fail" and e >= max(2, n // 2):
        print("RuntimeError: CUDA out of memory (practice: this failure is pretend)", flush=True)
        sys.exit(1)
print("practice run finished: %s" % out, flush=True)
'''


def script(params: dict) -> tuple[str, str]:
    """(실행 스크립트 원본, 결과 폴더). 값은 여기서 범위를 좁힌다"""
    import json
    from .jobs import safe_name
    shape = params.get("shape") if params.get("shape") in SHAPES else "good"
    epochs = max(3, min(int(float(params.get("epochs") or 20)), 300))
    seconds = max(0.2, min(float(params["seconds"] if params.get("seconds") is not None else 1), 30))     # ★0을 "없음"으로 읽어 1초가 됐다
    name = safe_name(params.get("name") or f"practice_{shape}") or "practice"
    out = DIR / name
    k = 2
    while out.exists():                                   # 같은 이름이면 _2, _3 (앞 기록을 덮지 않게)
        out = DIR / f"{name}_{k}"; k += 1
    p = {"out": str(out), "epochs": epochs, "shape": shape, "seconds": seconds, "seed": params.get("seed", 0)}
    return TEMPLATE.format(params=json.dumps(p)), str(out)
