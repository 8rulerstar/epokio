"""HF 여러 에폭 학습의 첫 에폭: 막대가 global_step/max_steps를 따른다."""
import json

from epokio.scan import Run, read_run


def test_progress_uses_the_step_fraction_inside_the_first_epoch(tmp_path):
    """★남은 시간은 global_step/max_steps로 나오는데 막대는 첫 에폭 내내 0%였다"""
    d = tmp_path / "ft" / "checkpoint-50"
    d.mkdir(parents=True)
    log = [{"loss": 2.0, "learning_rate": 2e-5, "epoch": s / 300, "step": s} for s in (10, 20, 30, 40, 50)]
    (d / "trainer_state.json").write_text(json.dumps(
        {"epoch": 50 / 300, "global_step": 50, "max_steps": 900, "num_train_epochs": 3, "log_history": log}))
    r = read_run(tmp_path / "ft")
    assert r is not None and r.epoch == 0 and r.total == 3
    assert abs(r.progress - 50 / 900) < 1e-9 and abs(r.to_dict()["fraction"] - 50 / 900) < 1e-9


def test_fraction_never_lowers_or_overfills_the_bar():
    base = dict(name="r", path=".", elapsed=0, eta=None, metric=None, metric_name="", best=None,
                best_epoch=None, state="running", idle=0)
    assert Run(epoch=2, total=4, fraction=0.1, **base).progress == 0.5
    assert Run(epoch=4, total=4, fraction=0.9, **base).progress == 1.0
    assert Run(epoch=0, total=None, fraction=0.3, **base).progress is None
    assert Run.from_dict({**base, "epoch": 1, "total": 3}).progress == 1 / 3        # 옛 agent(필드 없음)
