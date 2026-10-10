"""0.9.2 외부 검토(2026-10-10)에서 나온 것: 0부터 적는 YOLOv8 로그, 객체가 아닌 config.json, step 학습의 '0s left'."""
import json
import os
import time

from epokio import config, scan


def _old(d, sec=3600):
    t = time.time() - sec
    for p in [d, *d.iterdir()]:
        os.utime(p, (t, t))


def test_yolov8_8_0_logs_that_count_epochs_from_zero_are_shifted(tmp_path):
    """8.0.200 전의 YOLOv8은 results.csv에 epoch를 0부터 적었다(공백으로 칸을 맞춤). 다 끝난 2에폭이 '1/2'였다"""
    d = tmp_path / "train"
    d.mkdir()
    rows = [("epoch", "train/box_loss", "metrics/mAP50(B)"), ("0", "1.0", "0.1"), ("1", "0.9", "0.2")]
    (d / "results.csv").write_text("".join(",".join(f"{c:>23}" for c in r) + "\n" for r in rows))
    (d / "args.yaml").write_text("epochs: 2\n")
    _old(d)
    r = scan.read_run(d)
    assert (r.epoch, r.total, r.state) == (2, 2, "done")


def test_logs_that_count_from_one_are_unchanged(tmp_path):
    d = tmp_path / "train"
    d.mkdir()
    (d / "results.csv").write_text("epoch,train/box_loss,metrics/mAP50(B)\n1,1.0,0.1\n2,0.9,0.2\n")
    (d / "args.yaml").write_text("epochs: 5\n")
    _old(d)
    assert scan.read_run(d).epoch == 2


def test_a_config_that_is_not_an_object_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FILE", tmp_path / "config.json")
    for text in ("null", "[1, 2]", '"x"', "3"):
        config.FILE.write_text(text)
        assert config.load() == config.DEFAULTS


def test_a_config_value_of_the_wrong_type_or_range_is_ignored_or_clamped(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FILE", tmp_path / "config.json")
    config.FILE.write_text(json.dumps({"disk_low_gb": "x", "stall_min": 1e999, "scan_mode": 7, "gpu_hot_c": 500}))
    c = config.load()
    assert c["disk_low_gb"] == config.DEFAULTS["disk_low_gb"] and c["stall_min"] == config.DEFAULTS["stall_min"]
    assert c["scan_mode"] == "auto" and c["gpu_hot_c"] == 105


def test_a_step_run_whose_files_appeared_together_has_no_time_left_rather_than_zero(tmp_path):
    """HF 폴더와 trainer_state.json이 거의 같이 생기면 경과 0.0001초로 재서 진행 중인 학습이 '0s left'였다"""
    d = tmp_path / "hf"
    d.mkdir()
    (d / "trainer_state.json").write_text(json.dumps({
        "global_step": 400, "max_steps": 1000, "num_train_epochs": 1,
        "log_history": [{"step": 400, "loss": 0.5, "eval_loss": 0.4}]}))
    r = scan.read_run(d, now=time.time())
    assert r.x_axis == "step" and r.state == "running" and r.eta is None


def test_a_tensorboard_run_whose_loss_turns_nan_has_failed(tmp_path):
    """TensorBoard의 손실 열은 train/loss라 '_loss'로 끝나는 열만 보던 검사가 NaN을 놓쳤다(2026-10-10)"""
    from test_tfevents import _event, _value, _write

    _write(tmp_path / "events.out.tfevents.1700000000.host.1.0", [
        _event(1000.0, 0, version="brain.Event:2"),
        _event(1000.0, 1, [_value("train/loss", 0.9)]),
        _event(1020.0, 3, [_value("train/loss", float("nan"))]),
    ])
    assert scan.read_run(tmp_path).state == "failed"


def test_adding_an_alert_says_which_machine_name_it_carries(tmp_path, monkeypatch, capsys):
    from epokio import alerts_cli

    monkeypatch.setattr(alerts_cli, "_label", lambda: "lab-07")
    assert alerts_cli.main(["--add", "https://ntfy.sh/a-long-random-topic-k3x9"]) == 0
    assert "Alerts name this machine 'lab-07'" in capsys.readouterr().out
