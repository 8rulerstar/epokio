"""알림 흐름: 대기열 작업 알림의 값, 같은 결과 한 번만, 죽은 학습의 뒤늦은 '멎음', patience 조기 종료.
(6차 점검의 알림 시험에서 실제로 잡힌 것)"""
import os
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace

from epokio import notify
from epokio.monitor import Event
from epokio.scan import Run, read_run

HEAD = "epoch,time,train/box_loss,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B),val/box_loss\n"


def _agent(tmp_path, monkeypatch):
    from epokio.agent import Agent
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label, a.events, a.seq = [], "t", deque(maxlen=50), 0
    monkeypatch.setattr(a, "_webhook", lambda *x: None)
    return a


def _yolo(d: Path, epochs: int, total: int, patience: int = 100, best_at: int | None = None, age: float = 0.0):
    d.mkdir(parents=True, exist_ok=True)
    (d / "args.yaml").write_text(f"task: detect\nepochs: {total}\npatience: {patience}\n", encoding="utf-8")
    rows = []
    for e in range(1, epochs + 1):
        m = 0.2 + 0.02 * min(e, best_at or e) - (0.001 * (e - best_at) if best_at and e > best_at else 0)
        rows.append(f"{e},{e * 60},1.0,0.5,0.5,{m + 0.1:.4f},{m:.4f},1.0")
    (d / "results.csv").write_text(HEAD + "\n".join(rows) + "\n", encoding="utf-8")
    if age:
        t = time.time() - age
        for f in d.iterdir():
            os.utime(f, (t, t))
    return d


def test_a_queue_job_alert_carries_the_runs_numbers(tmp_path, monkeypatch):
    """★작업 알림이 늘 '에폭 0/?'였고, 바른 값을 가진 '학습 끝남'을 같은 결과로 지웠다"""
    a = _agent(tmp_path, monkeypatch)
    run = _yolo(tmp_path / "runs" / "detect" / "train", 3, 3)
    j = SimpleNamespace(kind="train", name="pj", state="done", output=str(run), started=time.time() - 200, ended=time.time(), id="j1")
    a._job_event(j)
    ev = a.events[-1]
    assert ev["kind"] == "job_done" and ev["run"]["epoch"] == 3 and ev["run"]["total"] == 3 and ev["run"]["best"] is not None
    body = notify.body_of(Event("job_done", Run.from_dict({**ev["run"], "path": ev["run"]["path"]}), "running"), machine="pc")
    assert "3/3" in body and "0/?" not in body


def test_a_job_that_is_not_training_has_no_epoch_count_in_its_alert(tmp_path, monkeypatch):
    a = _agent(tmp_path, monkeypatch)
    a.queue = SimpleNamespace(tail=lambda jid, n: "Traceback\nModuleNotFoundError: No module named 'ultralytics'\n")
    a._job_event(SimpleNamespace(kind="export", name="to_onnx", state="failed", output="", started=1.0, ended=2.0, id="j2"))
    r = Run.from_dict({**a.events[-1]["run"], "path": ""})
    body = notify.body_of(Event("job_failed", r, "running"), machine="pc")
    assert "0/?" not in body and "to_onnx" in body
    assert r.error and r.error in body                              # 왜 실패했는지(로그로 본 이유)


def test_the_same_result_is_sent_once_even_when_the_last_validation_is_slow(tmp_path, monkeypatch):
    """★Ultralytics 마지막 검증이 2분을 넘으면 '학습 끝남'과 '작업 끝남'이 둘 다 갔다"""
    a = _agent(tmp_path, monkeypatch)
    clock = [1000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    a._push("finished", "running", {"name": "train", "path": "/p/runs/train", "updated": 990.0})
    clock[0] += 130
    a._push("job_done", "running", {"name": "train", "path": "/p/runs/train"})
    assert [e["kind"] for e in a.events] == ["finished"]


def test_a_script_job_and_the_run_it_wrote_are_one_result(tmp_path, monkeypatch):
    """★스크립트 작업은 결과 폴더를 몰라(output "") '작업 끝남'과 그 학습의 '학습 끝남'이 같은 초에 둘 다 갔다"""
    from epokio.watcher import _job_scope
    proj = os.path.normcase(os.path.abspath("/p"))
    run = os.path.join(proj, "runs", "train")
    assert _job_scope(SimpleNamespace(cwd="", params={"args": [os.path.join(proj, "fake_train.py")]})) == proj
    a = _agent(tmp_path, monkeypatch)
    a._push("job_done", "running", {"name": "x_script", "path": ""}, span=(1000.0, 1100.0, proj))
    a._push("finished", "running", {"name": "train", "path": run, "updated": 1095.0})
    a._push("finished", "running", {"name": "later", "path": os.path.join(proj, "runs", "later"), "updated": 5000.0})   # 작업이 끝난 뒤
    a._push("finished", "running", {"name": "theirs", "path": "/q/runs/theirs", "updated": 1050.0})   # 그 사이 끝난 남의 학습
    assert [e["run"]["name"] for e in a.events] == ["x_script", "later", "theirs"]
    b = _agent(tmp_path, monkeypatch)                                # 순서가 반대여도(학습이 먼저 끝남)
    b._push("finished", "running", {"name": "train", "path": run, "updated": 1095.0})
    b._push("job_done", "running", {"name": "x_script", "path": ""}, span=(1000.0, 1100.0, proj))
    assert [e["kind"] for e in b.events] == ["finished"]


def test_a_crashed_queue_job_is_one_alert_not_three(tmp_path, monkeypatch):
    """★대기열 학습 하나가 죽으면 '작업 실패'·'멎음'(급함)·'마지막 에폭 전에 멈춤'이 차례로 갔다"""
    a = _agent(tmp_path, monkeypatch)
    a._push("job_failed", "running", {"name": "train", "path": "/p/runs/train"})
    a._push("stalled", "running", {"name": "train", "path": "/p/runs/train"})
    a._push("stopped_early", "stalled", {"name": "train", "path": "/p/runs/train"})
    assert [e["kind"] for e in a.events] == ["job_failed"]
    a._push("recovered", "stopped", {"name": "train", "path": "/p/runs/train"})      # 다시 돌면(이어 하기) 다시 알린다
    a._push("stalled", "running", {"name": "train", "path": "/p/runs/train"})
    assert [e["kind"] for e in a.events] == ["job_failed", "recovered", "stalled"]


def test_a_patience_early_stop_is_finished_not_stalled(tmp_path):
    """★patience로 정상 조기 종료한 학습이 '멎음'(급함)으로, 30분 뒤 '마지막 에폭 전에 멈춤'으로 두 번 울렸다"""
    d = _yolo(tmp_path / "early", 8, 50, patience=3, best_at=5, age=400)
    r = read_run(d)
    assert r.best_epoch == 5 and r.state == "done"
    still = _yolo(tmp_path / "still", 8, 50, patience=10, best_at=5, age=400)     # patience가 아직 안 찼다: 진짜 멎음
    assert read_run(still).state == "stalled"
    fresh = _yolo(tmp_path / "fresh", 8, 50, patience=3, best_at=5)                # 방금 쓴 줄: 도는 중(조기 종료로 단정하지 않는다)
    assert read_run(fresh).state == "running"


def test_a_run_resumed_from_a_terminal_is_running_not_stopped(tmp_path):
    """★`yolo train resume`으로 다시 뜬 학습은 첫 에폭이 끝날 때까지 args.yaml만 새로 쓴다.
    그동안 '중단됨'과 '이어 하기' 단추가 보여 같은 폴더에 두 번째 학습을 붙일 수 있었다"""
    from epokio.retrain_args import resume_state
    d = _yolo(tmp_path / "train4", 30, 80, age=3 * 3600)
    (d / "weights").mkdir()
    (d / "weights" / "last.pt").write_bytes(b"x")
    t = time.time() - 3 * 3600
    os.utime(d / "weights" / "last.pt", (t, t))
    assert read_run(d).state == "stopped" and resume_state(d)["resumable"]
    (d / "args.yaml").write_text("task: detect\nepochs: 80\nresume: false\n", encoding="utf-8")  # 복사 등으로 새것일 뿐: 그대로 중단됨
    assert read_run(d).state == "stopped"
    (d / "args.yaml").write_text("task: detect\nepochs: 80\nresume: true\n", encoding="utf-8")   # 방금 다시 떴다
    r = read_run(d)
    assert r.state == "running" and r.epoch == 30
    assert not resume_state(d)["resumable"]


def test_a_chosen_main_score_does_not_turn_a_stalled_run_into_patience_done(tmp_path):
    """★대표 점수를 val/box_loss로 고르면 patience를 그 열의 최고 에폭(1)으로 재서, 점수가 계속 오르다 멎은 학습이 '끝남'으로 알려졌다.
    Ultralytics는 고른 열과 무관하게 fitness로 멈춘다"""
    from epokio import runmeta
    d = _yolo(tmp_path / "crashed", 30, 300, patience=10, age=1200)
    assert read_run(d).state == "stalled"
    runmeta.update(str(d), {"metric": "val/box_loss", "lower": True})
    r = read_run(d)
    assert r.metric_name == "val/box_loss" and r.state == "stalled"
