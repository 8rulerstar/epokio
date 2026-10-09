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
    y = Path(got["data"]).read_text(encoding="utf-8")        # ★인코딩을 안 적으면 윈도우(cp1252)가 한국어 주석에서 터졌다
    # 경로는 JSON 문자열로 적힌다. 윈도우에선 역슬래시가 두 겹이라 적힌 모양 그대로 찾는다
    assert json.dumps(str(ds / "images/train")) in y and json.dumps(str(out / "retrain/images")) in y and "0: cat" in y
    assert got["files"] == 2 and (ds / "labels/val/a.txt").read_text() == "0 0.5 0.5 0.2 0.2\n"
    # ★검증 이미지를 학습에 넣었으면 새 검증 목록에서 빠져야 한다(누수 방지)
    assert got["moved_from_val"] == 1 and "val.txt" in y
    assert str(img) not in (out / "retrain/val.txt").read_text(encoding="utf-8")


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


def test_pose_and_mask_labels_are_not_replaced_by_a_box(tmp_path, monkeypatch):
    """★고친 라벨은 'cls x y w h' 한 줄이라 포즈의 키포인트(분할의 다각형)를 잃었고, Ultralytics가 그 이미지를 깨진 라벨로
    빼서 고친 것이 조용히 사라졌다(맥 앱이 포즈 고치기를 열어 두었다). 400으로 이유를 알린다"""
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label = [], "t"

    class J:
        kind, output, params = "evaluate", str(tmp_path), {"model": "m"}

    class Q:
        def get(self, i):
            return J if i == "j1" else None
    a.queue = Q()
    for task in ("pose", "segment"):
        (tmp_path / "epokio_eval.json").write_text(json.dumps({**data(), "task": task}))
        code, body = a.post("/review/fix", {"job": "j1", "image": "/d/images/a.jpg", "boxes": [{"cls": 0, "box": B}]})
        assert code == 400 and "labelling tool" in body["error"]
        assert not (tmp_path / "labels_fixed").exists()


def test_pose_review_compares_box_with_box(tmp_path):
    """★포즈 검수의 '학습 때 점수'는 키포인트(OKS) 머리, 다시 채점한 값은 박스 IoU라 같은 'mAP50'에 다른 것을 나란히 보였다"""
    from epokio.api import review as review_api
    run = tmp_path / "pose" / "train"
    (run / "weights").mkdir(parents=True)
    (run / "weights" / "best.pt").write_bytes(b"x")
    (run / "results.csv").write_text("epoch,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B),"
                                     "metrics/precision(P),metrics/recall(P),metrics/mAP50(P),metrics/mAP50-95(P)\n"
                                     "1,0.6,0.6,0.665,0.4,0.7,0.7,0.67,0.5\n")
    got = review_api.trained(str(run / "weights" / "best.pt"), "pose")
    assert got and got["map50"] == 0.665


def test_same_named_images_keep_their_own_fix_and_the_originals_stay_untouched(tmp_path):
    """★val/cam1/0001.jpg와 val/cam2/0001.jpg를 둘 다 고르면 재학습 세트에서 두 번째 이미지가 첫 번째의 하드링크 위에
    쓰여 원본 cam1 이미지가 cam2 내용으로 바뀌었다. 고친 라벨도 이름(0001)으로만 저장돼 서로 덮고 둘 다에 들어갔다"""
    ds = tmp_path / "ds"
    imgs = []
    for cam, byte in (("cam1", b"one"), ("cam2", b"two")):
        (ds / "images/val" / cam).mkdir(parents=True)
        (ds / "labels/val" / cam).mkdir(parents=True)
        img = ds / "images/val" / cam / "0001.jpg"; img.write_bytes(byte)
        (ds / "labels/val" / cam / "0001.txt").write_text("0 0.5 0.5 0.2 0.2\n")
        imgs.append(img)
    (ds / "images/train").mkdir(parents=True)
    (ds / "data.yaml").write_text(f"path: {ds}\ntrain: images/train\nval: images/val\nnames:\n  0: cat\n  1: dog\n")
    run = tmp_path / "runs/t"; (run / "weights").mkdir(parents=True)
    (run / "args.yaml").write_text(f"data: {ds / 'data.yaml'}\n")
    out = tmp_path / "eval"; out.mkdir()
    d = data(); d["rows"] = [{**d["rows"][0], "image": str(i), "label": str(i).replace("images", "labels")[:-4] + ".txt"} for i in imgs]
    (out / "epokio_eval.json").write_text(json.dumps(d))
    (out / "review.csv").write_text(f"image,verdict\n{imgs[0]},model_wrong\n{imgs[1]},model_wrong\n")
    a = retrain.fix_label(out, str(imgs[0]), [{"cls": 0, "box": [0.1, 0.1, 0.1, 0.1]}])
    b = retrain.fix_label(out, str(imgs[1]), [{"cls": 1, "box": [0.9, 0.9, 0.1, 0.1]}])
    assert a != b and len(retrain.fixed_labels(out)) == 2
    got = retrain.build_retrain(out, str(run / "weights/best.pt"), ["model_wrong"], repeat=2)
    assert imgs[0].read_bytes() == b"one" and imgs[1].read_bytes() == b"two"          # 원본 그대로
    labels = sorted(p.read_text(encoding="utf-8") for p in (out / "retrain/labels").glob("*.txt"))
    assert got["files"] == 4 and len(list((out / "retrain/images").iterdir())) == 4
    assert labels.count("0 0.100000 0.100000 0.100000 0.100000\n") == 2 and labels.count("1 0.900000 0.900000 0.100000 0.100000\n") == 2
    import pytest
    with pytest.raises(FileExistsError):                                               # 있는 이름에는 절대 쓰지 않는다
        retrain._link(imgs[1], next((out / "retrain/images").iterdir()))
    assert imgs[0].read_bytes() == b"one"


def test_two_tabs_marking_do_not_erase_each_other(tmp_path, monkeypatch):
    """★웹이 화면의 판정 전체를 보내 review.csv를 통째로 바꿔, 열어 둔 다른 탭이 그사이 매긴 판정을 말없이 지웠다.
    patch(바뀐 것만, null = 지우기)는 저장된 판정에 섞는다. 맥 앱의 전체 보내기(verdicts)는 그대로 된다"""
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label = [], "t"

    class J:
        kind, output, params = "evaluate", str(tmp_path), {"model": "m"}

    class Q:
        def get(self, i):
            return J if i == "j1" else None
    a.queue = Q()
    (tmp_path / "epokio_eval.json").write_text(json.dumps(data()))
    A, Bimg = "/d/images/a.jpg", "/d/images/b.jpg"
    assert a.post("/review/verdicts", {"job": "j1", "patch": {A: "model_wrong"}})[0] == 200        # 탭 1
    code, got = a.post("/review/verdicts", {"job": "j1", "patch": {Bimg: "unsure"}})                 # 탭 2(탭 1의 것을 모른다)
    assert code == 200 and got["verdicts"] == {A: "model_wrong", Bimg: "unsure"} == retrain.verdicts(tmp_path)
    assert a.post("/review/verdicts", {"job": "j1", "patch": {A: None}})[1]["verdicts"] == {Bimg: "unsure"}   # 되돌리기
    assert a.post("/review/verdicts", {"job": "j1", "patch": {"/elsewhere.jpg": "ok"}})[0] == 400
    assert a.post("/review/verdicts", {"job": "j1", "verdicts": {A: None}})[0] == 400                   # 전체 보내기에는 null이 없다
    assert a.post("/review/verdicts", {"job": "j1", "verdicts": {A: "ok"}})[1]["verdicts"] == {A: "ok"}
    assert not list(tmp_path.glob("*.tmp"))


def test_two_reports_in_the_same_minute_do_not_overwrite(tmp_path):
    """★보고서 이름이 분 단위라 같은 분에 두 번 만들면 앞 보고서와 그림 폴더를 덮어썼다"""
    from epokio import report
    a = report.save([], tmp_path)
    b = report.save([], tmp_path)
    assert a != b and a.exists() and b.exists() and b.with_name(b.stem + "_files").is_dir()
