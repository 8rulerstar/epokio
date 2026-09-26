"""보고서와 검수 CSV의 결함 다섯 가지를 다시 못 나오게 막는다.

1 검수 결과가 보고서에 실린다 · 2 인자 없는 /report가 폴더를 섞지 않는다 · 3 원격(이름 붙은) run도 채워진다
4 만들 것이 없으면 200 + 경로가 아니라 400 · 5 CSV에 문턱·따옴표·BOM
"""
from pathlib import Path
from types import SimpleNamespace

from epokio import report, retrain
from epokio.agent import Agent
from epokio.scan import Run

RESULTS = ("epoch,train/box_loss,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B)\n"
           "1,1.0,0.5,0.4,0.45,0.30\n2,0.8,0.8,0.7,0.75,0.60\n")


def make_run(root: Path, name: str, source: str = "local") -> Run:
    d = root / name
    d.mkdir(parents=True)
    (d / "results.csv").write_text(RESULTS, encoding="utf-8")
    (d / "args.yaml").write_text("epochs: 2\n", encoding="utf-8")
    return Run(name=name, path=d, epoch=2, total=2, elapsed=10.0, eta=None, metric=0.6,
               metric_name="metrics/mAP50-95(B)", best=0.6, best_epoch=2, state="done", idle=1.0,
               history=[0.3, 0.6], source=source)


def eval_dir(root: Path, images=("a.jpg", "b.jpg")) -> Path:
    out = root / "evals" / "e1"
    out.mkdir(parents=True)
    rows = [{"image": str(root / i), "label": "", "gt": [{"cls": 0, "box": [0.5, 0.5, 0.2, 0.2]}],
             "pred": [{"cls": 0, "box": [0.5, 0.5, 0.2, 0.2], "conf": 0.9}] if i == "a.jpg" else []}
            for i in images]
    import json
    (out / "epokio_eval.json").write_text(json.dumps(
        {"task": "detect", "images": len(rows), "conf": 0.25, "conf_floor": 0.25, "iou": 0.5,
         "names": {"0": "thing"}, "rows": rows}), encoding="utf-8")
    return out


# ── 3. 원격·이름 붙은 폴더의 run ──────────────────────────────

def test_named_source_run_is_not_empty(tmp_path):
    """★source 문자열로 'local'을 찾던 탓에 이름 붙은 폴더·SSH로 비춰 온 run이 통째로 빈 보고서가 됐다."""
    r = make_run(tmp_path, "run1", source="gpu-server")
    assert report.readable(r)
    md = report.build([r])
    assert "0.800" in md and "No results yet" not in md


def test_missing_folder_is_not_analysed(tmp_path):
    r = make_run(tmp_path, "run2")
    r.path = tmp_path / "gone"
    assert not report.readable(r)
    assert "No results yet" in report.build([r])


# ── 1. 검수 결과가 보고서에 실린다 ─────────────────────────────

def test_review_summary_and_section(tmp_path):
    out = eval_dir(tmp_path)
    retrain.save_verdicts(out, {str(tmp_path / "a.jpg"): "ok", str(tmp_path / "b.jpg"): "model_wrong"}, 0.3, 0.5)
    s = retrain.review_summary(out)
    assert s["reviewed"] == 2 and s["counts"]["model_wrong"] == 1
    assert s["worst"] and s["worst"][0]["image"] == "b.jpg"
    r = make_run(tmp_path, "run3")
    md = report.build([r], None, {str(r.path): s})
    assert "Human review" in md and "model wrong 1" in md and "b.jpg" in md


def test_review_summary_is_none_without_verdicts(tmp_path):
    assert retrain.review_summary(eval_dir(tmp_path)) is None


# ── 5. 검수 CSV: 문턱 · 따옴표 · BOM ──────────────────────────

def test_review_csv_has_thresholds_bom_and_quoting(tmp_path):
    out = tmp_path / "e"
    out.mkdir()
    tricky = 'a,b "quoted".jpg'
    retrain.save_verdicts(out, {tricky: "ok"}, 0.35, 0.5)
    raw = (out / "review.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")                      # 엑셀 한글 안 깨짐
    text = raw.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("# epokio review") and "conf=0.350" in text.splitlines()[0]
    assert retrain.verdicts(out) == {tricky: "ok"}              # 쉼표·따옴표가 있어도 그대로 돌아온다
    assert retrain.thresholds(out) == {"conf": 0.35, "iou": 0.5}


def test_old_review_csv_still_reads(tmp_path):
    out = tmp_path / "e"
    out.mkdir()
    (out / "review.csv").write_text("image,verdict\nx.jpg,ok\n", encoding="utf-8")
    assert retrain.verdicts(out) == {"x.jpg": "ok"} and retrain.thresholds(out) == {}


def test_export_csv_carries_thresholds(tmp_path):
    from epokio import review as rv
    import json
    out = eval_dir(tmp_path)
    data = rv.rescore(json.loads((out / "epokio_eval.json").read_text()), 0.25, 0.5)
    text = retrain.export_csv(data, {str(tmp_path / "a.jpg"): "ok"})
    lines = text.splitlines()
    assert lines[0].startswith("# epokio review") and "iou=0.500" in lines[0]
    assert lines[1] == "image,score,correct,extra,missed,verdict"
    assert any(l.endswith(",ok") for l in lines[2:])


# ── 2·4. /report 범위와 빈 보고서 ─────────────────────────────

def _agent(tmp_path, monkeypatch, roots):
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    monkeypatch.setattr(Agent, "HOOKS_FILE", tmp_path / "hooks.json")
    a = Agent.__new__(Agent)
    a.roots, a.label = list(roots), "t"
    a.watch_roots = lambda: list(a.roots)          # 진짜 홈의 ~/.epokio/runs·예시 학습이 섞이지 않게
    a.queue = SimpleNamespace(jobs=[])
    return a


def test_report_without_scope_does_not_mix_folders(tmp_path, monkeypatch):
    """★팝오버 버튼이 인자 없이 부른다. 여러 고객사 폴더가 한 장에 섞이면 안 된다."""
    c1, c2 = tmp_path / "clientA", tmp_path / "clientB"
    make_run(c1, "a1"); make_run(c2, "b1")
    dest = tmp_path / "out"; dest.mkdir()
    a = _agent(tmp_path, monkeypatch, [c1, c2])
    code, body = a.post("/report", {"folder": str(dest)})
    assert code == 400 and sorted(Path(p).name for p in body["roots"]) == ["clientA", "clientB"]

    code, body = a.post("/report", {"folder": str(dest), "root": str(c1)})
    assert code == 200 and body["runs"] == 1
    md = Path(body["path"]).read_text(encoding="utf-8")
    assert "a1" in md and "b1" not in md

    code, body = a.post("/report", {"folder": str(dest), "all": True})
    assert code == 200 and body["runs"] == 2


def test_single_root_needs_no_scope(tmp_path, monkeypatch):
    c1 = tmp_path / "only"
    make_run(c1, "a1")
    dest = tmp_path / "out"; dest.mkdir()
    a = _agent(tmp_path, monkeypatch, [c1])
    code, body = a.post("/report", {"folder": str(dest)})
    assert code == 200 and body["runs"] == 1


def test_report_with_nothing_to_say_is_an_error(tmp_path, monkeypatch):
    """★빈 보고서를 200 + 경로로 돌려주면 앱이 'Report ready'를 띄운다."""
    c1 = tmp_path / "empty"
    c1.mkdir()
    dest = tmp_path / "out"; dest.mkdir()
    a = _agent(tmp_path, monkeypatch, [c1])
    assert a.post("/report", {"folder": str(dest)})[0] == 400
    assert a.post("/report", {"folder": str(dest), "paths": [str(c1 / "nope")]})[0] == 400


def test_report_root_must_be_watched(tmp_path, monkeypatch):
    c1 = tmp_path / "watched"
    make_run(c1, "a1")
    other = tmp_path / "elsewhere"; other.mkdir()
    dest = tmp_path / "out"; dest.mkdir()
    a = _agent(tmp_path, monkeypatch, [c1])
    assert a.post("/report", {"folder": str(dest), "root": str(other)})[0] == 400


def test_report_attaches_review_of_that_run(tmp_path, monkeypatch):
    c1 = tmp_path / "runs"
    r = make_run(c1, "a1")
    (r.path / "weights").mkdir()
    out = eval_dir(tmp_path)
    retrain.save_verdicts(out, {str(tmp_path / "b.jpg"): "model_wrong"}, 0.25, 0.5)
    dest = tmp_path / "out"; dest.mkdir()
    a = _agent(tmp_path, monkeypatch, [c1])
    a.queue = SimpleNamespace(jobs=[SimpleNamespace(
        kind="evaluate", state="done", output=str(out), params={"model": str(r.path / "weights" / "best.pt")})])
    code, body = a.post("/report", {"folder": str(dest), "root": str(c1)})
    assert code == 200
    md = Path(body["path"]).read_text(encoding="utf-8")
    assert "Human review" in md and "model wrong 1" in md
