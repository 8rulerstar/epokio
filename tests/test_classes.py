"""클래스별 성능: 학습 끝에 쓰는 도우미(jobs_templates.write_classes), 읽기(classes.py), 계산 요청(POST /classes)."""
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

from epokio import classes
from epokio.agent import Agent
from epokio.jobs_templates import CLASSES_TEMPLATE, ENV_HELPERS, TRAIN_TEMPLATE

KEYS = ["metrics/precision(B)", "metrics/recall(B)", "metrics/mAP50(B)", "metrics/mAP50-95(B)"]


class FakeMetrics:
    """ultralytics DetMetrics 에서 write_classes 가 쓰는 것만(8.4.150에서 실제 값과 대조한 모양)"""
    keys = KEYS
    names = {0: "person", 1: "dog", 2: "elephant"}
    ap_class_index = [0, 1, 2]
    nt_per_class = [10, 1, 2]
    nt_per_image = [3, 1, 1]
    _vals = [[0.557, 0.6, 0.581, 0.268], [0.548, 1.0, 0.995, 0.697], [0.371, 0.5, 0.516, 0.256]]

    def class_result(self, i):
        return self._vals[i]


def _write(tmp_path, m, source="val"):
    g = {}
    exec(ENV_HELPERS, g)
    g["write_classes"](tmp_path, m, source)
    return tmp_path / classes.FILE


def test_the_helper_writes_every_class_under_results_csv_names(tmp_path):
    f = _write(tmp_path, FakeMetrics())
    d = json.loads(f.read_text())
    assert d["source"] == "val" and d["keys"] == KEYS
    assert d["rows"][2] == {"name": "elephant", "instances": 2, "images": 1, **dict(zip(KEYS, [0.371, 0.5, 0.516, 0.256]))}


def test_the_helper_never_breaks_the_training(tmp_path, capsys):
    """학습이 끝난 뒤에 도는 코드다. 모양이 다른 판·분류(클래스별 없음)·None 이면 조용히 넘어간다"""
    assert not _write(tmp_path, None).exists()
    assert not _write(tmp_path, SimpleNamespace(keys=["metrics/accuracy_top1"], ap_class_index=[])).exists()
    bad = FakeMetrics()
    bad.class_result = lambda i: 1 / 0
    assert not _write(tmp_path, bad).exists()
    assert "could not save per-class scores" in capsys.readouterr().out


def test_weakest_first_and_the_note_names_them(tmp_path):
    _write(tmp_path, FakeMetrics(), "train")
    c = classes.read(tmp_path)
    h = c["heads"][0]
    assert c["source"] == "train" and h["head"] == "box" and h["main"] == "mAP50-95"
    assert [r["name"] for r in h["rows"]] == ["elephant", "person", "dog"]
    assert [r["weak"] for r in h["rows"]] == [True, True, False]
    assert h["rows"][0]["few"] and not h["rows"][1]["few"]
    obs, tip = classes.note(c)
    assert "elephant, person" in obs and "elephant" in tip


def test_pose_runs_get_both_heads():
    c = classes.read(Path(__file__).parent / "fixtures" / "formats" / "ultralytics84_pose")
    assert [h["head"] for h in c["heads"]] == ["box", "pose"]
    assert c["heads"][1]["rows"][0]["name"] == "rider"


def test_nothing_to_say_when_no_class_stands_out(tmp_path):
    m = FakeMetrics()
    m._vals = [[0.5, 0.5, 0.6, 0.40], [0.5, 0.5, 0.6, 0.42], [0.5, 0.5, 0.6, 0.41]]
    _write(tmp_path, m)
    assert classes.note(classes.read(tmp_path)) is None
    assert classes.read(tmp_path / "missing") is None


def test_the_train_template_saves_classes_after_training(tmp_path, monkeypatch):
    """학습 대기열로 돌린 학습은 마지막 검증 값을 그대로 적는다(검증을 다시 돌리지 않는다)"""
    fake = types.ModuleType("ultralytics")

    class YOLO:
        def __init__(self, model):
            self.trainer = None

        def add_callback(self, *a):
            pass

        def train(self, **p):
            self.trainer = SimpleNamespace(save_dir=str(tmp_path), validator=SimpleNamespace(metrics=FakeMetrics()))
    fake.YOLO = YOLO
    monkeypatch.setitem(sys.modules, "ultralytics", fake)
    src = ENV_HELPERS + TRAIN_TEMPLATE.format(params=json.dumps({"model": "m.pt", "data": "d.yaml"}), git=False)
    exec(compile(src, "train", "exec"), {"__name__": "__main__"})
    assert json.loads((tmp_path / classes.FILE).read_text())["source"] == "train"


def test_the_classes_template_writes_into_the_run(tmp_path, monkeypatch):
    fake = types.ModuleType("ultralytics")
    seen = {}

    class YOLO:
        def __init__(self, model):
            seen["model"] = model

        def val(self, **kw):
            seen.update(kw)
            return FakeMetrics()
    fake.YOLO = YOLO
    monkeypatch.setitem(sys.modules, "ultralytics", fake)
    run = tmp_path / "run"
    run.mkdir()
    p = {"model": str(run / "weights" / "best.pt"), "data": "coco8.yaml", "run": str(run), "tmp": str(tmp_path / "t")}
    exec(compile(ENV_HELPERS + CLASSES_TEMPLATE.format(params=json.dumps(p)), "classes", "exec"), {"__name__": "__main__"})
    assert seen["data"] == "coco8.yaml" and seen["plots"] is False and seen["project"] == str(tmp_path / "t")
    assert json.loads((run / classes.FILE).read_text())["source"] == "val"


def test_the_request_needs_a_watched_run_with_weights_and_data(tmp_path, monkeypatch):
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    run = tmp_path / "runs" / "train"
    (run / "weights").mkdir(parents=True)
    a.roots, a.label = [tmp_path / "runs"], "t"
    added = []
    a.queue = SimpleNamespace(jobs=[], add=lambda *x, **k: added.append(x) or SimpleNamespace(id="j1"))
    assert a.post("/classes", {"path": str(tmp_path / "elsewhere")})[0] == 400
    assert a.post("/classes", {"path": str(run)})[0] == 400                  # best.pt 없음
    (run / "weights" / "best.pt").write_bytes(b"x")
    assert a.post("/classes", {"path": str(run)})[0] == 400                  # args.yaml 의 data 없음
    (run / "args.yaml").write_text("data: coco8.yaml\n")
    monkeypatch.setattr("epokio.envs.list_envs", lambda: [{"path": "/py", "ready": True}])
    assert a.post("/classes", {"path": str(run)}) == (200, {"id": "j1"})
    kind, _, py, params = added[0]
    assert kind == "classes" and py == "/py" and params["run"] == str(run) and params["data"] == "coco8.yaml"


def test_pose_runs_talk_about_the_pose_head_and_absent_classes_stay_out(tmp_path):
    """★pose 학습인데 box 평균으로 말했고, 검증셋에 없는 클래스(instances 0)가 평균에 섞였다"""
    k = KEYS + ["metrics/precision(P)", "metrics/recall(P)", "metrics/mAP50(P)", "metrics/mAP50-95(P)"]
    rows = [{"name": "insulator", "instances": 40, **dict(zip(k, [.8, .8, .8, .60, .8, .8, .8, .50]))},
            {"name": "clamp", "instances": 30, **dict(zip(k, [.8, .8, .8, .58, .5, .5, .5, .20]))},
            {"name": "crossarm", "instances": 0, **dict(zip(k, [0, 0, 0, .52, 0, 0, 0, .52]))}]
    (tmp_path / classes.FILE).write_text(json.dumps({"source": "train", "keys": k, "rows": rows}))
    c = classes.read(tmp_path)
    pose = next(h for h in c["heads"] if h["head"] == "pose")
    assert pose["mean"] == 0.35                                    # crossarm(0개)은 평균에서 빠진다
    cross = next(r for r in pose["rows"] if r["name"] == "crossarm")
    assert cross["absent"] and not cross["weak"] and not cross["few"]
    obs, _ = classes.note(c)
    assert "clamp" in obs and "0.350" in obs                       # box 평균(0.59)이 아니라 pose 평균
