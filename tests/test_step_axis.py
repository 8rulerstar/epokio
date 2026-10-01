"""step으로 적는 학습(x_axis=step). 예전엔 W&B·CSV에서 통째로 빠졌고, TensorBoard는 읽어도 화면이 'epoch 12000'이라 했다.
행 모양은 그대로("epoch" 자리에 step 번호), Run.x_axis로 단위만 알린다."""
import os
import time

from epokio import adapters, analysis, msg, notify, scan
from epokio.scan_names import x_count

from test_tfevents import _event, _value, _write
from test_wandb import config, history, run


def _old(d, sec=3600):
    """방금 쓴 파일이면 '도는 중'이 된다. 끝난 학습처럼 시각을 돌려 놓는다"""
    t = time.time() - sec
    for p in [d, *d.iterdir()]:
        os.utime(p, (t, t))


def test_wandb_without_epoch_is_read_by_step_and_thinned(tmp_path):
    recs = [config({"lr": 1e-4, "max_steps": 10000})]
    recs += [history({"train/loss": 2.0 - s / 10000, "_step": s}) for s in range(0, 5000)]
    d = run(tmp_path, recs)
    got = adapters.load(d)
    assert got.args["x_axis"] == "step" and got.total == 10000
    assert len(got.rows) <= 2000 and got.rows[-1]["epoch"] == "4999"        # 솎아도 마지막 step은 남는다
    assert got.rows[0] == {"epoch": "0", "train/train_loss": "2.0"}
    r = scan.read_run(d)
    assert r.x_axis == "step" and r.epoch == 4999 and r.total == 10000
    assert r.to_dict()["x_axis"] == "step"


def test_wandb_epoch_runs_are_unchanged(tmp_path):
    recs = [config({"epochs": 3, "max_steps": 999})]                         # epoch가 있으면 step 열쇠는 안 본다
    recs += [history({"epoch": e + 1, "train/loss": 1.0 / (e + 1), "_step": e}) for e in range(3)]
    d = run(tmp_path, recs)
    got = adapters.load(d)
    assert "x_axis" not in got.args and got.total == 3
    assert scan.read_run(d).x_axis == "epoch"


def test_custom_csv_with_a_step_column(tmp_path):
    d = tmp_path / "llm"
    d.mkdir()
    (d / "train_log.csv").write_text("iter,loss,val_loss\n100,2.0,2.1\n200,1.5,1.7\n300,1.2,1.4\n")
    (d / "config.yaml").write_text("max_iters: 1000\nepochs: 3\n")
    got = adapters.load(d)
    assert got.framework == "custom" and got.args == {"x_axis": "step"} and got.total == 1000
    assert [r["epoch"] for r in got.rows] == ["100", "200", "300"] and got.rows[0]["val/val_loss"] == "2.1"
    r = scan.read_run(d)
    assert r.x_axis == "step" and r.epoch == 300 and r.total == 1000


def test_epoch_csv_still_reads_as_epochs(tmp_path):
    d = tmp_path / "cls"
    d.mkdir()
    (d / "train_log.csv").write_text("epoch,loss\n0,1.0\n1,0.8\n")
    got = adapters.load(d)
    assert [r["epoch"] for r in got.rows] == ["1", "2"] and got.args == {}
    assert scan.read_run(d).x_axis == "epoch"


def test_tensorboard_step_run_end_to_end(tmp_path):
    (tmp_path / "args.json").write_text('{"num_train_epochs": 3, "max_steps": 500}')
    _write(tmp_path / "events.out.tfevents.1700000000.host.1.0", [
        _event(1000.0, 0, version="brain.Event:2"),
        _event(1000.0, 100, [_value("train/loss", 0.9)]),
        _event(1010.0, 200, [_value("train/loss", 0.7)]),
    ])
    r = scan.read_run(tmp_path)
    assert r.framework == "tensorboard" and r.x_axis == "step"
    assert r.epoch == 200 and r.total == 500                                 # 에폭 수(3)를 step 총량으로 쓰지 않는다


def test_progress_text_and_phone_body_say_step(tmp_path):
    r = scan.Run(name="llm", path=tmp_path, epoch=12000, total=100000, elapsed=60, eta=None, metric=None,
                 metric_name="", best=None, best_epoch=None, state="running", idle=1, x_axis="step")
    assert x_count(r) == "12,000/100,000"
    assert "step 12,000/100,000" in notify.body_of(notify.Event("stalled", r, "running"))
    r.x_axis = "epoch"
    assert x_count(r) == "12000/100000"


def _plateau_steps(tmp_path):
    """점수가 step 3,000 근처에서 멈추고 그 뒤로 그대로인 step 학습(정체 해설이 나와야 한다)"""
    recs = []
    for i in range(20):
        s = (i + 1) * 500
        acc = min(0.5 + i * 0.05, 0.8)
        recs.append(history({"train/loss": 1.0 - i * 0.01, "val/accuracy": acc, "_step": s}))
    d = run(tmp_path, recs)
    _old(d)
    return d


def test_notes_for_a_step_run_say_step(tmp_path):
    d = _plateau_steps(tmp_path)
    a = analysis.analyze(d)
    text = " ".join(o for o, _ in a.notes)
    assert "step 3500 of 10000" in text and "epoch" not in text.lower()
    assert all(k.get("unit") == "step" for k in a.kinds)
    assert all(analysis.next_run(k, {}, "best.pt") is None for k in a.kinds)    # 에폭 수를 제안하지 않는다
    msg.set_from_header("ko")
    try:
        ko = " ".join(o for o, _ in analysis.analyze(d).notes)
    finally:
        msg.set_from_header("en")
    assert "스텝" in ko and "에폭" not in ko
    assert msg.tr("epoch {n}", n=1) == "epoch 1"                              # 해설이 끝나면 단위가 돌아온다
