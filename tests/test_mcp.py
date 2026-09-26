"""MCP 도구 층. mcp 패키지 없이도 돌게 작은 가짜 MCPServer를 끼운다(도구 함수만 본다)."""
import importlib
import json
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


@pytest.fixture
def mcp(monkeypatch, tmp_path):
    fake = types.ModuleType("mcp.server.mcpserver")

    class MCPServer:
        def __init__(self, **kw):
            pass

        def tool(self, **kw):
            return lambda f: f

    fake.MCPServer = MCPServer
    for name in ("mcp", "mcp.server"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", fake)
    monkeypatch.delitem(sys.modules, "epokio.mcp_server", raising=False)
    m = importlib.import_module("epokio.mcp_server")
    yield m
    sys.modules.pop("epokio.mcp_server", None)


def _serve(routes):
    """경로 → (코드, 본문)을 돌려주는 작은 agent 흉내"""
    seen = []

    class H(BaseHTTPRequestHandler):
        def _reply(self):
            seen.append((self.command, self.path))
            code, body = routes.get(self.path.split("?")[0], (404, {"error": "not found"}))
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        do_GET = do_POST = _reply

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


def test_the_agents_reason_reaches_the_assistant(mcp, monkeypatch):
    """★urllib 예외 그대로라 도우미는 'HTTP Error 400: Bad Request'만 봤다. agent가 말한 이유를 전한다"""
    srv, _ = _serve({"/jobs": (400, {"error": "Missing: data"})})
    monkeypatch.setattr(mcp, "AGENT", f"http://127.0.0.1:{srv.server_address[1]}")
    with pytest.raises(mcp.AgentError, match="Missing: data"):
        mcp._post("/jobs", {"kind": "train"})
    srv.shutdown(); srv.server_close()
    with pytest.raises(mcp.AgentError, match="not running"):
        mcp._get("/runs")                                   # 꺼진 agent: 켜는 방법을 알려 준다


def test_training_needs_a_discovered_python_and_no_output_overrides(mcp, monkeypatch):
    """★아무 실행 파일이나 'python'으로 받아 대기열이 띄웠다. extra로 project·exist_ok를 바꿔 옛 학습을 덮을 수 있었다"""
    srv, seen = _serve({"/pythons": (200, {"envs": [{"path": "/envs/yolo/bin/python", "ready": True}]}),
                        "/jobs": (200, {"id": "j1"})})
    monkeypatch.setattr(mcp, "AGENT", f"http://127.0.0.1:{srv.server_address[1]}")
    with pytest.raises(mcp.AgentError, match="/envs/yolo/bin/python"):
        mcp.start_training("d.yaml", "/bin/sh")
    with pytest.raises(mcp.AgentError, match="project"):
        mcp.start_training("d.yaml", "/envs/yolo/bin/python", extra={"project": "/etc", "imgsz": 640})
    with pytest.raises(mcp.AgentError, match="cfg"):                   # 설정 yaml로 save_dir·resume을 바꾸는 우회도
        mcp.start_training("d.yaml", "/envs/yolo/bin/python", extra={"cfg": "x.yaml"})
    assert not any(m == "POST" for m, _ in seen)
    assert mcp.start_training("d.yaml", "/envs/yolo/bin/python", extra={"imgsz": 640}) == {"id": "j1"}
    srv.shutdown(); srv.server_close()


def test_analyze_run_asks_the_agent_and_stays_small(mcp, monkeypatch):
    """★MCP 프로세스가 직접 읽어 다른 기계·HF·Keras 학습은 늘 실패했다. 곡선은 마지막 10개만"""
    srv, seen = _serve({"/run": (200, {"name": "exp", "framework": "keras", "heads": [], "notes": [],
                                       "args": {}, "columns": {"epoch": list(range(100))}, "images": []})})
    monkeypatch.setattr(mcp, "AGENT", f"http://127.0.0.1:{srv.server_address[1]}")
    got = mcp.analyze_run("/far/away/run")
    assert got["framework"] == "keras" and got["last_epochs"]["epoch"] == list(range(90, 100))
    assert seen[0][1].startswith("/run?path=")
    srv.shutdown(); srv.server_close()


def test_sweep_table_puts_the_best_run_first(mcp, monkeypatch):
    srv, _ = _serve({"/sweep": (200, {"keys": ["lr0"], "runs": [
        {"display": "a", "best": 0.3, "lower": False, "args": {"lr0": "0.01"}},
        {"display": "b", "best": 0.5, "lower": False, "args": {"lr0": "0.001"}},
        {"display": "c", "best": None, "args": {"lr0": "0.1"}}]})})
    monkeypatch.setattr(mcp, "AGENT", f"http://127.0.0.1:{srv.server_address[1]}")
    got = mcp.sweep_table()
    assert got["settings"] == ["lr0"] and [r["display"] for r in got["groups"][0]["runs"]] == ["b", "a"]
    srv.shutdown(); srv.server_close()


def test_sweep_table_ranks_each_score_on_its_own(mcp, monkeypatch):
    """★손실(낮을수록)과 mAP(높을수록)가 섞이면 한 방향으로 줄 세워 손실이 가장 큰 학습을 1등으로 돌려줬다"""
    srv, _ = _serve({"/sweep": (200, {"keys": [], "runs": [
        {"display": "m1", "best": 0.5, "lower": False, "metric_name": "map"},
        {"display": "l1", "best": 2.0, "lower": True, "metric_name": "val_loss"},
        {"display": "l2", "best": 0.9, "lower": True, "metric_name": "val_loss"}]})})
    monkeypatch.setattr(mcp, "AGENT", f"http://127.0.0.1:{srv.server_address[1]}")
    g = {x["score"]: x for x in mcp.sweep_table()["groups"]}
    assert [r["display"] for r in g["val_loss"]["runs"]] == ["l2", "l1"] and g["val_loss"]["lower_is_better"]
    srv.shutdown(); srv.server_close()
