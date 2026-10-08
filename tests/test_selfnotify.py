"""도우미 없이 학습 프로세스가 보내는 폰 알림(epokio.start(notify=True)). 진짜 네트워크로는 보내지 않는다."""
import json
import urllib.error
from collections import deque

import pytest

import epokio
from epokio import config, selfnotify
from epokio.agent import Agent


@pytest.fixture
def sent(monkeypatch):
    got = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        got.append(req)
        if "fail" in req.full_url:
            raise urllib.error.URLError("no network")
        return Resp()
    monkeypatch.setattr(selfnotify.urllib.request, "urlopen", fake)
    monkeypatch.setattr(config, "quiet_now", lambda *a, **k: False)
    return got


def _hooks(*urls):
    Agent.HOOKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    Agent.HOOKS_FILE.write_text(json.dumps({"urls": list(urls), "lang": "en"}), encoding="utf-8")


def test_a_finished_run_alerts_once_and_the_agent_does_not_repeat_it(tmp_path, sent, monkeypatch):
    _hooks("https://ntfy.sh/topic")
    d = tmp_path / "runs" / "colab"
    with epokio.start(d, epochs=2, notify=True) as run:
        run.log(val_loss=1.0)
        run.log(val_loss=0.5)
    assert len(sent) == 1 and b"colab" in sent[0].data
    assert selfnotify.claimed(d, "finished")
    # 같은 학습을 지켜보던 도우미는 웹후크를 다시 보내지 않는다(사건함에는 남는다)
    hooked = []
    monkeypatch.setattr("epokio.notify.webhook", lambda *a, **k: hooked.append(a))
    a = Agent.__new__(Agent)
    a.roots, a.label, a.events, a.seq = [], "t", deque(maxlen=10), 0
    base = {"epoch": 2, "total": 2, "elapsed": 1, "eta": None, "metric": None, "metric_name": "", "best": None,
            "best_epoch": None, "state": "done", "idle": 0}
    a._push("finished", "running", {**base, "name": "colab", "path": str(d)})
    assert len(a.events) == 1 and hooked == []
    a._push("finished", "running", {**base, "name": "other", "path": str(tmp_path / "other")})
    assert len(hooked) == 1


def test_a_crash_alerts_with_the_reason(tmp_path, sent):
    _hooks("https://ntfy.sh/topic")
    d = tmp_path / "runs" / "oom"
    with pytest.raises(RuntimeError):
        with epokio.start(d, epochs=5, notify=True) as run:
            run.log(val_loss=1.0)
            raise RuntimeError("CUDA out of memory")
    assert len(sent) == 1 and b"RuntimeError: CUDA out of memory" in sent[0].data


def test_no_network_never_breaks_training_and_lets_the_agent_send(tmp_path, sent):
    _hooks("https://ntfy.sh/fail")
    d = tmp_path / "runs" / "offline"
    with epokio.start(d, epochs=1, notify=True) as run:
        run.log(val_loss=1.0)
    assert len(sent) == 1 and not selfnotify.claimed(d, "finished")      # 못 보냈으면 도우미가 대신


def test_without_notify_nothing_is_sent(tmp_path, sent):
    _hooks("https://ntfy.sh/topic")
    with epokio.start(tmp_path / "runs" / "quiet", epochs=1) as run:
        run.log(val_loss=1.0)
    assert sent == []
