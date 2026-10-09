"""agent의 백그라운드 감시: 학습 상태 변화를 사건으로 쌓고, 폰 웹후크를 보내고, 기계 상태(디스크·GPU)를 경고한다.

Agent가 이 믹스인을 물려받는다. 요청 처리(보기·실행)는 agent.py, HTTP는 server.py.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from . import config, runmeta, watch_state
from .monitor import Monitor
from .sources import LocalSource

# 'quiet'(계획 에폭을 모르는 학습의 기록이 멈춤)은 일부러 뺀다. ★정상으로 끝난 케라스 학습마다 폰에 '멎음'이 갔다
DEFAULT_HOOK_KINDS = ["finished", "failed", "stalled", "stopped_early", "job_done", "job_failed", "goal",
                      "disk_low", "gpu_hot", "gpu_mem", "fan_max"]
_PUSH_LOCK = threading.Lock()
RUN_DEFAULTS = (("name", ""), ("path", ""), ("epoch", 0), ("total", None), ("elapsed", 0.0), ("eta", None), ("metric", None),
                ("metric_name", ""), ("best", None), ("best_epoch", None), ("state", "running"), ("idle", 0.0))


def _job_scope(j) -> str:
    """결과 폴더를 모르는 작업(스크립트)이 학습을 쓸 만한 곳: 작업 폴더(cwd), 없으면 스크립트 파일이 있는 폴더"""
    import os
    where = j.cwd if getattr(j, "cwd", "") else ""
    args = (getattr(j, "params", None) or {}).get("args") or []
    if not where and args and str(args[0]).lower().endswith(".py"):
        where = os.path.dirname(os.path.abspath(str(args[0])))
    return os.path.normcase(os.path.normpath(where)) if where else ""


class Watcher:
    def _job_event(self, j):
        """대기열 작업이 끝나면 알림 사건. 오토라벨링처럼 짧은 작업도 놓치지 않는다."""
        if j.kind == "setup":                  # 새 환경이 생겼다. 파이썬 목록을 다시 떠보게
            from . import envs
            envs.forget()
        kind = {"done": "job_done", "failed": "job_failed"}.get(j.state)
        if not kind:
            return
        self._push(kind, "running", self._job_run(j), span=(j.started or 0, j.ended or 0, _job_scope(j)))

    def _away_job_event(self, j):
        """다시 켜기 전에 띄운 작업이 끝났다. 종료 코드를 모르니 학습 폴더가 끝남·실패를 말할 때만 알린다
        (★재부팅으로 죽은 학습에 '작업 끝남'을 보내면 거짓말이다. 그런 학습은 감시가 '멎음'으로 알린다)"""
        if not j.output or j.kind not in ("train", "practice", "classes"):
            return
        try:
            from .scan import read_run
            r = read_run(Path(j.output))
        except Exception:
            return
        kind = {"done": "job_done", "failed": "job_failed"}.get(getattr(r, "state", ""))
        if kind:
            self._push(kind, "running", {**r.to_dict(), "source": self.label, "job_kind": j.kind},
                       span=(j.started or 0, j.ended or 0, _job_scope(j)))

    def _job_run(self, j) -> dict:
        """작업 알림에 실을 값. 작업이 학습 폴더를 썼으면 그 학습의 실제 에폭·점수, 실패면 로그로 본 이유.
        ★작업 알림이 늘 '에폭 0/?'였고, 2분 안에 온 같은 결과의 '학습 끝남'(바른 값)을 중복으로 지웠다"""
        run = {"name": j.name, "path": j.output, "epoch": 0, "total": None,
               "elapsed": (j.ended or 0) - (j.started or 0), "eta": None, "metric": None, "metric_name": "", "best": None,
               "best_epoch": None, "state": j.state, "idle": 0.0, "history": [], "source": self.label, "updated": 0.0}
        if j.output and j.kind in ("train", "practice", "classes"):
            try:
                from .scan import read_run
                r = read_run(Path(j.output))
                if r is not None:
                    run = {**r.to_dict(), "source": self.label}
            except Exception:                  # 알림은 값이 없어도 간다
                pass
        if j.state == "failed":
            try:
                from .diagnose import diagnose
                hint = (diagnose(self.queue.tail(j.id, 400)) or [{}])[0].get("title")
                if hint:
                    run["error"] = hint
            except Exception:
                pass
        run["job_kind"] = j.kind
        return run

    # 같은 결과로 보는 시간. 같은 폴더면 30분(★Ultralytics 마지막 검증이 2분을 넘으면 '학습 끝남'과 '작업 끝남'이 둘 다 갔다),
    # 폴더를 모르는 작업은 이름으로 2분
    SAME_RESULT_SEC, SAME_NAME_SEC = 1800, 120
    # 결과(끝남·실패)를 이미 알린 폴더의 뒤늦은 '멎음'·'마지막 에폭 전에 멈춤'은 보내지 않는다(다시 돌기 전까지)
    # ★대기열 학습 하나가 죽으면 '작업 실패'·'멎음'(급함)·'마지막 에폭 전에 멈춤'이 차례로 세 번 갔다
    AFTERMATH = ("stalled", "stopped_early", "quiet")

    def _duplicate(self, kind, run, now, span):
        """이 사건을 버릴까. _PUSH_LOCK 안에서 부른다"""
        import os
        p = run.get("path") or ""
        pk = os.path.normcase(os.path.normpath(p)) if p else ""
        outcome = {"finished": "ok", "job_done": "ok", "failed": "bad", "job_failed": "bad"}.get(kind)
        recent = {k: t for k, t in getattr(self, "_recent", {}).items() if now - t < (self.SAME_RESULT_SEC if k[0] else self.SAME_NAME_SEC)}
        closed = {k: t for k, t in getattr(self, "_closed", {}).items() if now - t < 6 * 3600}
        spans = [s for s in getattr(self, "_spans", []) if now - s[4] < self.SAME_RESULT_SEC]   # 폴더를 모르는 작업(스크립트)
        self._recent, self._closed, self._spans = recent, closed, spans
        if pk and kind in ("started", "recovered"):
            # 다시 돈다: 그 뒤의 멎음·끝남·실패는 새 결과다. ★닫힌 표시만 지워, 이어 하기 뒤 30분 안의 두 번째 실패가 사라졌다
            closed.pop(pk, None)
            for o in ("ok", "bad"):
                recent.pop((pk, o), None)
            getattr(self, "_runs_done", {}).pop(pk, None)
        if pk and kind in self.AFTERMATH and pk in closed:
            return True
        if not outcome:
            return False
        key = (pk, outcome) if pk else ("", f"{outcome}:{run.get('name')}")
        if key in recent:
            return True
        # 폴더를 모르는 작업(스크립트)과 그 작업이 쓴 학습: 학습의 마지막 기록이 작업이 돈 시간 안이면 같은 결과
        upd = run.get("updated") or 0
        # 그 작업의 폴더(cwd 또는 스크립트가 있는 폴더) 아래 학습만. ★폴더를 안 보면 그 사이 끝난 남의 학습 알림까지 지운다
        def inside(path, scope):
            return bool(scope) and (path == scope or path.startswith(scope.rstrip(os.sep) + os.sep))
        if pk and any(o == outcome and a - 10 <= upd <= b + 10 and inside(pk, sc) for a, b, sc, o, _ in spans):
            return True
        if not pk and span and span[0] and any(o == outcome and span[0] - 10 <= u <= span[1] + 10 and inside(k, span[2])
                                               for k, (u, o) in getattr(self, "_runs_done", {}).items()):
            return True
        recent[key] = now
        if pk:
            closed[pk] = now
            self._runs_done = {k: v for k, v in getattr(self, "_runs_done", {}).items() if now - closed.get(k, 0) < self.SAME_RESULT_SEC}
            self._runs_done[pk] = (upd, outcome)
        elif span and span[0] and span[2]:
            spans.append((span[0], span[1], span[2], outcome, now))
        return False

    def _push(self, kind, before, run, span=None):
        """사건을 쌓는다. 같은 결과(끝남·실패)는 한 번만(_duplicate).
        ★대기열 작업이 results.csv도 쓰면 '작업 끝남'과 '학습 끝남'이 겹쳐 알림이 두 번 떴다."""
        import time
        run.setdefault("source", getattr(self, "label", "local"))      # ★없으면 맥 앱 디코딩이 깨져 알림이 영영 멈췄다
        # 맥 앱 Run이 꼭 받는 칸(Models.swift의 Optional 아닌 let)도 채운다. ★스윕 조기 중단 사건은 이름·경로만 실어
        #   /events 디코딩 전체가 실패했고, 그 agent의 맥 알림이 다시 켤 때까지 멈췄다
        for k, v in RUN_DEFAULTS:
            run.setdefault(k, v)
        run.setdefault("history", [])
        # 감시 스레드와 대기열 스레드가 같이 부른다. 사건 번호가 겹치지 않게
        with _PUSH_LOCK:
            now = time.time()
            # 같은 결과 폴더(전체 경로)의 같은 결과(끝남·실패)만 겹친 것으로 본다.
            # ★폴더 이름만 봐서, 다른 프로젝트의 version_0 둘이 연달아 끝나면 두 번째(실패)가 사라졌다
            if self._duplicate(kind, run, now, span):
                return
            self.seq += 1
            self.events.append({"seq": self.seq, "kind": kind, "before": before, "run": run, "at": now})
        self._webhook(kind, run)

    HOOKS_FILE = Path.home() / ".epokio" / "webhooks.json"

    def _webhook(self, kind, run):
        """폰 알림(Slack·Discord·Telegram)은 학습 기계가 직접 보낸다. 맥이 꺼져 있어도 온다."""
        if not self.HOOKS_FILE.exists() or config.quiet_now():      # 조용한 시간에는 폰 푸시를 보내지 않는다
            return
        try:
            cfg = json.loads(self.HOOKS_FILE.read_text(encoding="utf-8"))
        except ValueError:
            return
        if kind not in cfg.get("kinds", DEFAULT_HOOK_KINDS) and kind != "goal":     # 목표 점수는 사람이 건 것이라 항상
            return
        from .selfnotify import claimed
        if claimed(run.get("path"), kind):            # 학습 프로세스가 직접 보냈다(epokio.start(notify=True)). 두 번 안 간다
            return
        from . import i18n
        from .monitor import Event
        from .notify import webhook
        from .scan import Run
        i18n.use(cfg.get("lang"))                      # 설정한 앱의 언어 (없으면 영어). 이 스레드만 부른다
        try:
            r = Run.from_dict({**run, "path": run.get("path", "")})
        except TypeError:
            return
        for url in cfg.get("urls", []):
            webhook(url, Event(kind, r, "running"), machine=getattr(self, "label", None))

    def stop_watch(self, timeout: float = 5.0):
        """감시 스레드를 멈추고 끝날 때까지 기다린다. 한 프로세스에 Agent를 여럿 만드는 시험용.
        ★멈추지 않은 스레드가 뒤 시험이 바꿔 둔 sweep.DIR을 읽어, 그 시험의 스윕 시도를 제 대기열에 넣었다.
        ★기계 표본 스레드도 멈춘다. 남은 수십 개가 CPU 직전 표본(전역)을 계속 바꿔, 뒤 시험의 CPU 값이 비었다(0.8.0 CI)"""
        self._stop_watching = True
        stop = getattr(getattr(self, "sampler", None), "stop", None)
        if stop is not None:
            stop()
        pace = getattr(self, "pace", None)
        if pace is not None:
            pace.wake.set()
        t = getattr(self, "_watch_thread", None)
        if t is not None and t.is_alive():
            t.join(timeout)

    def _watch(self):
        import time
        while not getattr(self, "_stop_watching", False):
            try:
                pace, changed = self._watch_once()
            except Exception:
                # 전부 삼키되 이유는 남긴다(매번 실패해도 알림이 멈춘 이유가 어디에도 남지 않았다)
                import logging
                logging.getLogger("epokio").exception("watch loop failed")
                pace = getattr(self, "pace", None)
                changed = False
            live = any(r.state in ("running", "starting") for r in getattr(getattr(self, "_mon", None), "runs", []) or [])
            busy = any(j.state == "running" for j in getattr(getattr(self, "queue", None), "jobs", []) or [])
            if pace is None:
                time.sleep(8)
            else:
                pace.sleep(pace.interval(live or busy, changed))     # 쉬는 날엔 간격을 늘린다(pace.py)

    def _watch_once(self):
        """감시 한 바퀴. (pace, 바뀐 것이 있었나)"""
        import time
        # ★예전엔 self.roots + runs만 봐서 SSH 비춤(~/.epokio/ssh)·데모 학습은 알림·웹후크가 한 번도 안 갔다.
        #   /runs와 같은 목록(watch_roots)을 쓴다
        roots = [r for r in self.watch_roots() if r.exists()]
        mon = getattr(self, "_mon", None)
        if mon is None:
            self._mon = mon = Monitor([])
        # ★모니터는 하나만 두고 소스만 갈아 끼운다. 새로 만들면 첫 회차를 조용히 넘기는
        #   규칙 때문에 영원히 알림이 안 났다 (폴더 수가 안 맞아 매번 새로 만들었다)
        mon.sources = [x for x in mon.sources if getattr(x, "root", None) in roots]   # ★뺀 폴더가 계속 알림을 보냈다
        have = {getattr(x, "root", None) for x in mon.sources}
        for r in roots:
            if r not in have:
                mon.add(LocalSource(r))          # 옛 학습은 조용히 기억만
        pace = getattr(self, "pace", None)
        if pace is None:                          # Agent.__init__ 을 거치지 않은 경우(시험의 __new__)
            from .pace import Pace
            self.pace = pace = Pace()
        key = [str(r) for r in roots]
        if getattr(self, "_pace_watching", None) != key:
            pace.watch(roots)                     # 파일 알림(watchdog 있을 때만). ★폴더가 늘거나 줄면 다시 건다
            self._pace_watching = key
        changed = False
        scanned = pace.should_scan()             # ★수동 모드: 폴더를 훑지 않는다(알림 없음). 대기열·스윕은 아래에서 계속
        if scanned:
            from .ssh_source import host_of
            # 이어 한 학습(Lightning version_1 ← version_0)이 있으면 앞 것의 멎음·끝남은 알리지 않는다(★재개마다 앞 것이 '멎음'을 냈다)
            evs = list(mon.refresh())
            if not getattr(self, "_missed_checked", False):     # 꺼진 사이 끝나거나 멈춘 학습(watch_state.py)
                self._missed_checked = True
                evs = watch_state.missed(mon) + evs
            later = {(str(r.path.parent), r.resumed_from) for r in mon.runs if getattr(r, "resumed_from", "")}
            for e in evs:
                if (str(e.run.path.parent), e.run.path.name) in later and e.kind in ("stalled", "quiet", "finished", "stopped_early"):
                    continue
                changed = True
                d = e.run.to_dict()
                h = host_of(str(e.run.path))
                if h:                                # SSH 비춤이면 사건·알림에 그 서버(★'local'로 가서 어느 기계인지 몰랐다).
                    d["source"] = f"ssh:{h}"         #   /runs는 그대로 local + ssh 칸(맥 앱이 source로 기계를 고른다)
                self._push(e.kind, e.before, d)
            self._scanned = (time.time(), key, mon.runs)   # /runs가 이걸 쓴다(다시 훑지 않게, 같은 폴더 목록일 때만)
            saver = getattr(self, "_state_saver", None) or watch_state.Saver()
            self._state_saver = saver
            saver.save(mon)
        # 스윕 조기 중단: 가망 없는 시도를 멈춘다(켠 스윕만)
        q = getattr(self, "queue", None)
        if q is not None and not getattr(self, "_stop_watching", False):
            from . import sweep
            for jid in sweep.check_prune(q):
                j = q.get(jid)
                self._push("pruned", "running", {"name": j.name if j else jid, "path": j.output if j else ""})
            sweep.advance(q)                      # 똑똑한 스윕: 앞 시도가 끝났으면 다음 값을 골라 넣는다
            sweep.dispatch(q)                     # 여러 기계 스윕: 빈 기계에 다음 시도
        # 목표 점수: 넘는 순간 한 번 알린다
        self._check_machine(roots)
        if scanned and any(m.get("goal") is not None and not m.get("goal_hit") for m in runmeta.load().values()):
            for r in runmeta.goals_reached(mon.runs):   # 방금 훑은 것을 쓴다(예전엔 폴더를 한 번 더 훑었다)
                self._push("goal", "running", r.to_dict())
        return pace, changed

    # 기계 상태 경고: 디스크 부족·GPU 과열·GPU 메모리 부족. 같은 경고는 30분에 한 번만
    # 기준값은 config.py(사용자가 앱 설정에서 바꾼다)

    def _warn(self, kind: str, text: str):
        import time
        seen = getattr(self, "_warned", {})
        self._warned = seen
        if time.time() - seen.get(kind, 0) < 1800:
            return
        seen[kind] = time.time()
        self._push(kind, "running", {"name": text, "path": "", "epoch": 0, "total": None, "elapsed": 0, "eta": None,
                                     "metric": None, "metric_name": "", "best": None, "best_epoch": None,
                                     "state": "running", "idle": 0, "history": []})

    def _machine_language(self):
        """경고 문장의 언어: 폰 알림을 저장한 앱의 언어, 없으면 이 기계의 표시 언어.
        ★영어로만 만들어 한국어 맥·폰·웹에서도 'GB free on the disk with …'로 보였다"""
        from . import i18n, jsonfile, msg
        lang = None
        try:
            cfg = jsonfile.read(self.HOOKS_FILE, {}, move_broken=False)
            lang = cfg.get("lang") if isinstance(cfg, dict) else None
        except (OSError, ValueError):
            pass
        msg.set_from_header((lang or i18n.system_language() or "en").replace("_", "-"))

    def _check_machine(self, roots):
        # 언어는 이 한 번에만(복사한 문맥 안에서). 스레드 전체의 언어를 바꾸지 않는다
        import contextvars
        contextvars.copy_context().run(self._check_machine_in_language, roots)

    def _check_machine_in_language(self, roots):
        import shutil
        from .msg import tr
        self._machine_language()
        for r in roots[:8]:
            try:
                free = shutil.disk_usage(r).free / 2**30
            except OSError:
                continue
            if free < config.load()["disk_low_gb"]:
                self._warn("disk_low", tr("{gb} GB free on the disk with {folder}", gb=f"{free:.1f}", folder=r.name))
                break
        cfg = config.load()
        s = self.sampler.latest
        for g in (s.gpus if s else []):
            if g.temp is not None and g.temp >= cfg["gpu_hot_c"]:
                self._warn("gpu_hot", tr("{gpu} at {c} °C", gpu=g.name, c=f"{g.temp:.0f}"))
            if g.mem_used and g.mem_total and g.mem_used / g.mem_total * 100 >= cfg["gpu_mem_pct"]:
                self._warn("gpu_mem", tr("{gpu} memory {used} of {total} GB", gpu=g.name,
                                         used=f"{g.mem_used:.1f}", total=f"{g.mem_total:.1f}"))
        self._check_fan(s)

    FAN_FULL_PCT, FAN_FULL_SEC = 90, 300

    def _check_fan(self, s, now: float | None = None):
        """학습 중 팬이 최대 가까이(90%+) 5분 넘게 붙어 있으면 한 번 알린다. 칩이 열 때문에 느려지기 직전이다.
        잠깐 치솟는 건 흔해서(에폭 시작·검증) 이어진 시간을 잰다. 학습이 없으면 재지 않는다(다른 앱 탓이다)"""
        import time
        from .msg import tr
        now = time.time() if now is None else now
        live = any(r.state == "running" for r in getattr(getattr(self, "_mon", None), "runs", []) or []) or \
            any(j.state == "running" for j in getattr(getattr(self, "queue", None), "jobs", []) or [])
        if not (live and getattr(s, "fan", None) is not None and s.fan >= self.FAN_FULL_PCT):
            self._fan_since = None
            return
        since = getattr(self, "_fan_since", None) or now
        self._fan_since = since
        if now - since >= self.FAN_FULL_SEC:
            m = int((now - since) // 60)
            if getattr(s, "fan_source", None) == "gpu":        # 윈도우·리눅스: GPU 팬(rpm 없음)
                self._warn("fan_max", tr("GPU fan at {pct}% for {min} min. The GPU may slow down to cool off.", pct=f"{s.fan:.0f}", min=m))
            else:
                self._warn("fan_max", tr("Fans at {pct}% ({rpm} rpm) for {min} min. The chip may slow down to cool off.",
                                         pct=f"{s.fan:.0f}", rpm=s.fan_rpm or "?", min=m))
