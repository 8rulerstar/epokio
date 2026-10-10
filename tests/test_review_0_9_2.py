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


def test_a_periodic_long_eval_does_not_raise_a_stall_once_it_has_been_seen(tmp_path):
    """에폭 1분, 5에폭마다 6분 평가: 한 번 본 긴 간격보다 짧은 조용함은 멎음이 아니다(2026-10-10)"""
    d = tmp_path / "run"
    d.mkdir()
    t, rows = 0.0, ["epoch,train/box_loss,metrics/mAP50(B),time"]
    for e in range(1, 11):
        t += 60 + (360 if e % 5 == 0 else 0)
        rows.append(f"{e},1.0,0.1,{t}")
    (d / "results.csv").write_text("\n".join(rows) + "\n")
    (d / "args.yaml").write_text("epochs: 50\n")
    mtime = time.time() - 400                     # 마지막 줄 뒤 400초: 다음 평가 중(문턱 180초보다 길다)
    os.utime(d / "results.csv", (mtime, mtime))
    assert scan.read_run(d).state == "running"


def test_adding_an_example_or_short_ntfy_topic_warns(tmp_path, monkeypatch, capsys):
    from epokio import alerts_cli

    monkeypatch.setattr(alerts_cli, "_label", lambda: "box")
    alerts_cli.main(["--add", "https://ntfy.sh/your-secret-topic"])
    assert "easy to guess" in capsys.readouterr().out
    alerts_cli.main(["--add", "https://ntfy.sh/kq83-zz71-pr0f-train-alerts"])
    assert "easy to guess" not in capsys.readouterr().out


def _csv_run(d, gaps, epochs=200, quiet=400):
    d.mkdir()
    t, rows = 0.0, ["epoch,train/box_loss,metrics/mAP50(B),time"]
    for e, g in enumerate(gaps, 1):
        t += g
        rows.append(f"{e},1.0,0.1,{t}")
    (d / "results.csv").write_text("\n".join(rows) + "\n")
    (d / "args.yaml").write_text(f"epochs: {epochs}\n")
    mtime = time.time() - quiet
    os.utime(d / "results.csv", (mtime, mtime))
    return scan.read_run(d).state


def test_an_evaluation_every_25_epochs_is_covered_once_it_has_recurred(tmp_path):
    """최근 20줄만 보면 25에폭마다의 평가가 창 밖으로 밀려 다시 '멎음'이었다"""
    gaps = [60 + (360 if e % 25 == 0 else 0) for e in range(1, 75)]  # 다음 평가(75) 중: 50의 간격은 최근 20줄 밖
    assert _csv_run(tmp_path / "a", gaps) == "running"


def test_a_one_off_long_delay_does_not_slow_stall_detection(tmp_path, monkeypatch):
    """한 번뿐인 40분 지연이 문턱을 끌어올려 진짜 멈춤을 50분 뒤에야 잡았다"""
    monkeypatch.setattr(scan, "STALE_SEC", 180)          # 다른 시험이 설정(stall_min)을 바꿔 둘 수 있다
    gaps = [60] * 5 + [2400] + [60] * 10
    assert _csv_run(tmp_path / "b", gaps) == "stalled"
