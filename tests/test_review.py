"""검수 깊이: 다시 채점(문턱·IoU), 클래스별 성적, 혼동 행렬, 라벨 고치기, 재학습 세트."""
import json
from pathlib import Path

from epokio import retrain, review
from epokio.agent import Agent

B = [0.5, 0.5, 0.2, 0.2]
FAR = [0.1, 0.1, 0.05, 0.05]


def data():
    return {"metric": "per-image F1", "conf": 0.25, "conf_floor": 0.05, "names": {"0": "cat", "1": "dog"}, "rows": [
        {"image": "/d/images/a.jpg", "label": "/d/labels/a.txt", "kpt": None,
         "gt": [{"cls": 0, "box": B, "kpts": []}],
         "pred": [{"cls": 0, "box": B, "conf": 0.9, "kpts": []}, {"cls": 1, "box": FAR, "conf": 0.1, "kpts": []}]},
        {"image": "/d/images/b.jpg", "label": "/d/labels/b.txt", "kpt": None,
         "gt": [{"cls": 0, "box": B, "kpts": []}],
         "pred": [{"cls": 1, "box": B, "conf": 0.8, "kpts": []}]},                    # 자리는 맞고 클래스가 틀림
        {"image": "/d/images/c.jpg", "label": "/d/labels/c.txt", "kpt": None,
         "gt": [{"cls": 1, "box": B, "kpts": []}], "pred": []},                       # 놓침
    ]}


def test_threshold_changes_counts_without_rerunning():
    hi = review.rescore(data(), 0.25)
    lo = review.rescore(data(), 0.05)
    assert hi["overall"]["fp"] == 1 and lo["overall"]["fp"] == 2     # 0.1짜리 헛검출은 낮은 문턱에서만
    assert review.rescore(data(), 0.01)["conf"] == 0.05                # 저장한 것보다 낮게는 못 내려간다


def test_wrong_class_is_its_own_status_and_in_confusion():
    r = review.rescore(data(), 0.25)
    b = next(x for x in r["rows"] if x["image"].endswith("b.jpg"))
    assert b["gt_status"] == ["cls"] and b["pred_status"] == ["cls"] and b["fp"] == 1 and b["fn"] == 1
    m, labels = r["confusion"]["matrix"], r["confusion"]["classes"]
    assert m[labels.index(0)][labels.index(1)] == 1                    # 정답 cat → 예측 dog
    assert m[labels.index(1)][labels.index(-1)] == 1                   # dog 놓침
    assert r["confusion"]["labels"][-1] == "background"


def test_per_class_and_curve():
    r = review.rescore(data(), 0.25)
    cat = next(c for c in r["per_class"] if c["name"] == "cat")
    assert (cat["tp"], cat["fn"], cat["support"]) == (1, 1, 2)
    assert r["curve"][0]["conf"] == 0.05 and r["best_conf"] is not None


def test_old_results_pass_through():
    old = {"metric": "per-image F1", "rows": [{"image": "x", "score": 1}]}
    assert review.rescore(old) == old


def test_fix_label_never_touches_original(tmp_path):
    f = retrain.fix_label(tmp_path, "/d/images/155010.457_a.jpg", [{"cls": 1, "box": [0.5, 0.5, 0.2, 0.3]}])
    assert f == tmp_path / "labels_fixed" / "155010.457_a.txt"          # ★마침표가 든 이름이 잘리지 않는다
    assert retrain.fixed_labels(tmp_path)["155010.457_a"][0]["cls"] == 1


def test_build_retrain_merges_with_original_yaml_and_keeps_val(tmp_path):
    ds = tmp_path / "ds"
    for sub in ("images/train", "images/val", "labels/val"):
        (ds / sub).mkdir(parents=True)
    img = ds / "images/val/a.jpg"; img.write_bytes(b"x")
    (ds / "labels/val/a.txt").write_text("0 0.5 0.5 0.2 0.2\n")
    (ds / "data.yaml").write_text(f"path: {ds}\ntrain: images/train\nval: images/val\nnames:\n  0: cat\n")
    run = tmp_path / "runs/t"; (run / "weights").mkdir(parents=True)
    (run / "args.yaml").write_text(f"data: {ds / 'data.yaml'}\n")
    out = tmp_path / "eval"; out.mkdir()
    d = data(); d["rows"][0]["image"], d["rows"][0]["label"] = str(img), str(ds / "labels/val/a.txt")
    (out / "epokio_eval.json").write_text(json.dumps(d))
    (out / "review.csv").write_text(f"image,verdict\n{img},model_wrong\n")
    got = retrain.build_retrain(out, str(run / "weights/best.pt"), ["model_wrong"], repeat=2)
    y = Path(got["data"]).read_text()
    assert str(ds / "images/train") in y and str(out / "retrain/images") in y and "0: cat" in y
    assert got["files"] == 2 and (ds / "labels/val/a.txt").read_text() == "0 0.5 0.5 0.2 0.2\n"
    # ★검증 이미지를 학습에 넣었으면 새 검증 목록에서 빠져야 한다(누수 방지)
    assert got["moved_from_val"] == 1 and "val.txt" in y
    assert str(img) not in (out / "retrain/val.txt").read_text()


def test_review_routes_validate(tmp_path, monkeypatch):
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label = [], "t"

    class J:  # 끝난 평가 작업 흉내
        kind, output, params = "evaluate", str(tmp_path), {"model": "m"}

    class Q:
        def get(self, i):
            return J if i == "j1" else None
    a.queue = Q()
    (tmp_path / "epokio_eval.json").write_text(json.dumps(data()))
    assert a.post("/review/fix", {"job": "nope"})[0] == 400
    assert a.post("/review/fix", {"job": "j1", "image": "/elsewhere.jpg", "boxes": []})[0] == 400
    assert a.post("/review/fix", {"job": "j1", "image": "/d/images/a.jpg", "boxes": [{"cls": 0, "box": [0.5, 0.5, 0, 0]}]})[0] == 400
    assert a.post("/review/fix", {"job": "j1", "image": "/d/images/a.jpg", "boxes": [{"cls": 0, "box": B}]})[0] == 200
    assert a.post("/review/verdicts", {"job": "j1", "verdicts": {"/d/images/a.jpg": "hmm"}})[0] == 400
    assert a.post("/review/verdicts", {"job": "j1", "verdicts": {"/d/images/a.jpg": "label_wrong"}})[0] == 200
    assert a.post("/review/retrain", {"job": "j1", "want": "all"})[0] == 400
