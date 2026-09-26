"""--parent-pid: 부모가 끝나면 agent가 스스로 끝나는가."""
import os
import subprocess
import sys
import threading
import time

import pytest

from epokio import parentwatch

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX 경로만 여기서 본다")


def test_alive_self_and_dead_pid():
    assert parentwatch.alive(os.getpid())
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    assert not parentwatch.alive(p.pid)
    assert not parentwatch.alive(0)


def test_watch_fires_when_fake_parent_dies():
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    gone = threading.Event()
    parentwatch.watch(parent.pid, on_gone=gone.set, interval=0.05)
    time.sleep(0.2)
    assert not gone.is_set()                 # 살아 있는 동안은 가만히
    parent.kill(); parent.wait()
    assert gone.wait(2)


def test_child_process_exits_after_parent(tmp_path):
    """진짜 흐름: 가짜 부모가 자식(감시자)을 띄우고 죽으면 자식도 끝난다."""
    pidfile = tmp_path / "child.pid"
    child_code = ("import os, sys, time; from epokio import parentwatch; "
                  f"open({str(pidfile)!r}, 'w').write(str(os.getpid())); "
                  "parentwatch.watch(os.getppid(), interval=0.05); time.sleep(30)")
    parent_code = ("import subprocess, sys, time; "
                   f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); time.sleep(0.5)")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    subprocess.run([sys.executable, "-c", parent_code], env=env, timeout=10)
    deadline = time.time() + 5
    while not pidfile.exists() and time.time() < deadline:
        time.sleep(0.05)
    child = int(pidfile.read_text())
    while parentwatch.alive(child) and time.time() < deadline:
        time.sleep(0.05)
    assert not parentwatch.alive(child)
