"""대기열이 멈추거나 엉뚱한 작업을 돌리지 않는지. 진짜 학습은 돌리지 않는다(작업을 직접 만들어 넣는다)."""
import json
import os
import sys

from epokio import jobs
from epokio.jobs import Job, Queue


def _q(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(jobs, "SCRIPTS", tmp_path / "scripts")
    return Queue(tmp_path / "jobs.json")


def test_moving_skips_over_a_cancelled_job(tmp_path, monkeypatch):
    """사이에 취소된 작업이 끼어 있어도 대기 중인 이웃과 자리를 바꾼다(예전엔 안 움직였다)."""
    q = _q(tmp_path, monkeypatch)
    a, b, c = (q.add("script", n, sys.executable, {"args": []}) for n in "abc")
    q.cancel(b.id)
    assert q.move(c.id, -1)
    assert [j.name for j in q.jobs if j.state == "queued"] == ["c", "a"]


def test_a_job_cancelled_before_it_starts_never_runs(tmp_path, monkeypatch):
    """대기열이 작업을 고른 뒤 띄우기 전에 취소가 오면, 띄우지 않는다."""
    q = _q(tmp_path, monkeypatch)
    mark = tmp_path / "ran"
    j = q.add("script", "x", sys.executable, {"args": ["-c", f"open({str(mark)!r},'w')"]})
    q.cancel(j.id)
    q._run(j)
    assert j.state == "cancelled" and j.pid is None and not mark.exists()


def test_a_broken_job_does_not_stop_the_queue(tmp_path, monkeypatch):
    """작업 하나에서 예외가 나도 스레드가 살아서 다음 작업을 돌린다(예전엔 대기열이 영원히 멈췄다)."""
    q = _q(tmp_path, monkeypatch)
    bad = q.add("script", "bad", sys.executable, {"args": []})
    good = q.add("script", "good", sys.executable, {"args": ["-c", "print(1)"]})
    calls = []
    real = q._run

    def run(j):
        calls.append(j.name)
        if j is bad:
            raise RuntimeError("boom")
        real(j)
        raise SystemExit                     # 두 번째 작업 뒤 스레드 반복을 끝낸다
    monkeypatch.setattr(q, "_run", run)
    try:
        q._worker()
    except SystemExit:
        pass
    assert calls == ["bad", "good"]
    assert bad.state == "failed" and good.state == "done"


def test_the_queue_file_is_utf8(tmp_path, monkeypatch):
    """한국어 윈도우 기본(cp949)으로 쓰면 é·学·맥 NFD 한글 이름에서 터졌다."""
    q = _q(tmp_path, monkeypatch)
    q.add("script", "é 学習 한글 한글", sys.executable, {"args": []})   # 뒤쪽은 NFD
    assert "学習" in (tmp_path / "jobs.json").read_text(encoding="utf-8")


def test_a_training_still_running_after_restart_is_waited_for(tmp_path, monkeypatch):
    """agent를 다시 켰을 때 전에 띄운 학습이 살아 있으면 실패로 적고 다음 작업을 띄우지 않는다.
    GPU에 두 개가 겹쳐 둘 다 메모리 부족으로 죽는다."""
    alive = Job(id="a1", kind="train", name="old", python="py", state="running", pid=os.getpid())
    dead = Job(id="d1", kind="train", name="gone", python="py", state="running", pid=None)
    (tmp_path / "jobs.json").write_text(json.dumps([alive.__dict__, dead.__dict__]), encoding="utf-8")
    q = _q(tmp_path, monkeypatch)
    assert q.get("a1").state == "running" and q._orphan is q.get("a1")
    # 꺼져 있는 사이에 끝난 작업은 '끝남(종료 코드 모름)'. ★실패로 적고 설명이 없어 잘 끝난 학습이 실패로 보였다
    assert q.get("d1").state == "done"


def test_pid_alive():
    assert jobs.pid_alive(os.getpid())
    assert not jobs.pid_alive(None)
    assert not jobs.pid_alive(2 ** 22 + 12345)


def test_export_options_are_json_not_python(tmp_path, monkeypatch):
    """true·false·null이 파이썬 코드로 들어가면 NameError가 났다."""
    monkeypatch.setattr(jobs, "SCRIPTS", tmp_path)
    j = Job(id="e1", kind="export", name="x", python="py",
            params={"model": str(tmp_path / "best.pt"), "format": "onnx", "half": True, "opset": None})
    src = (tmp_path / "e1.py").read_text(encoding="utf-8") if jobs.build_command(j) else ""
    compile(src, "export.py", "exec")
    assert "json.loads(" in src and "true" not in src.split("json.loads(")[0]


def test_an_unknown_key_in_the_queue_file_does_not_wipe_the_queue(tmp_path, monkeypatch):
    """새 판이 쓴 jobs.json을 옛 exe가 읽으면 모르는 칸 하나로 대기열이 통째로 비고 파일이 덮였다."""
    d = Job(id="k1", kind="train", name="keep", python="py").__dict__ | {"added_in_a_newer_version": 1}
    (tmp_path / "jobs.json").write_text(json.dumps([d]), encoding="utf-8")
    q = _q(tmp_path, monkeypatch)
    assert [j.name for j in q.jobs] == ["keep"]


def test_a_reused_process_id_is_not_the_old_training():
    """재부팅 뒤 같은 번호를 다른 프로그램이 받는다. 시작 시각이 다르면 옛 학습이 아니다."""
    me, started = os.getpid(), jobs.proc_start(os.getpid())
    assert started is not None
    assert jobs.pid_alive(me, started)
    assert not jobs.pid_alive(me, started - 3600)


def test_a_second_training_on_the_same_data_gets_its_own_folder(tmp_path, monkeypatch):
    """폴더가 있으면 ultralytics가 이름 뒤에 2를 붙인다. 작업이 옛 폴더를 가리키면 대기열이 끝난 옛 학습(50/50)을 보였다."""
    monkeypatch.setattr(jobs, "SCRIPTS", tmp_path / "s")
    proj = tmp_path / "runs"
    (proj / "mydata").mkdir(parents=True)
    (proj / "mydata2").mkdir()
    j = Job(id="n1", kind="train", name="mydata", python="py", params={"data": "d.yaml", "model": "m.pt", "project": str(proj)})
    jobs.build_command(j)
    assert j.output == str(proj / "mydata3")
    assert '"name": "mydata3"' in (tmp_path / "s" / "n1.py").read_text(encoding="utf-8")


def test_a_failed_save_after_launch_does_not_mark_the_training_failed(tmp_path, monkeypatch):
    """jobs.json 저장이 실패하면(윈도우 잠금) '못 띄움'으로 처리해 도는 학습을 실패로 적고 다음 작업을 같은 GPU에 띄웠다."""
    q = _q(tmp_path, monkeypatch)
    j = q.add("script", "x", sys.executable, {"args": ["-c", "print('ok')"]})
    real = q._save
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:                     # 첫 저장(running)은 되고, 띄운 직후 저장이 잠겨 실패
            raise PermissionError(5, "locked")
        return real(*a, **k)
    monkeypatch.setattr(q, "_save", flaky)
    q._run(j)
    assert j.state == "done" and j.returncode == 0


def test_add_keeps_nothing_when_the_save_fails(tmp_path, monkeypatch):
    """먼저 넣고 저장이 실패하면 사용자는 오류를 보고 다시 눌러 학습이 두 번 돌았다."""
    q = _q(tmp_path, monkeypatch)
    monkeypatch.setattr(q, "_save", lambda *a, **k: (_ for _ in ()).throw(PermissionError(5, "locked")))
    import pytest
    with pytest.raises(PermissionError):
        q.add("script", "x", sys.executable, {"args": []})
    assert q.jobs == []


def test_autolabelling_twice_uses_a_new_folder(tmp_path, monkeypatch):
    """같은 폴더에 다시 돌리면 라벨 파일에 이어 써서 박스가 두 번씩 들어갔다."""
    monkeypatch.setattr(jobs, "SCRIPTS", tmp_path / "s")
    (tmp_path / "labels_auto" / "al").mkdir(parents=True)
    j = Job(id="a1", kind="autolabel", name="al", python="py", params={"model": "m.pt", "source": str(tmp_path / "images")})
    jobs.build_command(j)
    assert j.output == str(tmp_path / "labels_auto" / "al2")


def test_resuming_writes_into_the_original_run_folder(tmp_path, monkeypatch):
    """이어 하기는 체크포인트의 학습 폴더에 이어 쓴다. ★새 이름(name2)을 주면 대기열은 빈 폴더를, 학습은 옛 폴더를 봤다"""
    monkeypatch.setattr(jobs, "SCRIPTS", tmp_path / "s")
    run = tmp_path / "runs" / "mydata"
    (run / "weights").mkdir(parents=True)
    ckpt = run / "weights" / "last.pt"
    ckpt.write_bytes(b"x")
    j = Job(id="r1", kind="train", name="mydata", python="py",
            params={"model": str(ckpt), "resume": True, "data": "other.yaml", "epochs": 999, "project": "elsewhere"})
    jobs.build_command(j)
    assert j.output == str(run)
    src = (tmp_path / "s" / "r1.py").read_text(encoding="utf-8")
    assert '"resume": true' in src and "other.yaml" not in src and "elsewhere" not in src


def test_a_full_disk_at_the_end_still_sends_the_finish_alert(tmp_path, monkeypatch):
    """★끝날 때 jobs.json 저장이 실패하면(디스크 가득) 예외로 빠져 끝남·실패 알림이 안 갔다"""
    q = _q(tmp_path, monkeypatch)
    j = q.add("script", "x", sys.executable, {"args": ["-c", "print('ok')"]})
    real, calls, told = q._save, {"n": 0}, []
    q.on_finish = told.append

    def full(*a, **k):
        calls["n"] += 1
        if calls["n"] >= 3:                     # 띄울 때까지는 되고, 끝날 때 디스크가 찼다
            raise OSError(28, "No space left on device")
        return real(*a, **k)
    monkeypatch.setattr(q, "_save", full)
    q._run(j)
    assert j.state == "done" and told == [j]


def test_only_one_helper_runs_the_queue(tmp_path, monkeypatch):
    """★같은 ~/.epokio로 도우미가 둘 뜨면 기다리던 작업이 두 번씩 돌았다. 두 번째는 대기열을 돌리지 않는다"""
    a = _q(tmp_path, monkeypatch).start()
    b = Queue(tmp_path / "jobs.json").start()
    assert not a.locked_out and b.locked_out


def test_a_damaged_queue_file_is_kept_and_old_jobs_are_pruned(tmp_path, monkeypatch):
    """★깨진 jobs.json을 빈 것으로 보고 덮어 대기열을 통째로 잊었다. 끝난 작업이 끝없이 쌓여 넣기가 느려졌다"""
    (tmp_path / "jobs.json").write_text('[{"id": "x", "kind"', encoding="utf-8")
    q = _q(tmp_path, monkeypatch)
    assert q.jobs == [] and list(tmp_path.glob("jobs.broken-*.json"))
    monkeypatch.setattr(Queue, "KEEP_FINISHED", 3)
    for i in range(6):
        q.jobs.append(Job(id=f"f{i}", kind="script", name="n", python="py", state="done"))
    q.add("script", "new", "py", {"args": []})
    assert [j.id for j in q.jobs if j.state == "done"] == ["f3", "f4", "f5"]
