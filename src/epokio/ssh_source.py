"""SSH light mode: watch remote training without installing anything on the server (view only).

Flow: the agent on this Mac passes the REMOTE script below (stdlib only) via `ssh -o BatchMode=yes host python3 -`
-> the server finds run folders and returns small log files (results.csv, args.yaml, trainer_state.json...) as JSON
-> they are mirrored with the same layout under ~/.epokio/ssh/<host>/. File times are set to the server times
-> everything else (list, status, details, alerts) uses the existing scan and adapters, like local folders. One set of logic.

* Server needs only python3. Password and host key checks are not bypassed (BatchMode: without a key it fails and reports)
* Folders: auto-discovery (common places under home, depth-limited) + paths the user lists
* Images and weights are not fetched. Starting training and sweeps need the agent
"""
from __future__ import annotations

import base64
import hashlib
import json
import locale
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

log = logging.getLogger(__name__)
HOME = Path.home() / ".epokio"
CONFIG = HOME / "ssh_hosts.json"
MIRROR = HOME / "ssh"
EVERY = 15                        # read each server at this interval (seconds)
TIMEOUT = 25
MAX_BACKOFF = 8                   # failing servers: interval doubles, up to this multiple
WORKERS = 4                       # read servers concurrently (one dead server does not delay the rest)
CONTROL_DIR = HOME / "ssh-control"

from .ssh_remote import REMOTE                 # script that runs on the server (separate because of the 400-line cap)

HOST_RE = re.compile(r"^[A-Za-z0-9_.@:\-\[\]]+$")      # names starting with "-" (could be read as ssh options) are rejected


def valid_host(h: str) -> bool:
    """★"."·".."도 통과해 미러 폴더가 ~/.epokio 자신이 됐다(빼기가 그 폴더를 통째로 지웠다). 글자나 숫자가 하나는 있어야 한다"""
    return bool(h) and not h.startswith("-") and bool(HOST_RE.match(h)) and bool(re.search(r"[A-Za-z0-9]", h))


def config_hosts(path: Path | None = None) -> list[str]:
    """Host names in ~/.ssh/config (wildcards excluded)"""
    p = path or Path.home() / ".ssh" / "config"
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.lower().startswith("host ") or s.lower().startswith("host\t"):
            for h in s.split()[1:]:
                if not any(c in h for c in "*?!") and h not in out:
                    out.append(h)
    return out


def load() -> list[dict]:
    try:
        raw = CONFIG.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode(locale.getpreferredencoding(False), errors="replace")   # older versions wrote the locale encoding
        hs = json.loads(text)
        return [h for h in hs if isinstance(h, dict) and valid_host(h.get("host", ""))]
    except (OSError, ValueError):
        return []


def save(hosts: list[dict]) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix(".tmp")
    # utf-8. Previously written without an encoding: cp949 on Korean Windows, and saving failed on chars cp949 lacks
    tmp.write_text(json.dumps(hosts, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(CONFIG)


def mirror_dir(host: str) -> Path:
    return MIRROR / re.sub(r"[^A-Za-z0-9_.\-]", "_", host)


def _ssh_cmd(ssh, host: str, arg: str) -> list[str]:
    """ssh command line. ssh is a program name or a [program, args...] list"""
    cmd = [ssh] if isinstance(ssh, str) else list(ssh)
    cmd += ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
    # Logging in fresh every 15 s is 5,760 logins a day per server: server logs pile up and fail2ban kicks in.
    #   So reuse the connection (ControlMaster). Sockets live only under ~/.epokio/ssh-control.
    #   Windows OpenSSH does not support ControlMaster (Unix socket sharing); enabling it makes the connection fail.
    #   So on Windows it is left out and every read logs in anew (slower, more server log; reported via the status note)
    if sys.platform != "win32":
        CONTROL_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(CONTROL_DIR, 0o700)
        except OSError:
            pass
        sock = CONTROL_DIR / (re.sub(r"[^A-Za-z0-9_.\-]", "_", host)[:40] + ".sock")
        cmd += ["-o", "ControlMaster=auto", "-o", f"ControlPath={sock}", "-o", "ControlPersist=120"]
    return cmd + [host, "python3", "-", _quote(arg)]


NO_REUSE_NOTE = ("Windows OpenSSH cannot reuse connections (ControlMaster), "
                 "so Epokio logs in to the server on every read")


def run_remote(host: str, cfg: dict, ssh="ssh", timeout: float = TIMEOUT, have: dict | None = None) -> dict:
    """Run the scan script on the server. On failure, ValueError (human-readable reason).
    have: {remote folder: {file: remote mtime}}. Prepended to the script and sent via stdin (the command line hits length limits)"""
    if not valid_host(host):
        raise ValueError("invalid host name")
    arg = json.dumps({"paths": cfg.get("paths", []), "auto": cfg.get("auto", True)})
    cmd = _ssh_cmd(ssh, host, arg)
    try:
        # pass bytes: text mode on Windows turns the script's \n into \r\n and reads output in the locale code page
        script = "HAVE_JSON = " + repr(json.dumps(have or {})) + "\n" + REMOTE
        p = subprocess.run(cmd, input=script.encode("utf-8"), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ValueError("timed out")
    except OSError as e:
        raise ValueError(str(e))
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()
        msg = err[-1] if err else f"ssh exited with {p.returncode}"
        if "python3" in msg and ("not found" in msg or "No such" in msg):
            msg = "python3 is not installed on the server"
        raise ValueError(msg[:300])
    try:
        return json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise ValueError("the server sent something Epokio could not read")


def _quote(s: str) -> str:
    """One argument for the remote shell (wrapped in single quotes)"""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def apply(host: str, got: dict, now: float | None = None) -> int:
    """Mirror the received logs, correcting server vs. this Mac clock skew, and delete vanished run folders. Returns run count"""
    now = time.time() if now is None else now
    skew = now - float(got.get("now") or now)
    base = mirror_dir(host)
    keep, skipped = set(), []
    for r in got.get("runs", []):
        d = local_dir(host, str(r.get("path", "")))
        if d is None:
            continue
        keep.add(d)
        for name, pair in (r.get("files") or {}).items():
            if _safe_rel(name):
                _put(host, str(r["path"]), d / name, name, pair, float(pair[0]) + skew, skipped)
                t = _TAIL.get(host, {}).get((str(r["path"]), name))
                if t and (d / name).exists():                    # file with only its tail: report that earlier records are missing
                    kept = (d / name).stat().st_size - t[0]
                    skipped.append({"path": str(r["path"]), "name": name, "size": kept + t[1], "kept": kept})
    if base.is_dir() and not got.get("truncated"):               # runs deleted on the server go here too
        for f in list(base.rglob("*")):                          # deleting after an incomplete scan made healthy runs vanish
            if f.is_file() and f.name != _PARENT_FILE and not any(k == f.parent or k in f.parents for k in keep):
                f.unlink(missing_ok=True)
    before = {(x["path"], x["name"]) for x in _SKIPPED.get(host, [])}
    _SKIPPED[host] = skipped
    skipped = [x for x in skipped if "kept" not in x]
    if skipped and {(x["path"], x["name"]) for x in skipped} != before:     # do not repeat the same warning every 15 s
        log.warning("ssh %s: skipped %d log file(s) over the size limit: %s", host, len(skipped),
                    ", ".join(x["path"] + "/" + x["name"] for x in skipped[:5]))
    return len(keep)


def _put(host: str, rpath: str, f: Path, name: str, pair: list, mt: float, skipped: list) -> None:
    """Write one file to the mirror. Format: see the ssh_remote.py header"""
    kind = pair[2] if len(pair) > 2 else None
    have = _HAVE.setdefault(host, {}).setdefault(rpath, {})
    tails = _TAIL.setdefault(host, {})
    if kind == "too_large":                                   # over the limit, not sent: report it, keep the existing mirror
        skipped.append({"path": rpath, "name": name, "size": int(pair[3])})
        have.pop(name, None)
        tails.pop((rpath, name), None)
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    if pair[1] is None:                                       # server: unchanged since last time. keep the mirror if present
        if f.exists():
            have[name] = pair[0]
            os.utime(f, (mt, mt))
        return
    if kind in ("append", "append_b64"):                      # only the appended chunk arrived
        data = pair[1].encode("utf-8") if kind == "append" else base64.b64decode(pair[1])
        t = tails.get((rpath, name), (0, 0))
        if not f.exists() or f.stat().st_size != int(pair[3]) - t[1] + t[0]:
            have.pop(name, None)                              # this Mac side is out of sync: fetch whole next time
            _FULL.setdefault(host, set()).add((rpath, name))
            tails.pop((rpath, name), None)
            return
        with open(f, "ab") as fh:
            fh.write(data)
    else:
        data = base64.b64decode(pair[1]) if kind == "b64" else pair[1].encode("utf-8")
        if kind == "tail":                                    # first line + tail: (first line length, tail start offset on server)
            tails[(rpath, name)] = (int(pair[4]), int(pair[3]))
        else:
            tails.pop((rpath, name), None)
        if not f.exists() or f.read_bytes() != data:          # raw bytes, newlines untouched (Windows)
            tmp = f.with_name(f.name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(f)
    _FULL.get(host, set()).discard((rpath, name))
    have[name] = pair[0]
    os.utime(f, (mt, mt))


_HAVE: dict[str, dict[str, dict[str, float]]] = {}      # host -> remote folder -> file -> received remote mtime
_FULL: dict[str, set] = {}                               # host -> (folder, file) to refetch whole after resume went out of sync
_TAIL: dict[str, dict] = {}                              # host -> (folder, file) -> (mirror first-line length, server tail start)
_SKIPPED: dict[str, list] = {}                           # host -> files skipped over the limit on the last read


def skipped(host: str) -> list[dict]:
    """Log files over the limit. With "kept", not skipped: only the tail (kept bytes) is fetched and continued"""
    return list(_SKIPPED.get(host, []))


def _print(f: Path) -> list | None:
    """[size, first 4KB hash, last 4KB hash] of a mirror file. The server checks the head matches and sends only the rest"""
    try:
        with open(f, "rb") as fh:
            size = os.fstat(fh.fileno()).st_size
            head = hashlib.md5(fh.read(min(4096, size))).hexdigest()[:16]
            fh.seek(max(0, size - 4096))
            return [size, head, hashlib.md5(fh.read()).hexdigest()[:16]]
    except OSError:
        return None


def have_for(host: str) -> dict:
    """'Already have' for the next scan: {folder: {file: [mtime, size, hash, hash]}}. Deleted mirror files get refetched"""
    out = {}
    full = _FULL.get(host, set())
    for path, files in _HAVE.get(host, {}).items():
        d = local_dir(host, path)
        keep = {}
        for n, m in files.items():
            fp = _print(d / n) if d is not None and (path, n) not in full else None
            t = _TAIL.get(host, {}).get((path, n))
            if fp and t:                                         # server-side size, no head hash (match only the last k bytes)
                k = min(4096, fp[0] - t[0])
                with open(d / n, "rb") as fh:
                    fh.seek(fp[0] - k)
                    fp = [fp[0] - t[0] + t[1], None, hashlib.md5(fh.read(k)).hexdigest()[:16], k]
            if fp:
                keep[n] = [m] + fp
        if keep:
            out[path] = keep
    return out


def _safe_rel(name: str) -> bool:
    """Can a server-given file name not escape the mirror folder? Also blocks C: and \\ which become absolute paths on Windows"""
    parts = re.split(r"[\\/]", name)
    return bool(name) and "" not in parts and ".." not in parts and "." not in parts and ":" not in name


_WIN_BAD = re.compile(r'[<>:"|?*%\x00-\x1f]')


def _local_name(n: str) -> str:
    """Make a run folder name creatable here. On Windows only, bad chars, trailing dots/spaces become %XX (Mac/Linux as is)"""
    if sys.platform != "win32":
        return n
    n = _WIN_BAD.sub(lambda m: "%%%02X" % ord(m.group()), n)
    return n[:-1] + "%%%02X" % ord(n[-1]) if n[-1] in ". " else n


def _win_path(p: str) -> bool:
    return "\\" in p or bool(re.match(r"^[A-Za-z]:", p))


def local_dir(host: str, remote: str) -> Path | None:
    """Server path -> mirror folder. <host>/<parent path as one level>/<run folder>: stays within scan depth, run name unchanged.
    Windows server paths (C:\\a\\b) split on \\ and the parent is written in that form (remote_path reverses it)"""
    win = _win_path(remote)
    parts = [p for p in re.split(r"[\\/]" if win else "/", remote) if p]
    if not parts or ".." in parts or "." in parts:
        return None
    parent = "\\".join(parts[:-1]) if win else "/" + "/".join(parts[:-1])
    return _parent_dir(host, parent) / _local_name(parts[-1])


_PARENT_FILE = ".remote-parent"


def _parent_dir(host: str, parent: str) -> Path:
    """One level for the parent path. Long ones on Windows get a short name; original path in its .remote-parent (for remote_path).
    Windows has a 260-char path limit; previously a long name copied from the server path made mirror files fail, hiding that run"""
    q = urllib.parse.quote(parent, safe="")
    if sys.platform != "win32" or len(q) <= 60:
        return mirror_dir(host) / q
    d = mirror_dir(host) / ("~" + hashlib.sha1(parent.encode("utf-8")).hexdigest()[:12])
    f = d / _PARENT_FILE
    if not f.exists():
        try:
            d.mkdir(parents=True, exist_ok=True)
            f.write_text(parent, encoding="utf-8")
        except OSError:
            pass
    return d


def host_of(path: str) -> str | None:
    """Host name (as registered) if this is a mirrored folder. Called for every list entry, so string comparison only"""
    base = str(MIRROR) + os.sep
    if not path.startswith(base):
        return None
    folder = path[len(base):].split(os.sep, 1)[0]
    return next((h["host"] for h in load() if mirror_dir(h["host"]).name == folder), folder)


def remote_path(path: str) -> str:
    """Mirrored folder -> original path on the server"""
    rest = path[len(str(MIRROR)) + 1:].split(os.sep)
    if len(rest) < 3:
        return ""
    if rest[1].startswith("~"):                                   # shortened long parent path (_parent_dir)
        try:
            parent = (MIRROR / rest[0] / rest[1] / _PARENT_FILE).read_text(encoding="utf-8")
        except OSError:
            return ""
    else:
        parent = urllib.parse.unquote(rest[1])
    name = urllib.parse.unquote(rest[2]) if sys.platform == "win32" else rest[2]
    sep = "\\" if _win_path(parent) else "/"
    return parent.rstrip(sep) + sep + sep.join([name] + rest[3:])


class Poller:
    """Reads registered servers in turn in the background. Status is status[host] = {ok, error, runs, at, python}"""

    def __init__(self, ssh: str = "ssh"):
        self.ssh = ssh
        self.status: dict[str, dict] = {}
        self._fails: dict[str, int] = {}        # consecutive failures (widens the interval)
        self._wake = threading.Event()
        self._stop = False

    def roots(self) -> list[Path]:
        return [mirror_dir(h["host"]) for h in load() if h.get("on", True)]

    def poll_once(self, host: dict) -> dict:
        h = host["host"]
        try:
            got = run_remote(h, host, self.ssh, have=have_for(h))
            n = apply(h, got)
            st = {"ok": True, "error": None, "runs": n, "at": time.time(), "python": got.get("python"),
                  "truncated": bool(got.get("truncated")), "skipped": skipped(h),
                  "note": NO_REUSE_NOTE if sys.platform == "win32" else None}
            self._fails.pop(h, None)
        except (ValueError, OSError) as e:       # OSError: mirror folder not creatable, etc. Keeps the thread alive
            self._fails[h] = min(self._fails.get(h, 0) + 1, 10)
            st = {**self.status.get(h, {}), "ok": False, "error": str(e), "at": time.time()}
        self.status[h] = st
        return st

    def due(self, h: str, now: float) -> bool:
        """Failing servers are checked less and less often (doubling, up to MAX_BACKOFF times)"""
        st = self.status.get(h)
        if not st or st.get("ok"):
            return True
        wait = EVERY * min(2 ** self._fails.get(h, 1), MAX_BACKOFF)
        return now - st.get("at", 0) >= wait

    def wake(self):
        self._wake.set()

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="ssh-poller").start()

    def _loop(self):
        import concurrent.futures as cf
        pool = cf.ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="ssh")
        while not self._stop:
            now = time.time()
            hosts = [h for h in load() if h.get("on", True) and self.due(h["host"], now)]
            if hosts:                                    # servers in parallel: 25 s waits on dead servers do not stack up
                list(pool.map(self.poll_once, hosts))
            self._wake.wait(EVERY)
            self._wake.clear()


def remove(host: str) -> None:
    save([h for h in load() if h.get("host") != host])
    d = mirror_dir(host)
    if valid_host(host) and d.resolve().parent == MIRROR.resolve():   # 미러 폴더 안의 한 칸만 지운다
        shutil.rmtree(d, ignore_errors=True)
