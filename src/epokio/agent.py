"""The small server that runs on the training machine. The Mac app, the web page and the terminal read state from it and queue jobs.

    epokio agent                        # this machine only (127.0.0.1)
    epokio agent --host 0.0.0.0         # other machines on the network too (a remote training PC)

Tokens (auth.py, tokens.py): starting or changing anything (POST) always needs a run token. Viewing (GET) is open
on 127.0.0.1 by default and needs a token when the helper is open to the network or started with --require-token.
A helper open to the network refuses jobs that run code unless started with --allow-run (jobs_queue.CODE_KINDS).
Standard library only, so nothing extra has to be installed on the training machine.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path

from . import autostart, config, envs, jsonfile, msg, rundetail, runmeta
from .jobs import Queue
from .watcher import Watcher
from .scan import TOO_LONG, scan, unique
from .roots import missing as roots_missing
from .ssh_source import host_of as ssh_host_of, remote_path as ssh_remote_path
from .roots import RootScanner
from .sysinfo import Sampler
from .api import API, NOT_MINE, result_file
from .api.jobs_post import TEXT_KEYS, typed_value  # noqa: F401  (keep the old import path)
from .api.roots_api import too_broad  # noqa: F401  (keep the old import path)
from .textnorm import mixed_forms, resolve

VERSION = 3                 # API level. 3: /sweep, display, lower, runs?lite, /shutdown



class Agent(Watcher):
    def __init__(self, roots: list[Path], label: str):
        config.apply()                                    # apply the saved stall threshold
        self.roots = roots
        self.discovered: set[Path] = set()      # auto-found folders (not saved to roots.json)
        self.removed: set[Path] = self._load_removed()   # folders the user removed (not re-added when found again; remembered across restarts)
        self.label = label
        self.sampler = Sampler().start()
        self.queue = Queue().start()
        from .ssh_source import Poller                    # SSH light mode: reads registered servers in the background, mirrors to ~/.epokio/ssh
        self.ssh = Poller()
        self.ssh.start()
        # Collects state changes (done, failed, stalled, early stop). The app fetches them and shows notifications.
        # If the agent showed notifications itself, notifications for remote (Windows) training would not appear on the Mac
        import threading
        from collections import deque
        self.events = deque(maxlen=200)
        self.seq = 0
        self.boot = secrets.token_hex(6)            # identifies this boot of the agent
        # The scan mode (pace) used to be created by the watch thread on its first pass. /runs before that had no pace (auto),
        #   later ones saw the battery and chose saver, so the list cache missed after start. Create it now (watching stays in the thread)
        from .pace import Pace
        self.pace = Pace()
        self._watch_thread = threading.Thread(target=self._watch, daemon=True)
        self._watch_thread.start()
        from . import sysrec                              # per-run machine record, every 15 s, separate from folder scans (sysrec.loop)
        threading.Thread(target=sysrec.loop, args=(self,), daemon=True).start()
        self.queue.on_finish = self._job_event
        self.queue.on_away = self._away_job_event         # ended with no exit code known (started before this agent)
        for j in self.queue.ended_away:                   # finished while the agent was off: alert now (previously nothing came)
            self._away_job_event(j)

    ROOTS_FILE = Path.home() / ".epokio" / "roots.json"
    REMOVED_FILE = Path.home() / ".epokio" / "removed_roots.json"

    def _load_removed(self) -> set[Path]:
        """Removed folders used to live only in memory, so auto-discovery re-added them after a restart"""
        try:
            return {Path(p) for p in json.loads(self.REMOVED_FILE.read_text(encoding="utf-8"))}
        except (OSError, ValueError, TypeError):
            return set()

    def _save_removed(self):
        self.REMOVED_FILE.parent.mkdir(parents=True, exist_ok=True)
        jsonfile.write(self.REMOVED_FILE, sorted(str(p) for p in self.removed))

    def _save_roots(self):
        """Remember folders the user added, so they survive an agent restart."""
        self.ROOTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Keep only user-added ones. Saving found folders too made the list non-empty on next start, so rediscovery stopped
        found = getattr(self, "discovered", set())
        jsonfile.write(self.ROOTS_FILE, [str(r) for r in self.roots if r not in found])

    def _data_index(self) -> dict:
        """Data fingerprint -> runs trained on that data. Cached for 30 s (previously every detail view scanned all runs)"""
        import time
        hit = getattr(self, "_didx", None)
        if hit and time.time() - hit[0] < 30:
            return hit[1]
        idx: dict = {}
        # Use the list the watch thread just scanned.
        # Previously every detail view (once per 30 s) rescanned all folders (seconds with 3,000 runs)
        sc = getattr(self, "_scanned", None)
        runs = sc[2] if sc and time.time() - sc[0] < 30 else [
            r for root in self.watch_roots() if root.exists() for r in scan(root)]
        runs = unique(runs)
        for r in runs:                                   # versions caches the fingerprint by file time
            fp = rundetail.detail_versions(Path(r.path)).get("data")
            if fp:
                idx.setdefault(fp, []).append({"path": str(r.path), "name": r.name})
        self._didx = (time.time(), idx)
        return idx

    def _run_paths(self) -> list[Path]:
        """All watched run folders. Cached for 30 s (used to find children in lineage)"""
        import time
        hit = getattr(self, "_rpaths", None)
        if hit and time.time() - hit[0] < 30:
            return hit[1]
        paths = [r.path for root in self.watch_roots() if root.exists() for r in scan(root)]
        self._rpaths = (time.time(), paths)
        return paths

    def watch_roots(self) -> list[Path]:
        from . import demo
        from .roots import expand                         # patterns like --root '/data/*/runs' are expanded on every scan
        return expand(self.roots) + [Path.home() / ".epokio" / "runs"] + ([demo.DIR] if demo.DIR.is_dir() else []) + (self.ssh.roots() if getattr(self, "ssh", None) else [])

    def file(self, path: str) -> Path | None:
        """Serve only images inside a run folder or listed in a finished eval result. Knowing the path is not enough otherwise."""
        # Check (as text) that it is inside a watched folder first. Touching the filesystem first leaked NTLM hashes via \\server\share paths
        from .textnorm import is_network
        from . import scope
        if Path(path).suffix.lower() not in rundetail.IMAGE_EXTS or is_network(path) or not scope.allows(path):
            return None
        if rundetail.inside(Path(path), self.watch_roots()):
            p = Path(resolve(path))
            if p.is_file() and rundetail.inside(p, self.watch_roots()):
                return p
            return None
        from .api import review as review_api                 # review screen (web): also images listed (as text) in eval results
        p = Path(resolve(path))                                # network paths were filtered above
        if str(p) in review_api.eval_images(self) and p.is_file():
            return p
        return None

    # resume
    def get(self, route: str, q: dict):
        from . import scope                                   # a token limited to folders sees only runs inside them (scope.py)
        return scope.get(self, route, q, self._get)

    def _get(self, route: str, q: dict):
        for mod in API:                                       # per-feature requests (review, sweep, model) live in api/
            got = mod.get(self, route, q)
            if got is not NOT_MINE:
                return got
        if route == "/health":
            from . import __version__
            # epokio: package version. setup and the tray restart an old helper if it differs from theirs
            #   Previously, after a pip upgrade the old helper kept running, served the new web page and loaded new modules (500s)
            return {"ok": True, "label": self.label, "version": VERSION, "api": VERSION, "epokio": __version__,
                    "boot": self.boot}
        if route == "/runs":
            import time
            hit = getattr(self, "_runs_cache", None)
            mode = self.pace.mode() if getattr(self, "pace", None) else "auto"
            ttl = {"manual": float("inf"), "saver": 20.0}.get(mode, 1.0)     # manual: last result until refresh is pressed (pace.py)
            # lite=1: drop curve snippets (history, up to 60 per run). The web does not use them.
            # Previously, with 3,000 runs the phone downloaded and parsed several MB every 4 s
            lite = q.get("lite", [""])[0] == "1"
            def slim(res):
                # The lite side also returns the same object (the server reuses its serialized and compressed result)
                if not lite:
                    return res
                c = getattr(self, "_lite_cache", None)
                if not c or c[0] is not res:
                    c = (res, {**res, "runs": [{k: v for k, v in d.items() if k != "history"} for d in res["runs"]]})
                    self._lite_cache = c
                return c[1]
            # Even if app, web and terminal ask at once, folders are scanned once per ttl. Rescan if the mode changed
            if hit and time.time() - hit[0] < ttl and hit[1].get("scan_mode") == mode:
                return slim(hit[1])
            # Use the result the watch thread just scanned (every 8 s). If the folder list is the same and under 15 s old, do not rescan;
            # only update 'time since last record' to now. Previously every request rescanned, taking 1.5 s with 2,000 runs
            from dataclasses import replace
            sc = getattr(self, "_scanned", None)
            now = time.time()
            # In auto mode the watch thread slows down on idle days (pace.py), so a 15 s old result showed new runs late. Use 2 s
            reuse = 2.0 if mode == "auto" else 15.0
            if sc and now - sc[0] < reuse and sc[1] == [str(r) for r in self.watch_roots() if r.exists()]:
                runs = [replace(r, idle=max(now - r.updated, 0.0)) for r in sc[2]]
                slow = getattr(self, "_slow_roots", [])
            else:
                if getattr(self, "_roots_scan", None) is None:
                    self._roots_scan = RootScanner()          # 3 s limit per folder, in parallel (roots.py)
                runs, slow = self._roots_scan.scan(self.watch_roots())
                runs = unique(runs)
                self._slow_roots = slow
            meta = runmeta.load()
            out = []
            for r in runs:
                d = r.to_dict()
                m = meta.get(runmeta.key(r.path))
                if m:
                    d["meta"] = m                       # star, tags, notes, goal
                h = ssh_host_of(str(r.path))
                if h:                                   # run mirrored over SSH: which server and path
                    d["ssh"] = {"host": h, "path": ssh_remote_path(str(r.path))}
                out.append(d)
            res = {"label": self.label, "roots": [str(r) for r in self.roots], "runs": out, "slow_roots": slow, "scan_mode": mode,
                   # missing folders (wrong --root etc.). Previously shown only as '0 runs', hiding what was wrong. The empty web page names them
                   "missing_roots": [str(r) for r in roots_missing(self.roots)],
                   # run folders unreadable due to the Windows 260-char limit (scan.TOO_LONG). WinError 3 was swallowed and they silently vanished
                   "too_long": [x for r in self.watch_roots() for x in TOO_LONG.get(str(r), [])]}
            self._runs_cache = (time.time(), res)
            return slim(res)
        if route == "/system":
            self.sampler.touch()
            s = self.sampler.latest
            return {"label": self.label, "now": s.to_dict() if s else None,
                    "history": [x.gpu for x in list(self.sampler.history)]}   # iterating the deque directly raced the sampler thread (500)
        if route == "/events":
            try:
                since = int(q.get("since", ["0"])[0])
            except ValueError:
                since = 0
            # boot: seq restarts from 1 when the agent restarts. If it changes, clients reset the cursor to 0 (previously new alerts were skipped)
            return {"seq": self.seq, "boot": self.boot, "events": [e for e in list(self.events) if e["seq"] > since]}
        if route == "/config":                                # user thresholds (stall, disk, GPU, quiet hours)
            return config.load()
        if route == "/recipes":
            from . import recipes
            return {"recipes": recipes.load()}
        if route == "/pythons":
            return {"envs": envs.list_envs()}
        if route == "/schema":                               # only discovered Pythons (any path let anyone launch an executable without a token)
            py = q.get("python", [""])[0]
            if py not in {e.get("path") for e in envs.list_envs()}:
                return 400, {"error": "unknown python"}
            return envs.schema(py, q.get("mode", ["train"])[0])
        if route == "/jobs":
            from dataclasses import asdict
            from . import gpus
            # All queued/running jobs plus the last 100 finished. Sending only the last 100 dropped running jobs, so they could not be stopped
            jobs = self.queue.jobs
            live = [j for j in jobs if j.state in ("queued", "running")]
            ended = [j for j in jobs if j.state not in ("queued", "running")][-100:]
            keep = {id(j) for j in live + ended}
            return {"jobs": [asdict(j) for j in jobs if id(j) in keep],
                    "gpus": {**gpus.describe(), "busy": getattr(self.queue, "busy_gpus", list)(),
                             "lanes": len(getattr(self.queue, "lanes", [None]))}}
        if route.startswith("/jobs/") and route.endswith("/logfile"):     # full log (for saving)
            j = self.queue.get(route.split("/")[2])
            if not j or not j.log or not Path(j.log).exists():
                return {"log": ""}
            with open(j.log, "rb") as fh:                 # last 20 MB only (reading it all then trimming used up memory on big logs)
                fh.seek(max(0, fh.seek(0, 2) - 20_000_000))
                return {"log": fh.read().decode("utf-8", "replace")}
        if route.startswith("/jobs/") and route.endswith("/log"):
            return {"log": self.queue.tail(route.split("/")[2], int(q.get("lines", ["200"])[0]))}
        if route.startswith("/jobs/") and route.endswith("/diagnose"):   # failure cause and fix (from the log tail)
            from .diagnose import diagnose
            return {"hints": diagnose(self.queue.tail(route.split("/")[2], 400))}
        if route.startswith("/jobs/") and route.endswith("/summary"):   # /eval is in api/review.py
            j = self.queue.get(route.split("/")[2])
            f = result_file(j, "summary")
            return json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else {"ready": False}
        if route == "/health-check":   # dataset health check (reads files only)
            from .health import check
            lim = q.get("deep_limit", [""])[0]
            return check(resolve(q.get("data", [""])[0]), deep_limit=int(lim) if lim.isdigit() else 20000,
                         full_hash=q.get("full_hash", ["0"])[0] in ("1", "true"))
        if route == "/run":            # details of one run (curves, scores, notes, image list)
            raw = q.get("path", [""])[0]
            if not rundetail.inside(Path(raw), self.watch_roots()):     # before resolve (filesystem access)
                return None
            d = Path(resolve(raw))
            if not rundetail.inside(d, self.watch_roots()):
                return None
            got = rundetail.detail(d)
            fp = (got or {}).get("versions", {}).get("data")
            if fp:                                        # other runs trained on the same data
                got["versions"]["same_data"] = [o for o in self._data_index().get(fp, []) if o["path"] != str(d)][:20]
            # Lineage: parent (gave starting weights), children (started from this run). Uses best.pt/model registry: YOLO or best.pt runs only.
            # Previously W&B and timm runs also showed "Put in use" and "no best.pt yet", which was wrong guidance
            if got is not None and (got.get("framework") == "ultralytics" or got.get("weights")):
                from . import lineage
                lin = lineage.lineage(d, self._run_paths())
                if lin["parent"]:
                    lin["parent"]["data"] = rundetail.detail_versions(Path(lin["parent"]["path"])).get("data")
                got["lineage"] = lin
                got["stage"] = runmeta.get(str(d)).get("stage", "")
            return got
        if route == "/names":          # whether NFC and NFD are mixed in one folder (Mac/Windows check)
            return mixed_forms(resolve(q.get("path", [""])[0]))
        return None

    # run (token required)
    RUN_REFUSED = (403, {"error": "This helper is open to the network, so it does not run training, scripts or models. "
                                  "Restart it with --allow-run to allow that, or use it from this machine (127.0.0.1)."})

    def post(self, route: str, body: dict):
        # A helper open to the network (--host 0.0.0.0, --lan) does not run code without --allow-run (jobs_queue.CODE_KINDS).
        # The queue gate (Queue.add) blocks it; /predict (bypasses the queue) and /sweeps (adds trials later) are blocked here
        from .jobs_queue import RunRefused, runs_code
        if not getattr(getattr(self, "queue", None), "code_ok", True) and runs_code(route, body):
            return self.RUN_REFUSED
        try:
            return self._post(route, body)
        except RunRefused:
            return self.RUN_REFUSED

    def _post(self, route: str, body: dict):
        for mod in API:
            got = mod.post(self, route, body)
            if got is not NOT_MINE:
                return got
        if route == "/refresh":                                # reread now ("refresh" in manual mode)
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
        if route == "/jobs/reorder":                          # drag to reorder the queue
            ids = body.get("ids")
            ok = isinstance(ids, list) and self.queue.reorder([str(i) for i in ids])
            return (200, {"ok": True}) if ok else (400, {"error": "ids must list every waiting job once"})
        if route in ("/recipes", "/recipes/delete"):         # training recipes
            from . import recipes
            try:
                rs = recipes.delete(str(body.get("name", ""))) if route.endswith("delete") else recipes.save(body.get("name", ""), body.get("params"))
            except ValueError as e:
                return 400, {"error": str(e)}
            return 200, {"recipes": rs}
        if route in ("/demo", "/demo/remove"):               # create or remove example runs
            from . import demo
            self._runs_cache = None
            return 200, ({"removed": demo.remove()} if route.endswith("remove") else {"runs": demo.create()})
        if route == "/jobs/clear":                            # clear the finished jobs list (result files stay)
            return 200, {"removed": self.queue.clear_finished()}
        if route == "/meta":                                  # change star, tags, notes, target score
            p = body.get("path")
            if not p:
                return 400, {"error": "path required"}
            if not rundetail.inside(Path(resolve(str(p))), self.watch_roots()):   # like other requests, only runs in watched folders
                return 400, {"error": "path must be a run in a watched folder"}
            self._runs_cache = None
            if "metric" in body or "lower" in body:
                self._scanned = None      # rescan on main score change (previously the old score showed until the watch thread's next turn)
            return 200, {"meta": runmeta.update(p, {k: v for k, v in body.items() if k != "path"})}
        if route.startswith("/jobs/") and getattr(getattr(self, "queue", None), "locked_out", False):
            return 409, {"error": msg.tr("Another Epokio helper on this machine runs the queue. Stop it first ({cmd}).", cmd=autostart.cli("agent --stop"))}
        parts = route.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "jobs":
            _, jid, action = parts
            if action == "cancel":
                return 200, {"ok": self.queue.cancel(jid)}
            if action in ("up", "down"):
                return 200, {"ok": self.queue.move(jid, -1 if action == "up" else 1)}
        return 404, {"error": "not found"}


from .server import main  # noqa: E402  (old path compat: python -m epokio.agent)

if __name__ == "__main__":
    main()

