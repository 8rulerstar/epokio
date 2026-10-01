"""폰 알림 시험 보내기(POST /webhooks/test)와 `epokio alerts` 명령. 진짜 네트워크로는 절대 보내지 않는다."""
import json
import urllib.error

import pytest

from epokio import alerts_cli, notify
from epokio.agent import Agent


@pytest.fixture
def sent(monkeypatch):
    """urlopen을 가짜로 바꾼다. 'fail'이 든 주소는 HTTP 404로 실패한다"""
    got = []

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        got.append(req)
        if "fail" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        return Resp()
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake)
    return got


def _agent():
    a = Agent.__new__(Agent)
    a.roots, a.label = [], "gpu-box"
    return a


def test_api_sends_one_test_to_each_saved_url(sent):
    a = _agent()
    assert a.post("/webhooks", {"urls": ["https://ntfy.sh/x", "https://hooks.slack.com/fail"]})[0] == 200
    code, body = a.post("/webhooks/test", {})
    assert code == 200
    res = {r["url"]: r for r in body["results"]}
    assert res["https://ntfy.sh/x"]["ok"] and res["https://ntfy.sh/x"]["status"] == 200
    assert not res["https://hooks.slack.com/fail"]["ok"] and res["https://hooks.slack.com/fail"]["status"] == 404
    assert len(sent) == 2
    assert b"gpu-box" in sent[0].data                     # 기계 이름이 본문에
    slack = json.loads(sent[1].data)                       # 실제 알림과 같은 모양(Slack text·Discord content)
    assert "gpu-box" in slack["text"] and slack["content"] == slack["text"]


def test_api_test_one_given_url_and_refuses_http(sent):
    a = _agent()
    code, body = a.post("/webhooks/test", {"url": "https://ntfy.sh/only"})
    assert code == 200 and [r["url"] for r in body["results"]] == ["https://ntfy.sh/only"]
    assert a.post("/webhooks/test", {"url": "http://plain"})[0] == 400
    assert len(sent) == 1


def test_api_test_without_webhooks_is_400(sent):
    assert _agent().post("/webhooks/test", {})[0] == 400
    assert not sent


def test_api_test_is_translated(sent):
    from epokio import msg
    msg.set_from_header("ko-KR")
    try:
        _agent().post("/webhooks/test", {"url": "https://ntfy.sh/ko"})
    finally:
        msg.set_from_header(None)
    assert "폰 알림" in sent[0].data.decode()


def test_cli_add_list_remove(capsys):
    assert alerts_cli.main(["--add", "https://ntfy.sh/a", "--add", "https://ntfy.sh/b", "--lang", "ko"]) == 0
    cfg = json.loads(Agent.HOOKS_FILE.read_text(encoding="utf-8"))
    assert cfg["urls"] == ["https://ntfy.sh/a", "https://ntfy.sh/b"] and cfg["lang"] == "ko" and cfg["kinds"]
    assert alerts_cli.main(["--remove", "https://ntfy.sh/a"]) == 0
    capsys.readouterr()
    assert alerts_cli.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "ntfy.sh/b" in out and "ntfy.sh/a" not in out
    # 웹 화면(agent)도 같은 파일을 본다
    assert _agent().get("/webhooks", {})["hosts"] == ["ntfy.sh"]


def test_cli_refuses_http_and_keeps_old(capsys):
    alerts_cli.main(["--add", "https://ntfy.sh/keep"])
    assert alerts_cli.main(["--add", "http://plain"]) == 2
    assert "https://" in capsys.readouterr().out
    assert json.loads(Agent.HOOKS_FILE.read_text(encoding="utf-8"))["urls"] == ["https://ntfy.sh/keep"]


def test_cli_test_sends_without_a_helper(sent, capsys):
    alerts_cli.main(["--add", "https://ntfy.sh/ok", "--add", "https://ntfy.sh/fail", "--lang", "en"])
    assert alerts_cli.main(["--test"]) == 1              # 하나라도 실패하면 1
    out = capsys.readouterr().out
    assert "ok" in out and "FAIL" in out and "404" in out
    assert len(sent) == 2 and b"Phone alerts from" in sent[0].data


def test_cli_test_with_nothing_saved(sent):
    assert alerts_cli.main(["--test"]) == 1 and not sent


def test_cli_is_wired(monkeypatch, capsys):
    from epokio import cli
    monkeypatch.setattr("sys.argv", ["epokio", "alerts", "--list"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0 and "No phone alerts" in capsys.readouterr().out
