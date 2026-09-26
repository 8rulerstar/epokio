"""윈도우 호환: sys.platform을 모킹해 윈도우 분기를 맥·리눅스에서 시험한다."""
import json
import subprocess
import sys
from types import SimpleNamespace

from epokio import envs, jobs, sysinfo, tui, winstats


def test_kill_tree_uses_taskkill_on_windows(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(jobs.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or SimpleNamespace(returncode=0))
    proc = SimpleNamespace(pid=4242, terminate=lambda: calls.append("terminate"))
    jobs.kill_tree(proc)
    assert calls == [["taskkill", "/PID", "4242", "/T", "/F"]]


def test_kill_tree_falls_back_to_terminate_when_taskkill_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(jobs.subprocess, "run", lambda cmd, **kw: SimpleNamespace(returncode=128))
    jobs.kill_tree(SimpleNamespace(pid=1, terminate=lambda: calls.append("terminate")))
    assert calls == ["terminate"]


def test_kill_tree_posix_uses_process_group(monkeypatch):
    got = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(jobs.os, "getpgid", lambda pid: 77, raising=False)
    monkeypatch.setattr(jobs.os, "killpg", lambda g, s: got.append((g, s)), raising=False)
    jobs.kill_tree(SimpleNamespace(pid=5, terminate=lambda: got.append("terminate")))
    assert got == [(77, jobs.signal.SIGTERM)]


def test_queue_state_file_is_utf8(tmp_path, monkeypatch):
    q = jobs.Queue.__new__(jobs.Queue)
    q.path, q.jobs = tmp_path / "jobs.json", []
    j = jobs.Job(id="a", kind="script", name="교통표지판_😀", python="py", params={}, state="done")
    q.jobs = [j]
    q._save()
    raw = q.path.read_bytes()
    assert "교통표지판_😀".encode("utf-8") in raw        # cp949로는 😀를 못 쓴다
    q.jobs = []
    q._load()
    assert q.jobs[0].name == "교통표지판_😀"


def test_win_cpu_from_times():
    assert winstats.cpu_from_times(None, (1, 2, 3)) is None
    # idle 60, kernel 80(idle 포함), user 20 → 사용 = 100-60 = 40%
    assert winstats.cpu_from_times((0, 0, 0), (60, 80, 20)) == 40.0
    assert winstats.cpu_from_times((5, 5, 5), (5, 5, 5)) is None


def test_nvidia_smi_nvsmi_fallback_on_windows(monkeypatch, tmp_path):
    exe = tmp_path / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sysinfo.shutil, "which", lambda n: None)
    monkeypatch.setenv("ProgramW6432", str(tmp_path))
    assert sysinfo.nvidia_smi_path() == str(exe)
    monkeypatch.setattr(sys, "platform", "linux")
    assert sysinfo.nvidia_smi_path() is None


def test_env_candidates_find_windows_layouts(monkeypatch, tmp_path):
    (tmp_path / "anaconda3" / "envs" / "yolo").mkdir(parents=True)
    (tmp_path / "anaconda3" / "envs" / "yolo" / "python.exe").write_text("")
    (tmp_path / "anaconda3" / "python.exe").write_text("")
    v = tmp_path / "Projects" / "proj" / ".venv" / "Scripts"
    v.mkdir(parents=True)
    (v / "python.exe").write_text("")
    monkeypatch.setattr(envs, "HOME", tmp_path)
    got = envs.candidates()
    for p in ("anaconda3/envs/yolo/python.exe", "anaconda3/python.exe", "proj/.venv/Scripts/python.exe"):
        assert any(g.replace("\\", "/").endswith(p) for g in got), p


def test_watch_without_curses_prints_once(monkeypatch, capsys):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **kw):
        if name == "curses":
            raise ImportError("no curses")
        return real(name, *a, **kw)
    printed = []
    monkeypatch.setattr(builtins, "__import__", fake)
    monkeypatch.setattr(tui, "print_once", lambda feed: printed.append(feed))
    monkeypatch.setattr(tui.sys.stdout, "isatty", lambda: True, raising=False)
    tui.main(["--root", "."])
    assert printed and "windows-curses" in capsys.readouterr().err
