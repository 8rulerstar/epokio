"""윈도우 온보딩: 자동 시작 항목과 `epokio setup`.

윈도우 사용자가 포기하는 자리라서, 여기가 조용히 깨지면 아무도 알려 주지 않는다.
실제 시작프로그램 폴더는 건드리지 않는다. enable/disable 이 폴더를 인자로 받는 건 그래서다.
"""
import subprocess
import sys

import pytest

from epokio import autostart, onboard


# ── 자동 시작 ────────────────────────────────────────

def test_it_knows_where_the_entry_goes():
    f = autostart.folder()
    assert f.is_absolute()
    if sys.platform == "win32":
        assert f.name == "Startup"
    elif sys.platform == "linux":
        assert f.name == "autostart"


def test_the_launcher_avoids_a_console_window_on_windows():
    exe, *args = autostart.launcher()
    assert args == ["-m", "epokio.tray" if autostart.tray_ready() else "epokio.agent"]   # 트레이 패키지가 없으면 도우미만
    if sys.platform == "win32":
        from pathlib import Path
        # pythonw 가 있는데도 python 을 고르면 로그인할 때마다 검은 창이 남는다
        assert not Path(exe).with_name("pythonw.exe").exists() or Path(exe).name == "pythonw.exe"


@pytest.mark.skipif(not autostart.supported(), reason="윈도우·리눅스에서만 만든다")
def test_enable_then_disable_leaves_nothing_behind(tmp_path):
    where = tmp_path / "Startup"
    assert not autostart.enabled(where)

    path = autostart.enable(where)
    assert autostart.enabled(where)
    assert path.exists() and path.stat().st_size > 0

    autostart.enable(where)                       # 두 번 켜도 하나만 남는다
    assert len(list(where.iterdir())) == 1

    assert autostart.disable(where) is True
    assert not autostart.enabled(where)
    assert list(where.iterdir()) == []
    assert autostart.disable(where) is False      # 이미 꺼져 있으면 False


@pytest.mark.skipif(sys.platform != "win32", reason="바로 가기는 윈도우만")
def test_the_shortcut_really_points_at_the_tray(tmp_path):
    """.lnk 를 되읽어서 확인한다. 파일이 생겼다는 것만으로는 켜진다는 뜻이 아니다."""
    path = autostart.enable(tmp_path / "Startup")
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:L);"
          "$s.TargetPath; $s.Arguments")
    import os
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ, "L": str(path)})
    if r.returncode != 0:
        pytest.skip("이 환경에서는 PowerShell 로 바로 가기를 읽을 수 없다")
    target, args = [x.strip() for x in r.stdout.strip().splitlines()[:2]]
    assert target.lower().endswith(("python.exe", "pythonw.exe")), target
    assert args == "-m epokio.tray", args


@pytest.mark.skipif(sys.platform != "linux", reason=".desktop 은 리눅스만")
def test_the_desktop_entry_is_well_formed(tmp_path):
    path = autostart.enable(tmp_path / "autostart")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("[Desktop Entry]")
    assert "Type=Application" in text and "epokio.tray" in text


# ── epokio setup ─────────────────────────────────────

def test_agent_alive_is_false_when_nothing_listens():
    assert onboard.agent_alive(port=59_999, timeout=0.3) is False


def test_lan_ip_is_an_address_or_nothing():
    ip = onboard.lan_ip()
    if ip is not None:
        parts = ip.split(".")
        assert len(parts) == 4 and all(p.isdigit() for p in parts), ip


def test_setup_binds_to_this_machine_only_unless_you_ask_for_lan(monkeypatch, tmp_path):
    """--lan 없이 0.0.0.0 으로 열면 사용자가 모르는 새 네트워크에 노출된다."""
    seen = {}

    def fake_start(roots, host, port=onboard.PORT, allow_run=False):
        seen["host"], seen["port"] = host, port
        return None

    monkeypatch.setattr(onboard, "start_agent", fake_start)
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: False)
    monkeypatch.setattr(onboard, "wait_for_agent", lambda *a, **k: True)

    onboard.main(["--root", str(tmp_path), "--port", "8798", "--no-browser"])
    assert seen["host"] == "127.0.0.1"

    seen.clear()
    onboard.main(["--root", str(tmp_path), "--port", "8798", "--no-browser", "--lan"])
    assert seen["host"] == "0.0.0.0"


def test_setup_label_is_remembered_for_the_helper(monkeypatch, tmp_path):
    """실습실 노트북 20대가 전부 DESKTOP-XXXX로 보였다. setup에서 준 이름을 트레이가 다시 띄우는 agent도 쓴다."""
    monkeypatch.setattr(onboard, "start_agent", lambda *a, **k: None)
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: False)
    monkeypatch.setattr(onboard, "wait_for_agent", lambda *a, **k: True)
    onboard.main(["--root", str(tmp_path), "--no-browser", "--label", " lab-07 "])
    assert onboard.label_file().read_text(encoding="utf-8") == "lab-07"


def test_setup_does_not_touch_autostart_unless_asked(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(autostart, "enable", lambda *a, **k: called.append(1))
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: True)
    monkeypatch.setattr(onboard, "owner", lambda *a, **k: "mine")          # 내 토큰을 증명한 내 도우미

    onboard.main(["--root", str(tmp_path), "--port", "8798", "--no-browser"])
    assert called == []


def test_setup_does_not_open_a_browser_when_told_not_to(monkeypatch, tmp_path):
    import webbrowser
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: True)
    monkeypatch.setattr(onboard, "owner", lambda *a, **k: "mine")          # 내 토큰을 증명한 내 도우미
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: pytest.fail("브라우저를 열었다"))
    assert onboard.main(["--root", str(tmp_path), "--port", "8798", "--no-browser"]) == 0



def test_setup_remembers_the_folders_you_gave_it(monkeypatch, tmp_path):
    """--root가 이번 도우미에만 넘어가, setup을 --root 없이 다시 돌리면 폴더를 잃었다. 뺀 폴더를 다시 주면 되살린다."""
    from epokio import jsonfile
    from epokio.agent import Agent
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: True)
    monkeypatch.setattr(onboard, "owner", lambda *a, **k: "mine")          # 내 토큰을 증명한 내 도우미
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    jsonfile.write(Agent.REMOVED_FILE, [str(b.resolve())])
    onboard.main(["--root", str(a), "--no-browser"])
    onboard.main(["--root", str(a), "--root", str(b), "--no-browser"])
    assert jsonfile.read(Agent.ROOTS_FILE, []) == [str(a.resolve()), str(b.resolve())]
    assert jsonfile.read(Agent.REMOVED_FILE, []) == []


def test_setup_prints_the_address_that_unlocks_the_page(monkeypatch, tmp_path, capsys):
    """브라우저엔 토큰 실은 주소를 열면서 화면엔 맨 주소를 찍어, 그걸로 연 사람은 학습 탭이 잠겨 있었다."""
    from epokio import auth, port
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: True)
    monkeypatch.setattr(onboard, "owner", lambda *a, **k: "mine")          # 내 토큰을 증명한 내 도우미
    monkeypatch.setattr(port, "verify_agent", lambda *a, **k: True)          # 그 포트에 뜬 것이 내 agent다
    monkeypatch.setattr(onboard, "headless", lambda: False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)   # 터미널에서 돌린 것처럼
    onboard.main(["--root", str(tmp_path), "--port", "8798", "--no-browser"])
    assert "#t=" + auth.token() in capsys.readouterr().out
    monkeypatch.setattr(onboard, "headless", lambda: True)       # SSH 세션: 터미널 기록에 토큰을 남기지 않는다
    onboard.main(["--root", str(tmp_path), "--port", "8798", "--no-browser"])
    assert "#t=" not in capsys.readouterr().out

# ── exe(PyInstaller)로 굳었을 때 ──────────────────────

def test_self_command_uses_the_exe_itself_when_frozen(monkeypatch):
    """굳은 exe 에 `-m epokio.agent` 를 붙이면 파이썬 인자로 안 먹고 그냥 흘러간다."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Epokio\Epokio.exe")
    assert autostart.self_command("agent") == [r"C:\Program Files\Epokio\Epokio.exe", "agent"]
    assert autostart.self_command("tray") == [r"C:\Program Files\Epokio\Epokio.exe", "tray"]
    assert "-m" not in autostart.self_command("agent")


def test_self_command_uses_python_dash_m_when_not_frozen(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    cmd = autostart.self_command("agent")
    assert cmd[1:] == ["-m", "epokio.agent"]


def test_child_env_drops_the_pyinstaller_temp_dir(monkeypatch):
    """자식이 부모의 임시 압축 해제 폴더를 물려받으면, 부모가 끝날 때 그 폴더가 사라진다.

    실측: 그 상태의 agent 는 /health(코드)는 200인데 /(번들된 index.html)에서 연결이 끊겼다.
    """
    monkeypatch.setenv("_MEIPASS2", r"C:\Temp\_MEI12345")
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", r"C:\Temp\_MEI12345")
    monkeypatch.setenv("PATH", "keep-me")
    env = autostart.child_env()
    assert "_MEIPASS2" not in env
    assert "_PYI_APPLICATION_HOME_DIR" not in env
    assert env["PATH"] == "keep-me"          # 나머지 환경은 그대로 물려준다


def test_the_helper_is_detached_so_the_terminal_comes_back(monkeypatch, tmp_path):
    """DETACHED_PROCESS 가 빠지면 도우미가 부모 콘솔을 붙잡아 `epokio setup` 이 안 끝난다."""
    if sys.platform != "win32":
        pytest.skip("프로세스 분리 플래그는 윈도우만")
    seen = {}

    class FakePopen:
        def __init__(self, cmd, **kw):
            seen.update(kw)

    monkeypatch.setattr(onboard.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: False)
    onboard.start_agent([tmp_path], "127.0.0.1", 8798)
    assert seen["creationflags"] & onboard.subprocess.DETACHED_PROCESS
    assert "_MEIPASS2" not in seen["env"]


def test_a_linux_server_without_a_display_is_headless(monkeypatch):
    """★SSH_CONNECTION만 봐서 sudo·로컬 콘솔의 서버에서는 브라우저를 띄우려 했고 트레이를 권했다."""
    monkeypatch.setattr(onboard.os, "name", "posix")
    monkeypatch.setattr(onboard.sys, "platform", "linux")
    for k in ("DISPLAY", "WAYLAND_DISPLAY", "SSH_CONNECTION"):
        monkeypatch.delenv(k, raising=False)
    assert onboard.headless()
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert not onboard.headless()


def test_headless_autostart_is_a_systemd_service(tmp_path):
    """화면 없는 서버에 트레이 바로 가기를 만들고 '로그인 때 뜬다'고 했지만 영영 안 떴다."""
    unit = onboard.systemd_unit([tmp_path / "runs"], "127.0.0.1", 8787)
    assert "-m epokio agent --port 8787 --host 127.0.0.1" in unit
    tricky = onboard.systemd_unit(["/data/my runs/exp 50% $HOME"], "127.0.0.1", 8787)
    assert "\"/data/my runs/exp 50%% $$HOME\"" in tricky          # ★공백·%·$ 경로에서 서비스가 안 떴다
    assert "Restart=on-failure" in unit and "WantedBy=default.target" in unit


def test_desktop_entry_quotes_paths_with_spaces():
    """★빈칸이 있는 venv 경로가 Exec에서 둘로 갈라져 트레이가 안 떴다"""
    assert autostart._desktop_quote("/home/lab user/my venv/bin/python") == '"/home/lab user/my venv/bin/python"'
    assert autostart._desktop_quote("-m") == "-m"
    assert autostart._desktop_quote('/x/a"b$c') == r'"/x/a\"b\$c"'


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX 권한")
def test_the_settings_folder_and_files_are_private(tmp_path):
    """★먼저 생긴 ~/.epokio가 0755로 남아 webhooks.json(비밀 주소)을 다른 사용자가 읽을 수 있었다"""
    import os
    from epokio import jsonfile
    d = tmp_path / ".epokio"
    d.mkdir(mode=0o755)
    os.chmod(d, 0o755)
    jsonfile.write(d / "webhooks.json", {"urls": ["https://hooks.slack.com/secret"]})
    assert d.stat().st_mode & 0o077 == 0 and (d / "webhooks.json").stat().st_mode & 0o077 == 0


def test_setup_restarts_an_older_helper(monkeypatch, tmp_path, capsys):
    """★pip으로 올려도 '이미 돌고 있다'고만 해서 옛 도우미가 계속 돌았다"""
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(onboard, "headless", lambda: False)
    monkeypatch.setattr(onboard, "find_roots", lambda: [])
    alive = {"v": True}
    monkeypatch.setattr(onboard, "agent_health", lambda *a, **k: {"epokio": "0.2.0"} if alive["v"] else None)
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: alive["v"])
    monkeypatch.setattr(onboard, "owner", lambda *a, **k: "mine" if alive["v"] else None)
    stopped, started = [], []
    monkeypatch.setattr(onboard, "stop_agent", lambda *a, **k: (stopped.append(1), alive.update(v=False)) and True)
    monkeypatch.setattr(onboard, "start_agent", lambda *a, **k: started.append(1))
    monkeypatch.setattr(onboard, "wait_for_agent", lambda *a, **k: True)
    assert onboard.main(["--no-browser"]) == 0
    assert stopped and started and "An older helper (0.2.0)" in capsys.readouterr().out


def test_doctor_prints_a_report_without_the_token(monkeypatch, tmp_path, capsys):
    import json
    from pathlib import Path
    from epokio import auth, envs
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / ".epokio" / "token")
    tok = auth.token()
    monkeypatch.setattr(onboard, "agent_health", lambda *a, **k: None)
    monkeypatch.setattr(envs, "list_envs", lambda: [])
    assert onboard.doctor(["--json"]) == 0
    out = capsys.readouterr().out
    d = json.loads(out)
    assert d["helper"]["running"] is False and d["token_file"] is True and tok not in out


def test_setup_root_reaches_a_running_helper(monkeypatch, tmp_path, capsys):
    """★처음엔 폴더 없이 setup, 그다음 setup --root: roots.json에만 적고 도는 도우미는 몰라 목록이 비어 있었다"""
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    sent = []
    monkeypatch.setattr(onboard, "outdated", lambda *a, **k: None)
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: True)
    monkeypatch.setattr(onboard, "owner", lambda *a, **k: "mine")          # 내 토큰을 증명한 내 도우미
    monkeypatch.setattr(onboard, "add_roots_live", lambda port, roots: sent.extend(roots) or True)
    monkeypatch.setattr(onboard, "headless", lambda: True)
    onboard.main(["--root", str(runs), "--no-browser"])
    assert sent == [runs.resolve()] and "Added the folder" in capsys.readouterr().out


def test_doctor_finds_the_helper_on_its_real_port(monkeypatch, tmp_path):
    """★8787로 고정해, 다른 포트로 뜬 도우미를 '안 돈다'고 오진했다"""
    from pathlib import Path
    from epokio import doctor, envs, port
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(port, "read_record", lambda: {"port": 8799, "pid": 1})
    monkeypatch.setattr(onboard, "agent_alive", lambda p, *a, **k: p == 8799)
    asked = []
    monkeypatch.setattr(onboard, "agent_health", lambda p, *a, **k: asked.append(p))
    monkeypatch.setattr(envs, "list_envs", lambda: [])
    doctor.doctor(["--json"])
    assert asked == [8799]


def test_setup_into_a_log_or_notebook_does_not_print_the_token(monkeypatch, tmp_path, capsys):
    """★노트북 셀·로그 파일로 받은 setup 출력에 #t=토큰 주소와 토큰이 그대로 남았다"""
    from epokio import auth
    monkeypatch.setattr(onboard, "start_agent", lambda *a, **k: None)
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: False)
    monkeypatch.setattr(onboard, "wait_for_agent", lambda *a, **k: True)
    monkeypatch.setattr(onboard, "headless", lambda: False)
    onboard.main(["--root", str(tmp_path), "--port", "8798", "--no-browser", "--lan"])
    out = capsys.readouterr().out                       # capsys: 터미널이 아니다
    assert auth.token() not in out and "#t=" not in out and "--show-token" in out


def test_doctor_log_tail_has_no_middle_dot(monkeypatch, tmp_path, capsys):
    """한국어 윈도우에서 agent.log 구분자(가운뎃점)가 doctor 출력에 깨져 보였다"""
    from pathlib import Path
    from epokio import envs, doctor
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".epokio").mkdir()
    (tmp_path / ".epokio" / "agent.log").write_text("x INFO start 0.7.0 · pc · 127.0.0.1:9000\n", encoding="utf-8")
    monkeypatch.setattr(onboard, "agent_health", lambda *a, **k: None)
    monkeypatch.setattr(envs, "list_envs", lambda: [])
    assert onboard.doctor([]) == 0
    out = capsys.readouterr().out
    assert "start 0.7.0 | pc | 127.0.0.1:9000" in out and "·" not in out
    assert doctor._console_safe("a·éb", "ascii") == "a??b"


def test_setup_under_sudo_says_it_is_setting_up_root(monkeypatch):
    """★`sudo epokio setup`은 아무 말 없이 root의 홈에 서비스·토큰을 썼다"""
    monkeypatch.setattr(onboard.os, "name", "posix")
    monkeypatch.setattr(onboard.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setenv("SUDO_USER", "lab")
    assert "for root, not lab" in onboard.sudo_warning()
    monkeypatch.delenv("SUDO_USER")
    assert onboard.sudo_warning() == ""


def _ssh_linux(monkeypatch, tmp_path, others):
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / "runs").mkdir(exist_ok=True)
    monkeypatch.setattr(onboard, "outdated", lambda *a, **k: None)
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: True)
    monkeypatch.setattr(onboard, "owner", lambda *a, **k: "mine")
    monkeypatch.setattr(onboard, "add_roots_live", lambda port, roots: True)
    monkeypatch.setattr(onboard, "headless", lambda: True)
    monkeypatch.setattr(onboard, "other_logins", lambda: others)
    monkeypatch.setattr(onboard.sys, "platform", "linux")
    return ["--root", str(tmp_path / "runs"), "--no-autostart"]


def test_setup_over_ssh_on_a_shared_linux_server_locks_reads_by_default(monkeypatch, tmp_path, capsys):
    """★공용 서버에서 다른 계정이 127.0.0.1로 내 학습을 읽는다는 것을 알리기만 해서 대부분 열려 있었다.
    터미널이 아니면 묻지 않고 잠그고 푸는 법을 찍는다. 다른 계정이 있는지 모를 때(None)도 잠근다"""
    from epokio import config
    for others in (True, None):
        config.update({"reads_token": "auto"})
        onboard.main(_ssh_linux(monkeypatch, tmp_path, others))
        out = capsys.readouterr().out
        assert config.load()["reads_token"] == "always"
        assert "config reads_token auto" in out and "agent --show-token" in out
    onboard.main(_ssh_linux(monkeypatch, tmp_path, True))        # 이미 잠겼으면 다시 말하지 않는다
    assert "reads_token" not in capsys.readouterr().out


def test_setup_asks_before_locking_reads_in_a_terminal(monkeypatch, tmp_path, capsys):
    from epokio import config
    argv = _ssh_linux(monkeypatch, tmp_path, True)
    monkeypatch.setattr(onboard.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(onboard.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(onboard.auth, "page_url", lambda u: u)
    asked = []
    monkeypatch.setattr("builtins.input", lambda q: asked.append(q) or "n")
    onboard.main(argv)
    assert any("[Y/n]" in q and "token" in q for q in asked)
    assert config.load()["reads_token"] == "auto" and "config reads_token always" in capsys.readouterr().out
    monkeypatch.setattr("builtins.input", lambda q: "")             # 그냥 엔터 = 예
    onboard.main(argv)
    assert config.load()["reads_token"] == "always"
    assert "config reads_token auto" not in capsys.readouterr().out   # 직접 고른 사람에게 푸는 법은 안 찍는다


def test_setup_leaves_reads_open_when_told_or_alone_or_never(monkeypatch, tmp_path, capsys):
    """--no-lock-reads, 다른 계정이 없는 기계, 사용자가 never로 둔 기계, 화면 있는 데스크톱은 그대로"""
    from epokio import config
    argv = _ssh_linux(monkeypatch, tmp_path, True)
    onboard.main(argv + ["--no-lock-reads"])
    assert config.load()["reads_token"] == "auto" and "config reads_token always" in capsys.readouterr().out
    monkeypatch.setattr(onboard, "other_logins", lambda: False)
    onboard.main(argv)
    assert config.load()["reads_token"] == "auto" and "reads_token" not in capsys.readouterr().out
    monkeypatch.setattr(onboard, "other_logins", lambda: True)
    config.update({"reads_token": "never"})
    onboard.main(argv)
    assert config.load()["reads_token"] == "never"
    config.update({"reads_token": "auto"})
    monkeypatch.setattr(onboard, "headless", lambda: False)
    monkeypatch.setattr("webbrowser.open", lambda *a, **k: True)
    onboard.main(argv + ["--no-browser"])
    assert config.load()["reads_token"] == "auto"


def test_other_logins_sees_real_accounts_only(monkeypatch, tmp_path):
    """시스템 계정(uid<1000, nologin)과 나 자신은 세지 않는다. pwd가 없으면(윈도우) 모른다"""
    import sys
    import types
    from epokio import onboard_parts
    U = lambda uid, sh: types.SimpleNamespace(pw_uid=uid, pw_shell=sh)        # noqa: E731
    fake = types.SimpleNamespace(getpwall=lambda: [U(0, "/bin/bash"), U(33, "/usr/sbin/nologin"), U(1000, "/bin/bash"),
                                                   U(65534, "/bin/sh"), U(1001, "/usr/sbin/nologin")])
    monkeypatch.setitem(sys.modules, "pwd", fake)
    monkeypatch.setattr(onboard_parts.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(onboard_parts, "Path", lambda p: tmp_path / "home" if p == "/home" else __import__("pathlib").Path(p))
    (tmp_path / "home").mkdir()
    assert onboard_parts.other_logins() is False
    fake.getpwall = lambda: [U(1000, "/bin/bash"), U(1002, "/bin/zsh")]
    assert onboard_parts.other_logins() is True
    monkeypatch.setitem(sys.modules, "pwd", None)                     # import pwd -> ImportError
    assert onboard_parts.other_logins() is None
