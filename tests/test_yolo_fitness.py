"""YOLO 분할·포즈·분류의 최고 에폭 = best.pt가 저장된 에폭(Ultralytics 8.4 fitness).
분할 = 마스크 + 박스 mAP50-95, 포즈 = 키포인트 + 박스, 분류 = top1 + top5. 검출은 mAP50-95(B) 하나라 그대로."""
from pathlib import Path

from epokio import analysis, schema
from epokio.scan import read_run


def _seg(d: Path, task="segment", head="M"):
    d.mkdir(parents=True)
    (d / "args.yaml").write_text(f"task: {task}\nepochs: 30\n", encoding="utf-8")
    cols = ["epoch", "time", f"metrics/precision(B)", "metrics/recall(B)", "metrics/mAP50(B)", "metrics/mAP50-95(B)",
            f"metrics/precision({head})", f"metrics/recall({head})", f"metrics/mAP50({head})", f"metrics/mAP50-95({head})"]
    rows = []
    for e in range(1, 31):
        box, other = 0.30 + e * 0.005, 0.30 + min(e, 24) * 0.005 - max(0, e - 24) * 0.001
        if e == 27:                       # 마스크는 24에폭보다 조금 낮지만 박스와 더하면 가장 크다 = best.pt
            box, other = 0.53, 0.418
        if e > 27:
            box = 0.50
        rows.append(",".join(str(x) for x in (e, e * 60, 0.6, 0.6, box + 0.2, box, 0.6, 0.6, other + 0.2, other)))
    (d / "results.csv").write_text(",".join(cols) + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return d


def test_segment_best_epoch_is_where_best_pt_was_saved(tmp_path):
    """★Mask 칸은 24에폭, Box 칸은 27에폭이라 '최고 에폭 기준' 칸들이 달랐고, 목록의 최고 점수·해설도 best.pt와 달랐다"""
    d = _seg(tmp_path / "segment" / "train")
    r = read_run(d)
    assert r.metric_name == "metrics/mAP50-95(M)" and r.best_epoch == 27 and abs(r.best - 0.418) < 1e-9
    a = analysis.analyze(d)
    assert {h.head: h.best_epoch for h in a.heads} == {"B": 27, "M": 27}
    assert a.score["best_epoch"] == 27


def test_pose_uses_keypoints_plus_box(tmp_path):
    d = _seg(tmp_path / "pose" / "train", task="pose", head="P")
    assert read_run(d).best_epoch == 27


def test_detect_and_a_chosen_score_keep_their_own_best(tmp_path):
    rows = [{"epoch": "1", "metrics/mAP50-95(B)": "0.3"}, {"epoch": "2", "metrics/mAP50-95(B)": "0.5"}]
    assert schema.fitness_index(rows, "metrics/mAP50-95(B)") is None          # 검출은 대표 점수 최고 그대로
    rows = [{"epoch": "1", "metrics/accuracy_top1": "0.80", "metrics/accuracy_top5": "0.90"},
            {"epoch": "2", "metrics/accuracy_top1": "0.81", "metrics/accuracy_top5": "0.85"},
            {"epoch": "3", "metrics/accuracy_top1": "0.79", "metrics/accuracy_top5": "nan"}]
    assert schema.fitness_index(rows, "metrics/accuracy_top1") == 0           # 분류: top1+top5(같으면 앞), NaN 줄은 건너뛴다
