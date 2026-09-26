"""사람마다 주는 토큰: 이름·권한(read/run), 평문 저장 금지, 기존 단일 토큰 하위 호환."""
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from epokio import auth, server, tokens


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token")
    monkeypatch.setattr(tokens, "FILE", tmp_path / "tokens.json")
    return tmp_path


# ── 저장 ───────────────────────────────────────────

def test_token_is_stored_hashed_and_shown_once(_store):
    tok, entry = tokens.issue("juno", tokens.READ)
    raw = tokens.FILE.read_text()
    assert tok not in raw                                  # 평문은 파일에 없다
    assert tokens.digest(tok) in raw
    assert entry["scope"] == "read" and entry["name"] == "juno"
    assert [e["name"] for e in tokens.listed()] == ["juno"]
    assert "hash" not in tokens.listed()[0]


@pytest.mark.skipif(os.name == "nt", reason="윈도우에는 POSIX 권한이 없다")
def test_token_file_is_private(_store):
    tokens.issue("a")
    assert (tokens.FILE.stat().st_mode & 0o777) == 0o600
    assert (tokens.FILE.parent.stat().st_mode & 0o777) == 0o700


def test_verify_and_revoke(_store):
    r, e1 = tokens.issue("viewer", tokens.READ)
    w, e2 = tokens.issue("runner", tokens.RUN)
    assert tokens.verify(r) == "read" and tokens.verify(w) == "run"
    assert tokens.verify("nope") is None and tokens.verify("") is None
    assert tokens.revoke(e1["id"]) and tokens.verify(r) is None
    assert tokens.verify(w) == "run"                        # 하나를 폐기해도 나머지는 산다
    assert tokens.revoke("runner") and not tokens.revoke("runner")   # 이름으로도 폐기
    assert tokens.listed() == []


def test_bad_scope_is_refused(_store):
    with pytest.raises(ValueError):
        tokens.issue("x", "admin")


def test_broken_file_does_not_lock_everyone_out(_store):
    tokens.FILE.parent.mkdir(parents=True, exist_ok=True)
    tokens.FILE.write_text("{not json")
    assert tokens.load() == [] and tokens.verify("x") is None


def test_single_token_stays_run_scope(_store):
    """하위 호환: ~/.epokio/token 은 그대로 실행 권한"""
    old = auth.token()
    assert auth.verify(old) == "run" and auth.check("Bearer " + old)
    assert auth.verify("wrong") is None
    tokens.issue("viewer", tokens.READ)
    assert auth.verify(old) == "run"                        # 새 토큰이 생겨도 그대로


# ── HTTP ───────────────────────────────────────────

class Stub:
    def get(self, route, q):
        return {"route": route}

    def post(self, route, body):
        return 200, {"started": True}

    def file(self, p):
        return None


@pytest.fixture
def srv():
    made = []

    def go(reads):
        h = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(Stub(), reads_need_token=reads))
        threading.Thread(target=h.serve_forever, daemon=True).start()
        made.append(h)
        return f"http://127.0.0.1:{h.server_port}"
    yield go
    for h in made:
        h.shutdown()


def req(url, headers=None, data=None):
    r = urllib.request.Request(url, headers=headers or {}, data=data, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_read_only_token_can_look_but_not_start(srv, _store):
    u = srv(True)
    view, _ = tokens.issue("viewer", tokens.READ)
    assert req(u + "/runs", {"Authorization": "Bearer " + view})[0] == 200
    code, _, body = req(u + "/jobs", {"Authorization": "Bearer " + view}, b"{}")
    assert code == 403 and b"read-only" in body                 # 토큰은 맞는데 권한이 없다
    assert req(u + "/jobs/x/cancel", {"Authorization": "Bearer " + view}, b"{}")[0] == 403


def test_no_token_and_unknown_token_are_401(srv, _store):
    u = srv(True)
    assert req(u + "/jobs", data=b"{}")[0] == 401
    assert req(u + "/jobs", {"Authorization": "Bearer nope"}, b"{}")[0] == 401
    assert req(u + "/runs", {"Authorization": "Bearer nope"})[0] == 401


def test_run_token_and_legacy_token_both_start_jobs(srv, _store):
    u = srv(True)
    run, _ = tokens.issue("runner", tokens.RUN)
    for tok in (run, auth.token()):
        code, _, body = req(u + "/jobs", {"Authorization": "Bearer " + tok}, b"{}")
        assert code == 200 and json.loads(body)["started"] is True


def test_cookie_carries_the_readers_own_token(srv, _store):
    """★예전엔 쿠키에 단일 토큰을 담아, 읽기 전용으로 들어와도 실행 권한 쿠키를 받아 갔다"""
    u = srv(True)
    view, _ = tokens.issue("viewer", tokens.READ)
    code, headers, _ = req(u + "/runs", {"Authorization": "Bearer " + view})
    cookie = headers.get("Set-Cookie", "")
    assert code == 200 and view in cookie and auth.token() not in cookie
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert req(u + "/runs", {"Cookie": cookie.split(";")[0]})[0] == 200        # 그림은 쿠키로 보인다
    assert req(u + "/jobs", {"Cookie": cookie.split(";")[0]}, b"{}")[0] == 401  # 실행은 쿠키로 못 한다


def test_login_gives_a_cookie_to_read_tokens_too(srv, _store):
    u = srv(True)
    view, _ = tokens.issue("viewer", tokens.READ)
    code, headers, _ = req(u + "/login", {"Authorization": "Bearer " + view}, b"{}")
    assert code == 200 and view in headers.get("Set-Cookie", "")               # 웹 화면에 들어는 간다
    assert req(u + "/login", {"Authorization": "Bearer nope"}, b"{}")[0] == 401


def test_old_security_still_holds_with_many_tokens(srv, _store):
    """Host 화이트리스트·/health?nonce 증명은 그대로"""
    import hashlib
    import hmac
    u = srv(False)
    run, _ = tokens.issue("runner", tokens.RUN)
    assert req(u + "/runs", {"Host": "evil.example"})[0] == 403
    assert req(u + "/jobs", {"Host": "evil.example", "Authorization": "Bearer " + run}, b"{}")[0] == 403
    code, _, body = req(u + "/health?nonce=abc")
    want = hmac.new(auth.token().encode(), b"abc", hashlib.sha256).hexdigest()
    assert code == 200 and json.loads(body)["proof"] == want                   # 증명은 단일 토큰 기준 그대로
