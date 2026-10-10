"""작업 대기열 본체(Queue). jobs.py가 다시 내보낸다(`from epokio.jobs import Queue`).

자리(lane): GPU마다 하나(gpus.lanes). 자리마다 스레드 하나가 빈 GPU에 맞는 작업을 집는다.
★경로 상수는 jobs 모듈에서 부를 때마다 읽는다(J.LOGS 등). 테스트가 jobs.LOGS를 바꿔 끼운다
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, fields
from pathlib import Path

from . import gpus
from . import jobs as J
from .jobs_proc import kill_tree, pid_alive
from .jobs_run import note as _note, run_job

FINISHED = ("done", "failed", "cancelled")


# 코드를 돌리는 작업(남이 준 .pt·.py·yaml을 읽거나 돌린다). 네트워크에 연 도우미는 --allow-run 없이는 받지 않는다.
# setup(정해 둔 패키지 설치)·practice(표준 라이브러리 연습)는 남이 준 코드를 돌리지 않아 늘 된다
CODE_KINDS = ("script", "train", "evaluate", "autolabel", "export", "classes")


def runs_code(route: str, body: dict) -> bool:
    """이 POST가 코드를 돌리나. 대기열을 거치지 않는 /predict와 나중에 시도를 넣는 스윕 만들기도"""
    if route == "/jobs":
        return body.get("kind") not in ("setup", "practice")
    return route in ("/predict", "/sweeps")


# 작업을 새로 시작하는 요청. 설정(config.launch_runs)이 꺼져 있으면 agent가 403(launch_off)으로 돌려준다.
# 이미 든 작업을 다루는 요청(취소·순서·지우기)은 늘 열려 있다
LAUNCH_ROUTES = ("/jobs", "/sweeps", "/predict", "/classes")


class RunRefused(Exception):
    """네트워크에 연 도우미가 --allow-run 없이 코드를 돌리는 작업을 받았다(agent가 403으로 돌려준다)"""


class Queue:
    KEEP_FINISHED = 500
    code_ok = True          # False: 코드를 돌리는 작업(CODE_KINDS)을 받지 않는다(server_cli가 네트워크에 열 때)

    def __init__(self, path: Path | None = None):
        self.path = path or J.STATE        # ★기본값을 정의 시점에 묶으면 테스트가 STATE를 바꿔도 진짜 ~/.epokio를 썼다
        self.jobs: list[J.Job] = []
        self._lock = threading.Lock()
        self._procs: dict[str, subprocess.Popen] = {}     # 돌고 있는 작업 id -> 프로세스 (자리마다 하나)
        self._wake = threading.Event()
        self.lanes: list[int | None] = [None]             # start()에서 GPU 수만큼 (gpus.lanes)
        self.locked_out = False
        self.on_finish = None            # 작업이 끝나면 부른다 (agent가 알림 사건으로 쌓는다)
        self.on_away = None              # 종료 코드를 모르고 끝난 작업(다시 켜기 전에 띄운 것)
        self._load()

    @property
    def _orphan(self):
        """agent를 다시 켜기 전에 띄워 아직 도는 학습(첫 번째)"""
        return self._orphans[0] if self._orphans else None

    # 저장
    def _load(self):
        if self.path.exists():
            try:
                # 아는 칸만 받는다. ★모르는 칸 하나(새 판이 쓴 파일을 옛 exe가 읽을 때)에 TypeError로 대기열 전체가 비었다
                known = {f.name for f in fields(J.Job)}
                self.jobs = [J.Job(**{k: v for k, v in d.items() if k in known})
                             for d in json.loads(self.path.read_text(encoding="utf-8")) if isinstance(d, dict)]
            except (ValueError, TypeError):
                # 깨진 파일은 옆에 남긴다. ★빈 것으로 보고 다음 저장이 덮어, 대기열과 도는 학습을 통째로 잊었다
                self.jobs = []
                try:
                    self.path.replace(self.path.with_name(f"{self.path.stem}.broken-{int(time.time())}{self.path.suffix}"))
                except OSError:
                    pass
        self._orphans: list[J.Job] = []
        self.ended_away: list[J.Job] = []     # 꺼진 사이 끝난 작업. agent가 on_finish를 단 뒤 알린다(★알림이 없었다)
        for j in self.jobs:
            if j.state != "running":
                continue
            # ★자식은 agent가 꺼져도 산다. 살아 있는데 실패로 적고 다음 작업을 띄우면 GPU에 학습 두 개가 겹친다.
            #   끝날 때까지 기다린다. 그 GPU(gpu_index)는 계속 잡힌 것으로 센다
            if pid_alive(j.pid, j.pid_start):
                self._orphans.append(j)
            else:
                # 꺼져 있는 사이에 끝났다. '끝남(종료 코드 모름)'으로 적고 로그에 남긴다. ★실패로 적어 잘 끝난 학습이 실패로 보였다
                j.state, j.ended, j.pid, j.gpu_index = "done", time.time(), None, None   # ★죽은 작업이 GPU를 잡은 채로 남지 않게
                _note(j, "\nFinished while Epokio was not running. Its exit code is unknown; check the run's results.\n")
                self.ended_away.append(j)

    def _save(self, jobs: list | None = None):
        from .auth import private_dir
        private_dir(self.path.parent)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)   # 작업 인자·경로가 들어 있다: 나만
        os.close(fd)
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        # ★인코딩을 안 적으면 한국어 윈도우는 cp949로 쓰려다 é·学·맥 NFD 한글에서 터진다
        tmp.write_text(json.dumps([asdict(j) for j in (self.jobs if jobs is None else jobs)], ensure_ascii=False, indent=1),
                       encoding="utf-8")
        # 쓰다 죽어도 파일이 반쯤 깨지지 않게 바꿔치기. 윈도우에서 누가 읽는 중이면(WinError 5) 잠깐 뒤 다시
        for i in range(6):
            try:
                tmp.replace(self.path)
                return
            except PermissionError:
                if i == 5:
                    raise
                time.sleep(0.05 * (i + 1))

    # 조작
    def add(self, kind: str, name: str, python: str, params: dict, cwd: str = "", sweep: str = "",
            gpu: str = gpus.AUTO) -> J.Job:
        if not self.code_ok and kind in CODE_KINDS:
            raise RunRefused(kind)
        name = J.safe_name(name) or kind
        if isinstance(params.get("name"), str):
            params = {**params, "name": J.safe_name(params["name"]) or name}
        with self._lock:
            self._prune()
            j = J.Job(id=uuid.uuid4().hex[:8], kind=kind, name=name, python=python,
                      params=params, cwd=cwd, created=time.time(), sweep=sweep, gpu=gpus.normalize(gpu))
            from .auth import private_dir
            private_dir(J.LOGS)
            j.log = str(J.LOGS / f"{j.id}.log")
            # 저장이 된 다음에 목록에 넣는다. ★먼저 넣고 저장이 실패하면 사용자는 오류를 보고 다시 눌러 학습이 두 번 돌았다
            self._save(self.jobs + [j])
            self.jobs.append(j)
        self._wake.set()
        return j

    def record_done(self, kind: str, name: str, output: str, params: dict | None = None) -> J.Job:
        """실행 없이 '끝난 작업'으로 남긴다(예측 파일 가져오기: 검수 화면이 작업 목록에서 결과를 찾는다)"""
        with self._lock:
            now = time.time()
            j = J.Job(id=uuid.uuid4().hex[:8], kind=kind, name=name, python="", params=params or {}, created=now,
                      started=now, ended=now, state="done", output=output, returncode=0)
            self._save(self.jobs + [j])
            self.jobs.append(j)
        return j

    def clear_finished(self) -> int:
        """끝난 작업을 목록에서 뺀다. 결과를 화면에서 다시 여는 작업(끝난 평가·오토라벨)은 남긴다(검수·요약이 작업으로 결과를 찾는다).
        결과 폴더와 파일은 지우지 않는다(목록에서만 빠진다)"""
        with self._lock:
            keep = lambda j: j.state in ("queued", "running") or (j.state == "done" and j.kind in ("evaluate", "autolabel"))
            n = sum(1 for j in self.jobs if not keep(j))
            self.jobs = [j for j in self.jobs if keep(j)]
            self._save()
            return n

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            j = self.get(job_id)
            if not j or j.state in FINISHED:
                return False
            if j.state == "queued":
                j.state, j.ended = "cancelled", time.time()
            elif j.state == "running":
                proc = self._procs.get(j.id)     # ★자리가 여럿이면 '지금 도는 프로세스'가 하나가 아니다
                if proc:
                    kill_tree(proc)
                elif j in self._orphans and pid_alive(j.pid, j.pid_start):
                    kill_tree(j.pid)             # agent를 다시 켜기 전에 띄운 학습
                # 아직 Popen 전이면 _run이 띄운 직후 이 표시를 보고 끈다.
                # ★예전엔 프로세스 손잡이가 없으면 True만 돌려주고 상태는 running으로 남았다
                j.state = "cancelled"
            self._save()
            return True

    def move(self, job_id: str, delta: int) -> bool:
        """대기 중인 작업의 순서를 바꾼다."""
        with self._lock:
            waiting = [j for j in self.jobs if j.state == "queued"]
            j = self.get(job_id)
            if j not in waiting:
                return False
            # ★바로 옆 칸이 아니라 대기 중인 이웃과 바꾼다. 사이에 취소된 작업이 끼면 예전엔 안 움직였다
            w = waiting.index(j) + delta
            if not 0 <= w < len(waiting):
                return False
            i, k = self.jobs.index(j), self.jobs.index(waiting[w])
            self.jobs[i], self.jobs[k] = self.jobs[k], self.jobs[i]
            self._save()
            return True

    def reorder(self, ids: list[str]) -> bool:
        """대기 중인 작업의 새 순서(끌어서 옮기기). ids는 대기 중인 작업 전부여야 한다"""
        with self._lock:
            waiting = [j for j in self.jobs if j.state == "queued"]
            if sorted(ids) != sorted(j.id for j in waiting):
                return False
            slots = [i for i, j in enumerate(self.jobs) if j.state == "queued"]
            by = {j.id: j for j in waiting}
            for slot, jid in zip(slots, ids):
                self.jobs[slot] = by[jid]
            self._save()
            return True

    def get(self, job_id: str) -> J.Job | None:
        return next((j for j in self.jobs if j.id == job_id), None)

    def tail(self, job_id: str, lines: int = 200) -> str:
        j = self.get(job_id)
        if not j or not j.log or not Path(j.log).exists():
            return ""
        with open(j.log, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 64_000))
            text = fh.read().decode("utf-8", "replace")
        # 진행 막대의 \r 덮어쓰기를 풀어 마지막 모습만 남긴다
        text = "\n".join(l.split("\r")[-1] for l in text.splitlines())
        return "\n".join(text.splitlines()[-lines:])

    def busy_gpus(self) -> list[int]:
        """지금 쓰이고 있는 GPU 번호. 자물쇠 파일이 아니라 대기열 상태에서 읽는다"""
        return [j.gpu_index for j in self.jobs if j.state == "running" and j.gpu_index is not None]

    def _prune(self):
        """끝난 작업은 최근 KEEP_FINISHED개만(로그·스크립트도 지운다). ★jobs.json·로그가 끝없이 늘어
        작업 하나 넣는 데 5만 개에서 0.7초가 걸렸다. 사용자의 학습 결과 폴더는 건드리지 않는다"""
        done = [j for j in self.jobs if j.state in FINISHED]
        drop = done[:-self.KEEP_FINISHED] if len(done) > self.KEEP_FINISHED else []
        if not drop:
            return
        gone = {id(j) for j in drop}
        self.jobs = [j for j in self.jobs if id(j) not in gone]
        for j in drop:
            for f in (Path(j.log) if j.log else None, J.SCRIPTS / f"{j.id}.py"):
                try:
                    if f is not None:
                        f.unlink(missing_ok=True)
                except OSError:
                    pass

    # 실행
    def start(self):
        """이 기계에서 대기열을 돌리는 도우미는 하나만(잠금 파일). ★같은 ~/.epokio로 도우미가 둘 뜨면 기다리던 작업이
        둘 다에서 한 번씩, 두 번 돌았다. 잠금을 못 잡으면 대기열을 돌리지 않는다.
        GPU 장수는 여기서 한 번만 센다. 도중에 GPU를 꽂았다 빼는 경우는 agent를 다시 켠다"""
        self.locked_out = not self._take_lock()
        if self.locked_out:
            return self
        self.lanes = gpus.lanes()
        if self._orphans:
            threading.Thread(target=self._wait_orphans, daemon=True).start()
        for lane in self.lanes:
            threading.Thread(target=self._worker, args=(lane,), daemon=True).start()
        return self

    def _take_lock(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(self.path.with_suffix(".lock"), "a+b")
        except OSError:
            return True                   # 잠금 파일을 못 만들면 예전처럼 돈다
        try:
            if sys.platform == "win32":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self._lock_file = fh              # 프로세스가 끝날 때까지 쥐고 있는다
        return True

    def _wait_orphans(self):
        """다시 켜기 전에 띄운 학습이 끝나면 '끝남(종료 코드 모름)'으로 적고 그 자리를 푼다."""
        while True:
            ended = []
            with self._lock:
                for j in list(self._orphans):
                    if j.state == "running" and pid_alive(j.pid, j.pid_start):
                        continue
                    if j.state == "running":     # 종료 코드는 모른다(우리가 띄운 자식이 아니다)
                        j.state, j.ended = "done", time.time()
                        _note(j, "\nFinished while Epokio was restarting. Its exit code is unknown; check the run's results.\n")
                        ended.append(j)
                    j.pid, j.gpu_index = None, None
                    self._orphans.remove(j)
                    try:
                        self._save()
                    except OSError:
                        pass
                done = not self._orphans
                if done:
                    self._wake.set()
            for j in ended:                       # 잠금 밖에서. 종료 코드를 모르니 agent가 결과 폴더로 판단한다(on_away)
                try:
                    if self.on_away:
                        self.on_away(j)
                except Exception:
                    pass
            if done:
                return
            time.sleep(5)

    def _claim(self, lane: int | None) -> J.Job | None:
        """이 자리에서 돌릴 작업 하나를 집어 running으로 못 박는다.
        ★고르기와 표시를 따로 하면 자리 둘이 같은 작업을 집는다(GPU 두 장에서 같은 학습이 두 번 돌았다)"""
        with self._lock:
            # 다시 켜기 전에 띄운 학습이 이 자리(또는 어느 GPU인지 모름)를 쓰는 중이면 기다린다
            if any(o.gpu_index is None or o.gpu_index == lane for o in self._orphans):
                return None
            taken = {j.gpu_index for j in self.jobs if j.state == "running"}
            if lane is not None and lane in taken:
                return None
            j = next((x for x in self.jobs if x.state == "queued" and gpus.fits(x.gpu, lane)), None)
            if j is None:
                return None
            j.state, j.started = "running", time.time()
            j.gpu_index = gpus.assigned(j.gpu, lane)
            self._save()
            return j

    def _worker(self, lane: int | None = None):
        while True:
            j = self._claim(lane)
            if j is None:
                self._wake.wait(2.0)       # 자리가 여럿이면 깨우기 신호를 놓칠 수 있다: 2초 폴링이 받쳐 준다
                self._wake.clear()
                continue
            # ★여기서 예외가 새면 스레드가 죽어 대기열이 영원히 멈춘다(작업은 '도는 중'으로 남는다)
            try:
                self._run(j)
            except Exception as e:
                with self._lock:
                    if j.state in ("queued", "running"):
                        j.state, j.ended = "failed", time.time()
                    j.gpu_index = None
                    self._procs.pop(j.id, None)
                    _note(j, f"\nEpokio could not run this job: {e}\n")
                    try:
                        self._save()
                    except OSError:
                        pass

    _run = run_job                 # 띄우고 기다리고 끝을 적는 부분(jobs_run.py). 길어서 따로 둔다
