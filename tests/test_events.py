"""상태 변화 → 알림 판정. 알림이 틀리면 믿지 않게 되므로 경우를 다 박제한다."""
import json
from pathlib import Path

from epokio.monitor import Monitor, classify
from epokio.scan import Run


def run(state, epoch=10, total=40):
    return Run(name="r", path=Path("/tmp/r"), epoch=epoch, total=total, elapsed=100.0,
               eta=None, metric=None, metric_name="", best=None, best_epoch=None,
               state=state, idle=1.0)


def test_finished():
    assert classify("running", run("done", 40)) == "finished"


def test_crash_looks_like_stall_first():
    assert classify("running", run("stalled")) == "stalled"


def test_stopped_before_planned_epochs():
    assert classify("stalled", run("stopped", 12, 40)) == "stopped_early"


def test_stopped_at_planned_epochs_is_finished():
    assert classify("running", run("stopped", 40, 40)) == "finished"


def test_nan_is_failed():
    assert classify("running", run("failed")) == "failed"


def test_recovered():
    assert classify("stalled", run("running")) == "recovered"


def test_no_change_no_event():
    assert classify("running", run("running")) is None


class FakeSource:
    label, error = "fake", None

    def __init__(self):
        self.state = "running"

    def fetch(self):
        r = run(self.state)
        r.source = "fake"
        return [r]


def test_first_refresh_is_silent_then_fires_once():
    src = FakeSource()
    m = Monitor([src])
    assert m.refresh() == []                      # 켤 때 조용
    src.state = "stalled"
    ev = m.refresh()
    assert [e.kind for e in ev] == ["stalled"]
    assert m.refresh() == []                      # 같은 사건을 두 번 알리지 않는다


def test_short_run_seen_only_when_done_still_notifies():
    """감시 주기보다 짧게 끝난 작업: 처음 본 게 '완료'여도 알린다."""
    class Src:
        label, error = "fake", None
        def __init__(self): self.runs = []
        def fetch(self): return list(self.runs)
    src = Src()
    m = Monitor([src])
    m.refresh()                                   # 켤 때: 아무것도 없음
    r = run("done", 40); r.source = "fake"
    src.runs = [r]
    assert [e.kind for e in m.refresh()] == ["finished"]


def test_source_added_later_does_not_replay_old_runs():
    class Src:
        label, error = "fake", None
        def fetch(self):
            r = run("done", 40); r.source = "late"; r.path = Path("/tmp/old"); return [r]
    m = Monitor([])
    m.refresh()
    m.add(Src())
    assert m.refresh() == []


def test_phone_alerts_use_the_language_of_the_app_that_set_them(tmp_path, monkeypatch):
    """웹후크 문구는 설정한 앱의 언어로. 예전엔 언어를 고르는 곳이 없어 늘 영어였다."""
    from epokio import i18n, msg, notify
    from epokio.agent import Agent
    monkeypatch.setattr(Agent, "HOOKS_FILE", tmp_path / "hooks.json")
    a = Agent.__new__(Agent)
    msg.set_from_header("ko-KR,ko;q=0.9")
    try:
        assert a.post("/webhooks", {"urls": ["https://ntfy.sh/x"]})[0] == 200
    finally:
        msg.set_from_header(None)                 # 요청 언어가 다음 테스트로 새지 않게
    assert json.loads((tmp_path / "hooks.json").read_text())["lang"] == "ko-KR"
    sent = []
    monkeypatch.setattr(notify, "webhook", lambda url, e: sent.append(i18n.t(notify.KINDS[e.kind])))
    monkeypatch.setattr("epokio.config.quiet_now", lambda: False)
    try:
        a._webhook("failed", {"name": "r", "path": "", "epoch": 1, "total": 2, "elapsed": 1, "eta": None,
                              "metric": None, "metric_name": "", "best": None, "best_epoch": None,
                              "state": "failed", "idle": 0})
    finally:
        i18n.use("en")
    assert sent == ["학습이 실패했습니다"]
