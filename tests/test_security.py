"""네트워크에 연 agent: 보기(GET)에도 토큰, 웹 화면과 /health는 열림, 그림용 쿠키, 쓰기는 늘 토큰"""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from epokio.server_cli import QuietServer

import pytest

from epokio import auth, server


class Stub:
    def get(self, route, q):
        return {"route": route}

    def post(self, route, body):
        return 200, {"ok": True}

    def file(self, p):
        return None


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token")
    tok = auth.token()
    def start(reads):
        h = QuietServer(("127.0.0.1", 0), server.make_handler(Stub(), reads_need_token=reads))
        threading.Thread(target=h.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{h.server_port}", h
    made = []
    def go(reads):
        u, h = start(reads); made.append(h); return u
    yield go, tok
    for h in made:
        h.shutdown()


def req(url, headers=None, data=None):
    r = urllib.request.Request(url, headers=headers or {}, data=data, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_reads_need_token_when_exposed(srv):
    go, tok = srv
    u = go(True)
    assert req(u + "/runs")[0] == 401
    assert req(u + "/health")[0] == 200 and req(u + "/")[0] == 200            # 토큰을 묻는 화면은 열려 있어야 한다
    code, headers, body = req(u + "/runs", {"Authorization": "Bearer " + tok})
    assert code == 200 and json.loads(body)["route"] == "/runs"
    cookie = headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert req(u + "/runs", {"Cookie": cookie.split(";")[0]})[0] == 200         # 그림(<img>)은 쿠키로
    assert req(u + "/runs", {"Authorization": "Bearer wrong"})[0] == 401


def test_loopback_reads_stay_open_but_writes_need_token(srv):
    go, tok = srv
    u = go(False)
    code, headers, _ = req(u + "/runs")
    assert code == 200 and "Set-Cookie" not in headers
    assert req(u + "/jobs", data=b"{}")[0] == 401
    assert req(u + "/jobs", {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}, b"{}")[0] == 200


def test_login_sets_cookie_only_with_token(srv):
    go, tok = srv
    u = go(True)
    assert req(u + "/login", data=b"{}")[0] == 401
    code, headers, _ = req(u + "/login", {"Authorization": "Bearer " + tok}, b"{}")
    assert code == 200 and tok in headers.get("Set-Cookie", "")


def test_loopback_names():
    assert auth.is_loopback("127.0.0.1") and auth.is_loopback("localhost") and not auth.is_loopback("0.0.0.0")


def test_dns_rebinding_host_is_refused_on_loopback(srv):
    go, tok = srv
    u = go(False)
    assert req(u + "/runs", {"Host": "evil.example"})[0] == 403
    assert req(u + "/jobs", {"Host": "evil.example:8787", "Authorization": "Bearer " + tok}, b"{}")[0] == 403
    assert req(u + "/runs", {"Host": "localhost:8787"})[0] == 200


def test_path_reading_routes_need_token_and_health_proves_identity(srv):
    import hashlib, hmac
    go, tok = srv
    u = go(False)
    assert req(u + "/names?path=/")[0] == 401 and req(u + "/health-check?data=/etc/hosts")[0] == 401
    code, _, body = req(u + "/health?nonce=abc")
    assert code == 200 and json.loads(body)["proof"] == hmac.new(tok.encode(), b"abc", hashlib.sha256).hexdigest()


def test_host_ok():
    assert server.host_ok("127.0.0.1:8787", False) and server.host_ok("[::1]:8787", False) and server.host_ok("localhost", False)
    assert not server.host_ok("evil.example", False) and not server.host_ok(None, False)
    assert server.host_ok("gpu-box.lan:8787", True)                         # 네트워크 모드는 토큰이 지킨다


def test_only_python_interpreters_can_be_queued():
    from epokio.inputs import python_ok
    assert python_ok("") and python_ok("/opt/anaconda3/bin/python3") and python_ok("C:\\env\\python.exe".replace("\\", "/"))
    assert not python_ok("/bin/sh") and not python_ok("/usr/bin/curl") and not python_ok("/tmp/evil")


def test_shared_machine_does_not_attach_to_another_users_agent(tmp_path, monkeypatch):
    """공용 서버: 8787에 남의 Epokio가 떠 있으면 붙지 않고, 내 것이면 붙는다"""
    from epokio import port
    monkeypatch.setattr(port, "record_file", lambda: tmp_path / "agent.json")
    monkeypatch.setattr(port, "probe", lambda url, timeout=1.0: "epokio")
    monkeypatch.setattr(port, "agent_proof", lambda url, timeout=2.0: "no")      # 남의 agent(내 토큰으로 증명 못 함)
    assert port.local_url() == port.NO_AGENT
    monkeypatch.setattr(port, "agent_proof", lambda url, timeout=2.0: "ok")       # 내 agent
    assert port.local_url() == port.url_for(port.DEFAULT_PORT)


def test_reads_token_setting(tmp_path, monkeypatch):
    """공용 서버용: 설정 reads_token=always면 이 기계 안에서 보는 것도 토큰이 필요하다"""
    from epokio import config
    monkeypatch.setattr(config, "FILE", tmp_path / "config.json")
    assert config.load()["reads_token"] == "auto"
    assert config.update({"reads_token": "always"})["reads_token"] == "always"
    assert config.update({"reads_token": "turbo"})["reads_token"] == "always"     # 모르는 값은 무시
