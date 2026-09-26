"""종단 시험: 진짜 agent 프로세스(`python -m epokio.agent`)를 띄우고 HTTP로만 묻는다.

단위 시험은 함수를 바로 부른다. 여기서는 앱·웹이 실제로 하는 것처럼 서버 밖에서 요청하고,
학습 중인 폴더는 results.csv에 에폭 줄을 덧붙여 흉내 낸다(학습은 돌지 않는다).

격리: HOME은 임시 폴더(~/.epokio 안 건드림), 포트는 OS가 준 빈 포트(8787 안 씀), git 안 씀.
멈춤·끝남 판정은 3분·30분이라 기다리지 않고 results.csv의 파일 시각을 과거로 돌려 흉내 낸다.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FORMATS = ROOT / "tests" / "fixtures" / "formats"
FRAMEWORK_RUNS = sorted(p.name for p in FORMATS.iterdir() if (p / "results.csv").exists())
DETECT_HEAD = ("epoch,time,train/box_loss,train/cls_loss,train/dfl_loss,metrics/precision(B),metrics/recall(B),"
               "metrics/mAP50(B),metrics/mAP50-95(B),val/box_loss,val/cls_loss,val/dfl_loss,lr/pg0\n")


NET_HOST = "127.0.0.2" if os.name == "nt" else "127.1"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _row(epoch: int, score: float, loss: str = "1.2") -> str:
    return f"{epoch},{epoch * 10.0},{loss},{loss},{loss},0.5,0.5,{score},{score},{loss},{loss},{loss},0.001\n"


class AgentProc:
    """HOME을 바꾼 채 agent를 띄우고, 끝나면 반드시 끈다"""

    def __init__(self, home: Path, roots: list[Path], host: str = "127.0.0.1"):
        self.home, self.port = home, _free_port()
        (home / ".epokio").mkdir(parents=True, exist_ok=True)
        # 배터리로 돌면 절전 모드가 되어 /runs가 20초씩 캐시된다. 시험은 기계 전원과 무관해야 한다
        (home / ".epokio" / "config.json").write_text(json.dumps({"scan_mode": "auto", "saver_on_battery": False}))
        env = {k: v for k, v in os.environ.items() if not k.startswith("EPOKIO")}
        # ★윈도우의 Path.home()은 HOME이 아니라 USERPROFILE을 본다. HOME만 바꿔 agent가 다른 집에 agent.json·토큰을 썼다
        # PYTHONFAULTHANDLER: 답이 없을 때 SIGABRT로 모든 스레드의 위치를 출력 파일에 받는다(아래 _hung)
        env.update(HOME=str(home), USERPROFILE=str(home), PYTHONPATH=str(ROOT / "src"), PYTHONUNBUFFERED="1",
                   PYTHONFAULTHANDLER="1")
        cmd = [sys.executable, "-m", "epokio.agent", "--port", str(self.port), "--host", host, "--label", "e2e"]
        for r in roots:
            cmd += ["--root", str(r)]
        # 출력은 파일로. ★아무도 안 읽는 PIPE는 가득 차면 agent가 print에서 멈추고, 멈춘 이유도 남지 않았다
        self.out = home / "agent.out"
        self._out = open(self.out, "w", encoding="utf-8")
        self.proc = subprocess.Popen(cmd, env=env, cwd=str(home), stdout=self._out,
                                     stderr=subprocess.STDOUT, text=True)
        # 127.0.0.2는 윈도우용(아래 NET_HOST). 나머지는 모두 127.0.0.1로 닿는다
        self.url = f"http://{'127.0.0.2' if host == '127.0.0.2' else '127.0.0.1'}:{self.port}"
        deadline = time.time() + 30             # 새로 받은 CI 기계는 첫 실행이 느리다
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("agent exited early:\n" + self._output())
            try:
                self.get("/health")
                return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("agent did not answer /health in 30 s\n" + self._hung())

    def _output(self) -> str:
        # ★_hung 이 stop() 으로 파일을 닫은 뒤 부른다. 닫힌 파일에 flush 하다 죽어 정작 멈춘 위치가 안 남았다(맥 CI)
        if not self._out.closed:
            self._out.flush()
        text = self.out.read_text(encoding="utf-8", errors="replace")
        log = self.home / ".epokio" / "agent.log"
        if log.exists():
            text += "\n--- agent.log ---\n" + log.read_text(encoding="utf-8", errors="replace")[-4000:]
        return text

    def _hung(self) -> str:
        """답이 없는 agent의 모든 스레드 위치를 받아 온다(POSIX만: faulthandler가 SIGABRT에 스택을 찍는다)"""
        if os.name != "nt" and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGABRT)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        self.stop()
        return self._output()

    def request(self, path: str, body: dict | None = None, headers: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=data, headers=headers or {})
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def get(self, path: str, **kw):
        code, _, raw = self.request(path, **kw)
        return code, json.loads(raw)

    def token(self) -> str:
        return (self.home / ".epokio" / "token").read_text().strip()

    def stop(self) -> int:
        """POSIX는 SIGTERM(도우미 종료 신호 처리를 시험한다). ★윈도우의 SIGTERM은 TerminateProcess라 atexit가 안 돌아
        agent.json이 남고 종료 코드도 1이다. 윈도우에서 실제로 끄는 길(epokio agent --stop)은 /shutdown이라 그것을 쓴다"""
        if self.proc.poll() is None:
            if os.name == "nt":
                self.shutdown_request()
            else:
                self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        if not self._out.closed:
            self._out.close()
        return self.proc.returncode

    def shutdown_request(self):
        try:
            self.request("/shutdown", body={}, headers={"Authorization": "Bearer " + self.token()})
        except OSError:
            pass


def _run_by_name(agent: AgentProc, name: str) -> dict | None:
    code, d = agent.get("/runs")
    assert code == 200
    return next((r for r in d["runs"] if r["name"] == name), None)


def _wait_run(agent: AgentProc, name: str, ok, timeout: float = 6.0) -> dict:
    """/runs는 1초 캐시다. 조건이 맞을 때까지 다시 묻는다"""
    deadline, last = time.time() + timeout, None
    while time.time() < deadline:
        last = _run_by_name(agent, name)
        if last is not None and ok(last):
            return last
        time.sleep(0.25)
    raise AssertionError(f"{name} never reached the expected state, last seen: {last}")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("e2e")
    home, runs = base / "home", base / "runs"
    home.mkdir()
    runs.mkdir()
    for name in FRAMEWORK_RUNS:                     # 프레임워크마다 끝난(또는 오래전에 멈춘) 학습 하나
        # ★copytree는 macOS에서 원본 폴더의 생성 시각까지 옮긴다. 시간 열이 없는 학습(yolov5)은 '폴더가 생긴 뒤
        #   흐른 시간'으로 에폭 길이를 어림하므로, 오래전에 받은 저장소에서는 에폭당 17시간으로 잡혀 '도는 중'이 됐다
        #   (새로 받은 CI에선 통과). 폴더는 지금 만들고 파일은 내용만 옮겨 받은 시점과 무관하게 한다
        (runs / name).mkdir()
        for f in (FORMATS / name).iterdir():
            if f.is_file():
                shutil.copyfile(f, runs / name / f.name)
        old = time.time() - 3600                    # 새로 받은 저장소는 파일 시각이 방금이라 '도는 중'으로 보인다
        for f in (runs / name).iterdir():
            os.utime(f, (old, old))
    agent = AgentProc(home, [runs])
    try:
        yield agent, runs
    finally:
        agent.stop()


# ── 보기 ────────────────────────────────────────────────────────────

def test_health_and_agent_record(world):
    agent, _ = world
    code, h = agent.get("/health")
    assert code == 200 and h["ok"] is True and h["label"] == "e2e" and h["version"]
    rec = json.loads((agent.home / ".epokio" / "agent.json").read_text())     # 앱·웹·터미널이 찾는 주소
    assert rec["port"] == agent.port
    tok = agent.home / ".epokio" / "token"
    assert len(agent.token()) >= 32
    if os.name != "nt":                  # 윈도우는 권한 비트가 없다(사용자 프로필 ACL이 막는다)
        assert (tok.stat().st_mode & 0o777) == 0o600


def test_runs_lists_every_framework_fixture(world):
    agent, runs = world
    code, d = agent.get("/runs")
    assert code == 200 and d["label"] == "e2e" and d["roots"] == [str(runs)] and d["slow_roots"] == []
    got = {r["name"]: r for r in d["runs"]}
    assert set(FRAMEWORK_RUNS) <= set(got)
    for name in FRAMEWORK_RUNS:
        r = got[name]
        assert r["epoch"] >= 5 and r["metric_name"], name           # 점수 열을 골랐다
        assert r["best"] is not None and r["best_epoch"] is not None, name
        assert r["state"] in ("done", "stopped"), name               # 옛 파일: 도는 중이 아니다
        assert r["eta"] is None, name


def test_run_detail_for_each_framework(world):
    agent, runs = world
    for name in FRAMEWORK_RUNS:
        code, d = agent.get("/run?path=" + urllib.parse.quote(str(runs / name)))
        assert code == 200, name
        assert d["column_info"], name                                # 화면이 쓰는 열 풀이
        assert "lineage" in d, name


def test_run_detail_refuses_paths_outside_watched_roots(world):
    agent, runs = world
    code, _ = agent.get("/run?path=" + urllib.parse.quote(str(agent.home)))
    assert code == 404
    code, _ = agent.get("/run?path=" + urllib.parse.quote(str(runs / ".." / "home")))
    assert code == 404


def test_runs_table_has_one_row_per_run(world):
    agent, _ = world
    code, t = agent.get("/runs/table")
    assert code == 200 and t["label"] == "e2e"
    names = [r["name"] for r in t["rows"]]
    assert set(FRAMEWORK_RUNS) <= set(names) and len(names) == len(set(names))
    assert "epochs" in t["keys"]                                     # args.yaml 설정이 칸으로


def test_system_snapshot(world):
    agent, _ = world
    code, s = agent.get("/system")
    assert code == 200 and s["label"] == "e2e" and "history" in s


def test_web_page_and_assets(world):
    agent, _ = world
    code, headers, body = agent.request("/")
    assert code == 200 and headers["Content-Type"].startswith("text/html") and b"<html" in body.lower()
    code, headers, _ = agent.request("/web/app.js")
    assert code == 200 and headers["Content-Type"].startswith("text/javascript")
    code, _, _ = agent.request("/web/../server.py")
    assert code == 404


# ── 실행 요청은 토큰 ────────────────────────────────────────────────

@pytest.mark.parametrize("path,body", [("/refresh", {}), ("/jobs", {"kind": "setup"}),
                                       ("/config", {"stall_min": 10}), ("/roots", {"path": "/"})])
def test_writes_without_token_are_refused(world, path, body):
    agent, _ = world
    code, d = agent.get(path, body=body)
    assert code == 401 and d["error"] == "token required"
    code, _ = agent.get(path, body=body, headers={"Authorization": "Bearer wrong-token-wrong-token-wrong-token"})
    assert code == 401


def test_write_with_token_is_accepted_and_nothing_ran(world):
    agent, _ = world
    code, _ = agent.get("/refresh", body={}, headers={"Authorization": "Bearer " + agent.token()})
    assert code == 200
    tok = {"Authorization": "Bearer " + agent.token()}               # /jobs 보기도 토큰 뒤(dev 보안: 열 것만 적는 방식)
    assert agent.get("/jobs", headers=tok)[1]["jobs"] == []                       # 거절된 요청은 대기열에 아무것도 안 남겼다
    assert agent.get("/config")[1]["stall_min"] == 3                 # 거절된 설정 변경도 반영 안 됨


# ── 진행 중인 학습 흉내 ─────────────────────────────────────────────

def test_live_training_progress_eta_and_best_update(world):
    agent, runs = world
    run = runs / "live"
    run.mkdir()
    (run / "args.yaml").write_text("task: detect\nepochs: 10\n")
    r = _wait_run(agent, "live", lambda r: r["state"] == "starting")  # results.csv 전: 시작했다
    assert r["epoch"] == 0 and r["total"] == 10

    csv = run / "results.csv"
    csv.write_text(DETECT_HEAD + _row(1, 0.10))
    r = _wait_run(agent, "live", lambda r: r["epoch"] == 1)
    assert r["state"] == "running" and r["total"] == 10
    assert r["best"] == pytest.approx(0.10) and r["eta"] == pytest.approx(90.0)   # 10초/에폭 × 남은 9에폭

    with csv.open("a") as f:
        f.write(_row(2, 0.30) + _row(3, 0.20))                       # 3에폭은 나빠졌다
    r = _wait_run(agent, "live", lambda r: r["epoch"] == 3)
    assert r["state"] == "running"
    assert r["best"] == pytest.approx(0.30) and r["best_epoch"] == 2 and r["metric"] == pytest.approx(0.20)
    assert r["eta"] == pytest.approx(70.0)

    with csv.open("a") as f:
        f.write("".join(_row(e, 0.3 + e / 100) for e in range(4, 11)))
    r = _wait_run(agent, "live", lambda r: r["epoch"] == 10)
    assert r["state"] == "done" and r["eta"] is None and r["best_epoch"] == 10


def test_half_written_last_line_is_not_read_as_a_score(world):
    agent, runs = world
    run = runs / "half"
    run.mkdir()
    (run / "args.yaml").write_text("epochs: 10\n")
    (run / "results.csv").write_text(DETECT_HEAD + _row(1, 0.4) + "2,20.0,1.1,1.1")   # 쓰는 도중
    r = _wait_run(agent, "half", lambda r: r["epoch"] >= 1)
    assert r["epoch"] == 1 and r["best"] == pytest.approx(0.4)


def test_training_that_stops_writing_becomes_stalled_then_stopped(world):
    agent, runs = world
    run = runs / "quiet"
    run.mkdir()
    (run / "args.yaml").write_text("epochs: 10\n")
    csv = run / "results.csv"
    csv.write_text(DETECT_HEAD + _row(1, 0.1) + _row(2, 0.2))
    _wait_run(agent, "quiet", lambda r: r["state"] == "running")
    t = time.time() - 4 * 60                                         # 4분째 새 줄 없음 (기준 3분)
    os.utime(csv, (t, t))
    r = _wait_run(agent, "quiet", lambda r: r["state"] == "stalled")
    assert r["eta"] is None and r["epoch"] == 2
    t = time.time() - 31 * 60                                        # 30분 넘으면 경고가 아니라 끝난 것
    os.utime(csv, (t, t))
    _wait_run(agent, "quiet", lambda r: r["state"] == "stopped")
    with csv.open("a") as f:                                         # 다시 쓰기 시작하면 도는 중으로
        f.write(_row(3, 0.3))
    _wait_run(agent, "quiet", lambda r: r["state"] == "running" and r["epoch"] == 3)


def test_nan_loss_marks_the_run_failed_and_detail_explains_divergence(world):
    agent, runs = world
    run = runs / "boom"
    run.mkdir()
    (run / "args.yaml").write_text("epochs: 10\n")
    csv = run / "results.csv"
    csv.write_text(DETECT_HEAD + _row(1, 0.1) + _row(2, 0.2))
    _wait_run(agent, "boom", lambda r: r["state"] == "running")
    with csv.open("a") as f:
        f.write(_row(3, 0.0, loss="nan"))
    r = _wait_run(agent, "boom", lambda r: r["state"] == "failed")
    assert r["eta"] is None and r["best"] == pytest.approx(0.2)      # 최고점은 발산 전 값
    code, d = agent.get("/run?path=" + urllib.parse.quote(str(run)))
    assert code == 200
    assert "diverged" in json.dumps(d)                               # 해설이 발산을 말한다


# ── 네트워크 모드 · 기록 정리 ───────────────────────────────────────

def test_network_mode_needs_token_for_reads(tmp_path):
    """이 기계 밖에서 닿게 띄우면 보기에도 토큰. 0.0.0.0은 실제로 LAN에 열리므로
    '127.1'(루프백 주소지만 is_loopback 목록 밖)으로 띄워 같은 경로를 탄다.
    ★윈도우의 getaddrinfo는 '127.1'을 모른다(Errno 11001). 윈도우는 127.0.0.0/8 전체가 루프백이라 127.0.0.2를 쓴다
    (맥은 lo0에 127.0.0.1만 있어 127.0.0.2를 못 연다)"""
    runs = tmp_path / "runs"
    shutil.copytree(FORMATS / "ultralytics84_detect", runs / "a")
    agent = AgentProc(tmp_path / "home", [runs], host=NET_HOST)
    try:
        assert agent.get("/health")[0] == 200                        # 살아 있는지 보기는 열려 있다
        assert agent.request("/")[0] == 200                          # 토큰 입력 화면
        for path in ("/runs", "/runs/table", "/system", "/run?path=" + urllib.parse.quote(str(runs / "a"))):
            code, d = agent.get(path)
            assert code == 401 and d["error"] == "token required", path
        auth = {"Authorization": "Bearer " + agent.token()}
        code, d = agent.get("/runs", headers=auth)
        assert code == 200 and [r["name"] for r in d["runs"]] == ["a"]
        code, d = agent.get("/runs", headers={"Cookie": "epokio_token=" + agent.token()})
        assert code == 200                                           # 웹 그림용 쿠키
    finally:
        agent.stop()


def test_agent_record_is_removed_on_shutdown(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    agent = AgentProc(tmp_path / "home", [runs])
    rec = tmp_path / "home" / ".epokio" / "agent.json"
    assert json.loads(rec.read_text(encoding="utf-8"))["port"] == agent.port
    assert agent.stop() == 0
    assert not rec.exists()                                          # 끝나면 지운다: 앱이 죽은 주소를 안 믿게
    with pytest.raises(OSError):
        urllib.request.urlopen(agent.url + "/health", timeout=1)     # 포트도 닫혔다


def test_shutdown_request_also_removes_record(tmp_path):
    """윈도우가 도우미를 끄는 길(/shutdown, epokio agent --stop). 맥·리눅스에서도 같은 길을 한 번 시험한다"""
    runs = tmp_path / "runs"
    runs.mkdir()
    agent = AgentProc(tmp_path / "home", [runs])
    rec = tmp_path / "home" / ".epokio" / "agent.json"
    assert rec.exists()
    agent.shutdown_request()
    agent.proc.wait(timeout=10)
    assert agent.stop() == 0 and not rec.exists()
