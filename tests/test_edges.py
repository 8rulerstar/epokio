"""엣지 케이스(2026-09-22에 실제로 틀렸던 것들). 고친 뒤 다시 틀리지 않게 박제한다."""
import json
import os
import time

import pytest

from epokio import predictions, review, scan


def _run(tmp_path, name, text, args="epochs: 10\n"):
    d = tmp_path / name
    d.mkdir()
    (d / "results.csv").write_text(text, encoding="utf-8")
    (d / "args.yaml").write_text(args)
    return d


def test_csv_with_bom_is_read(tmp_path):
    """엑셀 등이 붙이는 BOM 때문에 첫 열(epoch)이 안 읽혀 빈 학습으로 보였다"""
    r = scan.read_run(_run(tmp_path, "bom", "﻿epoch,metrics/mAP50(B)\n1,0.4\n"))
    assert r.epoch == 1 and r.best == 0.4


def test_half_written_last_line_is_ignored_while_writing(tmp_path):
    """학습이 줄을 쓰는 도중에 읽으면 "2,0."이 점수 0.0으로 들어갔다"""
    r = scan.read_run(_run(tmp_path, "part", "epoch,metrics/mAP50(B)\n1,0.3\n2,0."))
    assert r.epoch == 1 and r.metric == 0.3


def test_old_file_without_final_newline_keeps_last_row(tmp_path):
    """끝 줄바꿈 없이 저장하는 도구도 있다. 오래된(쓰는 중이 아닌) 파일의 마지막 줄은 버리지 않는다"""
    d = _run(tmp_path, "old", "epoch,metrics/mAP50(B)\n1,0.3\n2,0.5")
    old = time.time() - 3600
    os.utime(d / "results.csv", (old, old))
    r = scan.read_run(d)
    assert r.epoch == 2 and r.best == 0.5


def _det(conf_in_pred=True):
    q = {"cls": 0, "box": [.5, .5, .2, .2], "kpts": []}
    if conf_in_pred:
        q["conf"] = .9
    return {"task": "detect", "rows": [{"image": "a", "gt": [{"cls": 0, "box": [.5, .5, .2, .2], "kpts": []}], "pred": [q]}]}


def test_prediction_without_conf_counts_as_certain():
    """신뢰도가 없는 예측이 0으로 쳐져 채점에서 통째로 빠졌다"""
    assert review.rescore(_det(conf_in_pred=False), 0.5)["overall"]["tp"] == 1


def test_threshold_is_clamped_to_0_1():
    assert review.rescore(_det(), 1.5)["conf"] == 1.0
    assert review.rescore(_det(), -3)["conf"] >= 0


def _load(tmp_path, text):
    f = tmp_path / "p.json"
    f.write_text(text, encoding="utf-8")
    return predictions.load(f)


def test_predictions_accept_a_json_array(tmp_path):
    rows = [{"image": "a.jpg", "gt": [], "pred": [{"cls": 0, "box": [.5, .5, .2, .2]}]}]
    assert _load(tmp_path, json.dumps(rows, indent=2))["images"] == 1


@pytest.mark.parametrize("text, words", [
    ("not json", "not valid JSON"),
    ('{"x": 1}', "missing field 'image'"),
    ("[1, 2]", "JSON object"),
    ("[]", "no rows found"),
])
def test_predictions_errors_are_readable(tmp_path, text, words):
    """★"'image'"·"list indices must be integers"처럼 파이썬 속사정이 그대로 보였다"""
    with pytest.raises(ValueError, match=words):
        _load(tmp_path, text)


# ── 2차(2026-09-22): 대기열·검수·폴더 요청 ──

def test_job_names_cannot_escape_the_output_folder(tmp_path):
    """★"../../x"면 project 밖에 결과를 썼다"""
    from epokio.jobs import Queue, safe_name
    assert "/" not in safe_name("../../etc") and "\n" not in safe_name("a\nb")
    q = Queue(tmp_path / "q.json")
    j = q.add("train", "../../evil", "/usr/bin/python3", {"data": "d", "name": "../x"})
    assert "/" not in j.name and "/" not in j.params["name"]


def test_jobs_never_wait_for_input(tmp_path, monkeypatch):
    """★입력을 기다리는 작업(빈 스크립트·라이브러리 질문)이 대기열을 영영 막았다. pytest는 stdin을 이미 바꿔 두므로
    실제로 돌려 보는 대신 Popen에 무엇을 넘기는지 본다"""
    import subprocess
    import sys
    from epokio import jobs
    seen = {}
    real = subprocess.Popen

    def spy(*a, **k):
        seen.update(k)
        return real(*a, **k)
    monkeypatch.setattr(jobs.subprocess, "Popen", spy)
    q = jobs.Queue(tmp_path / "q.json").start()
    j = q.add("script", "reads", sys.executable, {"args": ["-c", "pass"]}, cwd=str(tmp_path))
    deadline = time.time() + 15
    while time.time() < deadline and q.get(j.id).state in ("queued", "running"):
        time.sleep(0.1)
    assert seen.get("stdin") is subprocess.DEVNULL


def _agent(tmp_path, monkeypatch, roots=()):
    from epokio.agent import Agent
    from epokio.jobs import Queue
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label, a.queue = list(roots), "t", Queue(tmp_path / "jobs.json")
    return a


def test_script_job_needs_a_file(tmp_path, monkeypatch):
    code, body = _agent(tmp_path, monkeypatch).post("/jobs", {"kind": "script", "python": "/usr/bin/python3", "params": {}})
    assert code == 400 and "file" in body["error"]


def test_too_broad_watch_folders_are_refused(tmp_path, monkeypatch):
    """★"/"·홈 자체를 받으면 새로고침마다 디스크를 훑었다"""
    from pathlib import Path
    a = _agent(tmp_path, monkeypatch)
    for p in ("/", str(Path.home())):
        code, body = a.post("/roots", {"path": p})
        assert code == 400 and "broad" in body["error"], p
    assert a.post("/roots", {"path": str(tmp_path)})[0] == 200


def test_meta_only_for_watched_runs(tmp_path, monkeypatch):
    a = _agent(tmp_path, monkeypatch, roots=[tmp_path])
    assert a.post("/meta", {"path": "/etc", "star": True})[0] == 400


def test_import_only_reads_json_files(tmp_path, monkeypatch):
    """★/etc/passwd도 열어 읽었다"""
    code, body = _agent(tmp_path, monkeypatch).post("/review/import", {"path": "/etc/passwd"})
    assert code == 400 and ".jsonl" in body["error"]


def test_fixed_label_for_image_without_extension(tmp_path):
    """★확장자 없는 이미지는 이름이 ""라 ".txt"로 저장됐다"""
    from epokio import retrain
    f = retrain.fix_label(tmp_path, "/x/img_no_ext", [{"cls": 0, "box": [.5, .5, .2, .2]}])
    assert f.name == "img_no_ext.txt"
    with pytest.raises(ValueError, match="class number"):
        retrain.fix_label(tmp_path, "/x/a.jpg", [{"cls": "a", "box": [1, 2]}])


def test_retrain_without_results_says_so(tmp_path):
    from epokio import retrain
    with pytest.raises(ValueError, match="no results yet"):
        retrain.build_retrain(tmp_path, "/nope.pt", ["model_wrong"])


def test_sweep_summary_survives_partial_spec(tmp_path):
    """★옛 판 스윕 파일에 열쇠 하나가 없으면 KeyError로 스윕 목록 전체가 죽었다"""
    from epokio import sweep
    from epokio.jobs import Queue
    q = Queue(tmp_path / "q.json")
    assert sweep.summary({"id": "x"}, q)["total"] == 0
    assert sweep.summary({"id": "x", "space": [{"nokey": 1}, "str"], "trials": [{"job": "j"}]}, q)["total"] == 1


def test_unknown_event_is_not_called_finished():
    from epokio import notify
    assert notify.title("something_new") == "Epokio"


def test_train_params_from_text_are_typed(tmp_path, monkeypatch):
    """웹의 "다음 학습"은 args.yaml 값을 글자로 보낸다. 울트라리틱스는 lr0="0.01"을 거부한다 → 숫자로 바꿔 넣는다"""
    a = _agent(tmp_path, monkeypatch)
    code, body = a.post("/jobs", {"kind": "train", "python": "/usr/bin/python3",
                                  "params": {"model": "yolo11n.pt", "data": "d.yaml", "epochs": "60", "lr0": "0.0033", "amp": "true", "name": "007"}})
    assert code == 200
    p = a.queue.get(body["id"]).params
    assert p["epochs"] == 60 and p["lr0"] == 0.0033 and p["amp"] is True and p["name"] == "007"


def test_next_run_suggestions():
    """해설 → 바꿔 볼 설정(Ultralytics Platform의 다음 학습 제안을 규칙으로)"""
    from epokio.analysis import next_run
    assert next_run({"kind": "overfit", "best_epoch": 40}, {"epochs": "100"}, None) == {"epochs": 48}
    assert next_run({"kind": "still_improving", "epochs": 30}, {"epochs": "30"}, "/r/best.pt") == {"epochs": 60, "weights": "/r/best.pt"}
    assert next_run({"kind": "still_improving", "epochs": 30}, {}, None) is None      # 이어 할 가중치가 없으면 제안 안 함
    assert next_run({"kind": "early_best"}, {"lr0": "0.01"}, None) == {"lr0": 0.003333}
    assert next_run({"kind": "diverged"}, {"lr0": "abc"}, None) == {"lr0": 0.001}      # 못 읽으면 기본 0.01에서
    assert next_run({"kind": "misses"}, {}, None) is None                              # 문턱 문제는 학습 제안 아님


def test_runs_table_has_settings_columns(tmp_path, monkeypatch):
    """학습 기록 표: 한 줄에 점수·상태·설정값. 윈도 경로도 파일 이름만"""
    run = tmp_path / "exp1"
    run.mkdir()
    (run / "results.csv").write_text("epoch,metrics/mAP50-95(B)\n1,0.3\n2,0.5\n")
    (run / "args.yaml").write_text("epochs: 2\nlr0: 0.01\nmodel: C:\\\\Users\\\\me\\\\yolo11n.pt\nbatch: 16\n")
    a = _agent(tmp_path, monkeypatch, roots=[tmp_path])
    got = a.get("/runs/table", {})
    row = next(r for r in got["rows"] if r["name"] == "exp1")
    assert row["best"] == 0.5 and row["args"]["lr0"] == "0.01" and row["args"]["model"] == "yolo11n.pt"
    assert {"lr0", "batch", "model", "epochs"} <= set(got["keys"])


def test_collections_are_saved_like_tags(tmp_path, monkeypatch):
    from epokio import runmeta
    monkeypatch.setattr(runmeta, "FILE", tmp_path / "meta.json")
    m = runmeta.update(str(tmp_path / "run"), {"collections": ["배포 후보", " 배포 후보 ", "", "헬멧 실험"]})
    assert m["collections"] == ["배포 후보", "헬멧 실험"]
    assert "collections" not in runmeta.update(str(tmp_path / "run"), {"collections": []})


def test_a_copied_run_without_a_time_column_has_no_pace(tmp_path):
    """시간 열이 없으면 폴더 시각으로 잰다. 복사해 온 폴더는 파일이 한 순간에 생겨 '0s/epoch · 0s left'로 보였다."""
    from epokio.scan import read_run
    d = tmp_path / "train"
    d.mkdir()
    (d / "args.yaml").write_text("epochs: 40\n")
    (d / "results.csv").write_text("epoch,metrics/mAP50-95(B)\n" + "".join(f"{i},0.{i}\n" for i in range(1, 10)))
    r = read_run(d)
    assert r.state == "running" and r.elapsed == 0 and r.eta is None
