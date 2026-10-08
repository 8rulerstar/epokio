"""출시 전 보안 기본값: 새 토큰은 보기 전용, 네트워크에 연 도우미는 --allow-run 없이 코드를 돌리지 않는다.
이 기계의 토큰(~/.epokio/token, 맥 앱·이 기계의 웹 화면이 쓴다)은 그대로 실행 권한이다."""
import sys

import pytest

from epokio import auth, onboard, server_cli, tokens
from epokio.agent import Agent
from epokio.jobs_queue import Queue, RunRefused


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token")
    monkeypatch.setattr(tokens, "FILE", tmp_path / "tokens.json")


def test_add_token_without_scope_is_view_only(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["epokio-agent", "--add-token", "juno"])
    server_cli.main()
    assert tokens.listed()[0]["scope"] == tokens.READ
    monkeypatch.setattr(sys, "argv", ["epokio-agent", "--add-token", "ops", "--scope", "run"])
    server_cli.main()
    assert [e["scope"] for e in tokens.listed()] == [tokens.READ, tokens.RUN]


def test_this_machines_own_token_still_starts_jobs():
    """맥 앱(AgentClient)은 ~/.epokio/token을 직접 읽어 학습을 건다. 그 토큰은 실행 권한 그대로"""
    assert auth.post_scope("Bearer " + auth.token()) == tokens.RUN


def _agent(tmp_path, code_ok):
    a = Agent.__new__(Agent)
    a.roots, a.label = [tmp_path], "t"
    a.queue = Queue(tmp_path / "jobs.json")
    a.queue.code_ok = code_ok
    return a


def test_a_helper_open_to_the_network_refuses_code_without_allow_run(tmp_path):
    a = _agent(tmp_path, code_ok=False)
    for kind in ("script", "train", "evaluate", "autolabel", "export"):
        code, body = a.post("/jobs", {"kind": kind, "params": {"args": ["x.py"]}})
        assert code == 403 and "--allow-run" in body["error"], kind
    assert a.post("/predict", {})[0] == 403 and a.post("/sweeps", {})[0] == 403
    with pytest.raises(RunRefused):
        a.queue.add("classes", "c", sys.executable, {})               # 대기열 관문(다른 길로 들어와도)
    code, body = a.post("/jobs", {"kind": "practice", "params": {"epochs": 1}})
    assert code == 200                                                # 남의 코드를 안 돌리는 연습은 된다


def test_allow_run_or_localhost_keeps_jobs_working(tmp_path):
    a = _agent(tmp_path, code_ok=True)
    code, body = a.post("/jobs", {"kind": "script", "python": sys.executable, "params": {"args": [str(tmp_path / "x.py")]}})
    assert code != 403


def test_setup_lan_hands_out_a_view_only_token_not_this_machines_token(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(onboard, "start_agent", lambda *a, **k: None)
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: False)
    monkeypatch.setattr(onboard, "wait_for_agent", lambda *a, **k: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    onboard.main(["--root", str(tmp_path), "--port", "8798", "--no-browser", "--lan"])
    out = capsys.readouterr().out
    lan = [e for e in tokens.listed() if e["name"] == "setup-lan"]
    assert len(lan) == 1 and lan[0]["scope"] == tokens.READ
    assert "view-only" in out and "--allow-run" in out
    onboard.main(["--root", str(tmp_path), "--port", "8798", "--no-browser", "--lan"])
    assert len([e for e in tokens.listed() if e["name"] == "setup-lan"]) == 1   # 다시 돌려도 하나


def test_the_lan_banner_names_no_mac_and_says_what_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["epokio-agent", "--help"])
    with pytest.raises(SystemExit):
        server_cli.main()
    assert "--allow-run" in capsys.readouterr().out
    src = open(server_cli.__file__, encoding="utf-8").read()
    assert "on your Mac" not in src


def test_health_shows_the_token_command_without_the_user_folder(monkeypatch):
    """★/health token_cmd가 venv 전체 경로(사용자 이름)를 냈다"""
    import os
    from epokio import autostart
    home = os.path.expanduser("~")
    monkeypatch.setattr(autostart, "venv_python", lambda: os.path.join(home, "envs", "ml", "python"))
    cmd = autostart.short_home(autostart.cli("agent --show-token"))
    assert home not in cmd and cmd.startswith("~") and cmd.endswith("agent --show-token")
    q = autostart.short_home('& "' + os.path.join(home, "my venv", "python.exe") + '" -m epokio')
    assert home not in q and q.startswith('& "$HOME')


def test_console_text_falls_back_to_ascii_when_the_console_cannot_print_it():
    import io
    from epokio.autostart import console_text
    cp = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
    assert console_text("epokio agent 0.6 · lab · http://x", cp) == "epokio agent 0.6 | lab | http://x"
    kr = io.TextIOWrapper(io.BytesIO(), encoding="cp949")              # 찍을 수는 있어도 UTF-8로 읽으면 깨진다
    assert console_text("a · b", kr) == "a | b"
    utf = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    assert console_text("a · b", utf) == "a · b"


def test_agent_docstring_no_longer_says_viewing_needs_no_token():
    from epokio import agent
    assert "토큰 없이" not in (agent.__doc__ or "") and "GET needs no token" not in (agent.__doc__ or "")
