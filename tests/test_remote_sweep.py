"""여러 기계 스윕: 같은 프로세스에 "원격" agent를 하나 더 띄워 흐름을 시험한다(학습은 돌지 않는다. 결과 파일을 흉내 낸다)."""
import threading
from http.server import ThreadingHTTPServer

from epokio.server_cli import QuietServer

from epokio import auth, sweep, sweep_remote
from epokio.agent import Agent
from epokio.jobs import Queue
from epokio.server import make_handler

SPACE = [{"key": "lr0", "values": [0.01, 0.003, 0.001, 0.0003]}]


def _remote(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "check", lambda h: h == "Bearer secret")       # 원격의 토큰은 "secret"
    a = Agent.__new__(Agent)
    a.roots, a.label, a.queue = [tmp_path / "remote_runs"], "gpu", Queue(tmp_path / "remote_jobs.json")
    (tmp_path / "remote_runs").mkdir()
    srv = QuietServer(("127.0.0.1", 0), make_handler(a))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, a, f"http://127.0.0.1:{srv.server_port}"


def _finish_job(j, folder, score):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "results.csv").write_text("epoch,metrics/mAP50-95(B)\n1,%.3f\n2,%.3f\n" % (score / 2, score))
    j.output, j.state = str(folder), "done"


def test_distributed_sweep_spreads_trials_and_collects_scores(tmp_path, monkeypatch):
    srv, remote, url = _remote(tmp_path, monkeypatch)
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    monkeypatch.setattr(sweep_remote, "TOKENS", {url: "secret"})
    monkeypatch.setattr(sweep_remote, "_jobs_cache", {})
    local = Queue(tmp_path / "local_jobs.json")
    try:
        spec = sweep.create(local, "d", "/usr/bin/python3", {"model": "yolo11n.pt", "data": "/mac/data.yaml", "epochs": 2}, SPACE, "grid",
                            machines=[{"url": "local"}, {"url": url, "python": "/gpu/python", "data": "/gpu/data.yaml"}])
        assert [t.get("machine", "") for t in spec["trials"]] == ["", url]     # 기계마다 하나씩
        rj = remote.queue.jobs[0]
        assert rj.python == "/gpu/python" and rj.params["data"] == "/gpu/data.yaml"   # 원격은 그 기계의 경로로
        assert sweep.dispatch(local) == []                                    # 둘 다 바쁘면 더 넣지 않는다
        _finish_job(local.jobs[0], tmp_path / "l1", 0.5)
        _finish_job(rj, tmp_path / "remote_runs" / "r1", 0.8)
        sweep_remote._jobs_cache.clear()
        assert len(sweep.dispatch(local)) == 2                                # 끝난 기계마다 다음 시도
        s = sweep.summary(sweep.load(spec["id"]), local)
        remote_row = next(r for r in s["rows"] if r["machine"] == url)
        assert remote_row["best"] == 0.8 and s["best"]["machine"] == url     # 원격 점수도 모인다
        assert s["total"] == 4 and s["machines"] == ["local", url]
    finally:
        srv.shutdown()


def test_missing_token_pauses_that_machine(tmp_path, monkeypatch):
    srv, remote, url = _remote(tmp_path, monkeypatch)
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    monkeypatch.setattr(sweep_remote, "TOKENS", {})                           # agent가 다시 켜져 토큰이 비었다
    local = Queue(tmp_path / "local_jobs.json")
    try:
        spec = sweep.create(local, "d", "/usr/bin/python3", {"model": "yolo11n.pt", "data": "d.yaml"}, SPACE, "grid",
                            machines=[{"url": "local"}, {"url": url, "python": "/gpu/python"}])
        assert remote.queue.jobs == [] and spec["needs_tokens"] == [url]
        assert sweep.summary(spec, local)["needs_tokens"] == [url]           # 화면이 "토큰 필요"를 알 수 있다
        sweep_remote.set_tokens({url: "secret"})
        sweep.dispatch(local)
        assert len(remote.queue.jobs) == 1 and sweep.load(spec["id"])["needs_tokens"] == []
    finally:
        srv.shutdown()


def test_tokens_are_never_written_to_disk(tmp_path, monkeypatch):
    """사용자 결정: 원격 토큰은 메모리에만"""
    srv, remote, url = _remote(tmp_path, monkeypatch)
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    monkeypatch.setattr(sweep_remote, "TOKENS", {url: "secret"})
    local = Queue(tmp_path / "local_jobs.json")
    try:
        sweep.create(local, "d", "/usr/bin/python3", {"model": "yolo11n.pt", "data": "d.yaml"}, SPACE, "grid",
                     machines=[{"url": url, "python": "/gpu/python", "token": "secret"}])
        for f in tmp_path.rglob("*.json"):
            assert "secret" not in f.read_text(), f
    finally:
        srv.shutdown()


def test_pruning_reaches_remote_runs_and_spares_good_ones(tmp_path, monkeypatch):
    """조기 중단이 원격에서 도는 시도도 멈춘다. 앞서는 시도는 건드리지 않는다"""
    srv, remote, url = _remote(tmp_path, monkeypatch)
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    monkeypatch.setattr(sweep_remote, "TOKENS", {url: "secret"})
    monkeypatch.setattr(sweep_remote, "_jobs_cache", {})
    local = Queue(tmp_path / "local_jobs.json")
    space = [{"key": "lr0", "values": [0.1, 0.01, 0.001, 0.0001]}]
    try:
        spec = sweep.create(local, "p", "/usr/bin/python3", {"model": "yolo11n.pt", "data": "d.yaml", "epochs": 10}, space, "grid",
                            prune=True, prune_at=0.2, machines=[{"url": "local"}, {"url": url, "python": "/gpu/python"}])
        # 먼저 끝난 두 시도(비교 기준): 2에폭에 0.5·0.6
        _finish_job(local.jobs[0], tmp_path / "l1", 0.6)
        _finish_job(remote.queue.jobs[0], tmp_path / "remote_runs" / "r1", 0.5)
        sweep_remote._jobs_cache.clear()
        sweep.dispatch(local)
        # 다음 두 시도가 도는 중: 이 맥은 2에폭에 0.9(앞섬), 원격은 0.1(뒤처짐)
        lj, rj = local.jobs[1], remote.queue.jobs[1]
        for j, folder, sc in ((lj, tmp_path / "l2", 0.9), (rj, tmp_path / "remote_runs" / "r2", 0.1)):
            folder.mkdir(parents=True)
            (folder / "results.csv").write_text(f"epoch,metrics/mAP50-95(B)\n1,{sc / 2}\n2,{sc}\n")
            j.output, j.state = str(folder), "running"
        sweep_remote._jobs_cache.clear()
        stopped = sweep.check_prune(local)
        assert stopped == [rj.id]                                   # 원격의 뒤처진 것만
        assert rj.state == "cancelled" and lj.state == "running"
    finally:
        srv.shutdown()
