"""SSH 가벼운 모드: 서버에 아무것도 설치하지 않고 원격 학습을 본다(보기 전용).

흐름: 이 Mac의 agent가 `ssh -o BatchMode=yes 호스트 python3 -` 로 아래 REMOTE 스크립트(표준 라이브러리만)를 넘긴다
→ 서버가 학습 폴더를 찾아 작은 기록 파일(results.csv·args.yaml·trainer_state.json…)을 JSON으로 돌려준다
→ ~/.epokio/ssh/<호스트>/ 아래에 같은 모양으로 비춰 둔다(mirror). 파일 시각은 서버 시각에 맞춘다
→ 나머지(목록·상태·상세·알림)는 로컬 폴더와 똑같이 기존 scan·adapters가 처리한다. 판정 로직은 한 벌.

* 서버에 필요한 것: python3 하나. 비밀번호·호스트 키 확인은 우회하지 않는다(BatchMode: 키 없으면 실패로 알림)
* 폴더: 자동 탐색(홈 아래 흔한 곳, 깊이 제한) + 사용자가 적은 경로
* 그림·가중치는 가져오지 않는다. 학습 시작·스윕은 agent가 필요하다
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
EVERY = 15                        # 서버 한 대를 이 간격(초)으로 읽는다
TIMEOUT = 25
MAX_BACKOFF = 8                   # 실패한 서버는 간격을 2배씩, 최대 이 배수까지 늘린다
WORKERS = 4                       # 서버를 동시에 읽는다(죽은 서버 하나가 나머지를 늦추지 않게)
CONTROL_DIR = HOME / "ssh-control"

from .ssh_remote import REMOTE                 # 서버에서 도는 스크립트(400줄 상한 때문에 따로)

HOST_RE = re.compile(r"^[A-Za-z0-9_.@:\-\[\]]+$")      # ssh 옵션으로 읽힐 수 있는 "-"로 시작하는 이름은 막는다


def valid_host(h: str) -> bool:
    return bool(h) and not h.startswith("-") and bool(HOST_RE.match(h))


def config_hosts(path: Path | None = None) -> list[str]:
    """~/.ssh/config 의 Host 이름들(와일드카드 제외)"""
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
            text = raw.decode(locale.getpreferredencoding(False), errors="replace")   # 예전 판이 이 기계의 기본 인코딩으로 쓴 파일
        hs = json.loads(text)
        return [h for h in hs if isinstance(h, dict) and valid_host(h.get("host", ""))]
    except (OSError, ValueError):
        return []


def save(hosts: list[dict]) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix(".tmp")
    # utf-8로. ★인코딩 없이 써서 한국어 윈도우에선 cp949였고, cp949에 없는 글자가 들어오면 저장이 실패했다
    tmp.write_text(json.dumps(hosts, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(CONFIG)


def mirror_dir(host: str) -> Path:
    return MIRROR / re.sub(r"[^A-Za-z0-9_.\-]", "_", host)


def _ssh_cmd(ssh, host: str, arg: str) -> list[str]:
    """ssh 명령 줄. ssh는 프로그램 이름 하나 또는 [프로그램, 인자...] 목록"""
    cmd = [ssh] if isinstance(ssh, str) else list(ssh)
    cmd += ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
    # ★한 서버에 15초마다 새로 로그인하면 하루 5,760번이라 서버 로그가 쌓이고 fail2ban에 걸린다.
    #   접속을 재사용한다(ControlMaster). 소켓은 ~/.epokio/ssh-control 아래에만 둔다.
    #   윈도우판 OpenSSH는 ControlMaster(유닉스 소켓 공유)를 지원하지 않아 켜면 접속 자체가 실패한다.
    #   그래서 윈도우에서는 빼고 매번 새로 접속한다(느리고 서버 로그가 더 쌓인다, 상태의 note로 알린다)
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
    """서버에서 스캔 스크립트를 돌린다. 실패하면 ValueError(사람이 읽을 이유).
    have: {원격 폴더: {파일: 원격 수정 시각}}. 스크립트 앞에 붙여 표준 입력으로 보낸다(★명령줄로는 길이 제한에 걸린다)"""
    if not valid_host(host):
        raise ValueError("invalid host name")
    arg = json.dumps({"paths": cfg.get("paths", []), "auto": cfg.get("auto", True)})
    cmd = _ssh_cmd(ssh, host, arg)
    try:
        # 바이트로 넘긴다: 텍스트 모드는 윈도우에서 스크립트의 \n을 \r\n으로 바꾸고, 출력은 로캘 코드페이지로 읽는다
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
    """원격 셸에 넘길 한 인자(작은따옴표로 감싼다)"""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def apply(host: str, got: dict, now: float | None = None) -> int:
    """받은 기록을 비춰 둔다. 서버 시계와 이 Mac 시계 차이는 보정한다. 사라진 학습 폴더는 지운다. 학습 수"""
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
                if t and (d / name).exists():                    # 끝부분만 가진 파일: 앞 기록이 빠졌다고 알린다
                    kept = (d / name).stat().st_size - t[0]
                    skipped.append({"path": str(r["path"]), "name": name, "size": kept + t[1], "kept": kept})
    if base.is_dir() and not got.get("truncated"):               # 서버에서 지운 학습은 여기서도
        for f in list(base.rglob("*")):                          # ★다 못 본 스캔으로 지우면 멀쩡한 학습이 화면에서 사라진다
            if f.is_file() and f.name != _PARENT_FILE and not any(k == f.parent or k in f.parents for k in keep):
                f.unlink(missing_ok=True)
    before = {(x["path"], x["name"]) for x in _SKIPPED.get(host, [])}
    _SKIPPED[host] = skipped
    skipped = [x for x in skipped if "kept" not in x]
    if skipped and {(x["path"], x["name"]) for x in skipped} != before:     # 15초마다 같은 경고를 쌓지 않는다
        log.warning("ssh %s: skipped %d log file(s) over the size limit: %s", host, len(skipped),
                    ", ".join(x["path"] + "/" + x["name"] for x in skipped[:5]))
    return len(keep)


def _put(host: str, rpath: str, f: Path, name: str, pair: list, mt: float, skipped: list) -> None:
    """파일 하나를 비춤에 쓴다. 모양은 ssh_remote.py 머리말"""
    kind = pair[2] if len(pair) > 2 else None
    have = _HAVE.setdefault(host, {}).setdefault(rpath, {})
    tails = _TAIL.setdefault(host, {})
    if kind == "too_large":                                   # 한도를 넘어 안 왔다: 알리고, 있던 비춤은 그대로
        skipped.append({"path": rpath, "name": name, "size": int(pair[3])})
        have.pop(name, None)
        tails.pop((rpath, name), None)
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    if pair[1] is None:                                       # 서버: 지난번과 같다. 비춤이 남아 있으면 그대로
        if f.exists():
            have[name] = pair[0]
            os.utime(f, (mt, mt))
        return
    if kind in ("append", "append_b64"):                      # 뒤에 붙은 조각만 왔다
        data = pair[1].encode("utf-8") if kind == "append" else base64.b64decode(pair[1])
        t = tails.get((rpath, name), (0, 0))
        if not f.exists() or f.stat().st_size != int(pair[3]) - t[1] + t[0]:
            have.pop(name, None)                              # 이 Mac 쪽이 어긋났다: 다음번엔 통째로
            _FULL.setdefault(host, set()).add((rpath, name))
            tails.pop((rpath, name), None)
            return
        with open(f, "ab") as fh:
            fh.write(data)
    else:
        data = base64.b64decode(pair[1]) if kind == "b64" else pair[1].encode("utf-8")
        if kind == "tail":                                    # 첫 줄 + 끝부분: (첫 줄 길이, 서버에서 끝부분 시작 위치)
            tails[(rpath, name)] = (int(pair[4]), int(pair[3]))
        else:
            tails.pop((rpath, name), None)
        if not f.exists() or f.read_bytes() != data:          # 개행을 바꾸지 않고 바이트 그대로(윈도우)
            tmp = f.with_name(f.name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(f)
    _FULL.get(host, set()).discard((rpath, name))
    have[name] = pair[0]
    os.utime(f, (mt, mt))


_HAVE: dict[str, dict[str, dict[str, float]]] = {}      # 호스트 → 원격 폴더 → 파일 → 받은 원격 수정 시각
_FULL: dict[str, set] = {}                               # 호스트 → 이어 받기가 어긋나 통째로 다시 받을 (폴더, 파일)
_TAIL: dict[str, dict] = {}                              # 호스트 → (폴더, 파일) → (비춤 앞 첫 줄 길이, 서버 쪽 끝부분 시작)
_SKIPPED: dict[str, list] = {}                           # 호스트 → 지난 읽기에서 한도를 넘어 건너뛴 파일


def skipped(host: str) -> list[dict]:
    """한도를 넘은 기록 파일. "kept"가 있으면 건너뛴 게 아니라 끝부분(kept 바이트)만 받아 이어 가는 중"""
    return list(_SKIPPED.get(host, []))


def _print(f: Path) -> list | None:
    """비춤 파일의 [크기, 처음 4KB 지문, 마지막 4KB 지문]. 서버가 같은 앞부분인지 보고 뒤만 보낸다"""
    try:
        with open(f, "rb") as fh:
            size = os.fstat(fh.fileno()).st_size
            head = hashlib.md5(fh.read(min(4096, size))).hexdigest()[:16]
            fh.seek(max(0, size - 4096))
            return [size, head, hashlib.md5(fh.read()).hexdigest()[:16]]
    except OSError:
        return None


def have_for(host: str) -> dict:
    """다음 스캔에 보낼 '이미 받은 것' {폴더: {파일: [시각, 크기, 지문, 지문]}}. 비춤 파일이 지워졌으면 빼서 다시 받는다"""
    out = {}
    full = _FULL.get(host, set())
    for path, files in _HAVE.get(host, {}).items():
        d = local_dir(host, path)
        keep = {}
        for n, m in files.items():
            fp = _print(d / n) if d is not None and (path, n) not in full else None
            t = _TAIL.get(host, {}).get((path, n))
            if fp and t:                                         # 서버 기준 크기로, 처음 지문은 없음(끝 k바이트만 맞춰 본다)
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
    """서버가 준 파일 이름이 비춤 폴더 밖으로 못 나가는가. 윈도우에서 절대 경로가 되는 C: 와 \\ 도 막는다"""
    parts = re.split(r"[\\/]", name)
    return bool(name) and "" not in parts and ".." not in parts and "." not in parts and ":" not in name


_WIN_BAD = re.compile(r'[<>:"|?*%\x00-\x1f]')


def _local_name(n: str) -> str:
    """학습 폴더 이름을 이 기계에서 만들 수 있게. 윈도우에서만 금지 글자와 끝의 점·공백을 %XX로(맥·리눅스는 그대로)"""
    if sys.platform != "win32":
        return n
    n = _WIN_BAD.sub(lambda m: "%%%02X" % ord(m.group()), n)
    return n[:-1] + "%%%02X" % ord(n[-1]) if n[-1] in ". " else n


def _win_path(p: str) -> bool:
    return "\\" in p or bool(re.match(r"^[A-Za-z]:", p))


def local_dir(host: str, remote: str) -> Path | None:
    """서버 경로 → 비춤 폴더. <호스트>/<부모 경로를 한 칸으로>/<학습 폴더>: scan 깊이 안에 들고, 학습 이름은 그대로.
    윈도우 서버 경로(C:\\a\\b)는 \\ 로 가르고 부모를 그 모양대로 적어 둔다(remote_path가 되돌린다)"""
    win = _win_path(remote)
    parts = [p for p in re.split(r"[\\/]" if win else "/", remote) if p]
    if not parts or ".." in parts or "." in parts:
        return None
    parent = "\\".join(parts[:-1]) if win else "/" + "/".join(parts[:-1])
    return _parent_dir(host, parent) / _local_name(parts[-1])


_PARENT_FILE = ".remote-parent"


def _parent_dir(host: str, parent: str) -> Path:
    """부모 경로 한 칸. 윈도우에서 길면 짧은 이름으로 두고 원래 경로를 그 안의 .remote-parent에 적는다(remote_path가 읽는다).
    ★윈도우는 경로 260자 제한이라, 서버 경로를 통째로 옮긴 이름이 길면 비춤 파일을 못 만들어 그 학습이 안 보였다"""
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
    """비춰 둔 폴더면 그 호스트 이름(등록할 때 쓴 이름). ★목록마다 부르므로 글자 비교만"""
    base = str(MIRROR) + os.sep
    if not path.startswith(base):
        return None
    folder = path[len(base):].split(os.sep, 1)[0]
    return next((h["host"] for h in load() if mirror_dir(h["host"]).name == folder), folder)


def remote_path(path: str) -> str:
    """비춰 둔 폴더 → 서버의 원래 경로"""
    rest = path[len(str(MIRROR)) + 1:].split(os.sep)
    if len(rest) < 3:
        return ""
    if rest[1].startswith("~"):                                   # 길어서 줄인 부모 경로(_parent_dir)
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
    """등록된 서버를 뒤에서 차례로 읽는다. 상태는 status[호스트] = {ok, error, runs, at, python}"""

    def __init__(self, ssh: str = "ssh"):
        self.ssh = ssh
        self.status: dict[str, dict] = {}
        self._fails: dict[str, int] = {}        # 연이어 실패한 횟수(간격을 늘린다)
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
        except (ValueError, OSError) as e:       # OSError: 비춤 폴더를 못 만듦 등. 뒤 스레드가 죽지 않게
            self._fails[h] = min(self._fails.get(h, 0) + 1, 10)
            st = {**self.status.get(h, {}), "ok": False, "error": str(e), "at": time.time()}
        self.status[h] = st
        return st

    def due(self, h: str, now: float) -> bool:
        """실패한 서버는 점점 드물게 본다(2배씩, 최대 MAX_BACKOFF배)"""
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
            if hosts:                                    # 서버를 동시에: 죽은 서버의 25초 대기가 줄줄이 쌓이지 않는다
                list(pool.map(self.poll_once, hosts))
            self._wake.wait(EVERY)
            self._wake.clear()


def remove(host: str) -> None:
    save([h for h in load() if h.get("host") != host])
    shutil.rmtree(mirror_dir(host), ignore_errors=True)
