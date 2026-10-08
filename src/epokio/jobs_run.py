"""Runs one queued job (Queue._run): build the command, launch, wait, record the end, notify.

Paths and subprocess are read from the jobs module on each call (tests swap jobs.subprocess.Popen etc.)
"""
from __future__ import annotations

import os
import sys
import time

from . import gpus
from . import jobs as J
from .jobs_proc import NO_WINDOW, kill_tree, proc_start


def note(j, text: str):
    """Append a line to the job log. If the log doesn't exist, create it owner-only"""
    try:
        with os.fdopen(os.open(j.log, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600), "a", encoding="utf-8") as fh:
            fh.write(text)
    except (OSError, TypeError):
        pass


def _repro(kind: str, j):
    """Reproducibility record (repro_runs). Training continues even if this fails"""
    if j.kind not in ("train", "evaluate"):
        return
    try:
        from . import repro_runs
        if kind == "start":
            repro_runs.for_job(j)                  # which code, environment and data it ran with
        elif j.output:
            repro_runs.adopt(j.id, j.output)       # if ultralytics renames to name2, j.output is off: take the actual folder
    except Exception:
        pass


def run_job(q, j):
    """q: Queue. j is either a job _claim already pinned as running (slot thread) or one still queued (direct call)."""
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
        if j.state not in ("queued", "running"):   # cancelled after being picked but before launch: don't start the process
            j.gpu_index, j.ended = None, j.ended or time.time()
            q._save()
            return
        if j.state == "queued":                     # called directly, without going through slot claiming (_claim)
            j.state, j.started = "running", time.time()
            q._save()
    _repro("start", j)
    env = gpus.env_for(j.gpu, j.gpu_index)      # CUDA_VISIBLE_DEVICES: only the GPUs this job should see
    # Logs are read as utf-8. PYTHONUTF8: keeps the child's output and file writes from becoming cp949 on Korean Windows
    env.update(PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    with os.fdopen(os.open(j.log, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600), "ab") as log:   # log holds paths/args: owner-only
        log.write(("$ " + " ".join(cmd) + "\n").encode())
        log.flush()                  # without this it gets written late, after the child's output
        try:
            proc = J.subprocess.Popen(
                cmd, cwd=j.cwd or None, stdout=log, stderr=J.subprocess.STDOUT, env=env,
                stdin=J.subprocess.DEVNULL,           # previously jobs awaiting input (empty script, library prompt) blocked the queue
                start_new_session=(sys.platform != "win32"),
                creationflags=NO_WINDOW)              # no console window under an agent the tray launched windowless
            with q._lock:
                q._procs[j.id] = proc
                j.pid, j.pid_start = proc.pid, proc_start(proc.pid)
                if j.state == "cancelled":   # a cancel arrived during launch, when there was no process to kill yet
                    kill_tree(proc)
                # A failed save must not count as "failed to start". Previously the except OSError below marked the running
                #   training failed and launched the next job on the same GPU. State is correct in memory, so the next save keeps it
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
        j.gpu_index = None                # release the GPU once finished (so a dead job isn't counted at the next slot claim)
        q._procs.pop(j.id, None)
        # Send the done/failed notification even if saving fails (disk full). Previously an OSError here meant no notification
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
