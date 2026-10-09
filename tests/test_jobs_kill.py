"""취소가 손자 프로세스까지 끄는가. 진짜 프로세스를 띄워서 잰다.

학습을 취소했는데 dataloader 워커가 남으면 GPU 메모리를 계속 쥐고, 다음 학습이 메모리 부족으로
죽는다. 윈도우에는 프로세스 그룹이 없어서 terminate()가 직접 자식 하나만 죽인다(2026-09-23 실측).
"""
import subprocess
import sys
import time

import pytest

from epokio.jobs import kill_tree

# 손자: 자기 pid를 파일에 적고 기다린다. 부모: 손자를 띄우고 기다린다.
GRANDCHILD = "import os,sys,time\nopen(sys.argv[1],'w').write(str(os.getpid()))\ntime.sleep(60)\n"
PARENT = ("import subprocess,sys,time\n"
          f"subprocess.Popen([sys.executable,'-c',{GRANDCHILD!r},sys.argv[1]])\n"
          "time.sleep(60)\n")


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                             capture_output=True, text=True, errors="replace").stdout
        return str(pid) in out
    try:
        import os
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_cancelling_a_job_kills_the_grandchildren(tmp_path):
    marker = tmp_path / "grandchild.pid"
    proc = subprocess.Popen([sys.executable, "-c", PARENT, str(marker)],
                            start_new_session=(sys.platform != "win32"))
    try:
        for _ in range(60):                       # 손자가 자기 pid를 적을 때까지
            if marker.exists() and marker.read_text().strip():
                break
            time.sleep(0.1)
        else:
            pytest.skip("손자 프로세스가 제때 뜨지 않았다")
        gc_pid = int(marker.read_text().strip())
        assert _alive(gc_pid)

        kill_tree(proc)
        proc.wait(timeout=15)

        for _ in range(50):
            if not _alive(gc_pid):
                break
            time.sleep(0.1)
        assert not _alive(gc_pid), "손자가 살아남았다. GPU 메모리를 쥐고 있다"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
