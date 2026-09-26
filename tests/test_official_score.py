"""검수 화면의 공식 규칙 값(review.official)이 Ultralytics 8.4.150 검증과 같은 수치를 내는지(독자 구현, 기대값은 그 라이브러리를 블랙박스로 호출해 관찰한 출력). 학습·모델 없이 고정 자료로만."""
from epokio import review
from epokio.api import review as api_review

B = [0.5, 0.5, 0.2, 0.2]
FAR = [0.1, 0.1, 0.05, 0.05]


def _det(rows, names=None):
    return {"task": "detect", "conf": 0.25, "conf_floor": 0.05, "names": names or {"0": "a", "1": "b"}, "rows": rows}


def test_perfect_boxes_give_0995_map():
    # 관찰: 완벽한 예측에도 0.995(마지막 재현율에서 정밀도 0으로 닫고 101칸 사다리꼴로 적분)
    data = _det([{"image": "x", "label": "", "gt": [{"cls": 0, "box": B, "kpts": []}],
                  "pred": [{"cls": 0, "box": B, "conf": 0.9, "kpts": []}]}])
    o = review.rescore(data)["official"]
    assert o["precision"] == 1.0 and o["recall"] == 1.0
    assert abs(o["map50"] - 0.995) < 1e-9


def test_single_class_precision_recall_match_epokio_counts():
    # 한 클래스, 맞춘 2개는 높은 신뢰도, 헛검출 1개는 바닥 신뢰도, 놓침 1개: 두 규칙이 같은 P·R을 내야 한다
    gt = [{"cls": 0, "box": B, "kpts": []}, {"cls": 0, "box": [0.8, 0.8, 0.1, 0.1], "kpts": []},
          {"cls": 0, "box": [0.2, 0.8, 0.1, 0.1], "kpts": []}]
    pred = [{"cls": 0, "box": B, "conf": 0.95, "kpts": []}, {"cls": 0, "box": [0.8, 0.8, 0.1, 0.1], "conf": 0.9, "kpts": []},
            {"cls": 0, "box": FAR, "conf": 0.06, "kpts": []}]
    r = review.rescore(_det([{"image": "x", "label": "", "gt": gt, "pred": pred}]), conf=0.5)
    ours, o = r["overall"], r["official"]
    assert (ours["precision"], round(ours["recall"], 3)) == (1.0, 0.667)
    assert abs(o["precision"] - ours["precision"]) < 0.03
    assert abs(o["recall"] - ours["recall"]) < 0.03


def test_official_is_class_mean_not_pooled():
    # a: 3개 전부 맞춤, b: 1개 중 0개. 합치면 재현율 0.75, 클래스 평균이면 0.5
    rows = [{"image": "x", "label": "",
             "gt": [{"cls": 0, "box": [0.2 * i + 0.1, 0.5, 0.1, 0.1], "kpts": []} for i in range(3)] + [{"cls": 1, "box": FAR, "kpts": []}],
             "pred": [{"cls": 0, "box": [0.2 * i + 0.1, 0.5, 0.1, 0.1], "conf": 0.9, "kpts": []} for i in range(3)]}]
    r = review.rescore(_det(rows), conf=0.5)
    assert r["overall"]["recall"] == 0.75
    assert r["official"]["recall"] == 0.5
    assert abs(r["official"]["map50"] - 0.995 / 2) < 1e-9


def test_matching_prefers_earlier_prediction_on_shared_truth():
    # 관찰: 한 정답을 두 예측이 가리키면 IoU가 아니라 앞선 예측(보통 신뢰도 높은 쪽)이 갖는다
    g = [0.5, 0.5, 0.2, 0.2]
    p_hi, p_lo = [0.54, 0.5, 0.2, 0.2], [0.505, 0.5, 0.2, 0.2]
    assert 0.5 <= review.iou(p_hi, g) < review.iou(p_lo, g)
    gt = [{"cls": 0, "box": g, "kpts": []}]
    pred = [{"cls": 0, "box": p_hi, "conf": 0.9, "kpts": []}, {"cls": 0, "box": p_lo, "conf": 0.8, "kpts": []}]
    assert review.overlap_tp(gt, pred, 0.5, None) == [True, False]


def test_matching_does_not_fall_back_to_second_truth():
    # 관찰: 정답×예측 IoU [[0.9, 0.8], [0.7, 0.6]] -> 예측 0만 맞춤. 예측 1은 정답 1로 넘어가지 않는다
    gt = [{"cls": 0, "box": B, "kpts": []}] * 2
    pred = [{"cls": 0, "box": B, "conf": 0.9, "kpts": []}] * 2
    assert review.overlap_tp(gt, pred, 0.5, [[0.9, 0.8], [0.7, 0.6]]) == [True, False]


def test_classify_top1_ignores_confidence():
    rows = [{"image": "a", "label": "a", "truth": 0, "top": [[0, 0.1], [1, 0.05]]},
            {"image": "b", "label": "b", "truth": 1, "top": [[1, 0.9]]}]
    r = review.rescore({"task": "classify", "conf": 0.25, "conf_floor": 0.05, "names": {"0": "a", "1": "b"}, "rows": rows})
    assert r["official"]["top1"] == 1.0
    assert r["overall"]["recall"] == 0.5              # Epokio: 문턱 밑 1위는 '애매함'


def test_old_keys_kept():
    data = _det([{"image": "x", "label": "", "gt": [{"cls": 0, "box": B, "kpts": []}], "pred": []}])
    r = review.rescore(data)
    for k in ("overall", "per_class", "confusion", "curve", "best_conf", "rows", "conf", "iou"):
        assert k in r


def test_trained_reads_results_csv(tmp_path):
    run = tmp_path / "run"
    (run / "weights").mkdir(parents=True)
    (run / "results.csv").write_text(
        "epoch,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B)\n"
        "1,0.5,0.4,0.45,0.30\n2,0.7,0.6,0.65,0.50\n3,0.6,0.5,0.55,0.40\n")
    best = api_review.trained(str(run / "weights" / "best.pt"), "detect")
    assert (best["epoch"], best["map50"], best["precision"]) == (2, 0.65, 0.7)
    last = api_review.trained(str(run / "weights" / "last.pt"), "detect")
    assert last["map50"] == 0.55
    assert api_review.trained(str(tmp_path / "x.pt"), "detect") is None


def test_ap101_partial_curve():
    # 관찰값: 정답 2개, 맞춤·헛검출·맞춤 -> 0.828333..., 정답 2개에 맞춤 1개 -> 0.495
    from epokio.apmetric import ap101, pr_curve
    _, rec, prec = pr_curve([0.9, 0.8, 0.7], [True, False, True], 2)
    assert abs(ap101(rec, prec) - 0.8283333333333333) < 1e-9
    _, rec, prec = pr_curve([0.9], [True], 2)
    assert abs(ap101(rec, prec) - 0.495) < 1e-9
