"""YOLO 밖 학습(Keras·Lightning·HF)의 해설: 그 프레임워크의 말로 조언하고, 공통 판정(정체·폭주)이 돈다."""
import math

from epokio import analysis


def keras(tmp_path, vals):
    d = tmp_path / "keras_run"
    d.mkdir()
    lines = ["epoch,accuracy,loss,val_accuracy,val_loss"] + [f"{e},{a},{l},{va},{vl}" for e, (a, l, va, vl) in enumerate(vals)]
    (d / "training.log").write_text("\n".join(lines) + "\n")
    return d


def lightning(tmp_path, train_loss, val_acc):
    d = tmp_path / "lightning_logs" / "version_0"
    d.mkdir(parents=True)
    (d / "hparams.yaml").write_text(f"max_epochs: {len(train_loss)}\n")
    m = ["epoch,step,train_loss,val_loss,val_acc"]
    for e, (tl, va) in enumerate(zip(train_loss, val_acc)):
        m += [f"{e},{e},{tl},,", f"{e},{e},,{tl + 0.1},{va}"]
    (d / "metrics.csv").write_text("\n".join(m) + "\n")
    return d


def _kinds(d):
    a = analysis.analyze(d)
    return {k["kind"]: (o, t) for (o, t), k in zip(a.notes, a.kinds)}


def test_keras_gets_keras_advice_not_best_pt(tmp_path):
    rows = [(0.6 + 0.02 * e, round(math.exp(-e / 4), 3), 0.6 + 0.03 * min(e, 9),
             round(0.6 * math.exp(-e / 4) + 0.02 * max(0, e - 8) ** 1.3 + 0.15, 3)) for e in range(20)]
    obs, tip = _kinds(keras(tmp_path, rows))["loss_rise"]
    assert "ModelCheckpoint(save_best_only=True)" in tip and "best.pt" not in tip


def test_an_early_peak_that_fell_is_not_called_steady(tmp_path):
    """★최고점이 1에폭이라 과적합 판정을 건너뛰었는데, 다음 문장이 '점수는 떨어지지 않았다'고 했다(0.6 → 0.3이었다)"""
    tl = [0.8 - 0.05 * e if e < 5 else 0.6 + 0.4 * (e - 5) ** 1.5 for e in range(10)]
    k = _kinds(lightning(tmp_path, tl, [0.6] * 5 + [0.3] * 5))
    assert "loss_rise" not in k and "early_best" in k
    obs, tip = k["diverged"]                                   # NaN 없이 불어난 손실도 발산으로 본다
    assert "grew to" in obs and "learning rate" in tip


def test_a_plateau_suggests_that_frameworks_early_stopping(tmp_path):
    acc = [0.5 + 0.05 * min(e, 6) for e in range(20)]          # 7에폭부터 그대로
    k = _kinds(lightning(tmp_path, [0.8 - 0.01 * e for e in range(20)], acc))
    obs, tip = k["plateau"]
    assert "epoch 7 of 20" in obs and "The last 13 epochs" in obs and "EarlyStopping" in tip
    assert analysis.next_run({"kind": "plateau", "best_epoch": 7}, {}, None) == {"epochs": 10, "patience": 10}


def test_a_steady_climb_has_no_plateau_or_blowup(tmp_path):
    k = _kinds(lightning(tmp_path, [0.8 - 0.03 * e for e in range(20)], [0.5 + 0.02 * e for e in range(20)]))
    assert "plateau" not in k and "diverged" not in k
