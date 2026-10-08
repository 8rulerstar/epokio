"""연습 학습: 진짜 학습과 같은 모양으로 기록하고, fail 모양은 실패로 끝나며, 값 범위를 좁힌다"""
import subprocess
from pathlib import Path
import sys

from epokio import practice, schema


def _run(tmp_path, monkeypatch, **p):
    monkeypatch.setattr(practice, "DIR", tmp_path)
    src, out = practice.script({"seconds": 0.2, "epochs": 4, **p})
    f = tmp_path / "s.py"; f.write_text(src)
    r = subprocess.run([sys.executable, str(f)], capture_output=True, text=True, timeout=30)
    return r, Path(out)                       # out은 이미 DIR 아래 전체 경로. 윈도우 경로는 "/"로 안 잘린다


def test_good_run_writes_results_like_ultralytics(tmp_path, monkeypatch):
    r, out = _run(tmp_path, monkeypatch, shape="good", name="p1")
    assert r.returncode == 0, r.stderr
    lines = (out / "results.csv").read_text().splitlines()
    assert len(lines) == 5
    assert schema.pick_metric(lines[0].split(",")) is not None           # 대표 점수를 고를 수 있다
    assert "practice: true" in (out / "args.yaml").read_text()
    assert not (out / "weights").exists()                                   # 가짜 가중치는 만들지 않는다


def test_fail_shape_exits_nonzero(tmp_path, monkeypatch):
    r, out = _run(tmp_path, monkeypatch, shape="fail", name="p2")
    assert r.returncode == 1 and "pretend" in r.stdout


def test_clamps_and_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(practice, "DIR", tmp_path)
    (tmp_path / "same").mkdir()
    src, out = practice.script({"name": "same", "epochs": 99999, "seconds": 0, "shape": "evil"})
    assert out.endswith("same_2")
    assert '"epochs": 300' in src and '"shape": "good"' in src and '"seconds": 0.2' in src
