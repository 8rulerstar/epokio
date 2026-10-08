"""학습 폴더들의 부모에 놓인 epoch·loss CSV가 아래 학습을 전부 가리던 것"""
from epokio.scan import scan


def _ultra(d, n=3):
    d.mkdir(parents=True)
    rows = ["epoch,train/box_loss,metrics/mAP50-95(B)"] + [f"{i},{1.0 / i:.3f},{0.1 * i:.3f}" for i in range(1, n + 1)]
    (d / "results.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _loose(f):
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("epoch,loss\n1,0.9\n2,0.5\n", encoding="utf-8")


def test_a_summary_csv_above_run_folders_does_not_swallow_them(tmp_path):
    for i in range(8):
        _ultra(tmp_path / "runs" / f"exp{i}")
    _loose(tmp_path / "runs" / "loss_summary.csv")
    got = sorted(r.name for r in scan(tmp_path))
    assert got == [f"exp{i}" for i in range(8)]


def test_a_loose_csv_next_to_one_run_folder_shows_the_run(tmp_path):
    _ultra(tmp_path / "runs" / "xss" / "exp")
    _loose(tmp_path / "runs" / "xss" / "mylog.csv")
    assert [r.name for r in scan(tmp_path)] == ["exp"]


def test_a_loose_csv_with_no_runs_below_is_still_a_run(tmp_path):
    _loose(tmp_path / "mine" / "train_log.csv")
    (tmp_path / "mine" / "plots").mkdir()
    assert [r.name for r in scan(tmp_path)] == ["mine"]
