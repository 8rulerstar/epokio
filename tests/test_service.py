"""도우미가 로그아웃·재부팅 뒤에도 사는가(service.py)와 doctor의 한 줄 상태.
진짜 systemctl·launchctl·loginctl은 부르지 않는다: conftest가 service._run을 막고, 여기서는 기록만 하는 가짜로 바꾼다.
만드는 파일은 전부 가짜 홈(tmp_path) 아래다."""
import json
import plistlib
import sys
from pathlib import Path

import pytest

from epokio import autostart, doctor, envs, onboard, service


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("USER", "lab")
    return tmp_path


def _fake_run(monkeypatch, ok=True, linger_after=True):
    """명령을 기록만 한다. loginctl show-user는 enable-linger 전엔 no, 뒤엔 linger_after"""
    calls, state = [], {"linger": False}

    def run(cmd, timeout=20):
        calls.append(" ".join(cmd))
        if cmd[:2] == ["loginctl", "show-user"]:
            return True, "Linger=" + ("yes" if state["linger"] else "no")
        if cmd[:2] == ["loginctl", "enable-linger"]:
            state["linger"] = linger_after
            return linger_after, ""
        if cmd[:3] == ["systemctl", "--user", "is-enabled"]:
            return ok, "enabled" if ok else "disabled"
        return ok, ""
    monkeypatch.setattr(service, "_run", run)
    return calls


def test_each_os_gets_a_no_root_autostart(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert service.kind() == "startup"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert service.kind() == "launchd" and service.path().name.endswith(".plist")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(service.shutil, "which", lambda n: "/usr/bin/systemctl")
    assert service.kind() == "systemd" and service.path() == onboard.unit_file()
    assert ".config/systemd/user" in service.path().as_posix()            # 사용자 서비스(관리자 권한 없이)
    monkeypatch.setattr(service.shutil, "which", lambda n: None)
    assert service.kind() is None                                            # systemd 없는 리눅스: 옛 트레이 .desktop


def test_the_launchd_agent_runs_the_helper_and_keeps_odd_paths_whole(home):
    text = service.launchd_plist([Path("/opt/lab/my runs/a&b <x>")], "127.0.0.1", 8787)
    d = plistlib.loads(text.encode("utf-8"))
    assert d["Label"] == service.LABEL and d["RunAtLoad"] is True
    assert d["KeepAlive"] == {"SuccessfulExit": False}                     # 죽으면 다시, --stop이면 그대로
    args = d["ProgramArguments"]
    assert args[0] == sys.executable and args[1:6] == ["-m", "epokio", "agent", "--port", "8787"]
    assert args[args.index("--root") + 1] == str(Path("/opt/lab/my runs/a&b <x>"))
    assert "--allow-run" not in args and "--launch-runs" not in args       # 작업 시작은 설정을 따른다
    assert "--allow-run" in plistlib.loads(service.launchd_plist([], "0.0.0.0", 1, True).encode())["ProgramArguments"]


def test_systemd_install_enables_starts_and_turns_on_linger_without_sudo(home, monkeypatch, capsys):
    monkeypatch.setattr(service, "kind", lambda: "systemd")
    calls = _fake_run(monkeypatch)
    assert service.install([home / "runs"], "127.0.0.1", 8787) is True
    unit = home / ".config" / "systemd" / "user" / "epokio.service"
    assert "-m epokio agent --port 8787" in unit.read_text(encoding="utf-8")
    assert calls[:3] == ["systemctl --user daemon-reload", "systemctl --user enable epokio", "systemctl --user start epokio"]
    assert "loginctl enable-linger lab" in calls and not any("sudo" in c for c in calls)
    out = capsys.readouterr().out
    assert "no sudo" in out and "enabled and started" in out and "keeps running after you log out" in out


def test_systemd_install_says_what_to_run_when_it_cannot(home, monkeypatch, capsys):
    monkeypatch.setattr(service, "kind", lambda: "systemd")
    _fake_run(monkeypatch, ok=False, linger_after=False)
    assert service.install([], "127.0.0.1", 8787) is False
    out = capsys.readouterr().out
    assert "systemctl --user daemon-reload && systemctl --user enable --now epokio" in out
    assert "loginctl enable-linger $USER" in out and "sudo loginctl enable-linger lab" in out


def test_systemd_install_next_to_a_running_helper_only_enables_it(home, monkeypatch, capsys):
    """setup이 방금 띄운 도우미가 포트를 쥐고 있으면, 서비스까지 띄우면 같은 포트에 둘이라 서비스가 '실패'한다"""
    monkeypatch.setattr(service, "kind", lambda: "systemd")
    calls = _fake_run(monkeypatch)
    service.install([], "127.0.0.1", 8787, running=True)
    assert "systemctl --user start epokio" not in calls and "systemctl --user enable epokio" in calls
    assert "next login or reboot" in capsys.readouterr().out


def test_rerunning_setup_on_a_server_applies_the_new_settings(home, monkeypatch, capsys):
    """★도는 도우미가 바로 그 서비스인데 '먼저 끄라'고만 해서, --lan을 뺀 뒤에도 옛 도우미가 0.0.0.0에 열려 있었다"""
    monkeypatch.setattr(service, "kind", lambda: "systemd")
    monkeypatch.setattr(onboard, "headless", lambda: True)
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: True)
    monkeypatch.setattr(onboard, "owner", lambda *a, **k: "mine")
    monkeypatch.setattr(onboard, "find_roots", lambda: [])
    calls = _fake_run(monkeypatch)
    unit = onboard.unit_file()
    unit.parent.mkdir(parents=True)
    unit.write_text("old --host 0.0.0.0", encoding="utf-8")
    onboard.main(["--autostart", "--no-browser"])
    assert "systemctl --user restart epokio" in calls and "--host 127.0.0.1" in unit.read_text(encoding="utf-8")


def test_setup_with_autostart_starts_the_helper_itself_when_systemd_is_unreachable(home, monkeypatch, capsys):
    """★서비스에 맡긴다며 도우미를 안 띄웠는데 systemd가 없으면(WSL·컨테이너) 아무것도 안 돌았다"""
    monkeypatch.setattr(service, "kind", lambda: "systemd")
    monkeypatch.setattr(onboard, "headless", lambda: True)
    monkeypatch.setattr(onboard, "owner", lambda *a, **k: None)
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: False)
    monkeypatch.setattr(onboard, "find_roots", lambda: [])
    started = []
    monkeypatch.setattr(onboard, "start_agent", lambda *a, **k: started.append(a))
    monkeypatch.setattr(onboard, "wait_for_agent", lambda *a, **k: True)
    _fake_run(monkeypatch, ok=False)
    onboard.main(["--autostart", "--no-browser"])
    assert len(started) == 1 and "Started the helper for now." in capsys.readouterr().out


def test_setup_suggests_autostart_without_installing_it(home, monkeypatch, capsys):
    monkeypatch.setattr(service, "kind", lambda: "systemd")
    monkeypatch.setattr(onboard, "headless", lambda: True)
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: True)
    monkeypatch.setattr(onboard, "owner", lambda *a, **k: "mine")
    monkeypatch.setattr(onboard, "find_roots", lambda: [])
    monkeypatch.setattr(service, "install", lambda *a, **k: pytest.fail("installed without being asked"))
    onboard.main(["--no-browser"])
    out = capsys.readouterr().out
    assert "stops at reboot and when you log out" in out and "setup --autostart" in out
    onboard.main(["--no-browser", "--no-autostart"])
    assert "setup --autostart" not in capsys.readouterr().out


def test_autostart_on_and_off_use_the_service(home, monkeypatch, capsys):
    monkeypatch.setattr(service, "kind", lambda: "systemd")
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: False)
    monkeypatch.setattr(autostart, "enable", lambda *a, **k: pytest.fail("made a tray entry"))
    calls = _fake_run(monkeypatch)
    assert onboard.autostart_main(["--on"]) == 0
    assert onboard.unit_file().exists() and "systemctl --user start epokio" in calls
    assert onboard.autostart_main([]) == 0
    assert "installed (systemd user service, enabled, keeps running after logout)" in capsys.readouterr().out
    assert onboard.autostart_main(["--off"]) == 0
    assert "systemctl --user disable --now epokio" in calls and not onboard.unit_file().exists()
    assert onboard.autostart_main(["--off"]) == 0 and "It was not on." in capsys.readouterr().out


def test_windows_startup_shortcut_starts_the_helper_when_there_is_no_tray(monkeypatch):
    """★트레이 패키지가 없으면 '설치하라'고만 해서 재부팅 뒤 알림이 끊겼다"""
    monkeypatch.setattr(autostart, "tray_ready", lambda: False)
    assert autostart.launcher()[-1] in ("agent", "epokio.agent")
    monkeypatch.setattr(autostart, "tray_ready", lambda: True)
    assert autostart.launcher()[-1] in ("tray", "epokio.tray")


def _doctor(monkeypatch, capsys, argv, running=False, hooks=()):
    monkeypatch.setattr(onboard, "agent_health", lambda *a, **k: {"epokio": "x", "label": "pc"} if running else None)
    monkeypatch.setattr(envs, "list_envs", lambda: [])
    if hooks:
        from epokio import alerts_cli
        f = alerts_cli.hooks_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"urls": list(hooks)}), encoding="utf-8")
    code = doctor.doctor(argv)
    return code, capsys.readouterr().out


def test_doctor_says_in_one_line_if_the_helper_runs_and_survives(home, monkeypatch, capsys):
    monkeypatch.setattr(service, "kind", lambda: "systemd")
    _fake_run(monkeypatch)
    code, out = _doctor(monkeypatch, capsys, [])
    line = next(l for l in out.splitlines() if l.strip().startswith("Helper:"))
    assert "Helper: NOT running" in line and "autostart: not installed" in line and "phone alerts: none saved" in line
    assert "Next: start it:" in out
    onboard.unit_file().parent.mkdir(parents=True)
    onboard.unit_file().write_text("x", encoding="utf-8")
    service._run(["loginctl", "enable-linger", "lab"])
    code, out = _doctor(monkeypatch, capsys, [], running=True, hooks=["https://ntfy.sh/t0p1c"])
    line = next(l for l in out.splitlines() if l.strip().startswith("Helper:"))
    assert line.strip().startswith("Helper: running now on port")
    assert "installed (systemd user service, enabled, keeps running after logout)" in line and "phone alerts: 1 webhook" in line
    assert "doctor --test-alert" in out and "t0p1c" not in out


def test_doctor_sends_a_test_alert_only_when_asked(home, monkeypatch, capsys):
    from epokio import notify
    sent = []
    monkeypatch.setattr(notify, "send_test", lambda url, machine=None, timeout=5: sent.append(url) or {"url": url, "ok": True, "status": 200})
    code, _ = _doctor(monkeypatch, capsys, [], hooks=["https://ntfy.sh/abc"])
    assert code == 0 and sent == []
    code, out = _doctor(monkeypatch, capsys, ["--test-alert"], hooks=["https://ntfy.sh/abc"])
    assert code == 0 and sent == ["https://ntfy.sh/abc"] and "Sending a test alert" in out
    monkeypatch.setattr(notify, "send_test", lambda url, machine=None, timeout=5: {"url": url, "ok": False, "error": "x"})
    assert _doctor(monkeypatch, capsys, ["--test-alert"], hooks=["https://ntfy.sh/abc"])[0] == 1
    code, out = _doctor(monkeypatch, capsys, ["--json"])
    assert json.loads(out)["autostart"]["installed"] is False
