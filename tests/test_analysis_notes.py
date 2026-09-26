"""자동 해설이 서로 모순되거나 틀린 조언을 하지 않는지."""
from epokio.analysis import _notes, head_stats


def rows(val_loss, maps):
    return [{"epoch": str(i + 1), "val/box_loss": str(v), "val/cls_loss": "0.5",
             "metrics/precision(B)": "0.6", "metrics/recall(B)": "0.6",
             "metrics/mAP50(B)": str(m + 0.2), "metrics/mAP50-95(B)": str(m)}
            for i, (v, m) in enumerate(zip(val_loss, maps))]


def notes_of(rs):
    heads = [h for h in [head_stats(rs, "B")] if h]
    return " ".join(o for o, *_ in _notes(rs, heads))


def test_loss_rising_while_the_score_still_climbs_is_not_called_overfitting():
    """YOLO는 cls 손실이 과신으로 오르는 동안에도 mAP가 끝까지 오른다.
    예전엔 '과적합 같다'와 '아직 오르는 중'이 한 학습에 같이 나왔다."""
    rs = rows([1.0, 0.8, 0.6, 0.5, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0], [0.1 + 0.03 * i for i in range(10)])
    t = notes_of(rs)
    assert "overfitting." not in t.replace("not overfitting.", "") and "still improving" in t   # "이것만으로는 과적합이 아니다"는 괜찮다


def test_loss_rising_and_the_score_falling_is_overfitting():
    rs = rows([1.0, 0.8, 0.6, 0.5, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
              [0.1, 0.2, 0.3, 0.4, 0.45, 0.44, 0.40, 0.38, 0.36, 0.35])
    assert "overfitting" in notes_of(rs)
