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


def test_two_dimensional_keypoints_are_read_in_pairs(tmp_path):
    """★kpt_shape [N, 2](tiger-pose 등)인 라벨을 3개씩 잘라 x를 '보임'으로 읽어 검수 키포인트 점수가 엉터리였다"""
    f = tmp_path / "a.txt"
    f.write_text("0 0.5 0.5 0.2 0.2 " + " ".join(f"0.{i} 0.{i + 1}" for i in range(1, 7)) + "\n")   # 키포인트 6개 x y
    two = H["read_gt"](f, kdim=2)[0]["kpts"]
    assert len(two) == 6 and two[0] == [0.1, 0.2, 1.0] and all(len(k) == 3 for k in two)
    assert len(H["read_gt"](f)[0]["kpts"]) == 4                     # 예전 방식(3개씩)이면 4개로 잘못 읽힌다


def test_the_eval_template_knows_the_keypoint_shape():
    from epokio.templates import EVAL_TEMPLATE
    src = EVAL_TEMPLATE.format(params='{"model": "m.pt", "source": "s", "project": "p", "name": "n"}')
    compile(src, "eval", "exec")
    assert 'kpt_shape' in src and "KDIM if KDIM in (2, 3)" in src


def test_the_try_it_script_compiles_and_reads_a_fake_result(tmp_path):
    """★/predict의 스크립트가 들여쓰기가 빠져 IndentationError였다(그림 한 장 시험이 늘 500). 가짜 ultralytics로 실제로 돌린다"""
    import json
    import subprocess
    import sys
    from epokio.api import predict
    compile(predict.SCRIPT, "predict.py", "exec")
    fake = tmp_path / "ultralytics"
    fake.mkdir()
    (fake / "__init__.py").write_text('''
class _T:
    def __init__(self, v): self.v = v
    def tolist(self): return self.v
class _B:
    xywhn, cls, conf = _T([[0.5, 0.5, 0.2, 0.2]]), _T([1.0]), _T([0.87654])
    def __len__(self): return 1
class _R:
    names, orig_shape, boxes, keypoints = {1: "dog"}, (480, 640), _B(), None
class YOLO:
    def __init__(self, m): pass
    def predict(self, **k): return iter([_R()])
''')
    r = subprocess.run([sys.executable, "-c", predict.SCRIPT, json.dumps({"model": "m.pt", "image": "a.jpg", "conf": 0.25, "device": None})],
                       capture_output=True, text=True, timeout=60, env={**__import__("os").environ, "PYTHONPATH": str(tmp_path)})
    line = next(x for x in r.stdout.splitlines() if x.startswith("EPOKIO_JSON"))
    got = json.loads(line[len("EPOKIO_JSON"):])
    assert got["size"] == [640, 480] and got["boxes"] == [{"cls": 1, "box": [0.5, 0.5, 0.2, 0.2], "conf": 0.8765, "kpts": []}]
