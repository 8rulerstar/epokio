"""폰 알림이 실제로 닿는지: 텔레그램 글자 모양, 실패한 전송 다시 보내기, NaN 실패의 이유, 빈 알림 종류, 맥 앱이 읽는 사건 모양.
(7차 점검의 알림 시험에서 실제로 잡힌 것. 진짜 네트워크로는 보내지 않는다)"""
import json
import re
import urllib.error
from collections import deque
from pathlib import Path

import pytest

from epokio import alerts_cli, i18n, notify
from epokio.agent import Agent
from epokio.monitor import Event
from epokio.scan import Run

MODELS = Path(__file__).resolve().parents[1] / "mac" / "Sources" / "Epokio" / "Models.swift"


def _run(**kw):
    d = {"name": "my_run_v2", "path": "/r/my_run_v2", "epoch": 11, "total": 50, "elapsed": 600.0, "eta": None, "metric": None,
         "metric_name": "metrics/mAP50-95(B)", "best": 0.41, "best_epoch": 9, "state": "failed", "idle": 5.0, "history": []}
    d.update(kw)
    return Run.from_dict(d)


def test_telegram_alert_has_a_bold_title_not_literal_asterisks():
    req = notify._request("https://api.telegram.org/bot1:x/sendMessage?chat_id=5", "Training finished", "a_b <c> & d")
    body = json.loads(req.data)
    assert body["parse_mode"] == "HTML" and "*" not in body["text"]
    assert body["text"] == "<b>Training finished</b>\na_b &lt;c&gt; &amp; d"     # ★밑줄 이름이 Markdown 해석을 깨면 알림이 통째로 거절된다
    slack = json.loads(notify._request("https://hooks.slack.com/x", "T", "b").data)
    assert slack["text"] == "*T*\nb" and "parse_mode" not in slack


class _Resp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b"{}"


def _flaky(monkeypatch, errors):
    """앞의 몇 번은 errors 차례대로 실패하고 그다음은 성공하는 urlopen"""
    calls = []

    def fake(req, timeout=None):
        calls.append(req.full_url)
        if len(calls) <= len(errors):
            raise errors[len(calls) - 1]
        return _Resp()
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake)
    return calls


def test_a_failed_delivery_is_tried_again(monkeypatch):
    """★Wi-Fi가 잠깐 끊긴 순간에 학습이 끝나면 그 알림은 영영 오지 않았다"""
    calls = _flaky(monkeypatch, [urllib.error.URLError("network down"),
                                 urllib.error.HTTPError("https://ntfy.sh/x", 503, "busy", {}, None)])
    req = notify._request("https://ntfy.sh/x", "T", "b")
    assert notify.deliver(req, "https://ntfy.sh/x", delays=(0, 0)) is True and len(calls) == 3


def test_a_refused_address_is_not_hammered(monkeypatch, caplog):
    calls = _flaky(monkeypatch, [urllib.error.HTTPError("https://hooks.slack.com/x", 404, "no", {}, None)] * 3)
    assert notify.deliver(notify._request("https://hooks.slack.com/x", "T", "b"), "https://hooks.slack.com/x", delays=(0, 0)) is False
    assert len(calls) == 1 and "after 1 tries" in caplog.text and "/x" not in caplog.text    # 주소 경로(비밀)는 로그에 없다


def test_gives_up_after_the_last_try(monkeypatch):
    calls = _flaky(monkeypatch, [urllib.error.URLError("down")] * 5)
    assert notify.deliver(notify._request("https://ntfy.sh/x", "T", "b"), "https://ntfy.sh/x", delays=(0, 0)) is False
    assert len(calls) == 3


def test_a_nan_failure_alert_says_why():
    """★손실이 NaN이 돼 실패한 학습의 알림이 '학습이 실패했습니다'뿐이었다(왜인지 없음)"""
    try:
        i18n.use("en")
        assert "loss became NaN" in notify.body_of(Event("failed", _run(), "running"))
        assert "loss became NaN" not in notify.body_of(Event("failed", _run(error="CUDA out of memory"), "running"))
        i18n.use("ko")
        assert "손실이 NaN이 됨" in notify.body_of(Event("failed", _run(), "running"))
    finally:
        i18n.use("en")


def _agent(tmp_path, monkeypatch):
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    monkeypatch.setattr(Agent, "HOOKS_FILE", tmp_path / "hooks.json")
    a = Agent.__new__(Agent)
    a.roots, a.label, a.events, a.seq = [], "t", deque(maxlen=50), 0
    return a


def test_turning_every_alert_kind_off_is_kept(tmp_path, monkeypatch):
    """★종류를 전부 끄고 저장하면 빈 목록이 기본값(전부 켬)으로 되돌아갔다(앱·명령 둘 다)"""
    a = _agent(tmp_path, monkeypatch)
    assert a.post("/webhooks", {"urls": ["https://ntfy.sh/mine"], "kinds": []})[0] == 200
    assert json.loads(a.HOOKS_FILE.read_text(encoding="utf-8"))["kinds"] == []
    a.post("/webhooks", {"urls": ["https://ntfy.sh/two"], "add": True})          # 종류를 안 보내면 그대로
    assert json.loads(a.HOOKS_FILE.read_text(encoding="utf-8"))["kinds"] == []
    monkeypatch.setattr(alerts_cli, "hooks_file", lambda: a.HOOKS_FILE)
    assert alerts_cli.main(["--add", "https://ntfy.sh/three"]) == 0
    assert json.loads(a.HOOKS_FILE.read_text(encoding="utf-8"))["kinds"] == []


def _swift_required_run_keys() -> set:
    """Models.swift의 struct Run에서 키가 꼭 있어야 하는 칸(Optional이 아닌 저장 프로퍼티. 합성 Decodable은 기본값이 있어도 키를 요구한다)"""
    text = MODELS.read_text(encoding="utf-8")
    body = text.split("struct Run: Codable", 1)[1].split("\n    struct ", 1)[0]
    keys = set()
    for m in re.finditer(r"^    (?:let|var) (\w+): ([^=/{\n]+?)\s*(?:=[^{\n]*)?(?://.*)?$", body, re.M):
        if not m.group(2).strip().endswith("?"):
            keys.add(m.group(1))
    return keys


def test_every_event_carries_what_the_mac_app_must_decode(tmp_path, monkeypatch):
    """★스윕 조기 중단 사건이 이름·경로만 실어 맥 앱의 /events 디코딩 전체가 실패했고, 그 agent의 알림이 다시 켤 때까지 멈췄다"""
    need = _swift_required_run_keys()
    assert {"name", "path", "epoch", "elapsed", "metric_name", "state", "idle", "history", "source"} <= need
    a = _agent(tmp_path, monkeypatch)
    monkeypatch.setattr(a, "_webhook", lambda *x: None)
    a._push("pruned", "running", {"name": "lr_0.01", "path": ""})
    a._warn("disk_low", "2 GB free")
    a._push("finished", "running", _run(state="done").to_dict())
    for e in a.events:
        missing = {k for k in need if e["run"].get(k) is None}
        assert not missing, (e["kind"], missing)
        assert isinstance(e["run"]["history"], list)
