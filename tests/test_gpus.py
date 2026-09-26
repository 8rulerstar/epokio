"""여러 GPU 나눠 쓰기. GPU 없는 기계·nvidia-smi가 깨진 기계에서 예전 동작으로 떨어지는지까지.

실제 다중 GPU 기계가 없으므로 nvidia-smi 출력과 gpus.lanes()를 갈아 끼워 시험한다.
"""
import json
import sys
import time

import pytest

from epokio import gpus
from epokio.jobs import Queue


@pytest.fixture(autouse=True)
def _fresh_cache():
    gpus.forget()
    yield
    gpus.forget()


# ── 목록 세기 ───────────────────────────────────────

def test_no_nvidia_smi_means_single_lane(monkeypatch):
    """맥·GPU 없는 리눅스: 세지 않고 예전처럼 한 줄"""
    monkeypatch.setattr(gpus, "smi_path", lambda: None)
    assert gpus.detect() == [] and gpus.count() == 0
    assert gpus.lanes() == [None]
    assert gpus.describe()["multi"] is False
    assert "CUDA_VISIBLE_DEVICES" not in gpus.env_for(gpus.AUTO, None, base={})


def test_broken_nvidia_smi_falls_back_quietly(monkeypatch):
    """드라이버가 깨져 nvidia-smi가 실패하거나 멈춘다: 조용히 GPU 0장"""
    import subprocess

    monkeypatch.setattr(gpus, "smi_path", lambda: "/usr/bin/nvidia-smi")

    def boom(*a, **k):
        raise OSError("no driver")
    monkeypatch.setattr(subprocess, "run", boom)
    assert gpus.detect() == [] and gpus.lanes() == [None]

    class R:
        returncode, stdout = 9, "Failed to initialize NVML"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    gpus.forget()
    assert gpus.detect() == []

    class Empty:
        returncode, stdout = 0, "\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Empty())
    gpus.forget()
    assert gpus.detect() == [] and gpus.lanes() == [None]


def test_parse_index_names():
    out = "0, NVIDIA GeForce RTX 4090\n1, NVIDIA GeForce RTX 4090\nbad line\n"
    assert gpus.parse_index_names(out) == [{"index": 0, "name": "NVIDIA GeForce RTX 4090"},
                                           {"index": 1, "name": "NVIDIA GeForce RTX 4090"}]
    assert gpus.parse_index_names("") == []


def _two(monkeypatch):
    monkeypatch.setattr(gpus, "detect", lambda: [{"index": 0, "name": "A"}, {"index": 1, "name": "B"}])
    gpus.forget()


def test_two_gpus_make_two_lanes(monkeypatch):
    _two(monkeypatch)
    assert gpus.count() == 2 and gpus.lanes() == [0, 1] and gpus.describe()["multi"] is True


def test_one_gpu_still_single_lane(monkeypatch):
    monkeypatch.setattr(gpus, "detect", lambda: [{"index": 0, "name": "A"}])
    gpus.forget()
    assert gpus.lanes() == [None]              # 한 장이면 나눌 것이 없다


def test_request_normalizing_and_env():
    assert gpus.normalize(None) == "auto" and gpus.normalize(" CPU ") == "cpu"
    assert gpus.normalize("1") == "1" and gpus.normalize("cuda:1") == "auto"    # 모르는 값은 auto
    assert gpus.env_for("cpu", None, base={})["CUDA_VISIBLE_DEVICES"] == ""
    assert gpus.env_for("auto", 1, base={})["CUDA_VISIBLE_DEVICES"] == "1"
    assert gpus.env_for("auto", None, base={"X": "1"}) == {"X": "1"}


def test_fits_and_assigned():
    assert gpus.fits("auto", 0) and gpus.fits("1", 1) and not gpus.fits("1", 0)
    assert gpus.fits("1", None)                      # 자리가 하나면 무엇이든 받는다
    assert gpus.assigned("auto", 1) == 1 and gpus.assigned("cpu", 1) is None
    assert gpus.assigned("1", None) == 1             # GPU를 못 세도 사용자가 고른 번호는 존중


def test_known_rejects_missing_index(monkeypatch):
    _two(monkeypatch)
    assert gpus.known("1") and not gpus.known("3")
    monkeypatch.setattr(gpus, "detect", lambda: [])
    gpus.forget()
    assert gpus.known("3")                           # 못 셌으면 막지 않는다(막으면 영영 못 돌린다)


# ── 대기열 ─────────────────────────────────────────

SCRIPT = """
import json, os, sys, time
t0 = time.time()
time.sleep(0.6)
json.dump({"cuda": os.environ.get("CUDA_VISIBLE_DEVICES", "<unset>"), "start": t0, "end": time.time()},
          open(sys.argv[1], "w"))
"""


def _queue(tmp_path, monkeypatch, lanes):
    monkeypatch.setattr(gpus, "lanes", lambda: lanes)
    monkeypatch.setattr("epokio.jobs.LOGS", tmp_path / "logs")
    return Queue(tmp_path / "jobs.json")


def _script_job(q, tmp_path, name, gpu="auto"):
    s = tmp_path / "work.py"
    s.write_text(SCRIPT)
    return q.add("script", name, sys.executable, {"args": [str(s), str(tmp_path / f"{name}.json")]}, gpu=gpu)


def _wait(jobs, seconds=30):
    end = time.time() + seconds
    while time.time() < end and any(j.state in ("queued", "running") for j in jobs):
        time.sleep(0.05)
    return all(j.state == "done" for j in jobs)


def test_two_jobs_run_on_different_gpus_at_the_same_time(tmp_path, monkeypatch):
    q = _queue(tmp_path, monkeypatch, [0, 1])
    a = _script_job(q, tmp_path, "a")
    b = _script_job(q, tmp_path, "b")
    q.start()
    assert _wait([a, b]), (a.state, b.state)
    got = {json.loads((tmp_path / f"{n}.json").read_text())["cuda"] for n in ("a", "b")}
    assert got == {"0", "1"}                          # 한 장씩 나눠 가졌다
    ra, rb = (json.loads((tmp_path / f"{n}.json").read_text()) for n in ("a", "b"))
    assert ra["start"] < rb["end"] and rb["start"] < ra["end"]     # 겹쳐서 돌았다
    assert a.gpu_index is None and b.gpu_index is None             # 끝나면 GPU를 놓는다
    assert q.busy_gpus() == []


def test_single_lane_keeps_running_one_at_a_time(tmp_path, monkeypatch):
    """GPU가 없거나 한 장: 예전 그대로 하나씩, CUDA_VISIBLE_DEVICES는 건드리지 않는다"""
    q = _queue(tmp_path, monkeypatch, [None])
    a = _script_job(q, tmp_path, "a")
    b = _script_job(q, tmp_path, "b")
    q.start()
    assert _wait([a, b])
    ra, rb = (json.loads((tmp_path / f"{n}.json").read_text()) for n in ("a", "b"))
    assert ra["cuda"] == rb["cuda"] == "<unset>"
    assert ra["end"] <= rb["start"] or rb["end"] <= ra["start"]    # 겹치지 않았다


def test_same_gpu_never_runs_two_jobs_at_once(tmp_path, monkeypatch):
    """둘 다 1번 GPU를 찍어 달라고 하면 줄을 선다"""
    q = _queue(tmp_path, monkeypatch, [0, 1])
    a = _script_job(q, tmp_path, "a", gpu="1")
    b = _script_job(q, tmp_path, "b", gpu="1")
    q.start()
    assert _wait([a, b])
    ra, rb = (json.loads((tmp_path / f"{n}.json").read_text()) for n in ("a", "b"))
    assert ra["cuda"] == rb["cuda"] == "1"
    assert ra["end"] <= rb["start"] or rb["end"] <= ra["start"]


def test_cpu_job_hides_every_gpu(tmp_path, monkeypatch):
    q = _queue(tmp_path, monkeypatch, [0, 1])
    j = _script_job(q, tmp_path, "c", gpu="cpu")
    q.start()
    assert _wait([j])
    assert json.loads((tmp_path / "c.json").read_text())["cuda"] == ""
    assert j.gpu_index is None


def test_crashed_agent_does_not_leave_a_gpu_taken(tmp_path, monkeypatch):
    """agent가 꺼진 사이 끝난 running 작업은 done(종료 코드 모름)이 되고 GPU 자리도 함께 비어야 한다"""
    monkeypatch.setattr(gpus, "lanes", lambda: [0, 1])
    monkeypatch.setattr("epokio.jobs.LOGS", tmp_path / "logs")
    f = tmp_path / "jobs.json"
    f.write_text(json.dumps([{"id": "x1", "kind": "script", "name": "n", "python": "p",
                              "state": "running", "gpu": "1", "gpu_index": 1, "pid": 99999}]))
    q = Queue(f)
    j = q.jobs[0]
    assert j.state == "done" and j.gpu_index is None and j.pid is None    # dev 감사: 꺼진 사이 끝난 작업은 "done(종료 코드 모름)"
    assert q.busy_gpus() == []


def test_cancel_kills_only_that_job(tmp_path, monkeypatch):
    q = _queue(tmp_path, monkeypatch, [0, 1])
    a = _script_job(q, tmp_path, "a")
    b = _script_job(q, tmp_path, "b")
    q.start()
    end = time.time() + 10
    while time.time() < end and not (a.state == "running" and b.state == "running"):
        time.sleep(0.02)
    assert q.cancel(a.id)
    end = time.time() + 20
    while time.time() < end and (a.state == "running" or b.state in ("queued", "running")):
        time.sleep(0.05)
    assert a.state == "cancelled" and b.state == "done"
    assert (tmp_path / "b.json").exists() and not (tmp_path / "a.json").exists()
    assert q.busy_gpus() == []


def test_old_jobs_file_without_gpu_fields_still_loads(tmp_path):
    f = tmp_path / "jobs.json"
    f.write_text(json.dumps([{"id": "a", "kind": "train", "name": "n", "python": "p", "state": "done"}]))
    j = Queue(f).jobs[0]
    assert j.gpu == "auto" and j.gpu_index is None      # 예전 파일에도 기본값이 붙는다


# ── HTTP 요청 ───────────────────────────────────────

def _agent(tmp_path, monkeypatch):
    from epokio.agent import Agent
    monkeypatch.setattr("epokio.jobs.LOGS", tmp_path / "logs")
    a = Agent.__new__(Agent)
    a.roots, a.label, a.queue = [], "t", Queue(tmp_path / "jobs.json")
    return a


def test_job_post_takes_a_gpu_and_rejects_a_missing_one(tmp_path, monkeypatch):
    _two(monkeypatch)
    a = _agent(tmp_path, monkeypatch)
    body = {"kind": "train", "python": "/opt/py/bin/python3", "params": {"model": "yolo11n.pt", "data": "d.yaml"}}
    code, out = a.post("/jobs", {**body, "gpu": "1"})
    assert code == 200 and out["gpu"] == "1" and a.queue.get(out["id"]).gpu == "1"
    assert a.post("/jobs", {**body, "gpu": "3"})[0] == 400          # 없는 번호는 받아 두지 않는다
    assert a.post("/jobs", body)[1]["gpu"] == "auto"                # 기본은 자동 배치
    assert a.post("/jobs", {**body, "gpu": "cpu"})[1]["gpu"] == "cpu"


def test_jobs_listing_reports_the_gpus(tmp_path, monkeypatch):
    _two(monkeypatch)
    a = _agent(tmp_path, monkeypatch)
    got = a.get("/jobs", {})["gpus"]
    assert got["count"] == 2 and got["multi"] is True and got["busy"] == []
    assert [g["index"] for g in got["gpus"]] == [0, 1]


def test_jobs_listing_on_a_machine_without_gpus(tmp_path, monkeypatch):
    monkeypatch.setattr(gpus, "smi_path", lambda: None)
    gpus.forget()
    got = _agent(tmp_path, monkeypatch).get("/jobs", {})["gpus"]
    assert got["count"] == 0 and got["multi"] is False and got["lanes"] == 1
