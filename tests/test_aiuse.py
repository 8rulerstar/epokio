"""AI 사용량: 프로세스 훑기 · 도구가 알려 주는 값 · 두 출처의 우선순위 · 토큰"""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from epokio.server_cli import QuietServer

import pytest

from epokio import aiuse, auth, server
from epokio.api import aiuse as api_aiuse

PS = """\
 99.2 /opt/anaconda3/bin/python3
 16.4 /Applications/Claude.app/Contents/Frameworks/Claude Helper.app/Contents/MacOS/Claude Helper
  6.4 /Users/me/Library/Application Support/Claude/claude-code/2.1.275/claude.app/Contents/MacOS/claude
  3.2 /usr/local/bin/ollama
  0.0 /System/Library/.../CursorUIViewService.xpc/Contents/MacOS/CursorUIViewService
  0.5 /Applications/Epokio.app/Contents/MacOS/Epokio
"""


@pytest.fixture(autouse=True)
def clean():
    aiuse._reset_for_tests()
    yield
    aiuse._reset_for_tests()


# ── 출처 1: 프로세스 ────────────────────────────────

def test_scan_adds_up_only_ai_tools():
    got = aiuse.scan_ps(PS, ["claude", "ollama"])
    assert got == pytest.approx((16.4 + 6.4 + 3.2) / aiuse.FULL_CPU * 100)


def test_scan_ignores_lookalikes():
    """'ollama' 안의 'llama', 시스템의 CursorUIViewService를 AI 도구로 세지 않는다"""
    assert aiuse.scan_ps(PS, ["llama"]) == 0.0
    assert aiuse.scan_ps(PS, ["cursor"]) == 0.0


def test_scan_stays_in_range_and_handles_junk():
    assert aiuse.scan_ps(" 900.0 /usr/local/bin/ollama\n", ["ollama"]) == 100.0
    assert aiuse.scan_ps("garbage line\n\n", ["ollama"]) == 0.0
    assert aiuse.scan_ps("", ["ollama"]) is None
    assert aiuse.scan_ps(PS, []) == 0.0


def test_tool_list_is_configurable_and_sanitized(tmp_path, monkeypatch):
    monkeypatch.setattr(aiuse, "TOOLS_FILE", tmp_path / "ai_tools.json")
    monkeypatch.delenv("EPOKIO_AI_TOOLS", raising=False)
    assert aiuse.save_tools(["  Ollama ", "", 7, "ollama", "x" * 90]) == ["ollama", "x" * 40]
    assert aiuse.tools() == ["ollama", "x" * 40]
    assert len(aiuse.clean_tools([str(i) for i in range(99)])) == 30
    monkeypatch.setenv("EPOKIO_AI_TOOLS", "Claude, ollama")
    assert aiuse.tools() == ["claude", "ollama"]


# ── 출처 2: 도구가 알려 주는 값 ─────────────────────

@pytest.mark.parametrize("bad", ["50", None, True, float("nan"), float("inf"), [5]])
def test_report_refuses_non_numbers(bad):
    with pytest.raises(ValueError):
        aiuse.report(bad, now=100.0)


def test_report_clamps_range():
    assert aiuse.report(-5, now=100.0) == 0.0
    assert aiuse.report(400, now=200.0) == 100.0


def test_report_refuses_a_flood():
    aiuse.report(50, now=100.0)
    with pytest.raises(aiuse.TooOften):
        aiuse.report(50, now=100.1)
    assert aiuse.report(50, now=101.0) == 50.0


def test_stale_report_falls_to_zero_not_to_the_old_value():
    aiuse.report(80, now=1000.0)
    assert aiuse.reported(now=1000.0 + aiuse.FRESH_SEC) == 80.0
    assert aiuse.reported(now=1001.0 + aiuse.FRESH_SEC) is None
    # 프로세스도 조용하면 0이다. 옛 값 80으로 계속 달리지 않는다
    assert aiuse.combine(0.0, now=1001.0 + aiuse.FRESH_SEC) == (0.0, "process")
    assert aiuse.combine(None, now=1001.0 + aiuse.FRESH_SEC) == (None, "none")


def test_fresh_report_wins_over_the_process_guess():
    aiuse.report(12, now=500.0)
    assert aiuse.combine(90.0, now=505.0) == (12.0, "reported")
    # 0 보고도 존중한다: 도구가 "끝났다"고 말하면 캐릭터가 멈출 수 있어야 한다
    aiuse.report(0, now=506.0)
    assert aiuse.combine(90.0, now=507.0) == (0.0, "reported")


# ── 창구 ───────────────────────────────────────────

class Agent:
    class sampler:
        latest = None
        touched = []
        @classmethod
        def touch(cls):
            cls.touched.append(1)


def test_route_checks_the_value():
    assert api_aiuse.post(Agent, "/ai/report", {"activity": "lots"})[0] == 400
    assert api_aiuse.post(Agent, "/ai/report", {"activity": 30})[0] == 200
    assert api_aiuse.post(Agent, "/ai/report", {"activity": 30})[0] == 429
    assert api_aiuse.post(Agent, "/ai/tools", {"tools": "ollama"})[0] == 400
    assert api_aiuse.post(Agent, "/ai/nope", {}) is api_aiuse.NOT_MINE


def test_writing_needs_the_token(tmp_path, monkeypatch):
    """보기(GET /ai)는 루프백에서 열려 있고, 보고(POST)는 토큰 없이는 401"""
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token")
    tok = auth.token()

    class Stub:
        def get(self, route, q):
            return {"route": route}

        def post(self, route, body):
            return 200, {"ok": True}

        def file(self, p):
            return None

    h = QuietServer(("127.0.0.1", 0), server.make_handler(Stub(), reads_need_token=False))
    threading.Thread(target=h.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{h.server_port}"
    try:
        body = json.dumps({"activity": 30}).encode()
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(base + "/ai/report", data=body, method="POST"))
        assert e.value.code == 401
        r = urllib.request.Request(base + "/ai/report", data=body, method="POST",
                                   headers={"Authorization": f"Bearer {tok}"})
        assert urllib.request.urlopen(r).status == 200
        assert urllib.request.urlopen(base + "/ai").status == 200
    finally:
        h.shutdown()
