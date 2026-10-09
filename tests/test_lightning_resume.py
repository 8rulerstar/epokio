"""Lightning을 체크포인트에서 이어 하면 같은 lightning_logs에 version_N이 새로 생긴다.
version_1이 version_0을 잇는다고 적고(resumed_from), 앞 것의 멎음·끝남 알림은 내지 않는다"""
import time
from collections import deque
from types import SimpleNamespace

from epokio.agent import Agent
from epokio.monitor import Event
from epokio.scan import read_run


def _ver(root, n, epochs):
    d = root / "lightning_logs" / f"version_{n}"
    d.mkdir(parents=True)
    rows = "".join(f"{e},{(e + 1) * 100},{1.0 / (e + 1):.3f},{0.9 / (e + 1):.3f},{0.5 + e / 20:.3f}\n" for e in epochs)
    (d / "metrics.csv").write_text("epoch,step,train_loss,val_loss,val_acc\n" + rows, encoding="utf-8")
    return d


def test_a_version_that_continues_the_epochs_is_linked(tmp_path):
    v0 = _ver(tmp_path / "exp", 0, [0, 1, 2])
    v1 = _ver(tmp_path / "exp", 1, [3, 4])
    v2 = _ver(tmp_path / "exp", 2, [0, 1])                     # 처음부터 다시: 새 학습
    assert read_run(v1).resumed_from == "version_0"
    assert read_run(v0).resumed_from == "" and read_run(v2).resumed_from == ""
    assert read_run(v1).to_dict()["resumed_from"] == "version_0"


def test_only_the_latest_version_alerts(tmp_path, monkeypatch):
    v0 = _ver(tmp_path / "exp", 0, [0, 1, 2])
    v1 = _ver(tmp_path / "exp", 1, [3, 4])
    r0, r1 = read_run(v0), read_run(v1)
    evs = [Event("stalled", r0, "running"), Event("finished", r1, "running"), Event("failed", r0, "running")]
    mon = SimpleNamespace(sources=[], runs=[r0, r1], refresh=lambda: evs, add=lambda s: None)
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label, a.events, a.seq = [], "t", deque(maxlen=10), 0
    a._mon = mon
    a.pace = SimpleNamespace(watch=lambda roots: True, should_scan=lambda: True)
    monkeypatch.setattr(a, "_webhook", lambda *x: None)
    monkeypatch.setattr(a, "_check_machine", lambda roots: None)
    a._watch_once()
    assert [(e["kind"], e["run"]["name"]) for e in a.events] == [("finished", "version_1"), ("failed", "version_0")]
    assert time.time() > 0


def test_resumed_from_is_not_a_training_setting(tmp_path):
    """★이어 한 Lightning 학습의 설정 표와 비교에 'resumed_from: version_0'이 학습 설정처럼 떴다"""
    from epokio import rundetail
    _ver(tmp_path / "exp", 0, [0, 1, 2])
    v1 = _ver(tmp_path / "exp", 1, [3, 4])
    (v1 / "hparams.yaml").write_text("lr: 0.01\n", encoding="utf-8")
    args = rundetail.detail(v1)["args"]
    assert args.get("lr") == "0.01" and "resumed_from" not in args
