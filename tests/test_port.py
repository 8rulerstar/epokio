"""기본 포트가 막혔을 때: 다음 빈 포트로, 기록 파일, 다른 프로그램 판별, 사용자가 준 포트는 옮기지 않음"""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from epokio.server_cli import QuietServer

import pytest

from epokio import port


def serve(body: bytes, code: int = 200):
    """/health에 body로 답하는 서버. (서버, 포트)"""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(code)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    h = QuietServer(("127.0.0.1", 0), H)
    threading.Thread(target=h.serve_forever, daemon=True).start()
    return h, h.server_address[1]


def free_block(n=3) -> int:
    """연속으로 비어 있는 포트 n개의 첫 번호"""
    for base in range(47000, 48000, 7):
        if not any(port.listening(base + i) for i in range(n)):
            return base
    raise RuntimeError("no free block")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(port.Path, "home", staticmethod(lambda: tmp_path))
    return tmp_path


def make(h, p):
    return QuietServer((h, p), BaseHTTPRequestHandler)


def test_probe_tells_epokio_from_other():
    a, pa = serve(json.dumps({"ok": True, "label": "x", "version": "1"}).encode())
    b, pb = serve(b"<html>RStudio</html>")
    c, pc = serve(b"nope", code=404)
    try:
        assert port.probe(port.url_for(pa)) == "epokio"
        assert port.probe(port.url_for(pb)) == "other"
        assert port.probe(port.url_for(pc)) == "other"
        assert port.probe(port.url_for(free_block(1))) is None
    finally:
        for s in (a, b, c):
            s.shutdown()


def test_busy_default_moves_to_next_free(monkeypatch):
    base = free_block()
    monkeypatch.setattr(port, "DEFAULT_PORT", base)
    hog = socket.socket()
    hog.bind(("127.0.0.1", base))
    hog.listen()
    try:
        srv, got = port.bind(make, "127.0.0.1", None)
        srv.server_close()
        assert got == base + 1
    finally:
        hog.close()


def test_explicit_port_is_not_moved_and_names_other_program(monkeypatch):
    other, p = serve(b"<html>RStudio</html>")
    try:
        with pytest.raises(SystemExit) as e:
            port.bind(make, "127.0.0.1", p)
        assert "another program" in str(e.value) and str(p) in str(e.value)
    finally:
        other.shutdown()


def test_existing_epokio_on_default_is_not_duplicated(monkeypatch):
    ep, p = serve(json.dumps({"ok": True, "label": "x", "version": "1"}).encode())
    monkeypatch.setattr(port, "DEFAULT_PORT", p)
    monkeypatch.setattr(port, "agent_proof", lambda url, timeout=2.0: "ok")    # 내 계정의 agent
    try:
        with pytest.raises(SystemExit) as e:
            port.bind(make, "127.0.0.1", None)
        assert "already running" in str(e.value)
    finally:
        ep.shutdown()


def test_no_free_port_in_span(monkeypatch):
    base = free_block()
    monkeypatch.setattr(port, "DEFAULT_PORT", base)
    monkeypatch.setattr(port, "SPAN", 1)
    hogs = []
    for i in range(2):
        s = socket.socket()
        s.bind(("127.0.0.1", base + i))
        s.listen()
        hogs.append(s)
    try:
        with pytest.raises(SystemExit, match="No free port"):
            port.bind(make, "127.0.0.1", None)
    finally:
        for s in hogs:
            s.close()


def test_record_written_found_and_cleared(home, monkeypatch):
    ep, p = serve(json.dumps({"ok": True, "label": "x", "version": "1"}).encode())
    monkeypatch.setattr(port, "agent_proof", lambda url, timeout=2.0: "ok")    # 내 계정의 agent
    try:
        port.write_record(p, "127.0.0.1")
        d = json.loads((home / ".epokio" / "agent.json").read_text())
        assert d["port"] == p and "pid" in d and "started" in d
        assert port.local_url() == port.url_for(p)
        assert port.wait_local(1) == port.url_for(p)
    finally:
        ep.shutdown()
    port.clear_record()
    assert not (home / ".epokio" / "agent.json").exists()


def test_stale_or_foreign_record(home, monkeypatch):
    f = home / ".epokio" / "agent.json"
    f.parent.mkdir()
    f.write_text(json.dumps({"pid": 1, "port": free_block(1), "host": "127.0.0.1"}))
    # ★이 기계에서 Epokio 앱이 돌고 있으면 기본 포트에 진짜 agent가 있어(다른 HOME이라 '남의 것') 여기가 깨졌다
    real = port.probe
    monkeypatch.setattr(port, "probe", lambda url, **k: None if url == port.url_for(port.DEFAULT_PORT) else real(url, **k))
    assert port.local_url() == port.url_for(port.DEFAULT_PORT)
    port.clear_record()                     # 남의 pid면 지우지 않는다
    assert f.exists()


def test_local_url_warns_when_default_is_other_program(home, monkeypatch, capsys):
    other, p = serve(b"<html>RStudio</html>")
    monkeypatch.setattr(port, "DEFAULT_PORT", p)
    try:
        assert port.local_url(warn=True) == port.url_for(p)
        assert "another program" in capsys.readouterr().err
    finally:
        other.shutdown()


def test_another_users_agent_on_default_port_moves_to_next(monkeypatch):
    """공용 서버: 8787이 남의 Epokio면 막히지 말고 다음 포트로 옮겨 뜬다"""
    ep, p = serve(json.dumps({"ok": True, "label": "x", "version": "1"}).encode())
    monkeypatch.setattr(port, "DEFAULT_PORT", p)
    monkeypatch.setattr(port, "agent_proof", lambda url, timeout=2.0: "no")   # 남의 agent
    try:
        srv, got = port.bind(make, "127.0.0.1", None)
        assert got != p and p < got <= p + port.SPAN
        srv.server_close()
    finally:
        ep.shutdown()
