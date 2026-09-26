"""형식 자료 만들기. 머리줄은 README의 근거에서 옮겼고, 값은 만든 숫자다.
다시 만들기: python tests/fixtures/formats/make.py
"""
from pathlib import Path

HERE = Path(__file__).parent
D = "metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B)"
M, P = D.replace("(B)", "(M)"), D.replace("(B)", "(P)")
LR = "lr/pg0,lr/pg1,lr/pg2"
SETS = {
    "ultralytics84_detect": ("detect", f"epoch,time,train/box_loss,train/cls_loss,train/dfl_loss,{D},val/box_loss,val/cls_loss,val/dfl_loss,{LR}"),
    "ultralytics84_yolo26_nodfl": ("detect", f"epoch,time,train/box_loss,train/cls_loss,train/l1_loss,{D},val/box_loss,val/cls_loss,val/l1_loss,{LR}"),
    "ultralytics84_segment": ("segment", f"epoch,time,train/box_loss,train/seg_loss,train/cls_loss,train/dfl_loss,train/sem_loss,{D},{M},val/box_loss,val/seg_loss,val/cls_loss,val/dfl_loss,val/sem_loss,{LR}"),
    "ultralytics84_pose": ("pose", f"epoch,time,train/box_loss,train/pose_loss,train/kobj_loss,train/cls_loss,train/dfl_loss,{D},{P},val/box_loss,val/pose_loss,val/kobj_loss,val/cls_loss,val/dfl_loss,{LR}"),
    "ultralytics84_classify": ("classify", f"epoch,time,train/loss,metrics/accuracy_top1,metrics/accuracy_top5,val/loss,{LR}"),
    "ultralytics84_depth": ("depth", "epoch,time,train/dlog_loss,train/dgrad_loss,metrics/delta1,metrics/delta2,metrics/delta3,metrics/abs_rel,metrics/rmse,metrics/silog,val/dlog_loss,val/dgrad_loss,lr/pg0"),
    "yolov5_detect": ("detect", "               epoch,      train/box_loss,      train/obj_loss,      train/cls_loss,   metrics/precision,      metrics/recall,     metrics/mAP_0.5,metrics/mAP_0.5:0.95,        val/box_loss,        val/obj_loss,        val/cls_loss,               x/lr0,               x/lr1,               x/lr2"),
}


def value(c: str, e: int, v5: bool) -> str:
    c = c.strip()
    if c == "epoch":
        return str(e if v5 else e + 1)
    if c == "time":
        return f"{30.5 * (e + 1):.6g}"
    if "loss" in c:
        return f"{1.5 - 0.1 * e:.6g}"
    if "lr" in c:
        return "0.00066"
    if any(x in c for x in ("rmse", "abs_rel", "silog")):
        return f"{0.9 - 0.1 * e:.6g}"                   # 낮을수록 좋은 점수: 마지막이 최고
    return f"{0.2 + 0.1 * e:.6g}"


for name, (task, header) in SETS.items():
    d = HERE / name
    d.mkdir(exist_ok=True)
    cols = header.split(",")
    rows = [",".join(value(c, e, name.startswith("yolov5")) for c in cols) for e in range(6)]
    (d / "results.csv").write_text("\n".join([header, *rows]) + "\n")
    (d / "args.yaml").write_text(f"task: {task}\nepochs: 10\n")
