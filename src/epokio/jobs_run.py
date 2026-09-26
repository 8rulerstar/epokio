"""대기열의 작업 하나 돌리기(Queue._run). 명령 만들기, 띄우기, 기다리기, 끝 적기, 알림.

★경로·subprocess는 jobs 모듈 것을 부를 때마다 읽는다(테스트가 jobs.subprocess.Popen 등을 갈아 끼운다)
"""
from __future__ import annotations

import os
import sys
import time

from . import gpus
from . import jobs as J
from .jobs_proc import NO_WINDOW, kill_tree, proc_start


def note(j, text: str):
    """작업 로그 끝에 한 줄. 로그가 없으면 나만 읽게 만든다"""
    try:
        with os.fdopen(os.open(j.log, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600), "a", encoding="utf-8") as fh:
            fh.write(text)
    except (OSError, TypeError):
        pass


def _repro(kind: str, j):
    """재현 기록(repro_runs). 실패해도 학습은 그대로 간다"""
    if j.kind not in ("train", "evaluate"):
        return
    try:
        from . import repro_runs
        if kind == "start":
            repro_runs.for_job(j)                  # 어떤 코드·환경·데이터로 돌렸나
        elif j.output:
            repro_runs.adopt(j.id, j.output)       # ★ultralytics가 이름을 name2로 바꾸면 j.output과 어긋난다: 실제 폴더를 받는다
    except Exception:
        pass


def run_job(q, j):
    """q: Queue. j는 _claim이 running으로 못 박은 작업이거나(자리 스레드), 아직 queued인 작업(직접 부를 때)."""
    try:
        cmd = [str(c) for c in J.build_command(j)]
    except Exception as e:
        with q._lock:
            if j.state != "cancelled":
                j.state = "failed"
            j.ended, j.gpu_index = time.time(), None
            try:
                with os.fdopen(os.open(j.log, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600), "w", encoding="utf-8") as fh:
                    fh.write(f"could not build command: {e}\n")
            except (OSError, TypeError):
                pass
            q._save()
        return
    with q._lock:
        if j.state not in ("queued", "running"):   # ★고른 뒤 띄우기 전에 취소됐다: 프로세스를 띄우지 않는다
            j.gpu_index, j.ended = None, j.ended or time.time()
            q._save()
            return
        if j.state == "queued":                     # 자리 잡기(_claim)를 거치지 않고 바로 불렀다
            j.state, j.started = "running", time.time()
            q._save()
    _repro("start", j)
    env = gpus.env_for(j.gpu, j.gpu_index)      # CUDA_VISIBLE_DEVICES: 이 작업이 볼 GPU만
    # 로그는 utf-8로 읽는다. PYTHONUTF8: 한국어 윈도우에서 자식의 출력·파일 쓰기가 cp949가 되지 않게
    env.update(PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    with os.fdopen(os.open(j.log, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600), "ab") as log:   # 로그엔 경로·인자: 나만
        log.write(("$ " + " ".join(cmd) + "\n").encode())
        log.flush()                  # ★안 하면 자식 출력 뒤에 늦게 써진다
        try:
            proc = J.subprocess.Popen(
                cmd, cwd=j.cwd or None, stdout=log, stderr=J.subprocess.STDOUT, env=env,
                stdin=J.subprocess.DEVNULL,           # ★입력을 기다리는 작업(빈 스크립트·라이브러리 질문)이 대기열을 영영 막았다
                start_new_session=(sys.platform != "win32"),
                creationflags=NO_WINDOW)              # 트레이가 창 없이 띄운 agent 밑에서 콘솔 창이 뜨지 않게
            with q._lock:
                q._procs[j.id] = proc
                j.pid, j.pid_start = proc.pid, proc_start(proc.pid)
                if j.state == "cancelled":   # ★띄우는 사이에 취소가 왔다. 그때는 죽일 프로세스가 없었다
                    kill_tree(proc)
                # 저장 실패가 '못 띄움'이 되면 안 된다. ★아래 except OSError에 걸려 도는 학습을 실패로 적고
                #   같은 GPU에 다음 작업을 띄웠다. 상태는 메모리에 맞게 있으니 다음 저장 때 남는다
                try:
                    q._save()
                except OSError:
                    pass
            rc = proc.wait()
        except OSError as e:
            log.write(f"\nfailed to start: {e}\n".encode())
            rc = -1
    with q._lock:
        j.returncode, j.ended, j.pid = rc, time.time(), None
        if j.state != "cancelled":
            j.state = "done" if rc == 0 else "failed"
        j.gpu_index = None                # ★끝났으면 GPU를 놓는다(죽어도 다음 자리 잡기에서 안 센다)
        q._procs.pop(j.id, None)
        # 저장이 실패해도(디스크 가득) 끝남·실패 알림은 보낸다. ★여기서 OSError가 나 알림이 안 갔다
        try:
            q._save()
        except OSError:
            pass
    _repro("end", j)
    if q.on_finish:
        try:
            q.on_finish(j)
        except Exception:
            pass
