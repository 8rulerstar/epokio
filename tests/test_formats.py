"""형식 자료(tests/fixtures/formats)를 모든 층이 같은 뜻으로 읽는지. 형식이 바뀌면 여기가 먼저 깨진다."""
import json
import shutil
from pathlib import Path

import pytest

from epokio import rundetail, scan, schema

FIX = Path(__file__).parent / "fixtures" / "formats"

# 폴더 → (대표 점수, 최고 에폭, 머리들)
EXPECT = {
    "ultralytics84_detect": ("metrics/mAP50-95(B)", 6, ["B"]),
    "ultralytics84_yolo26_nodfl": ("metrics/mAP50-95(B)", 6, ["B"]),
    "ultralytics84_segment": ("metrics/mAP50-95(M)", 6, ["B", "M"]),
    "ultralytics84_pose": ("metrics/mAP50-95(P)", 6, ["B", "P"]),
    "ultralytics84_classify": ("metrics/accuracy_top1", 6, []),
    "ultralytics84_depth": ("metrics/delta1", 6, []),
    "yolov5_detect": ("metrics/mAP50-95(B)", 6, ["B"]),       # 0부터 세던 에폭이 1부터로
    "custom_script_csv": ("val_macro_f1", 5, []),              # 직접 짠 스크립트: 접두사 없는 val_acc·val_macro_f1도 점수(2026-09-22)
}


def test_every_fixture_has_an_expectation():
    assert {p.name for p in FIX.iterdir() if p.is_dir()} == set(EXPECT)


@pytest.mark.parametrize("name", sorted(EXPECT))
def test_format(name, tmp_path):
    d = tmp_path / name
    shutil.copytree(FIX / name, d)
    metric, best_ep, heads = EXPECT[name]
    r = scan.read_run(d)
    assert r and r.metric_name == metric and r.best_epoch == best_ep and r.epoch == 6
    det = rundetail.detail(d)
    assert [h["head"] for h in det["heads"]] == heads
    info = det["column_info"]
    assert set(info) == set(det["columns"])
    assert all(i["kind"] != "other" for k, i in info.items() if k not in ("epoch", "time")), info
    json.dumps(det)                                                   # 화면으로 보낼 수 있어야 한다


def test_representative_score_follows_ultralytics_task2metric():
    """대표 점수 = Ultralytics 공식 TASK2METRIC (사용자 결정 2026-09-22). task를 몰라도 열만으로 같게"""
    cols = json.loads((Path(__file__).parent / "fixtures" / "ultralytics_columns.json").read_text())
    for name, c in cols.items():
        if name.startswith("_"):
            continue
        want = schema.TASK2METRIC[c["task"]]
        assert schema.pick_metric(c["header"]) == want, name
        assert schema.pick_metric(c["header"], task=c["task"]) == want, name


@pytest.mark.parametrize("name", sorted(n for n in EXPECT if n.startswith("ultralytics84_")))
def test_ultralytics_fixtures_raise_no_format_warning(name):
    """형식 자료가 8.4.150 실제 열 이름과 같아야 한다(depth는 dlog·dgrad 손실, 2026-09-22 갱신)"""
    from epokio import adapters
    d = FIX / name
    header = (d / "results.csv").read_text().splitlines()[0].split(",")
    task = (d / "args.yaml").read_text().split("task:")[1].split()[0]
    assert adapters.ultralytics_warnings(header, task) == []


def test_old_files_without_mask_or_pose_fall_back_to_box():
    assert schema.pick_metric(["epoch", "metrics/mAP50(B)", "metrics/mAP50-95(B)"]) == "metrics/mAP50-95(B)"
    assert schema.pick_metric(["epoch", "metrics/mAP50-95(B)"], task="segment") == "metrics/mAP50-95(B)"


def test_lower_is_better_scores():
    assert not schema.higher_is_better("metrics/rmse")
    assert not schema.higher_is_better("metrics/abs_rel")
    assert schema.higher_is_better("metrics/mAP50-95(B)")
    assert not schema.higher_is_better("val/box_loss")


def test_pretty_names():
    assert schema.pretty("metrics/mAP50-95(B)") == "mAP50-95 · Box"
    assert schema.pretty("val/box_loss") == "val box"
    assert schema.pretty("train/loss") == "train loss"
    assert schema.info("lr/pg0")["kind"] == "lr"


def test_task_metric_single_source():
    """대표 점수 표는 schema.TASK2METRIC 한 벌. adapters는 같은 객체를 쓴다"""
    from epokio import adapters
    assert adapters.ULTRA_TASK_METRIC is schema.TASK2METRIC
    assert set(schema.TASK2METRIC) == adapters.ULTRA_TASKS
