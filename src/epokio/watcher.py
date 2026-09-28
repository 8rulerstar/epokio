"""agent의 백그라운드 감시: 학습 상태 변화를 사건으로 쌓고, 폰 웹후크를 보내고, 기계 상태(디스크·GPU)를 경고한다.

Agent가 이 믹스인을 물려받는다. 요청 처리(보기·실행)는 agent.py, HTTP는 server.py.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from . import config, runmeta
from .monitor import Monitor
from .sources import LocalSource

DEFAULT_HOOK_KINDS = ["finished", "failed", "stalled", "stopped_early", "job_done", "job_failed", "goal",
                      "disk_low", "gpu_hot", "gpu_mem", "fan_max"]
_PUSH_LOCK = threading.Lock()


class Watcher:
    def _job_event(self, j):
        """대기열 작업이 끝나면 알림 사건. 오토라벨링처럼 짧은 작업도 놓치지 않는다."""
        if j.kind == "setup":                  # 새 환경이 생겼다. 파이썬 목록을 다시 떠보게
            from . import envs
            envs.forget()
        kind = {"done": "job_done", "failed": "job_failed"}.get(j.state)
        if not kind:
            return
        self._push(kind, "running", {"name": j.name, "path": j.output, "epoch": 0, "total": None,
                                    "elapsed": (j.ended or 0) - (j.started or 0), "eta": None,
                                    "metric": None, "metric_name": "", "best": None,
                                    "best_epoch": None, "state": j.state, "idle": 0.0,
                                    "history": [], "source": self.label, "updated": 0.0,
                                    "job_kind": j.kind})

    def _push(self, kind, before, run):
        """사건을 쌓는다. 같은 결과 폴더에 2분 안에 또 오면 버린다.
        ★대기열 작업이 results.csv도 쓰면 '작업 끝남'과 '학습 끝남'이 겹쳐 알림이 두 번 떴다."""
        import time
        run.setdefault("source", getattr(self, "label", "local"))      # ★없으면 맥 앱 디코딩이 깨져 알림이 영영 멈췄다
        run.setdefault("history", [])
        # 감시 스레드와 대기열 스레드가 같이 부른다. 사건 번호가 겹치지 않게
        with _PUSH_LOCK:
            now = time.time()
            recent = getattr(self, "_recent", {})
            self._recent = recent = {k: t for k, t in recent.items() if now - t < 120}
            key = Path(run.get("path") or "").name or run.get("name")    # 경로든 이름이든 폴더 이름으로 맞춘다
            if kind in ("finished", "failed", "job_done", "job_failed") and key in recent:
                return
            if kind in ("finished", "failed", "job_done", "job_failed"):
                recent[key] = now
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
            webhook(url, Event(kind, r, "running"))

    def stop_watch(self, timeout: float = 5.0):
        """감시 스레드를 멈추고 끝날 때까지 기다린다. 한 프로세스에 Agent를 여럿 만드는 시험용.
        ★멈추지 않은 스레드가 뒤 시험이 바꿔 둔 sweep.DIR을 읽어, 그 시험의 스윕 시도를 제 대기열에 넣었다"""
        self._stop_watching = True
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
                roots = [r for r in self.roots + [Path.home() / ".epokio" / "runs"] if r.exists()]
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
                if not getattr(self, "_pace_watching", False):
                    pace.watch(roots)                     # 파일 알림(watchdog 있을 때만)
                    self._pace_watching = True
                changed = False
                scanned = pace.should_scan()             # ★수동 모드: 폴더를 훑지 않는다(알림 없음). 대기열·스윕은 아래에서 계속
                if scanned:
                    for e in mon.refresh():
                        changed = True
                        self._push(e.kind, e.before, e.run.to_dict())
                    self._scanned = (time.time(), [str(r) for r in roots], mon.runs)   # /runs가 이걸 쓴다(다시 훑지 않게)
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
            self._warn("fan_max", tr("Fans at {pct}% ({rpm} rpm) for {min} min. The chip may slow down to cool off.",
                                     pct=f"{s.fan:.0f}", rpm=s.fan_rpm or "?", min=int((now - since) // 60)))
