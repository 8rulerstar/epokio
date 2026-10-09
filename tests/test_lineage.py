"""버전 관리 깊이: 계보, 데이터 목록과 차이, 모델 등록부, 단계, 낮을수록 좋은 목표."""
import json
from pathlib import Path

from epokio import lineage, runmeta
from epokio.scan import Run


def _dataset(root: Path, n_img: int, labels: dict[str, str]) -> Path:
    for sub in ("images/train", "labels/train"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    for i in range(n_img):
        (root / f"images/train/{i}.jpg").write_bytes(b"x" * (i + 1))
    for name, text in labels.items():
        (root / f"labels/train/{name}.txt").write_text(text)
    y = root / "data.yaml"
    y.write_text(f"path: {root}\ntrain: images/train\nval: images/train\n")
    return y


def test_manifest_diff_finds_added_removed_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(lineage, "DATA_DIR", tmp_path / "ds")
    ds = tmp_path / "data"
    y = _dataset(ds, 3, {"0": "0 .5 .5 .1 .1\n", "1": "1 .5 .5 .1 .1\n"})
    a = lineage.record(y)
    (ds / "images/train/0.jpg").unlink()                          # 빠짐
    (ds / "images/train/9.jpg").write_bytes(b"new")              # 더해짐
    (ds / "labels/train/1.txt").write_text("1 .5 .5 .1 .1\n0 .2 .2 .1 .1\n")   # 바뀜(박스 하나 더)
    b = lineage.record(y)
    assert a and b and a != b
    d = lineage.diff(a, b)
    assert d["images"] == {"added": 1, "removed": 1, "changed": 0, "before": 3, "after": 3}
    assert d["labels"]["changed"] == 1 and "labels/train/1.txt" in d["changed"]
    assert {x["cls"]: (x["before"], x["after"]) for x in d["boxes"]}["0"] == (1, 2)


def test_diff_refuses_unknown_versions(tmp_path, monkeypatch):
    monkeypatch.setattr(lineage, "DATA_DIR", tmp_path / "ds")
    import pytest
    with pytest.raises(ValueError):
        lineage.diff("deadbeef", "../../etc")


def _run(d: Path, model: str) -> Path:
    (d / "weights").mkdir(parents=True)
    (d / "weights/best.pt").write_bytes(b"w")
    (d / "args.yaml").write_text(f"model: {model}\nepochs: 3\n")
    return d


def test_lineage_parent_children_and_ancestors(tmp_path):
    a = _run(tmp_path / "a", "yolo11n.pt")
    b = _run(tmp_path / "b", str(a / "weights/best.pt"))
    c = _run(tmp_path / "c", str(b / "weights/last.pt"))
    la = lineage.lineage(a, [a, b, c])
    assert la["parent"] is None and la["pretrained"] and [k["name"] for k in la["children"]] == ["b"]
    lc = lineage.lineage(c, [a, b, c])
    assert [x["name"] for x in lc["ancestors"]] == ["b", "a"] and lc["parent"]["name"] == "b"


def test_promote_copies_and_versions(tmp_path):
    r = _run(tmp_path / "runs/exp", "yolo11n.pt")
    reg = tmp_path / "models"
    m1 = lineage.promote(r, "helmet det", {"best": 0.7}, reg)
    m2 = lineage.promote(r, "helmet det", {"best": 0.8}, reg)
    assert (m1["version"], m2["version"]) == (1, 2) and Path(m2["path"]).read_bytes() == b"w"
    assert m1["name"] == "helmet_det" and (r / "weights/best.pt").exists()
    assert [m["version"] for m in lineage.registry(reg)] == [2, 1]


def test_stage_only_known_values(tmp_path, monkeypatch):
    monkeypatch.setattr(runmeta, "FILE", tmp_path / "m.json")
    assert runmeta.update("/r", {"stage": "production"})["stage"] == "production"
    assert runmeta.update("/r", {"stage": "shipped!"})["stage"] == "production"


def test_goal_respects_lower_is_better(tmp_path, monkeypatch):
    monkeypatch.setattr(runmeta, "FILE", tmp_path / "m.json")
    runmeta.update("/r", {"goal": 0.3})
    r = Run(name="r", path=Path("/r"), epoch=3, total=10, elapsed=1, eta=None, metric=0.25, metric_name="metrics/rmse",
            best=0.25, best_epoch=3, state="running", idle=1)
    assert runmeta.goals_reached([r]) == [r]                      # rmse 0.25 ≤ 0.3 → 목표 도달
    json.loads((tmp_path / "m.json").read_text())


def test_label_content_change_changes_fingerprint_after_cache_window(tmp_path, monkeypatch):
    from epokio import versions
    y = _dataset(tmp_path / "d", 1, {"0": "0 .5 .5 .1 .1\n"})
    a = versions.data_fingerprint(y)
    f = tmp_path / "d/labels/train/0.txt"
    f.write_text("0 .5 .5 .1 .1\n0 .1 .1 .1 .1\n")                 # 폴더 시각은 그대로, 내용만
    import os, time
    os.utime(f, (time.time() + 5, time.time() + 5))
    monkeypatch.setattr(versions.time, "time", lambda: time.monotonic() + 10_000_000)   # 캐시 창을 넘긴다
    assert versions.data_fingerprint(y) != a


def test_data_versions_are_numbered_per_yaml_in_the_order_seen(tmp_path, monkeypatch):
    monkeypatch.setattr(lineage, "DATA_DIR", tmp_path / "ds")
    ds, other = tmp_path / "data", tmp_path / "other"
    y = _dataset(ds, 2, {"0": "0 .5 .5 .1 .1\n"})
    z = _dataset(other, 1, {})
    t = iter(range(100, 200))
    monkeypatch.setattr(lineage.time, "time", lambda: next(t))
    a = lineage.record(y)
    lineage.record(z)                                                # 다른 data.yaml은 따로 센다
    (ds / "images/train/7.jpg").write_bytes(b"new")
    monkeypatch.setattr(lineage.versions, "_cache", {})
    b = lineage.record(y)
    assert lineage.data_version(a) == {"n": 1, "of": 2} and lineage.data_version(b) == {"n": 2, "of": 2}
    assert lineage.data_version("deadbeef") is None
    (tmp_path / "ds" / "index.json").unlink()                        # 이 기능 전에 적힌 목록들: 한 번 읽어 다시 만든다
    assert lineage.data_version(b) == {"n": 2, "of": 2}


def test_a_run_keeps_the_data_it_trained_on(tmp_path, monkeypatch):
    """상세를 열 때 지문을 재서, 학습 뒤 데이터가 바뀌면 옛 학습도 새 데이터로 학습한 것처럼 보였다"""
    import json
    from epokio import repro, rundetail
    monkeypatch.setattr(lineage, "DATA_DIR", tmp_path / "ds")
    ds = tmp_path / "data"
    y = _dataset(ds, 2, {"0": "0 .5 .5 .1 .1\n"})
    run = tmp_path / "run"
    run.mkdir()
    (run / "args.yaml").write_text(f"data: {y}\n")
    start = repro.data_info(y)["fingerprint"]                        # 대기열이 학습 시작 때 적는 값
    (run / repro.FILE).write_text(json.dumps({"data": {"fingerprint": start}}))
    assert rundetail.detail_versions(run)["data"] == start and "data_now" not in rundetail.detail_versions(run)
    (ds / "images/train/7.jpg").write_bytes(b"new")
    monkeypatch.setattr(lineage.versions, "_cache", {})
    v = rundetail.detail_versions(run)
    assert v["data"] == start and v["data_now"] not in (None, start)


def test_a_run_resumed_in_place_is_not_its_own_child(tmp_path):
    """★`yolo train resume`은 args.yaml의 model을 제 weights/last.pt로 바꾼다. 그 학습이 제 자식으로 보였고 '사전 학습 가중치에서 시작'이라 했다"""
    r = tmp_path / "train"
    _run(r, str(r / "weights" / "last.pt"))
    other = _run(tmp_path / "other", "yolo11n.pt")
    got = lineage.lineage(r, [r, other])
    assert got["children"] == [] and got["parent"] is None and got["ancestors"] == [] and not got["pretrained"]
