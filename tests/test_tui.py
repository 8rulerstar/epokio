"""터미널 화면: 한글 폭 맞춤, 흔한 이름 구분, 줄 길이."""
from pathlib import Path

from epokio import tui
from epokio.scan import Run


def _run(path, **kw):
    d = dict(name=Path(path).name, path=Path(path), epoch=5, total=10, elapsed=60, eta=30, metric=0.5,
             metric_name="m", best=0.6, best_epoch=4, state="running", idle=1)
    d.update(kw)
    return Run(**d)


def test_fit_counts_wide_chars():
    assert tui.cells("시선") == 4
    assert tui.cells(tui.fit("교통표지판_테스트/train", 12)) == 12
    assert tui.fit("abc", 5) == "abc  "


def test_generic_name_gets_parent():
    assert tui.display_name(_run("/x/defect_det/train")) == "defect_det/train"
    assert tui.display_name(_run("/x/runs/detect/train2")) == "x/train2"
    assert tui.display_name(_run("/x/coco8")) == "coco8"


def test_rows_same_width():
    a = tui.row(_run("/x/a/train"), 100)
    b = tui.row(_run("/x/교통표지판/train", state="done", total=150, epoch=150), 100)
    assert tui.cells(a) == tui.cells(b)          # 한글 이름이어도 막대 끝이 맞는다


def test_once_survives_a_console_that_cannot_print_the_bar(tmp_path):
    """파이프·파일로 받으면(한국어 윈도우 cp949, 영어 윈도우 cp1252) 막대 글자 █에서 죽었다."""
    import os
    import subprocess
    import sys
    d = tmp_path / "exp"
    d.mkdir()
    (d / "args.yaml").write_text("epochs: 10\n")
    (d / "results.csv").write_text("epoch,time,metrics/mAP50-95(B)\n1,1,0.1\n2,2,0.2\n")
    env = dict(os.environ, PYTHONIOENCODING="ascii")        # 막대 글자를 못 쓰는 콘솔
    r = subprocess.run([sys.executable, "-m", "epokio.tui", "--once", "--root", str(tmp_path)],
                       capture_output=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr.decode(errors="replace")[-400:]
    assert b"exp" in r.stdout


def test_once_into_a_pipe_uses_ascii_marks_and_bars(capsys):
    """★--once를 파이프·파일로 받으면 ✓·✗·‖·█가 '?'로 깨지거나 뭉개졌다. 터미널이 아니면 ASCII로 찍는다"""
    class Feed:
        where = "folders: x"
        def runs(self):
            return [_run("/x/a/train", state="done", total=10, epoch=10), _run("/x/b/train"),
                    _run("/x/c/train", state="stalled"), _run("/x/d/train", state="failed", meta={"star": True})]
        def system(self):
            return None
    tui.print_once(Feed())                    # capsys의 stdout은 터미널이 아니다
    out = capsys.readouterr().out
    assert not set("▶…‖✗■✓★█▌·") & set(out), out
    lines, legend = out.splitlines()[2:-1], out.splitlines()[-1]
    assert [ln[0] for ln in lines] == [">", "!", "x", "+"] and "#" in lines[0] and "*" in lines[2]
    assert "NaN loss" in lines[2] and "x failed" in legend and "! stalled" in legend   # 실패는 기호만이 아니라 이유도
    assert tui.cells(lines[0]) == tui.cells(lines[3])
    assert "█" in tui.row(_run("/x/a/train"), 100)          # 터미널 화면(curses)은 그대로



SEKRET = "sekret-" * 6                 # auth.token()은 32자보다 짧은 토큰을 새로 만든다


def test_watch_sends_the_local_token_and_names_a_401(monkeypatch, tmp_path):
    """watch가 토큰을 안 보내 --lan 도우미를 '안 닿음'으로 봤다. 이 기계 토큰만 자동, 다른 기계엔 안 보낸다"""
    import io
    import urllib.error
    import urllib.request
    from epokio import auth
    monkeypatch.delenv("EPOKIO_TOKEN", raising=False)
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token")
    (tmp_path / "token").write_text(SEKRET + "\n", encoding="utf-8")
    seen = []

    def fake(req, timeout=0):
        if isinstance(req, str):                 # port.verify_agent: 이 기계의 agent라는 증명(/health?nonce)
            import hashlib, hmac, json
            from urllib.parse import parse_qs, urlsplit
            from epokio.port import proof_for
            nonce = parse_qs(urlsplit(req).query)["nonce"][0]
            return io.BytesIO(json.dumps({"proof_port": proof_for(SEKRET, nonce, urlsplit(req).port)}).encode())
        seen.append((req.full_url, req.get_header("Authorization")))
        if req.get_header("Authorization") != "Bearer " + SEKRET:
            raise urllib.error.HTTPError(req.full_url, 401, "token", {}, io.BytesIO(b""))
        return io.BytesIO(b'{"runs": [], "label": "pc"}')
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    f = tui.Feed("http://127.0.0.1:9", [])
    f.runs()
    assert seen[-1][1] == "Bearer " + SEKRET and not f.down
    g = tui.Feed("http://gpu-pc:9", [])
    g.runs()
    assert seen[-1][1] is None and g.down and "needs a token" in g.where
    w = tui.Feed("http://gpu-pc:9", [], token="wrong")
    w.runs()
    assert w.down and "rejected the token" in w.where          # ★틀린 토큰도 '토큰이 필요함'으로만 나왔다


def test_watch_does_not_hand_the_token_to_another_program_on_the_port(monkeypatch, tmp_path):
    """★공용 서버에서 남이 127.0.0.1:8787에 띄운 프로그램이 watch·트레이가 보낸 토큰을 받아 갔다.
    이 기계의 토큰은 그 주소가 HMAC 증명을 낼 때만 싣는다. 진짜 agent에는 그대로 붙는다"""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from epokio import auth, server
    from epokio.server_cli import QuietServer
    monkeypatch.delenv("EPOKIO_TOKEN", raising=False)
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token")
    auth._CACHE.pop(tmp_path / "token", None)
    mine = auth.token()
    heard = []

    class Thief(BaseHTTPRequestHandler):
        def do_GET(self):
            heard.append(self.headers.get("Authorization"))
            body = b'{"ok": true, "runs": [], "label": "x"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    class Stub:
        def get(self, route, q):
            return {"runs": [], "label": "mine"} if route == "/runs" else {"ok": True}

        def file(self, p):
            return None

    thief = ThreadingHTTPServer(("127.0.0.1", 0), Thief)
    real = QuietServer(("127.0.0.1", 0), server.make_handler(Stub(), reads_need_token=True))
    for h in (thief, real):
        threading.Thread(target=h.serve_forever, daemon=True).start()
    try:
        f = tui.Feed(f"http://127.0.0.1:{thief.server_port}", [])
        f.runs(), f.runs()
        assert heard and not any(heard), heard                   # 증명을 못 낸 곳에는 토큰이 안 간다
        g = tui.Feed(f"http://127.0.0.1:{real.server_port}", [])
        g.runs()
        assert not g.down and "mine" in g.where                  # 진짜 agent(보기에도 토큰)는 토큰으로 읽는다
        assert mine
    finally:
        thief.shutdown()
        real.shutdown()


def _proving(monkeypatch, tmp_path, honest):
    """가짜 urlopen: honest[0]이 참이면 그 포트에 이 기계의 agent(증명을 낸다), 거짓이면 다른 프로그램. 실린 Authorization을 모은다"""
    import io
    import json
    import urllib.request
    from urllib.parse import parse_qs, urlsplit
    from epokio import auth
    from epokio.port import proof_for
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token")
    (tmp_path / "token").write_text(SEKRET + "\n", encoding="utf-8")
    auth._CACHE.pop(tmp_path / "token", None)
    seen = []

    def fake(req, timeout=0):
        if isinstance(req, str):
            u = urlsplit(req)
            nonce = parse_qs(u.query)["nonce"][0]
            return io.BytesIO(json.dumps({"proof_port": proof_for(SEKRET if honest[0] else "guess", nonce, u.port)}).encode())
        seen.append(req.get_header("Authorization"))
        return io.BytesIO(b'{"runs": [], "label": "pc"}')
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return seen


def test_watch_checks_the_agent_before_every_request(monkeypatch, tmp_path):
    """★한 번 확인한 것을 기억해, 진짜 agent가 꺼진 자리에 남이 같은 포트로 뜨면 다음 요청이 이 기계의 토큰을 실었다"""
    monkeypatch.delenv("EPOKIO_TOKEN", raising=False)
    honest = [True]
    seen = _proving(monkeypatch, tmp_path, honest)
    f = tui.Feed("http://127.0.0.1:9", [])
    f.runs()
    assert seen[-1] == "Bearer " + SEKRET
    honest[0] = False                        # 같은 포트에 다른 프로그램
    f.runs()
    assert seen[-1] is None


def test_watch_sends_a_given_token_to_a_found_local_port_only_after_proof(monkeypatch, tmp_path):
    """★EPOKIO_TOKEN(다른 기계용)을 찾아 붙은 기본 포트에 확인 없이 보내, 8787의 다른 프로그램이 받았다. --agent로 준 주소에는 그대로"""
    monkeypatch.setenv("EPOKIO_TOKEN", "remote-secret")
    seen = _proving(monkeypatch, tmp_path, [False])
    tui.Feed("http://127.0.0.1:9", []).runs()
    assert seen[-1] is None
    tui.Feed("http://127.0.0.1:9", [], explicit=True).runs()
    assert seen[-1] == "Bearer remote-secret"
    tui.Feed("http://gpu-pc:9", []).runs()
    assert seen[-1] == "Bearer remote-secret"


def test_dashboard_link_carries_the_token_only_to_a_proven_agent(monkeypatch):
    """★트레이의 대시보드 항목이 루프백이면 확인 없이 '#t=토큰'을 붙여, 8787의 다른 프로그램 페이지가 자바스크립트로 읽을 수 있었다"""
    from epokio import auth, port
    monkeypatch.setattr(port, "verify_agent", lambda *a, **k: False)
    assert "#t=" not in auth.page_url("http://127.0.0.1:8787")
    monkeypatch.setattr(port, "verify_agent", lambda *a, **k: True)
    assert auth.page_url("http://127.0.0.1:8787").endswith("#t=" + auth.token())
