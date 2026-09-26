"""분석 규칙·템플릿 버그 회귀: 내보내기 템플릿 JSON, 점수 기준 과적합, 중간 NaN, YOLO 밖 대표 지표."""
import ast
import json

from epokio import analysis
from epokio.templates import EXPORT_TEMPLATE


def test_export_template_survives_json_literals():
    """true/false/null이 파이썬 소스에 그대로 들어가면 NameError였다"""
    params = {"model": "best.pt", "format": "onnx", "half": True, "dynamic": False, "imgsz": None}
    src = EXPORT_TEMPLATE.format(params=json.dumps(params))
    ast.parse(src)
    line = next(ln for ln in src.splitlines() if ln.startswith("p = "))
    ns = {"json": json}
    exec(line, ns)
    assert ns["p"] == params


def _hf(tmp, evals):
    d = tmp / "hf"
    d.mkdir()
    hist = []
    for e, (acc, loss) in enumerate(evals, 1):
        hist += [{"epoch": e, "loss": 1.0 / e}, {"epoch": e, "eval_accuracy": acc, "eval_loss": loss}]
    (d / "trainer_state.json").write_text(json.dumps({"log_history": hist, "num_train_epochs": len(evals)}))
    return d


def test_hf_still_improving(tmp_path):
    a = analysis.analyze(_hf(tmp_path, [(0.5 + 0.04 * i, 1.0 - 0.05 * i) for i in range(8)]))
    assert not a.heads and a.score["metric"] == "accuracy" and a.score["best_epoch"] == 8
    assert "still_improving" in [k["kind"] for k in a.kinds]


def test_hf_score_drop_is_overfit(tmp_path):
    acc = [0.5, 0.6, 0.7, 0.8, 0.85, 0.8, 0.75, 0.72, 0.7, 0.68]
    a = analysis.analyze(_hf(tmp_path, [(x, 1.0) for x in acc]))
    kinds = {k["kind"]: k for k in a.kinds}
    assert kinds["overfit"]["best_epoch"] == 5


def test_lower_is_better_metric(tmp_path):
    """오차류 대표 점수는 낮을수록 좋다: 끝에서 최저면 아직 좋아지는 중"""
    d = tmp_path / "hf"
    d.mkdir()
    hist = [{"epoch": e, "eval_rmse": 1.0 / e} for e in range(1, 7)]
    (d / "trainer_state.json").write_text(json.dumps({"log_history": hist}))
    a = analysis.analyze(d)
    assert a.score and a.score["metric"] == "rmse" and a.score["best_epoch"] == 6


def _run_export(params):
    """틀을 가짜 YOLO로 돌려 export에 넘긴 인자를 본다(ultralytics 없이)"""
    got = {}

    class Fake:
        def __init__(self, m):
            got["model"] = m

        def export(self, **kw):
            got.update(kw)
            return "out"
    src = EXPORT_TEMPLATE.format(params=json.dumps(params)).replace("from ultralytics import YOLO", "")
    exec(src, {"YOLO": Fake, "__name__": "x"})
    return got


def test_export_imgsz_from_run_args(tmp_path):
    """앱이 imgsz를 안 보내면 640 고정이 아니라 학습 run의 args.yaml 값(weights/best.pt의 한 칸 위)"""
    (tmp_path / "weights").mkdir()
    (tmp_path / "args.yaml").write_text("task: detect\nimgsz: 1024 # size\n")
    got = _run_export({"model": str(tmp_path / "weights" / "best.pt"), "format": "onnx"})
    assert got["imgsz"] == 1024 and "half" not in got
    got = _run_export({"model": str(tmp_path / "weights" / "best.pt"), "format": "onnx", "imgsz": 320})
    assert got["imgsz"] == 320                                   # 보낸 값이 먼저


def test_export_imgsz_fallback_and_flags(tmp_path):
    got = _run_export({"model": str(tmp_path / "best.pt"), "format": "engine", "half": True, "int8": False,
                       "dynamic": None})
    assert got["imgsz"] == 640 and got["half"] is True and got["int8"] is False and "dynamic" not in got


def test_setup_pins_verified_ultralytics():
    from epokio.templates import SETUP_TEMPLATE, ULTRALYTICS_SPEC
    src = SETUP_TEMPLATE.format(target="/tmp/x")
    assert ULTRALYTICS_SPEC == "ultralytics==8.4.150" and '"ultralytics==8.4.150"' in src and "EPOKIO_ULTRALYTICS_SPEC" in src
    ast.parse(src)
