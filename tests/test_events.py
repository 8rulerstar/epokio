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
    monkeypatch.setattr(notify, "webhook", lambda url, e, machine=None: sent.append(i18n.t(notify.KINDS[e.kind])))
    monkeypatch.setattr("epokio.config.quiet_now", lambda: False)
    try:
        a._webhook("failed", {"name": "r", "path": "", "epoch": 1, "total": 2, "elapsed": 1, "eta": None,
                              "metric": None, "metric_name": "", "best": None, "best_epoch": None,
                              "state": "failed", "idle": 0})
    finally:
        i18n.use("en")
    assert sent == ["학습이 실패했습니다"]


def test_a_run_with_no_planned_epochs_is_never_called_finished_when_it_goes_quiet():
    """★계획 에폭을 모르는 학습은 크래시로 죽어도 30분 뒤 '학습이 끝났습니다'가 갔다. 멎음 알림(stalled)으로 끝낸다"""
    from types import SimpleNamespace as N
    from epokio.monitor import classify
    assert classify("stalled", N(state="stopped", total=None, epoch=4)) is None
    assert classify("running", N(state="stopped", total=None, epoch=4)) == "quiet"
    assert classify("stalled", N(state="stopped", total=10, epoch=4)) == "stopped_early"
    assert classify("running", N(state="done", total=None, epoch=4)) == "finished"     # epokio_done 같은 끝 표시가 있으면 끝


def test_a_run_with_no_planned_epochs_that_goes_quiet_does_not_buzz_the_phone(tmp_path, monkeypatch):
    """★계획 에폭을 모르는 학습(케라스 CSVLogger)이 정상으로 끝나도 3분 뒤 '멎음'이 폰까지 갔다.
    'quiet'으로 알리고, 웹후크 기본 종류에는 넣지 않는다. 계획 에폭이 있으면 그대로 'stalled'"""
    import json as _json
    from types import SimpleNamespace as N
    from epokio import notify
    from epokio.agent import Agent
    assert classify("running", N(state="stalled", total=None, epoch=4)) == "quiet"
    assert classify("running", N(state="stalled", total=10, epoch=4)) == "stalled"
    hooks = tmp_path / "hooks.json"
    hooks.write_text(_json.dumps({"urls": ["https://ntfy.sh/x"]}), encoding="utf-8")       # 종류를 안 고른 기본 설정
    monkeypatch.setattr(Agent, "HOOKS_FILE", hooks)
    monkeypatch.setattr("epokio.config.quiet_now", lambda: False)
    sent = []
    monkeypatch.setattr(notify, "webhook", lambda url, e, machine=None: sent.append(e.kind))
    a = Agent.__new__(Agent)
    r = {"name": "k", "path": "", "epoch": 4, "total": None, "elapsed": 1, "eta": None, "metric": None,
         "metric_name": "", "best": None, "best_epoch": None, "state": "stalled", "idle": 200}
    a._webhook("quiet", r)
    a._webhook("stalled", r)
    assert sent == ["stalled"]
    assert notify.title("quiet") != "Epokio" and "quiet" not in notify.URGENT


def test_phone_text_says_which_machine_and_which_score():
    """★로컬 학습이면 기계 이름이 빠지고, '최고 0.6000'만 와서 무슨 점수인지 몰랐다"""
    from epokio import notify
    from epokio.monitor import Event
    from epokio.scan import Run
    r = Run.from_dict({"name": "version_0", "path": "/r/litnan/version_0", "epoch": 4, "total": None, "elapsed": 1,
                       "eta": None, "metric": 0.6, "metric_name": "metrics/val_acc", "best": 0.6, "best_epoch": 3,
                       "state": "failed", "idle": 0, "history": [], "source": "local"})
    body = notify.body_of(Event("failed", r, "running"), machine="gpu-box-3")
    assert "litnan/version_0" in body and "val_acc 0.6000" in body and body.endswith("gpu-box-3")


def test_two_runs_with_the_same_folder_name_both_get_their_alerts(tmp_path, monkeypatch):
    """★다른 프로젝트의 version_0 둘이 연달아 끝나면, 폴더 이름만 봐서 두 번째(실패)를 겹친 것으로 버렸다"""
    from collections import deque
    from epokio.agent import Agent
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label, a.events, a.seq = [], "t", deque(maxlen=50), 0
    monkeypatch.setattr(a, "_webhook", lambda *x: None)
    a._push("finished", "running", {"name": "version_0", "path": "/a/lightning_logs/version_0"})
    a._push("failed", "running", {"name": "version_0", "path": "/b/lightning_logs/version_0"})
    a._push("job_done", "running", {"name": "x", "path": "/a/lightning_logs/version_0"})   # 같은 폴더 같은 결과: 겹침
    assert [e["kind"] for e in a.events] == ["finished", "failed"]


def test_a_request_without_a_language_keeps_the_saved_alert_language(tmp_path, monkeypatch):
    """★Accept-Language 없는 POST /webhooks(curl·터미널·스크립트)가 저장된 폰 알림 언어를 영어로 되돌렸다"""
    from epokio import msg
    from epokio.agent import Agent
    monkeypatch.setattr(Agent, "HOOKS_FILE", tmp_path / "hooks.json")
    a = Agent.__new__(Agent)
    try:
        msg.set_from_header("ko-KR")
        a.post("/webhooks", {"urls": ["https://ntfy.sh/x"]})
        msg.set_from_header(None)
        assert not msg.given()
        a.post("/webhooks", {"urls": ["https://ntfy.sh/y"], "add": True})
        assert json.loads((tmp_path / "hooks.json").read_text())["lang"] == "ko-KR"
        msg.set_from_header("ja")                          # 언어를 실은 요청이면 그 언어로
        a.post("/webhooks", {"urls": ["https://ntfy.sh/y"]})
        assert json.loads((tmp_path / "hooks.json").read_text())["lang"] == "ja"
    finally:
        msg.set_from_header(None)
    assert msg.resolve("zh-Hant-TW") == "zh-Hant" and msg.resolve("zh_CN") == "zh-Hans" and msg.resolve("pt_BR") == "pt-BR"


def test_turning_alerts_off_can_be_undone(tmp_path, monkeypatch):
    """★웹의 '끄기' 한 번에 맥 앱·터미널에서 넣은 슬랙·텔레그램 주소까지 지워졌고 되돌릴 길이 없었다"""
    from epokio.agent import Agent
    monkeypatch.setattr(Agent, "HOOKS_FILE", tmp_path / "hooks.json")
    a = Agent.__new__(Agent)
    urls = ["https://ntfy.sh/x", "https://hooks.slack.com/services/T/B/C"]
    a.post("/webhooks", {"urls": urls, "kinds": ["failed"]})
    assert a.post("/webhooks", {"urls": []})[0] == 200
    assert json.loads((tmp_path / "hooks.json").read_text())["urls"] == []
    code, got = a.post("/webhooks", {"restore": True})
    cfg = json.loads((tmp_path / "hooks.json").read_text())
    assert code == 200 and got["count"] == 2 and cfg["urls"] == urls and cfg["kinds"] == ["failed"]
    (tmp_path / "webhooks.removed.json").unlink()
    assert a.post("/webhooks", {"restore": True})[0] == 400
