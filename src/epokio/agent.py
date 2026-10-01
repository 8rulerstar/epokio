"""학습하는 기계에서 띄우는 작은 서버. 맥·윈도우 앱이 여기서 상태를 읽고 작업을 넣는다.

    epokio-agent                        # 이 기계 안에서만 (127.0.0.1)
    epokio-agent --host 0.0.0.0         # 같은 네트워크의 다른 기계에서도 (원격 학습 PC)

보기(GET)는 토큰 없이, 실행(POST)은 **토큰이 있어야만** 받는다.
표준 라이브러리만 쓴다 (학습 기계에 따로 깔 것이 없게).
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path

from . import config, envs, jsonfile, msg, rundetail, runmeta
from .jobs import Queue
from .watcher import Watcher
from .scan import scan, unique
from .ssh_source import host_of as ssh_host_of, remote_path as ssh_remote_path
from .roots import RootScanner
from .sysinfo import Sampler
from .api import API, NOT_MINE, result_file
from .api.jobs_post import TEXT_KEYS, typed_value  # noqa: F401  (옛 import 경로 유지)
from .api.roots_api import too_broad  # noqa: F401  (옛 import 경로 유지)
from .textnorm import mixed_forms, resolve

VERSION = 3                 # API 수준. 3: /sweep·display·lower·runs?lite·/shutdown



class Agent(Watcher):
    def __init__(self, roots: list[Path], label: str):
        config.apply()                                    # 저장된 멈춤 판정 시간 반영
        self.roots = roots
        self.discovered: set[Path] = set()      # 저절로 찾은 폴더(roots.json에 남기지 않는다)
        self.removed: set[Path] = self._load_removed()   # 사용자가 뺀 폴더(다시 찾아도 넣지 않는다. 재시작해도 기억한다)
        self.label = label
        self.sampler = Sampler().start()
        self.queue = Queue().start()
        from .ssh_source import Poller                    # SSH 가벼운 모드: 등록한 서버를 뒤에서 읽어 ~/.epokio/ssh 에 비춘다
        self.ssh = Poller()
        self.ssh.start()
        # 상태 변화(완료·실패·멎음·조기 종료)를 쌓아 둔다. 앱이 가져가 알림을 띄운다.
        # ★알림을 agent가 직접 띄우면 원격(윈도우) 학습의 알림이 맥에 안 뜬다
        import threading
        from collections import deque
        self.events = deque(maxlen=200)
        self.seq = 0
        self.boot = secrets.token_hex(6)            # 이번에 켜진 에이전트를 가리키는 값
        # ★스캔 모드(pace)는 감시 스레드가 첫 바퀴에서 만들었다. 그 전에 온 /runs는 pace가 없어 auto로, 뒤의 요청은
        #   배터리를 보고 saver로 판단해 켠 직후 목록 캐시가 빗나갔다. 처음부터 있게 한다(파일 알림 걸기는 감시 스레드 몫)
        from .pace import Pace
        self.pace = Pace()
        self._watch_thread = threading.Thread(target=self._watch, daemon=True)
        self._watch_thread.start()
        from . import sysrec                              # 학습별 기계 기록. 폴더 훑기와 따로 15초마다(sysrec.loop)
        threading.Thread(target=sysrec.loop, args=(self,), daemon=True).start()
        self.queue.on_finish = self._job_event

    ROOTS_FILE = Path.home() / ".epokio" / "roots.json"
    REMOVED_FILE = Path.home() / ".epokio" / "removed_roots.json"

    def _load_removed(self) -> set[Path]:
        """★뺀 폴더를 메모리에만 두어서, 재시작하면 자동 찾기가 다시 넣었다"""
        try:
            return {Path(p) for p in json.loads(self.REMOVED_FILE.read_text(encoding="utf-8"))}
        except (OSError, ValueError, TypeError):
            return set()

    def _save_removed(self):
        self.REMOVED_FILE.parent.mkdir(parents=True, exist_ok=True)
        jsonfile.write(self.REMOVED_FILE, sorted(str(p) for p in self.removed))

    def _save_roots(self):
        """사용자가 더한 폴더는 기억한다. agent를 다시 켜도 남게."""
        self.ROOTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        # 사용자가 더한 것만 남긴다. ★찾은 폴더까지 남겨서, 다음에 켤 때 목록이 비어 있지 않으니 다시 찾기가 멈췄다
        found = getattr(self, "discovered", set())
        jsonfile.write(self.ROOTS_FILE, [str(r) for r in self.roots if r not in found])

    def _data_index(self) -> dict:
        """데이터 지문 → 그 데이터로 학습한 학습들. 30초 동안 기억한다(★상세를 열 때마다 모든 학습을 훑었다)"""
        import time
        hit = getattr(self, "_didx", None)
        if hit and time.time() - hit[0] < 30:
            return hit[1]
        idx: dict = {}
        # 감시 스레드가 방금 훑은 목록을 쓴다.
        # ★상세를 열 때마다(30초에 한 번) 모든 폴더를 새로 훑었다(학습 3,000개에서 수 초)
        sc = getattr(self, "_scanned", None)
        runs = sc[2] if sc and time.time() - sc[0] < 30 else [
            r for root in self.watch_roots() if root.exists() for r in scan(root)]
        runs = unique(runs)
        for r in runs:                                   # 지문은 versions가 파일 시각으로 기억해 둔다
            fp = rundetail.detail_versions(Path(r.path)).get("data")
            if fp:
                idx.setdefault(fp, []).append({"path": str(r.path), "name": r.name})
        self._didx = (time.time(), idx)
        return idx

    def _run_paths(self) -> list[Path]:
        """지켜보는 모든 학습 폴더. 30초 기억(계보에서 자식을 찾을 때 쓴다)"""
        import time
        hit = getattr(self, "_rpaths", None)
        if hit and time.time() - hit[0] < 30:
            return hit[1]
        paths = [r.path for root in self.watch_roots() if root.exists() for r in scan(root)]
        self._rpaths = (time.time(), paths)
        return paths

    def watch_roots(self) -> list[Path]:
        from . import demo
        return self.roots + [Path.home() / ".epokio" / "runs"] + ([demo.DIR] if demo.DIR.is_dir() else []) + (self.ssh.roots() if getattr(self, "ssh", None) else [])

    def file(self, path: str) -> Path | None:
        """학습 폴더 안의 그림, 또는 끝난 평가 결과에 적힌 그림만 내준다. 그 밖은 경로를 알아도 못 받는다."""
        # ★감시 폴더 안인지부터(글자로) 본다. 예전엔 먼저 파일 시스템을 봐서 \\서버\공유 경로로 NTLM 해시가 샜다
        from .textnorm import is_network
        if Path(path).suffix.lower() not in rundetail.IMAGE_EXTS or is_network(path):
            return None
        if rundetail.inside(Path(path), self.watch_roots()):
            p = Path(resolve(path))
            if p.is_file() and rundetail.inside(p, self.watch_roots()):
                return p
            return None
        from .api import review as review_api                 # 검수 화면(웹): 평가 결과에 적힌 이미지도 내준다(목록에 글자로 있어야)
        p = Path(resolve(path))                                # 네트워크 경로는 위에서 걸렀다
        if str(p) in review_api.eval_images(self) and p.is_file():
            return p
        return None

    # 이어 하기
    def get(self, route: str, q: dict):
        for mod in API:                                       # 기능별 요청(검수·스윕·모델)은 api/ 에서
            got = mod.get(self, route, q)
            if got is not NOT_MINE:
                return got
        if route == "/health":
            from . import __version__
            # epokio: 패키지 판. setup·트레이가 자기 판과 다르면 옛 도우미를 다시 띄운다
            #   ★pip으로 올려도 옛 도우미가 계속 돌며 새 웹 화면을 내주고, 새 모듈을 불러 500이 났다
            return {"ok": True, "label": self.label, "version": VERSION, "api": VERSION, "epokio": __version__,
                    "boot": self.boot}
        if route == "/runs":
            import time
            hit = getattr(self, "_runs_cache", None)
            mode = self.pace.mode() if getattr(self, "pace", None) else "auto"
            ttl = {"manual": float("inf"), "saver": 20.0}.get(mode, 1.0)     # 수동: 새로 고침을 누를 때까지 지난 결과(pace.py)
            # lite=1: 곡선 조각(history, 학습마다 최대 60개)을 뺀다. 웹은 안 쓴다.
            # ★학습 3,000개면 4초마다 폰이 수 MB를 받아 파싱했다
            lite = q.get("lite", [""])[0] == "1"
            def slim(res):
                # 가벼운 쪽도 같은 객체를 돌려준다(서버가 같은 객체의 직렬화·압축 결과를 다시 쓴다)
                if not lite:
                    return res
                c = getattr(self, "_lite_cache", None)
                if not c or c[0] is not res:
                    c = (res, {**res, "runs": [{k: v for k, v in d.items() if k != "history"} for d in res["runs"]]})
                    self._lite_cache = c
                return c[1]
            # 앱·웹·터미널이 한꺼번에 물어도 폴더는 ttl에 한 번만 훑는다. 모드가 바뀌었으면 새로
            if hit and time.time() - hit[0] < ttl and hit[1].get("scan_mode") == mode:
                return slim(hit[1])
            # 감시 스레드가 방금(8초마다) 훑은 결과를 쓴다. 폴더 목록이 같고 15초 안이면 다시 훑지 않고,
            # '마지막 기록 뒤 지난 시간'만 지금 기준으로 고친다. ★예전엔 요청마다 또 훑어서 학습 2,000개에서 1.5초씩 걸렸다
            from dataclasses import replace
            sc = getattr(self, "_scanned", None)
            now = time.time()
            # ★auto 모드에선 감시 스레드가 쉬는 날 간격을 늘려(pace.py) 15초 묵은 결과면 새 학습이 늦게 보였다. 2초로
            reuse = 2.0 if mode == "auto" else 15.0
            if sc and now - sc[0] < reuse and sc[1] == [str(r) for r in self.watch_roots() if r.exists()]:
                runs = [replace(r, idle=max(now - r.updated, 0.0)) for r in sc[2]]
                slow = getattr(self, "_slow_roots", [])
            else:
                if getattr(self, "_roots_scan", None) is None:
                    self._roots_scan = RootScanner()          # 폴더마다 동시에 3초 한도(roots.py)
                runs, slow = self._roots_scan.scan(self.watch_roots())
                runs = unique(runs)
                self._slow_roots = slow
            meta = runmeta.load()
            out = []
            for r in runs:
                d = r.to_dict()
                m = meta.get(runmeta.key(r.path))
                if m:
                    d["meta"] = m                       # 별표·태그·메모·목표
                h = ssh_host_of(str(r.path))
                if h:                                   # SSH로 비춰 온 학습: 어느 서버의 어느 경로인지
                    d["ssh"] = {"host": h, "path": ssh_remote_path(str(r.path))}
                out.append(d)
            res = {"label": self.label, "roots": [str(r) for r in self.roots], "runs": out, "slow_roots": slow, "scan_mode": mode}
            self._runs_cache = (time.time(), res)
            return slim(res)
        if route == "/system":
            self.sampler.touch()
            s = self.sampler.latest
            return {"label": self.label, "now": s.to_dict() if s else None,
                    "history": [x.gpu for x in list(self.sampler.history)]}   # ★deque를 바로 돌면 표본 스레드와 겹쳐 500
        if route == "/events":
            try:
                since = int(q.get("since", ["0"])[0])
            except ValueError:
                since = 0
            # boot: 에이전트를 다시 켜면 seq가 1부터 다시 센다. 바뀌면 받는 쪽이 커서를 0으로(★예전엔 알 방법이 없어 새 알림을 건너뛰었다)
            return {"seq": self.seq, "boot": self.boot, "events": [e for e in list(self.events) if e["seq"] > since]}
        if route == "/config":                                # 사용자 기준값(멈춤·디스크·GPU·조용한 시간)
            return config.load()
        if route == "/recipes":
            from . import recipes
            return {"recipes": recipes.load()}
        if route == "/pythons":
            return {"envs": envs.list_envs()}
        if route == "/schema":                               # ★찾아 둔 파이썬만 실행한다(아무 경로나 받으면 토큰 없이 실행 파일을 띄울 수 있었다)
            py = q.get("python", [""])[0]
            if py not in {e.get("path") for e in envs.list_envs()}:
                return 400, {"error": "unknown python"}
            return envs.schema(py, q.get("mode", ["train"])[0])
        if route == "/jobs":
            from dataclasses import asdict
            from . import gpus
            # 기다리는·도는 작업은 전부, 끝난 것은 최근 100개. ★마지막 100개만 보내 작업이 많으면 도는 작업이 빠져 멈출 수 없었다
            jobs = self.queue.jobs
            live = [j for j in jobs if j.state in ("queued", "running")]
            ended = [j for j in jobs if j.state not in ("queued", "running")][-100:]
            keep = {id(j) for j in live + ended}
            return {"jobs": [asdict(j) for j in jobs if id(j) in keep],
                    "gpus": {**gpus.describe(), "busy": getattr(self.queue, "busy_gpus", list)(),
                             "lanes": len(getattr(self.queue, "lanes", [None]))}}
        if route.startswith("/jobs/") and route.endswith("/logfile"):     # 전체 로그 (저장용)
            j = self.queue.get(route.split("/")[2])
            if not j or not j.log or not Path(j.log).exists():
                return {"log": ""}
            with open(j.log, "rb") as fh:                 # 끝 20MB만 (★통째로 읽고 자르면 큰 로그에서 메모리를 다 먹었다)
                fh.seek(max(0, fh.seek(0, 2) - 20_000_000))
                return {"log": fh.read().decode("utf-8", "replace")}
        if route.startswith("/jobs/") and route.endswith("/log"):
            return {"log": self.queue.tail(route.split("/")[2], int(q.get("lines", ["200"])[0]))}
        if route.startswith("/jobs/") and route.endswith("/diagnose"):   # 실패 원인과 고칠 방법 (로그 끝부분에서)
            from .diagnose import diagnose
            return {"hints": diagnose(self.queue.tail(route.split("/")[2], 400))}
        if route.startswith("/jobs/") and route.endswith("/summary"):   # /eval은 api/review.py
            j = self.queue.get(route.split("/")[2])
            f = result_file(j, "summary")
            return json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else {"ready": False}
        if route == "/health-check":   # 데이터셋 건강 검진 (파일만 읽음)
            from .health import check
            lim = q.get("deep_limit", [""])[0]
            return check(resolve(q.get("data", [""])[0]), deep_limit=int(lim) if lim.isdigit() else 20000,
                         full_hash=q.get("full_hash", ["0"])[0] in ("1", "true"))
        if route == "/run":            # 학습 하나의 상세 (곡선·성적·해설·그림 목록)
            raw = q.get("path", [""])[0]
            if not rundetail.inside(Path(raw), self.watch_roots()):     # ★resolve(파일 시스템 접근)보다 먼저
                return None
            d = Path(resolve(raw))
            if not rundetail.inside(d, self.watch_roots()):
                return None
            got = rundetail.detail(d)
            fp = (got or {}).get("versions", {}).get("data")
            if fp:                                        # 같은 데이터로 학습한 다른 학습들
                got["versions"]["same_data"] = [o for o in self._data_index().get(fp, []) if o["path"] != str(d)][:20]
            # 계보: 시작 가중치를 준 학습(부모)·이 학습에서 시작한 학습(자식). best.pt·모델 등록부 기준이라 YOLO(또는 best.pt 있는) 학습만.
            # ★W&B·timm 학습에도 "Put in use"와 "best.pt가 아직 없다"가 떠서 틀린 안내를 했다
            if got is not None and (got.get("framework") == "ultralytics" or got.get("weights")):
                from . import lineage
                lin = lineage.lineage(d, self._run_paths())
                if lin["parent"]:
                    lin["parent"]["data"] = rundetail.detail_versions(Path(lin["parent"]["path"])).get("data")
                got["lineage"] = lin
                got["stage"] = runmeta.get(str(d)).get("stage", "")
            return got
        if route == "/names":          # 한 폴더에 NFC·NFD가 섞였는지 (맥↔윈도우 점검)
            return mixed_forms(resolve(q.get("path", [""])[0]))
        return None

    # 실행 (토큰 필수)
    def post(self, route: str, body: dict):
        for mod in API:
            got = mod.post(self, route, body)
            if got is not NOT_MINE:
                return got
        if route == "/refresh":                                # 지금 다시 읽기(수동 모드의 "새로 고침")
            self._runs_cache = None
            if getattr(self, "pace", None):
                self.pace.wake.set()
            return 200, {"ok": True}
        if route == "/config":
            c = config.update(body)
            config.apply(c)
            self._runs_cache = None
            if getattr(self, "pace", None):
                self.pace.wake.set()
            return 200, c
        if route == "/jobs/reorder":                          # 대기열 끌어서 순서 바꾸기
            ids = body.get("ids")
            ok = isinstance(ids, list) and self.queue.reorder([str(i) for i in ids])
            return (200, {"ok": True}) if ok else (400, {"error": "ids must list every waiting job once"})
        if route in ("/recipes", "/recipes/delete"):         # 학습 레시피
            from . import recipes
            try:
                rs = recipes.delete(str(body.get("name", ""))) if route.endswith("delete") else recipes.save(body.get("name", ""), body.get("params"))
            except ValueError as e:
                return 400, {"error": str(e)}
            return 200, {"recipes": rs}
        if route in ("/demo", "/demo/remove"):               # 예시 학습 만들기·지우기
            from . import demo
            self._runs_cache = None
            return 200, ({"removed": demo.remove()} if route.endswith("remove") else {"runs": demo.create()})
        if route == "/jobs/clear":                            # 끝난 작업 목록 비우기(결과 파일은 그대로)
            return 200, {"removed": self.queue.clear_finished()}
        if route == "/meta":                                  # 별표·태그·메모·목표 점수 바꾸기
            p = body.get("path")
            if not p:
                return 400, {"error": "path required"}
            if not rundetail.inside(Path(resolve(str(p))), self.watch_roots()):   # 다른 요청처럼 지켜보는 폴더 안의 학습만
                return 400, {"error": "path must be a run in a watched folder"}
            self._runs_cache = None
            if "metric" in body or "lower" in body:
                self._scanned = None      # 대표 점수가 바뀌면 다시 훑는다(★감시 스레드의 다음 차례까지 옛 점수가 보였다)
            return 200, {"meta": runmeta.update(p, {k: v for k, v in body.items() if k != "path"})}
        if route.startswith("/jobs/") and getattr(getattr(self, "queue", None), "locked_out", False):
            return 409, {"error": msg.tr("Another Epokio helper on this machine runs the queue. Stop it first (epokio agent --stop).")}
        parts = route.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "jobs":
            _, jid, action = parts
            if action == "cancel":
                return 200, {"ok": self.queue.cancel(jid)}
            if action in ("up", "down"):
                return 200, {"ok": self.queue.move(jid, -1 if action == "up" else 1)}
        return 404, {"error": "not found"}


from .server import main  # noqa: E402  (예전 경로 호환: python -m epokio.agent)

if __name__ == "__main__":
    main()

