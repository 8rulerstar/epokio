"""감시 스레드가 보는 폴더 = /runs가 보는 폴더. ★SSH 비춤·데모 학습은 알림이 한 번도 안 갔다"""
import time
from collections import deque
from types import SimpleNamespace

from epokio.agent import Agent


class _Pace:
    def __init__(self):
        self.watched = []

    def watch(self, roots):
        self.watched.append([str(r) for r in roots])
        return True

    def should_scan(self):
        return True


def _write(d, n):
    d.mkdir(parents=True, exist_ok=True)
    (d / "args.yaml").write_text("epochs: 3\n", encoding="utf-8")
    rows = ["epoch,train/box_loss,metrics/mAP50-95(B)"] + [f"{i},{1.0 / i:.3f},{0.1 * i:.3f}" for i in range(1, n + 1)]
    (d / "results.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _agent(tmp_path, monkeypatch, mirror):
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    a = Agent.__new__(Agent)
    a.roots, a.label, a.events, a.seq = [], "t", deque(maxlen=50), 0
    a.ssh = SimpleNamespace(roots=lambda: list(mirror))
    a.pace = _Pace()
    monkeypatch.setattr(a, "_webhook", lambda *x: None)
    monkeypatch.setattr(a, "_check_machine", lambda roots: None)
    return a


def test_an_ssh_mirrored_run_gets_its_finished_alert(tmp_path, monkeypatch):
    mirror = tmp_path / "home" / ".epokio" / "ssh" / "gpu-box"
    _write(mirror / "runs" / "detect" / "train", 2)
    a = _agent(tmp_path, monkeypatch, [mirror])
    a._watch_once()                                    # 첫 바퀴는 조용히 기억만
    _write(mirror / "runs" / "detect" / "train", 3)
    a._watch_once()
    assert [e["kind"] for e in a.events] == ["finished"]


def test_file_watch_is_rearmed_when_the_folders_change_and_runs_reuses_the_scan(tmp_path, monkeypatch):
    m1, m2 = tmp_path / "home" / ".epokio" / "ssh" / "a", tmp_path / "home" / ".epokio" / "ssh" / "b"
    _write(m1 / "r", 1)
    hosts = [m1]
    a = _agent(tmp_path, monkeypatch, hosts)
    a._watch_once()
    a._watch_once()
    assert a.pace.watched == [[str(m1)]]               # 같은 목록이면 다시 걸지 않는다
    _write(m2 / "r", 1)
    hosts.append(m2)
    a._watch_once()
    assert a.pace.watched[-1] == [str(m1), str(m2)]
    # /runs가 감시 스레드의 결과를 다시 쓰려면 폴더 목록이 같아야 한다(★예전엔 비춤이 있으면 늘 다시 훑었다)
    assert a._scanned[1] == [str(r) for r in a.watch_roots() if r.exists()]
    assert time.time() - a._scanned[0] < 5


def test_ssh_mirrored_alerts_name_the_host(tmp_path, monkeypatch):
    """★SSH 비춤 학습의 사건·알림이 source: local이라 어느 서버의 학습인지 몰랐다"""
    from epokio import notify, ssh_source
    from epokio.monitor import Event
    from epokio.scan import Run
    base = tmp_path / "home" / ".epokio" / "ssh"
    monkeypatch.setattr(ssh_source, "MIRROR", base)
    monkeypatch.setattr(ssh_source, "load", lambda: [{"host": "gpu-box"}])
    mirror = ssh_source.mirror_dir("gpu-box")
    _write(mirror / "runs" / "detect" / "train", 2)
    a = _agent(tmp_path, monkeypatch, [mirror])
    a._watch_once()
    _write(mirror / "runs" / "detect" / "train", 3)
    a._watch_once()
    ev = a.events[-1]
    assert ev["kind"] == "finished" and ev["run"]["source"] == "ssh:gpu-box"
    assert "ssh:gpu-box" in notify.body_of(Event("finished", Run.from_dict(ev["run"]), "running"), machine="mac")
