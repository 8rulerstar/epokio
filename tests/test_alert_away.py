"""agent가 꺼진 사이에 끝난 학습·작업도 알린다. 같은 폴더의 두 번째 실패(이어 하기 뒤)도 알린다.
(7차 점검의 알림 시험에서 실제로 잡힌 것)"""
import json
import os
import time
from collections import deque
from types import SimpleNamespace

from epokio import jobs, watch_state
from epokio.agent import Agent
from epokio.jobs_queue import Queue

HEAD = "epoch,time,train/box_loss,metrics/mAP50-95(B)\n"


class _Pace:
    def watch(self, roots):
        return True

    def should_scan(self):
        return True


def _write(d, n, total=10, age=0.0):
    d.mkdir(parents=True, exist_ok=True)
    (d / "args.yaml").write_text(f"task: detect\nepochs: {total}\n", encoding="utf-8")
    (d / "results.csv").write_text(HEAD + "".join(f"{e},{e * 60},1.0,{0.1 + e / 100:.3f}\n" for e in range(1, n + 1)), encoding="utf-8")
    if age:
        t = time.time() - age
        for f in d.iterdir():
            os.utime(f, (t, t))


def _agent(tmp_path, monkeypatch, root):
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label, a.events, a.seq = [root], "t", deque(maxlen=50), 0
    a.ssh = SimpleNamespace(roots=lambda: [])
    a.pace = _Pace()
    monkeypatch.setattr(a, "_webhook", lambda *x: None)
    monkeypatch.setattr(a, "_check_machine", lambda roots: None)
    return a


def test_a_run_that_finished_while_the_agent_was_off_is_alerted(tmp_path, monkeypatch):
    """★켜면 첫 바퀴는 조용히 기준만 잡아서, agent를 다시 켜는 사이 끝난 학습은 폰 알림이 영영 없었다"""
    root = tmp_path / "runs"
    _write(root / "a", 5)                      # 돈다
    _write(root / "b", 3)
    first = _agent(tmp_path, monkeypatch, root)
    first._watch_once()
    assert json.loads(watch_state.file().read_text(encoding="utf-8"))["runs"]      # 도는 학습을 적었다
    # agent가 꺼진 사이: a는 끝까지 갔고, b는 그대로 돈다
    _write(root / "a", 10)
    _write(root / "b", 4)
    second = _agent(tmp_path, monkeypatch, root)
    second._watch_once()
    assert [(e["kind"], e["run"]["name"]) for e in second.events] == [("finished", "a")]
    second._watch_once()                       # 다음 바퀴에 또 알리지 않는다
    assert len(second.events) == 1


def test_an_old_record_is_not_replayed(tmp_path, monkeypatch):
    root = tmp_path / "runs"
    _write(root / "a", 5)
    _agent(tmp_path, monkeypatch, root)._watch_once()
    f = watch_state.file()
    saved = json.loads(f.read_text(encoding="utf-8"))
    f.write_text(json.dumps({**saved, "at": time.time() - watch_state.MAX_AGE - 60}), encoding="utf-8")
    _write(root / "a", 10)
    a = _agent(tmp_path, monkeypatch, root)
    a._watch_once()
    assert not a.events


def test_a_second_failure_after_resume_is_alerted(tmp_path, monkeypatch):
    """★같은 폴더의 결과는 30분 동안 한 번만 보내는데, 다시 돈 뒤(이어 하기)에도 지우지 않아 두 번째 실패가 사라졌다"""
    a = _agent(tmp_path, monkeypatch, tmp_path)
    run = {"name": "x", "path": str(tmp_path / "x")}
    for kind in ("started", "failed", "started", "failed"):
        a._push(kind, "running", dict(run))
    assert [e["kind"] for e in a.events] == ["started", "failed", "started", "failed"]
    a._push("failed", "running", dict(run))        # 그래도 같은 실패를 두 번은 안 보낸다
    assert len(a.events) == 4


def test_a_queue_job_that_ended_while_the_agent_was_off_is_alerted_by_its_run(tmp_path, monkeypatch):
    out_ok, out_dead = tmp_path / "out" / "ok", tmp_path / "out" / "dead"
    _write(out_ok, 10, age=600)
    _write(out_dead, 4, age=7200)              # 재부팅으로 같이 죽었다: '작업 끝남'은 거짓말이다(감시가 멎음으로 알린다)
    now = time.time()
    rows = [{"id": i, "kind": "train", "name": i, "python": "py", "state": "running", "created": now - 9000, "started": now - 9000,
             "output": str(o), "pid": 999999, "pid_start": 1.0} for i, o in (("ok", out_ok), ("dead", out_dead))]
    jobs.STATE.parent.mkdir(parents=True, exist_ok=True)
    jobs.STATE.write_text(json.dumps(rows), encoding="utf-8")
    q = Queue()
    assert {j.id for j in q.ended_away} == {"ok", "dead"}
    a = _agent(tmp_path, monkeypatch, tmp_path)
    a.queue = q
    for j in q.ended_away:
        a._away_job_event(j)
    assert [(e["kind"], e["run"]["name"]) for e in a.events] == [("job_done", "ok")]
