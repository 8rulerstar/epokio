"""검수를 YOLO 검출 밖으로: 분류·분할 채점, 예측 파일 가져오기(다른 프레임워크), 분류 재학습 세트."""
import json
from pathlib import Path

import pytest

from epokio import predictions, retrain, review
from epokio.agent import Agent
from epokio.jobs import Queue


def classify_data():
    return {"task": "classify", "conf_floor": 0.0, "conf": 0.0, "names": {"0": "cat", "1": "dog", "2": "fox"}, "rows": [
        {"image": "/v/cat/1.jpg", "truth": 0, "top": [[0, 0.9], [1, 0.1]]},     # 맞음
        {"image": "/v/cat/2.jpg", "truth": 0, "top": [[1, 0.6], [0, 0.3]]},     # 개로 착각
        {"image": "/v/dog/3.jpg", "truth": 1, "top": [[1, 0.4], [2, 0.35]]},    # 맞지만 자신 없음
    ]}


def test_classify_scores_confusion_and_threshold():
    r = review.rescore(classify_data(), 0.0)
    assert r["task"] == "classify" and r["overall"]["tp"] == 2
    m, cl = r["confusion"]["matrix"], r["confusion"]["classes"]
    assert m[cl.index(0)][cl.index(1)] == 1                        # 고양이 → 개
    hard = r["rows"][0]
    assert hard["image"].endswith("2.jpg") and hard["score"] == 0.3   # 정답 클래스 확률이 낮은 것부터
    hi = review.rescore(classify_data(), 0.5)                       # 문턱 0.5: 자신 없는 답은 "애매함"(놓침)
    dog = next(x for x in hi["rows"] if x["image"].endswith("3.jpg"))
    assert dog["gt_status"] == ["fn"] and dog["pred"] == []


def test_segment_uses_mask_iou_not_boxes():
    box = [0.5, 0.5, 0.4, 0.4]
    d = {"task": "segment", "conf_floor": 0.05, "rows": [{"image": "a.jpg", "gt": [{"cls": 0, "box": box, "kpts": []}],
         "pred": [{"cls": 0, "box": box, "conf": 0.9, "kpts": []}], "ious": [[0.3]]}]}   # 박스는 똑같아도 마스크는 30%
    assert review.rescore(d, 0.25)["overall"]["tp"] == 0
    d["rows"][0]["ious"] = [[0.8]]
    assert review.rescore(d, 0.25)["overall"]["tp"] == 1


def test_mask_iou_index_survives_threshold_filter():
    b = [0.5, 0.5, 0.2, 0.2]
    d = {"task": "segment", "conf_floor": 0.05, "rows": [{"image": "a.jpg", "gt": [{"cls": 0, "box": b, "kpts": []}],
         "pred": [{"cls": 0, "box": b, "conf": 0.1, "kpts": []}, {"cls": 0, "box": b, "conf": 0.9, "kpts": []}],
         "ious": [[0.9, 0.2]]}]}                                   # 낮은 신뢰도 예측이 걸러져도 두 번째 예측의 IoU(0.2)를 써야 한다
    assert review.rescore(d, 0.25)["overall"]["tp"] == 0


def test_pose_keypoint_score_is_computed_here():
    b = [0.5, 0.5, 0.4, 0.4]
    d = {"task": "pose", "conf_floor": 0.05, "rows": [{"image": "a.jpg",
         "gt": [{"cls": 0, "box": b, "kpts": [[0.5, 0.5, 2]]}], "pred": [{"cls": 0, "box": b, "conf": 0.9, "kpts": [[0.5, 0.5]]}]}]}
    assert review.rescore(d, 0.25)["rows"][0]["score"] == 1.0


def _jsonl(tmp_path, lines):
    f = tmp_path / "p.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines))
    return f


def test_import_detection_with_pixel_boxes(tmp_path):
    f = _jsonl(tmp_path, [{"names": ["car", "bus"]},
                          {"image": "/i/a.jpg", "gt": [{"cls": "car", "xyxy": [0, 0, 50, 50], "width": 100, "height": 100}],
                           "pred": [{"cls": 0, "box": [0.25, 0.25, 0.5, 0.5], "conf": 0.8}]}])
    d = predictions.load(f)
    assert d["task"] == "detect" and d["rows"][0]["gt"][0]["box"] == [0.25, 0.25, 0.5, 0.5]
    assert review.rescore(d, 0.25)["overall"]["tp"] == 1


def test_import_classification_from_probs_and_names(tmp_path):
    f = _jsonl(tmp_path, [{"image": "/i/a.jpg", "label": "cat", "probs": [0.2, 0.8]}, {"image": "/i/b.jpg", "label": "dog", "pred": "dog", "conf": 0.7}])
    d = predictions.load(f)
    assert d["task"] == "classify" and d["names"]["0"] == "cat" and d["rows"][0]["top"][0] == [1, 0.8]
    r = review.rescore(d)
    assert r["overall"]["tp"] == 1 and r["overall"]["fp"] == 1


@pytest.mark.parametrize("bad", [[{"image": "a", "gt": [{"cls": 0, "box": [0.5, 0.5, 0, 0.1]}], "pred": []}],
                                 [{"gt": []}],
                                 [{"image": "a", "label": 0, "pred": 0}, {"image": "b", "gt": [], "pred": []}]])
def test_import_rejects_bad_lines_with_line_number(tmp_path, bad):
    with pytest.raises(ValueError, match="line"):
        predictions.load(_jsonl(tmp_path, bad))


def test_import_route_records_a_finished_check(tmp_path, monkeypatch):
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    monkeypatch.setattr("epokio.jobs.HOME", tmp_path)
    a = Agent.__new__(Agent)
    a.roots, a.label, a.queue = [], "t", Queue(tmp_path / "jobs.json")
    f = _jsonl(tmp_path, [{"image": "/i/a.jpg", "label": 0, "pred": 1, "conf": 0.9}])
    code, got = a.post("/review/import", {"path": str(f)})
    assert code == 200 and got["task"] == "classify"
    assert a.get(f"/jobs/{got['id']}/eval", {})["overall"]["fp"] == 1
    assert a.post("/review/retrain", {"job": got["id"], "want": ["model_wrong"]})[0] == 400   # 가져온 예측엔 라벨 파일이 없다
    assert a.post("/review/import", {"path": str(tmp_path / "nope.jsonl")})[0] == 400


def test_classify_retrain_moves_val_images_to_train(tmp_path):
    ds = tmp_path / "ds"
    for split, cls, n in (("train", "cat", 2), ("train", "dog", 1), ("val", "cat", 2), ("val", "dog", 1)):
        (ds / split / cls).mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (ds / split / cls / f"{split}{i}.jpg").write_bytes(b"x")
    run = tmp_path / "runs/c"; (run / "weights").mkdir(parents=True)
    (run / "args.yaml").write_text(f"data: {ds}\ntask: classify\n")
    out = tmp_path / "eval"; out.mkdir()
    wrong = ds / "val/cat/val0.jpg"
    d = {"task": "classify", "names": {"0": "cat", "1": "dog"}, "rows": [{"image": str(wrong), "truth": 0, "top": [[1, 0.7]]}]}
    (out / "epokio_eval.json").write_text(json.dumps(d))
    retrain.fix_label(out, str(wrong), [{"cls": 1, "box": [0.5, 0.5, 1, 1]}])          # 사실은 개였다
    got = retrain.build_retrain(out, str(run / "weights/best.pt"), ["model_wrong"], repeat=2)
    root = Path(got["data"])
    assert got["moved_from_val"] == 1 and not (root / "val/cat/val0.jpg").exists()      # 검증에서 빠졌다
    assert len(list((root / "train/dog").glob("val0__epokio*"))) == 2                  # 고친 클래스로 학습에 두 번
    assert (root / "train/cat/train0.jpg").exists() and wrong.exists()                 # 원래 학습 데이터 + 원본 보존
