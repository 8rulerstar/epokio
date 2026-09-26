"""Ultralytics 작업별 results.csv 열 이름을 어댑터가 모두 읽는지, 모르는 형식이면 조용히 넘기지 않고 경고를 채우는지.
열 표: tests/fixtures/ultralytics_columns.json (Ultralytics 8.4.150이 쓰는 공개 results.csv 출력 열 이름 목록, 코드 아님)"""
import json
from pathlib import Path

import pytest

from epokio import adapters, scan

TABLE = {k: v for k, v in json.loads((Path(__file__).parent / "fixtures" / "ultralytics_columns.json").read_text()).items()
         if not k.startswith("_")}


def make(d: Path, header, task=None, epochs=3):
    d.mkdir(parents=True, exist_ok=True)
    lines = [",".join(header)] + [",".join(str(e + 1) if c == "epoch" else f"{0.1 * (e + 1):.3g}" for c in header)
                                   for e in range(epochs)]
    (d / "results.csv").write_text("\n".join(lines) + "\n")
    if task:
        (d / "args.yaml").write_text(f"task: {task}\nepochs: 10\n")
    return d


def test_table_covers_every_task():
    assert {v["task"] for v in TABLE.values()} == adapters.ULTRA_TASKS


@pytest.mark.parametrize("name", sorted(TABLE))
def test_known_columns_load_without_warning(name, tmp_path):
    t = TABLE[name]
    d = make(tmp_path / name, t["header"], t["task"])
    got = adapters.load(d)
    assert got.framework == "ultralytics" and len(got.rows) == 3
    assert set(got.rows[0]) == set(t["header"])
    assert got.warnings == []
    r = scan.read_run(d)
    assert r and r.metric_name and r.epoch == 3


def test_unknown_column_warns(tmp_path):
    h = TABLE["detect"]["header"] + ["train/new_loss", "metrics/mAP75(B)"]
    got = adapters.load(make(tmp_path / "r", h, "detect"))
    assert len(got.rows) == 3                                     # 읽기는 그대로
    assert any("train/new_loss" in w and "metrics/mAP75(B)" in w for w in got.warnings)


def test_renamed_metrics_warn(tmp_path):
    h = [c.replace("(B)", "(Box)") for c in TABLE["detect"]["header"]]
    w = adapters.load(make(tmp_path / "r", h, "detect")).warnings
    assert all(x.startswith("unknown format/version") for x in w)
    assert any("missing metrics/mAP50-95(B)" in x for x in w)


def test_unknown_task_and_no_metrics(tmp_path):
    w = adapters.load(make(tmp_path / "r", ["epoch", "time", "train/box_loss"], "track3d")).warnings
    assert any("no metrics/" in x for x in w) and any("unknown task 'track3d'" in x for x in w)


def test_header_only_file_is_checked(tmp_path):
    d = make(tmp_path / "r", TABLE["obb"]["header"], "obb", epochs=0)
    got = adapters.load(d)
    assert got.rows == [] and got.warnings == []
    d2 = make(tmp_path / "r2", ["epoch", "time", "weird"], "obb", epochs=0)
    assert adapters.load(d2).warnings


def test_yolov5_names_are_known(tmp_path):
    fx = Path(__file__).parent / "fixtures" / "formats" / "yolov5_detect"
    d = tmp_path / "v5"
    d.mkdir()
    for f in fx.iterdir():
        (d / f.name).write_bytes(f.read_bytes())
    assert adapters.load(d).warnings == []


def test_existing_loaded_fields_kept(tmp_path):
    got = adapters.load(make(tmp_path / "r", TABLE["detect"]["header"], "detect"))
    assert got.total is None and got.args == {} and got.source.name == "results.csv"
