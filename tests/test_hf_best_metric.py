"""Hugging Face: 기록에 점수가 없고 trainer_state의 best_metric만 있을 때, 그리고 greater_is_better가 적어 둔 방향.
★best_metric을 버려 손실만 보였고, 방향은 열 이름 규칙만 봤다. 다른 점수가 없으면 eval_loss가 낮을수록 좋은 점수다."""
import json

from epokio.scan import read_run


def _hf(d, best, metric, greater=None, evals=("eval_loss",), state_extra=None):
    d.mkdir(parents=True)
    hist = []
    for ep, step in ((1, 100), (2, 200), (3, 300)):
        hist.append({"loss": 1.0 / ep, "epoch": float(ep), "step": step})
        hist.append({**{k: (0.5 + ep / 10 if k != "eval_loss" else 0.9 - ep / 10) for k in evals},
                     "epoch": float(ep), "step": step})
    st = {"log_history": hist, "epoch": 3.0, "global_step": 300, "max_steps": 300, "num_train_epochs": 3,
          "best_metric": best, "best_model_checkpoint": "out/checkpoint-200", **(state_extra or {})}
    (d / "trainer_state.json").write_text(json.dumps(st), encoding="utf-8")
    ta = {"metric_for_best_model": metric, "learning_rate": 5e-5}
    if greater is not None:
        ta["greater_is_better"] = greater
    (d / "training_args.json").write_text(json.dumps(ta), encoding="utf-8")
    return d


def test_best_metric_is_the_score_when_nothing_else_is_logged(tmp_path):
    r = read_run(_hf(tmp_path / "acc", 0.91, "accuracy", True))
    assert r.metric_name == "metrics/accuracy" and r.best == 0.91 and r.best_epoch == 2 and not r.lower
    r = read_run(_hf(tmp_path / "wer", 0.12, "eval_wer", False))
    assert r.metric_name == "metrics/wer" and r.best == 0.12 and r.lower           # 낮을수록 좋다


def test_eval_loss_is_a_lower_is_better_score_when_nothing_else_is_scored(tmp_path):
    """★손실만 평가하는 학습은 최고 점수가 늘 '–'였다. 기록된 eval_loss가 best_metric보다 먼저다"""
    r = read_run(_hf(tmp_path / "loss", 0.7, "eval_loss", False))
    assert r.metric_name == "metrics/eval_loss" and r.lower and abs(r.best - 0.6) < 1e-9 and r.best_epoch == 3


def test_a_loss_best_metric_fills_in_when_no_eval_was_logged(tmp_path):
    d = tmp_path / "trainonly"
    d.mkdir()
    st = {"log_history": [{"loss": 2.0 - i / 10, "epoch": i / 2, "step": i * 10} for i in range(1, 5)],
          "epoch": 2.0, "global_step": 40, "max_steps": 40, "num_train_epochs": 2, "best_metric": 1.5}
    (d / "trainer_state.json").write_text(json.dumps(st), encoding="utf-8")
    r = read_run(d)
    assert r.metric_name == "metrics/eval_loss" and r.best == 1.5 and r.lower


def test_a_max_steps_run_shows_step_progress_and_every_logged_loss(tmp_path):
    """★num_train_epochs 1, max_steps 750 학습이 '0/1 에폭'으로 남은 시간 없이 보였고, 곡선은 평가 때만 점이 찍혔다"""
    import time
    from epokio import adapters
    d = tmp_path / "out"
    ck = d / "checkpoint-500"
    ck.mkdir(parents=True)
    hist = [{"loss": 3.0 - s / 500, "epoch": s / 750, "step": s} for s in range(10, 510, 10)]
    hist += [{"eval_loss": 2.0 - s / 1000, "epoch": s / 750, "step": s} for s in (100, 200, 300, 400, 500)]
    st = {"log_history": hist, "epoch": 500 / 750, "global_step": 500, "max_steps": 750, "num_train_epochs": 1,
          "best_metric": 1.5, "best_model_checkpoint": "out/checkpoint-500"}
    (ck / "trainer_state.json").write_text(json.dumps(st), encoding="utf-8")
    got = adapters.load(d)
    assert len(got.rows) == 50 and got.rows[0]["epoch"] == "10" and got.rows[-1]["epoch"] == "500"
    import os
    later = time.time() + 50                             # 500 step에 50초 걸린 학습(시간 열이 없어 폴더 시각으로 잰다)
    os.utime(ck / "trainer_state.json", (later, later))
    r = read_run(d, now=later)
    assert r.x_axis == "step" and r.epoch == 500 and r.total == 750 and r.state == "running"
    assert r.metric_name == "metrics/eval_loss" and r.lower and r.best == 1.5 and r.best_epoch == 500
    assert r.eta is not None and 10 < r.eta < 60          # 남은 250 step x 칸당 약 0.1초


def test_a_logged_score_wins_over_best_metric_and_greater_is_better_sets_the_direction(tmp_path):
    """이미 점수가 기록돼 있으면 best_metric을 끼워 넣지 않는다. 방향은 사용자가 적은 greater_is_better"""
    d = _hf(tmp_path / "dist", 0.6, "distance", False, evals=("eval_loss", "eval_distance"))
    r = read_run(d)
    assert r.metric_name == "metrics/distance" and r.lower and r.best == 0.6 and r.best_epoch == 1
    d = _hf(tmp_path / "dist2", 0.8, "distance", True, evals=("eval_loss", "eval_distance"))
    r = read_run(d)
    assert not r.lower and r.best == 0.8 and r.best_epoch == 3


def test_an_eval_loss_only_run_is_explained_shown_once_and_steps_are_called_steps(tmp_path):
    """★해설이 '검증 점수가 없다'고 했고, /run에 eval_loss가 두 번(val/·metrics/), step 학습의 x 열이 epoch였다"""
    from epokio import rundetail
    d = tmp_path / "lm"
    d.mkdir()
    hist = [{"loss": 3.0 - s / 500, "epoch": s / 750, "step": s} for s in range(10, 510, 10)]
    hist += [{"eval_loss": 2.0 - s / 1000, "epoch": s / 750, "step": s} for s in (100, 200, 300, 400, 500)]
    st = {"log_history": hist, "epoch": 500 / 750, "global_step": 500, "max_steps": 750, "num_train_epochs": 1}
    (d / "trainer_state.json").write_text(json.dumps(st), encoding="utf-8")
    det = rundetail.detail(d)
    cols = det["columns"]
    assert "metrics/eval_loss" in cols and "val/eval_loss" not in cols
    assert det["x_axis"] == "step" and cols["step"][:2] == [10.0, 20.0]
    assert det["column_info"]["metrics/eval_loss"]["higher"] is False
    text = json.dumps(det["notes"], ensure_ascii=False) + json.dumps(det.get("explain", ""), ensure_ascii=False)
    assert "No validation score was logged" not in text
    from epokio import explain, i18n
    i18n.use("en")
    st.update(global_step=750, epoch=1.0)
    (d / "trainer_state.json").write_text(json.dumps(st), encoding="utf-8")
    res = explain.explain(d, "finished")
    assert "No validation score was logged" not in res["text"] and "eval_loss" in res["text"]


def test_a_multi_epoch_run_has_a_time_left_before_its_first_epoch_ends(tmp_path):
    """3에폭 LLM 미세 조정: 첫 에폭이 몇 시간이라 그동안 '0/3, – 남음'이었다. global_step/max_steps로 남은 시간"""
    import os
    import time
    d = tmp_path / "llama-ft"
    ck = d / "checkpoint-300"
    ck.mkdir(parents=True)
    logs = [{"loss": 2.0, "epoch": 0.3, "step": 100}, {"eval_loss": 1.9, "epoch": 0.3, "step": 100}]
    (ck / "trainer_state.json").write_text(json.dumps({"global_step": 300, "max_steps": 1000, "epoch": 0.9,
                                                       "num_train_epochs": 3, "log_history": logs}))
    now = time.time()
    for p in (d, d / "runs", ck):                    # 폴더가 생긴 때(윈도우는 st_birthtime)를 늦출 수 없어 기록 쪽을 5분 뒤로
        p.mkdir(exist_ok=True)
        os.utime(p, (now, now))
    os.utime(ck / "trainer_state.json", (now + 300, now + 300))
    r = read_run(d, now=now + 300)
    assert r.state == "running" and r.epoch == 0 and r.total == 3
    assert r.eta is not None and 600 < r.eta < 800   # 300초에 30% → 남은 70%는 약 700초
