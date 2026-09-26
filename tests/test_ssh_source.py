"""SSH 가벼운 모드: 가짜 ssh(이 기계에서 바로 실행)로 스캔 스크립트 → 비춤 → 기존 scan이 읽는지. 진짜 원격 서버는 여기서 안 본다"""
import os
import stat
import time

import pytest

from epokio import scan, ssh_source


@pytest.fixture
def env(tmp_path, monkeypatch):
    fake = tmp_path / "fakessh"
    fake.write_text('#!/bin/sh\nwhile [ "$1" = "-o" ]; do shift 2; done\nshift\nexec sh -c "$*"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    home = tmp_path / "server_home"
    run = home / "proj" / "runs" / "detect" / "train3"
    run.mkdir(parents=True)
    (run / "results.csv").write_text("epoch,metrics/mAP50-95(B),train/box_loss\n1,0.1,1.2\n2,0.2,1.0\n")
    (run / "args.yaml").write_text("epochs: 10\n")
    (home / "proj" / "datasets" / "junk").mkdir(parents=True)                      # 건너뛸 곳
    (home / "proj" / "datasets" / "junk" / "results.csv").write_text("epoch\n1\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(ssh_source, "MIRROR", tmp_path / "mirror")
    monkeypatch.setattr(ssh_source, "CONFIG", tmp_path / "hosts.json")
    return str(fake), run


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
    bad = tmp_path / "badssh"
    bad.write_text("#!/bin/sh\necho 'Permission denied (publickey).' >&2\nexit 255\n")
    bad.chmod(bad.stat().st_mode | stat.S_IEXEC)
    with pytest.raises(ValueError, match="Permission denied"):
        ssh_source.run_remote("h", {}, ssh=str(bad))


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
