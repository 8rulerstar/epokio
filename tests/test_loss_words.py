"""손실 낱말이 _가 아닌 구분자로 붙은 열(loss/train·loss/val·val-loss·loss_val)도 손실, 낮을수록 좋다.
★loss/train·loss/val CSV가 점수로 읽혀 가장 나쁜 에폭(1.2 @ 1)이 best, 높을수록 좋음이었다"""
from epokio import adapters, schema
from epokio.scan import read_run


def _csv(d, head, rows):
    d.mkdir(parents=True)
    (d / "log.csv").write_text(head + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return d


def test_slash_loss_columns_are_losses_not_scores(tmp_path):
    d = _csv(tmp_path / "custom" / "slashloss", "epoch,loss/train,loss/val", ["1,1.0,1.2", "2,0.5,0.7", "3,0.3,0.5"])
    cols = set(adapters.load(d).rows[-1])
    assert not any(c.startswith("metrics/") for c in cols)
    assert {"train/loss_train_loss", "val/loss_val_loss"} <= cols
    r = read_run(d)
    assert r.best is None or (r.lower and r.best == 0.5)


def test_every_direction_check_sees_a_loss_word_anywhere():
    for k in ("loss/train", "loss/val", "loss_val", "val-loss", "metrics/loss/val", "val.loss", "train loss"):
        assert schema.kind(k) == ("score" if k.startswith("metrics/") else "loss"), k
        assert not schema.higher_is_better(k), k
        assert schema.info(k)["higher"] is False, k
        assert schema.lower_for(k), k
    for k in ("metrics/glossary_acc", "metrics/lossless_acc", "metrics/accuracy"):
        assert schema.higher_is_better(k), k



def test_a_loss_named_after_its_side_reads_as_loss():
    """★HF·Keras·Lightning 곡선 범례가 "train train"·"val eval"(한국어 "학습 학습"·"검증 검증")이었다"""
    for col, side in (("train/train_loss", "train"), ("val/val_loss", "val"), ("val/eval_loss", "val"), ("train/loss", "train")):
        i = schema.info(col)
        assert (i["side"], i["name"], i["kind"]) == (side, "loss", "loss"), col
        assert schema.pretty(col) == f"{side} loss"
    assert schema.info("train/box_loss")["name"] == "box"            # 울트라리틱스 손실 이름은 그대로
    assert schema.info("val/dfl_loss")["name"] == "dfl"
