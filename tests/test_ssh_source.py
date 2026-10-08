"""SSH 가벼운 모드: 가짜 ssh(이 기계에서 바로 실행)로 스캔 스크립트 → 비춤 → 기존 scan이 읽는지. 진짜 원격 서버는 여기서 안 본다"""
import os
import sys
import time
from types import SimpleNamespace

import pytest

from epokio import scan, ssh_source

# 가짜 ssh 는 파이썬 스크립트다(셸 스크립트는 윈도우에서 실행 파일이 아니다: WinError 193).
# -o 옵션과 호스트를 건너뛰고, 원격 셸처럼 나머지를 shlex 로 풀어 이 기계의 파이썬으로 돌린다
FAKE_SSH = """import shlex, subprocess, sys
a = sys.argv[1:]
while a and a[0] == "-o":
    a = a[2:]
words = shlex.split(" ".join(a[1:]))
assert words[:2] == ["python3", "-"], words
sys.exit(subprocess.run([sys.executable, "-"] + words[2:]).returncode)
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    fake = tmp_path / "fakessh.py"
    fake.write_text(FAKE_SSH)
    home = tmp_path / "server_home"
    run = home / "proj" / "runs" / "detect" / "train3"
    run.mkdir(parents=True)
    (run / "results.csv").write_text("epoch,metrics/mAP50-95(B),train/box_loss\n1,0.1,1.2\n2,0.2,1.0\n")
    (run / "args.yaml").write_text("epochs: 10\n")
    (home / "proj" / "datasets" / "junk").mkdir(parents=True)                      # 건너뛸 곳
    (home / "proj" / "datasets" / "junk" / "results.csv").write_text("epoch\n1\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))       # 윈도우의 expanduser("~")는 HOME 이 아니라 이것을 본다
    monkeypatch.setattr(ssh_source, "MIRROR", tmp_path / "mirror")
    monkeypatch.setattr(ssh_source, "CONFIG", tmp_path / "hosts.json")
    return [sys.executable, str(fake)], run


def test_scan_mirror_and_read(env):
    fake, run = env
    got = ssh_source.run_remote("gpu-box", {"auto": True}, ssh=fake)
    assert [r["path"] for r in got["runs"]] == [str(run)]                           # datasets 아래는 안 본다
    assert ssh_source.apply("gpu-box", got) == 1
    runs = scan.scan(ssh_source.mirror_dir("gpu-box"))
    assert len(runs) == 1 and runs[0].epoch == 2 and runs[0].total == 10
    assert ssh_source.host_of(str(runs[0].path)) == "gpu-box"
    assert ssh_source.remote_path(str(runs[0].path)) == str(run)


def test_clock_skew_is_corrected(env):
    fake, run = env
    got = ssh_source.run_remote("gpu-box", {}, ssh=fake)
    got["now"] -= 3600                                    # 서버 시계가 한 시간 늦다
    ssh_source.apply("gpu-box", got)
    f = ssh_source.local_dir("gpu-box", str(run)) / "results.csv"
    assert abs(f.stat().st_mtime - (os.stat(run / "results.csv").st_mtime + 3600)) < 5


def test_removed_runs_disappear(env):
    fake, run = env
    ssh_source.apply("gpu-box", ssh_source.run_remote("gpu-box", {}, ssh=fake))
    ssh_source.apply("gpu-box", {"now": time.time(), "runs": []})
    assert scan.scan(ssh_source.mirror_dir("gpu-box")) == []


def test_manual_path_without_auto(env, tmp_path):
    fake, run = env
    other = tmp_path / "elsewhere" / "exp1"
    other.mkdir(parents=True)
    (other / "results.csv").write_text("epoch,metrics/mAP50-95(B)\n1,0.3\n")
    got = ssh_source.run_remote("h", {"auto": False, "paths": [str(tmp_path / "elsewhere")]}, ssh=fake)
    assert [r["path"] for r in got["runs"]] == [str(other)]


def test_rejects_option_like_hosts_and_bad_paths(env):
    with pytest.raises(ValueError):
        ssh_source.run_remote("-oProxyCommand=evil", {})
    n = ssh_source.apply("h", {"now": time.time(), "runs": [{"path": "/a/../../etc", "files": {"x": [0, "y"]}},
                                                           {"path": "/ok", "files": {"../../z": [0, "y"]}}]})
    assert n == 1 and not (ssh_source.MIRROR.parent / "z").exists()


def test_failure_message_is_readable(env, tmp_path):
    bad = tmp_path / "badssh.py"
    bad.write_text("import sys\nsys.stderr.write('Permission denied (publickey).\\n')\nsys.exit(255)\n")
    with pytest.raises(ValueError, match="Permission denied"):
        ssh_source.run_remote("h", {}, ssh=[sys.executable, str(bad)])


def test_config_hosts_skip_wildcards(tmp_path):
    c = tmp_path / "config"
    c.write_text("Host *\n  User x\nHost gpu1 gpu2\n  HostName 1.2.3.4\nHost !bad lab-*\n")
    assert ssh_source.config_hosts(c) == ["gpu1", "gpu2"]


def test_api_add_checks_before_saving(env):
    from types import SimpleNamespace
    from epokio.api import ssh as api
    fake, run = env
    agent = SimpleNamespace(ssh=ssh_source.Poller(ssh=fake), _runs_cache=1)
    code, got = api.post(agent, "/ssh/add", {"host": "gpu-box", "auto": True})
    assert code == 200 and got["status"]["runs"] == 1 and [h["host"] for h in ssh_source.load()] == ["gpu-box"]
    assert agent.ssh.roots() == [ssh_source.mirror_dir("gpu-box")]
    agent.ssh = ssh_source.Poller(ssh="/nonexistent/ssh")
    code, got = api.post(agent, "/ssh/add", {"host": "other"})
    assert code == 400 and [h["host"] for h in ssh_source.load()] == ["gpu-box"]      # 안 되는 서버는 저장하지 않는다
    assert api.post(agent, "/ssh/add", {"host": "-oProxyCommand=x"})[0] == 400
    api.post(agent, "/ssh/remove", {"host": "gpu-box"})
    assert ssh_source.load() == [] and not ssh_source.mirror_dir("gpu-box").exists()


def test_truncated_scan_keeps_the_mirror(env):
    """다 못 본 스캔으로 미러를 지우면 멀쩡한 학습이 화면에서 사라진다"""
    fake, run = env
    ssh_source.apply("gpu-box", ssh_source.run_remote("gpu-box", {}, ssh=fake))
    ssh_source.apply("gpu-box", {"now": time.time(), "runs": [], "truncated": True})
    assert scan.scan(ssh_source.mirror_dir("gpu-box")) != []            # 그대로 둔다
    ssh_source.apply("gpu-box", {"now": time.time(), "runs": []})
    assert scan.scan(ssh_source.mirror_dir("gpu-box")) == []            # 온전한 스캔이면 지운다


def test_failed_host_is_polled_less_often(env):
    fake, _ = env
    p = ssh_source.Poller(ssh="/nonexistent/ssh")
    assert p.due("h", time.time())                                       # 처음엔 본다
    p.poll_once({"host": "h"})
    assert not p.due("h", time.time())                                   # 실패 직후엔 쉰다
    assert p.due("h", time.time() + ssh_source.EVERY * ssh_source.MAX_BACKOFF + 1)


def test_windows_drops_connection_sharing(monkeypatch, tmp_path):
    """윈도우판 OpenSSH 는 ControlMaster 를 못 쓴다: 윈도우에서는 옵션을 빼고, 상태에 이유를 남긴다"""
    monkeypatch.setattr(ssh_source, "CONTROL_DIR", tmp_path / "ctl")
    monkeypatch.setattr(ssh_source, "MIRROR", tmp_path / "mirror")
    # ★윈도우가 아닌 쪽도 OS 를 못 박는다. 실제 OS 를 따르면 진짜 윈도우 CI 에서 기능이 옳게 옵션을 뺐는데 실패했다
    monkeypatch.setattr(sys, "platform", "linux")
    assert "ControlMaster=auto" in ssh_source._ssh_cmd("ssh", "h", "{}")
    monkeypatch.setattr(sys, "platform", "win32")
    win = ssh_source._ssh_cmd("ssh", "h", "{}")
    assert not any(a.startswith("Control") for a in win) and win[-4:] == ["h", "python3", "-", "'{}'"]
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        return SimpleNamespace(returncode=0, stdout=b'{"now": 1, "runs": []}\r\n', stderr=b"")
    monkeypatch.setattr(ssh_source.subprocess, "run", fake_run)
    st = ssh_source.Poller().poll_once({"host": "h"})
    assert st["ok"] and "ControlMaster" in st["note"]
    assert isinstance(seen["input"], bytes) and b"\r" not in seen["input"]      # 스크립트 개행을 바꾸지 않고 넘긴다


def test_windows_names_and_paths_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr(ssh_source, "MIRROR", tmp_path / "mirror")
    monkeypatch.setattr(sys, "platform", "win32")
    for remote in ["/home/u/runs/exp:1?", "C:\\Users\\u\\runs\\train3", "/home/u/runs/end."]:
        d = ssh_source.local_dir("h", remote)
        assert not any(c in d.name for c in '<>:"|?*') and not d.name.endswith(".")
        assert ssh_source.remote_path(os.sep.join([str(ssh_source.MIRROR), "h", d.parent.name, d.name])) == remote
    for bad in ["C:x", "..\\x", "a/../../x", "/abs", "\\\\srv\\x"]:
        assert not ssh_source._safe_rel(bad)
    assert ssh_source._safe_rel("checkpoint-5/trainer_state.json")


def test_crlf_files_are_mirrored_as_is(env):
    """윈도우 텍스트 모드는 LF 를 CRLF 로 바꾼다: 서버 내용을 바이트 그대로 쓰는지"""
    ssh_source.apply("h", {"now": time.time(), "runs": [{"path": "/r/exp", "files": {"results.csv": [0, "a\r\nb\n"]}}]})
    assert (ssh_source.local_dir("h", "/r/exp") / "results.csv").read_bytes() == b"a\r\nb\n"


# ── 늘어나는 파일은 뒤만, 너무 큰 파일은 알린다 ──
@pytest.fixture
def tail(env, monkeypatch):
    for k in ("_HAVE", "_FULL", "_SKIPPED", "_TAIL"):
        monkeypatch.setattr(ssh_source, k, {})
    fake, run = env

    def read():
        got = ssh_source.run_remote("gpu", {"auto": True}, ssh=fake, have=ssh_source.have_for("gpu"))
        ssh_source.apply("gpu", got)
        return {n: p for r in got["runs"] for n, p in r["files"].items()}
    return read, run


def bump(p, extra: bytes):
    with open(p, "ab") as f:
        f.write(extra)
    t = os.stat(p).st_mtime + 5                                         # 시각이 꼭 바뀌게
    os.utime(p, (t, t))


def test_growing_csv_and_binary_come_as_tails(tail):
    read, run = tail
    ev = run / "events.out.tfevents.1.host"
    ev.write_bytes(bytes(range(256)) * 40)
    read()
    size = os.stat(run / "results.csv").st_size
    bump(run / "results.csv", b"3,0.3,0.9\n")
    bump(ev, b"\x00\xff" * 100)
    got = read()
    assert got["results.csv"][1:] == ["3,0.3,0.9\n", "append", size]
    assert got["events.out.tfevents.1.host"][2] == "append_b64"
    d = ssh_source.local_dir("gpu", str(run))
    for n in ("results.csv", ev.name):
        assert (d / n).read_bytes() == (run / n).read_bytes()          # 바이트 그대로


def test_rewritten_file_falls_back_to_full(tail):
    read, run = tail
    read()
    (run / "results.csv").write_text("epoch,metrics/mAP50-95(B),train/box_loss\n1,0.5,1.2\n2,0.6,1.0\n3,0.7,0.8\n")
    bump(run / "results.csv", b"")
    got = read()
    assert len(got["results.csv"]) == 2                                 # 앞부분이 바뀌었다: 통째로
    assert (ssh_source.local_dir("gpu", str(run)) / "results.csv").read_bytes() == (run / "results.csv").read_bytes()


def test_local_mirror_out_of_step_resends_full(tail):
    read, run = tail
    read()
    f = ssh_source.local_dir("gpu", str(run)) / "results.csv"
    f.unlink()
    bump(run / "results.csv", b"3,0.3,0.9\n")
    assert len(read()["results.csv"]) == 2                              # 비춤을 지우면 통째로
    # 서버가 이어 보낸 조각이 이 Mac 크기와 안 맞으면 붙이지 않고, 다음번에 통째로 받는다
    pair = [os.stat(run / "results.csv").st_mtime + 1, "x\n", "append", 3]
    ssh_source.apply("gpu", {"now": time.time(), "runs": [{"path": str(run), "files": {"results.csv": pair}}]})
    assert f.read_bytes() == (run / "results.csv").read_bytes()
    assert "results.csv" not in ssh_source.have_for("gpu").get(str(run), {})
    bump(run / "results.csv", b"4,0.4,0.8\n")
    assert len(read()["results.csv"]) == 2 and f.read_bytes() == (run / "results.csv").read_bytes()


def test_oversized_file_is_reported(tail, monkeypatch):
    read, run = tail
    monkeypatch.setattr(ssh_source, "REMOTE", ssh_source.REMOTE.replace("4000000", "1000"))
    (run / "args.yaml").write_bytes(b"x: 1\n" * 400)                   # write_text는 윈도우에서 CRLF라 2400B
    got = read()
    assert got["args.yaml"][2:] == ["too_large", 2000]
    assert ssh_source.skipped("gpu") == [{"path": str(run), "name": "args.yaml", "size": 2000}]
    # 이어 받기면 한도는 붙은 조각에만: 1KB 한도로도 오래 도는 학습의 로그를 계속 받는다
    for _ in range(5):
        bump(run / "results.csv", b"9,0.9,0.1\n" * 50)
        assert read()["results.csv"][2] == "append"
    assert os.stat(run / "results.csv").st_size > 2000
    monkeypatch.setattr(ssh_source, "run_remote", lambda *a, **k: {"now": time.time(), "runs": [
        {"path": str(run), "files": {"args.yaml": [1, None, "too_large", 2000]}}]})
    assert ssh_source.Poller(ssh="ssh").poll_once({"host": "gpu"})["skipped"][0]["name"] == "args.yaml"


def test_oversized_growing_log_keeps_the_tail(tail, monkeypatch):
    read, run = tail
    monkeypatch.setattr(ssh_source, "REMOTE", ssh_source.REMOTE.replace("4000000", "1000").replace("20000000", "1000"))
    head = b"epoch,metrics/mAP50-95(B),train/box_loss\n"
    (run / "results.csv").write_bytes(head + b"".join(b"%d,0.5,1.0\n" % i for i in range(300)))
    (run / "args.yaml").write_bytes(b"x: 1\n" * 400)                    # 설정은 늘지 않는다: 그대로 건너뜀
    (run / "events.out.tfevents.1.host").write_bytes(b"\x00" * 2000)   # 바이너리는 레코드를 다시 못 맞춘다
    got = read()
    assert got["results.csv"][2] == "tail"
    assert got["args.yaml"][2] == "too_large" and got["events.out.tfevents.1.host"][2] == "too_large"
    f = ssh_source.local_dir("gpu", str(run)) / "results.csv"
    rest = f.read_bytes()[len(head):]
    assert f.read_bytes().startswith(head) and b"\n" + rest in (run / "results.csv").read_bytes()   # 줄 경계부터
    assert (run / "results.csv").read_bytes().endswith(rest) and len(rest) <= 1000
    sk = {x["name"]: x for x in ssh_source.skipped("gpu")}
    assert sk["results.csv"]["kept"] == len(rest) and sk["results.csv"]["size"] == os.stat(run / "results.csv").st_size
    assert "kept" not in sk["args.yaml"] and "kept" not in sk["events.out.tfevents.1.host"]
    for i in range(3):                                                   # 그 뒤로는 붙은 것만 받아 이어 간다
        bump(run / "results.csv", b"%d,0.9,0.1\n" % (900 + i))
        assert read()["results.csv"][2] == "append"
    assert f.read_bytes() == head + rest + b"900,0.9,0.1\n901,0.9,0.1\n902,0.9,0.1\n"
    assert {x["name"]: x for x in ssh_source.skipped("gpu")}["results.csv"]["size"] == os.stat(run / "results.csv").st_size
