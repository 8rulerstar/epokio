"""깨진 기록 하나가 폴더 전체를 지우지 않는다, 그리고 step 학습의 남은 시간.
★2026-10-08 외부 검토: 열이 넘치는 CSV 한 줄이나 배열로 된 trainer_state.json 하나 때문에 scan이 예외를 올려
  같은 폴더의 정상 학습까지 0개로 보였고, 100 step마다 기록하는 step 학습은 15분 남은 것이 "1d 1h"로 나왔다."""
import os
import time

from epokio import scan

from test_tfevents import _event, _value, _write


def _csv(d, text):
    d.mkdir(parents=True)
    (d / "results.csv").write_text(text)
    t = time.time() - 60
    os.utime(d / "results.csv", (t, t))


def test_a_row_with_extra_columns_is_read(tmp_path):
    _csv(tmp_path / "a", "epoch,train/box_loss,time\n1,1.0,10\n2,0.9,20,EXTRA,X\n")
    r = scan.read_run(tmp_path / "a")
    assert r is not None and r.epoch == 2


def test_a_trainer_state_that_is_not_an_object_is_skipped(tmp_path):
    d = tmp_path / "hf"
    d.mkdir()
    (d / "trainer_state.json").write_text("[1, 2]")
    assert scan.read_run(d) is None


def test_one_run_that_fails_does_not_hide_the_others(tmp_path, monkeypatch):
    for name in ("good1", "good2", "bad"):
        _csv(tmp_path / name, "epoch,train/box_loss,time\n1,1.0,10\n2,0.9,20\n")
    real = scan.read_run

    def read_run(d, now=None):
        if d.name == "bad":
            raise ValueError("broken log")
        return real(d, now=now)

    monkeypatch.setattr(scan, "read_run", read_run)
    assert sorted(r.name for r in scan.scan(tmp_path)) == ["good1", "good2"]


def test_step_run_eta_counts_time_per_step(tmp_path):
    """100 step마다 60초: 남은 1,500 step은 15분이다(줄 사이 60초 x 1,500 = 25시간이 아니라)"""
    (tmp_path / "args.json").write_text('{"max_steps": 2000}')
    now = time.time()
    start = now - 300
    _write(tmp_path / "events.out.tfevents.1700000000.host.1.0", [
        _event(start, 0, version="brain.Event:2"),
        *[_event(start + 60 * i, 100 * i, [_value("train/loss", 1.0 / i)]) for i in range(1, 6)],
    ])
    r = scan.read_run(tmp_path, now=now)
    assert r.x_axis == "step" and r.epoch == 500 and r.state == "running"
    assert abs(r.eta - 900) < 1


def test_epoch_run_eta_is_unchanged(tmp_path):
    _csv(tmp_path / "e", "epoch,train/box_loss,time\n1,1.0,60\n2,0.9,120\n3,0.8,180\n")
    (tmp_path / "e" / "args.yaml").write_text("epochs: 10\n")
    r = scan.read_run(tmp_path / "e", now=time.time())
    assert r.epoch == 3 and r.total == 10 and abs(r.eta - 420) < 1
