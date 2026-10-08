"""대표 점수 고정: 학습마다 또는 폴더마다(그 아래 학습 전부), `epokio score` 명령, 자동으로 고른 이유"""
import pytest

from epokio import rundetail, runmeta, score_cli
from epokio.scan import read_run


@pytest.fixture(autouse=True)
def _meta(tmp_path, monkeypatch):
    monkeypatch.setattr(runmeta, "FILE", tmp_path / "meta.json")


def _keras(d, rows=((0.5, 1.0, 0.4), (0.6, 0.8, 0.3), (0.7, 0.9, 0.35))):
    d.mkdir(parents=True)
    (d / "training.log").write_text("epoch,accuracy,loss,val_accuracy,val_loss,val_mae\n" + "".join(
        f"{i},{a},{l},{a},{l},{m}\n" for i, (a, l, m) in enumerate(rows)), encoding="utf-8")
    return d


def test_score_command_pins_a_run_and_auto_forgets(tmp_path, capsys):
    d = _keras(tmp_path / "runs" / "a")
    assert read_run(d).metric_name == "metrics/val_accuracy"
    assert score_cli.main([str(d), "val_mae", "--lower"]) == 0
    r = read_run(d)
    assert r.metric_name == "metrics/val_mae" and r.lower and r.best == 0.3
    assert rundetail.detail(d)["score_pick"]["why"] == "chosen"
    assert score_cli.main([str(d), "nope"]) == 2
    assert score_cli.main([str(d), "--auto"]) == 0
    assert read_run(d).metric_name == "metrics/val_accuracy"


def test_a_folder_choice_applies_to_every_run_under_it(tmp_path):
    a = _keras(tmp_path / "runs" / "a")
    b = _keras(tmp_path / "runs" / "b")
    assert score_cli.main([str(tmp_path / "runs"), "metrics/val_mae", "--lower"]) == 0
    assert read_run(a).metric_name == read_run(b).metric_name == "metrics/val_mae"
    assert rundetail.detail(a)["score_pick"]["why"] == "chosen_folder"
    runmeta.update(str(b), {"metric": "metrics/val_accuracy", "lower": False})      # 학습에 정한 것이 이긴다
    assert read_run(b).metric_name == "metrics/val_accuracy" and read_run(a).metric_name == "metrics/val_mae"


def test_the_run_detail_says_why_the_score_was_picked(tmp_path):
    d = _keras(tmp_path / "runs" / "a")
    sp = rundetail.detail(d)["score_pick"]
    assert sp == {"column": "metrics/val_accuracy", "why": "common", "lower": False}


def test_score_is_a_command(monkeypatch, capsys, tmp_path):
    from epokio import cli
    d = _keras(tmp_path / "runs" / "a")
    monkeypatch.setattr("sys.argv", ["epokio", "score", str(d), "--list"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0 and "metrics/val_mae" in capsys.readouterr().out
