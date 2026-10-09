"""`epokio setup`이 고르는 도우미와 넘기는 폴더. 진짜 HTTP 서버(내 도우미·남의 도우미)를 띄워서 본다.

★공용 서버에서 8787의 남의 도우미를 '이미 돈다'로 써서, 터널에 남의 학습이 떴다.
★지금 폴더(프로젝트)에서 찾은 runs를 'found'로 찍기만 하고 도우미에 안 넘겨, 홈에서 뜬 도우미는 영영 안 봤다.
"""
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from epokio import auth, onboard, port
from epokio.agent import Agent
from epokio.server import make_handler
from epokio.server_cli import QuietServer


@pytest.fixture
def my_helper(tmp_path):
    """이 계정의 진짜 도우미(같은 토큰, 포트에 묶인 증명). 감시 폴더 없이 뜬다"""
    agent = Agent([], "mine")
    srv = QuietServer(("127.0.0.1", 0), make_handler(agent))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield srv.server_address[1], agent
    finally:
        srv.shutdown(); srv.server_close(); agent.stop_watch()


@pytest.fixture
def their_helper():
    """다른 계정의 Epokio: /health 모양은 같지만 내 토큰으로 증명하지 못한다. POST가 오면 적어 둔다"""
    posts = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"ok": True, "label": "someone", "version": 3, "epokio": "0.8.0"}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)

        def do_POST(self):
            posts.append(self.path)
            self.send_response(200); self.end_headers(); self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield srv.server_address[1], posts
    finally:
        srv.shutdown(); srv.server_close()


def _quiet(monkeypatch, started):
    monkeypatch.setattr(onboard, "headless", lambda: False)
    monkeypatch.setattr(onboard, "start_agent", lambda roots, host, p=onboard.PORT, allow_run=False: started.append(p))
    monkeypatch.setattr(onboard, "wait_for_agent", lambda *a, **k: True)


def _found_lines(out):
    return [ln.split("found", 1)[1].strip() for ln in out.splitlines() if ln.strip().startswith("found ")]


def test_folders_found_in_the_project_folder_reach_a_running_helper(my_helper, tmp_path, monkeypatch, capsys):
    """찍은 'found' 목록 = 도우미가 보는 목록. 도는 내 도우미에는 토큰 증명 뒤 POST /roots로 준다"""
    p, agent = my_helper
    proj = tmp_path / "code" / "proj" / "runs"
    proj.mkdir(parents=True)
    started = []
    _quiet(monkeypatch, started)
    monkeypatch.setattr(onboard, "PORT", p)
    monkeypatch.setattr(onboard, "find_roots", lambda: [proj])      # setup을 프로젝트 폴더에서 돌렸다
    assert onboard.main(["--no-browser"]) == 0
    out = capsys.readouterr().out
    assert started == [] and "already running" in out
    assert [str(r) for r in agent.roots] == _found_lines(out) == [str(proj.resolve())]


def test_a_new_helper_reads_the_found_folders_when_it_starts(tmp_path, monkeypatch, capsys):
    """새로 띄우는 도우미는 roots.json을 읽고 뜬다. --root로 넘기지 않으니 5분마다 다시 찾기도 그대로다"""
    from epokio import jsonfile
    proj, gone = tmp_path / "proj" / "runs", tmp_path / "old" / "runs"
    proj.mkdir(parents=True); gone.mkdir(parents=True)
    jsonfile.write(Agent.REMOVED_FILE, [str(gone.resolve())])            # 사용자가 웹에서 뺀 폴더
    started = []
    _quiet(monkeypatch, started)
    monkeypatch.setattr(onboard, "agent_alive", lambda *a, **k: False)        # 아직 도우미가 없다
    monkeypatch.setattr(onboard, "find_roots", lambda: [gone, proj])
    assert onboard.main(["--no-browser"]) == 0
    out = capsys.readouterr().out
    assert started and _found_lines(out) == [str(proj.resolve())] == jsonfile.read(Agent.ROOTS_FILE, [])
    assert jsonfile.read(Agent.REMOVED_FILE, []) == [str(gone.resolve())]      # 뺀 폴더는 찍지도 되살리지도 않는다


def test_another_accounts_helper_is_not_reused(their_helper, tmp_path, monkeypatch, capsys):
    """남의 도우미면 다음 빈 포트에 내 것을 띄우고 그렇게 말한다. 그 도우미에는 아무것도 보내지 않는다"""
    p, posts = their_helper
    started = []
    _quiet(monkeypatch, started)
    monkeypatch.setattr(onboard, "PORT", p)
    assert onboard.main(["--root", str(tmp_path), "--no-browser"]) == 0
    out = capsys.readouterr().out
    assert len(started) == 1 and p < started[0] <= p + port.SPAN and posts == []
    assert f"Port {p} is used by another account's Epokio helper, so your helper uses port {started[0]}" in out
    assert f"http://127.0.0.1:{started[0]}/" in out and "already running" not in out


def test_a_port_you_chose_is_not_moved(their_helper, tmp_path, monkeypatch, capsys):
    p, posts = their_helper
    started = []
    _quiet(monkeypatch, started)
    assert onboard.main(["--root", str(tmp_path), "--port", str(p), "--no-browser"]) == 1
    assert started == [] and posts == [] and "another account's Epokio helper" in capsys.readouterr().out


def test_your_helper_already_moved_to_another_port_is_reused(their_helper, my_helper, tmp_path, monkeypatch, capsys):
    """남의 것이 8787을 쥔 서버에서 setup을 다시 돌리면, 지난번에 옮겨 띄운 내 도우미(기록 파일)를 다시 쓴다"""
    theirs, _ = their_helper
    mine, agent = my_helper
    port.write_record(mine, "127.0.0.1")
    started = []
    _quiet(monkeypatch, started)
    monkeypatch.setattr(onboard, "PORT", theirs)
    assert onboard.main(["--root", str(tmp_path), "--no-browser"]) == 0
    out = capsys.readouterr().out
    assert started == [] and f"uses port {mine}" in out and "already running" in out
    assert agent.roots == [tmp_path.resolve()]


def test_owner_tells_mine_theirs_and_nobody_apart(my_helper, their_helper):
    assert onboard.owner(my_helper[0]) == "mine"
    assert onboard.owner(their_helper[0]) == "theirs"
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); free = s.getsockname()[1]; s.close()
    assert onboard.owner(free) is None
