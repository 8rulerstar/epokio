"""평가 작업의 계산 부분(라벨 읽기·짝짓기). 사용자 파이썬에서 도는 글자라 여기서 그대로 exec해 본다."""
import pytest

from epokio import jobs

H: dict = {}
exec(jobs.EVAL_HELPERS, H)


def test_segmentation_polygons_become_their_bounding_box(tmp_path):
    """★폴리곤의 앞 숫자 4개(x1 y1 x2 y2)를 cx cy w h로 읽어 분할 모델 점수가 의미 없었다."""
    f = tmp_path / "a.txt"
    f.write_text("0 0.2 0.2 0.6 0.2 0.6 0.8 0.2 0.8\n")
    [g] = H["read_gt"](f, seg=True)
    assert g["box"] == pytest.approx([0.4, 0.5, 0.4, 0.6])


def test_detection_and_pose_rows_are_unchanged(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("1 0.5 0.5 0.2 0.2\n0 0.5 0.5 0.2 0.2 0.4 0.4 2 0.6 0.6 1\n")
    a, b = H["read_gt"](f)
    assert a["box"] == [0.5, 0.5, 0.2, 0.2] and a["kpts"] == []
    assert b["kpts"] == [[0.4, 0.4, 2], [0.6, 0.6, 1]]


def test_matching_follows_confidence_not_label_order():
    """정답 순서로 고르면 첫 정답 A(0.52)가 자기와 가장 많이 겹치는 p(0.54)를 가져가고,
    정답 B(0.55)는 남은 p(0.48)와 IoU가 0.5에 못 미쳐 놓쳤다(맞춤 1).
    COCO·ultralytics처럼 신뢰도 높은 예측부터 짝지으면 p(0.48, 0.9)가 A를, p(0.54)가 B를 찾아 둘 다 맞춘다."""
    box = lambda x: [x, 0.5, 0.2, 0.2]
    gt = [{"cls": 0, "box": box(0.52), "kpts": []}, {"cls": 0, "box": box(0.55), "kpts": []}]
    pred = [{"cls": 0, "box": box(0.54), "conf": 0.4, "kpts": []}, {"cls": 0, "box": box(0.48), "conf": 0.9, "kpts": []}]
    tp, _ = H["match"](gt, pred, 0.5)
    assert tp == 2


def test_other_classes_never_match():
    b = [0.5, 0.5, 0.2, 0.2]
    tp, _ = H["match"]([{"cls": 0, "box": b, "kpts": []}], [{"cls": 1, "box": b, "conf": 1.0, "kpts": []}], 0.5)
    assert tp == 0


def test_the_generated_script_still_compiles(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "SCRIPTS", tmp_path)
    cmd = jobs.build_command(jobs.Job(id="v1", kind="evaluate", name="e", python="py",
                                      params={"model": "m.pt", "source": str(tmp_path)}))
    src = (tmp_path / "v1.py").read_text(encoding="utf-8")
    compile(src, "eval.py", "exec")
    # 채점(짝짓기)은 agent의 review.py가 한다(맥 설계). 스크립트는 원자료만 모은다
    assert "EPOKIO_DONE" in src and cmd[-1].endswith("v1.py")


def test_each_training_records_its_environment(tmp_path, monkeypatch):
    """학습 스크립트가 결과 폴더가 생긴 직후(콜백) epokio_env.json을 쓴다. 미리 폴더를 만들면 ultralytics가 이름에 2를 붙인다."""
    import json
    from epokio import rundetail
    monkeypatch.setattr(jobs, "SCRIPTS", tmp_path / "s")
    jobs.build_command(jobs.Job(id="t1", kind="train", name="exp", python="py",
                                params={"data": "d.yaml", "model": "m.pt", "project": str(tmp_path / "runs")}))
    src = (tmp_path / "s" / "t1.py").read_text(encoding="utf-8")
    compile(src, "train.py", "exec")
    assert 'add_callback("on_pretrain_routine_start"' in src
    env: dict = {}
    exec(jobs.ENV_HELPERS, env)                          # 사용자 파이썬에서 도는 그 함수를 여기서 그대로
    out = tmp_path / "runs" / "exp"
    out.mkdir(parents=True)
    env["write_env"](out)
    got = json.loads((out / "epokio_env.json").read_text(encoding="utf-8"))
    assert got["python"] and len(got["packages_hash"]) == 12
    assert rundetail._env(out)["python"] == got["python"]
