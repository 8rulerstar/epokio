"""HTTP 경계를 진짜 서버를 띄워서 확인한다. 라우팅표만 보면 do_GET을 안 거치는 걸 놓친다.

/file 과 /run 은 rundetail.inside()로 감시 폴더 밖을 막는다. 그 방어가 살아 있는지도 여기서 본다.
"""
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from epokio.server_cli import QuietServer

import pytest

from epokio import auth
from epokio.agent import Agent
from epokio.server import make_handler


AGENTS: list = []          # 시험이 감시 스레드의 이전 훑기를 버리게(방금 만든 폴더가 보이도록)


def _fresh_sweep(base):
    """감시 스레드가 방금 만든 폴더를 훑을 때까지(최대 10초) 다시 묻는다. ★한 번만 비우면 도중에 끝난 옛 훑기가 되살아났다"""
    import time
    for _ in range(40):
        AGENTS[-1]._scanned = AGENTS[-1]._sweep_cache = None
        code, body = fetch(base + "/sweep", token=auth.token())
        # 두 학습이 다 보여야 한다(★하나만 만든 순간을 훑으면 값이 다른 설정이 없었다)
        if (b'"sw1"' in body and b'"sw2"' in body) or (b"version_1" in body and b"version_2" in body):
            return code, body
        time.sleep(0.25)
    return code, body


@pytest.fixture
def agent_url(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token")
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    monkeypatch.setattr(Agent, "HOOKS_FILE", tmp_path / "hooks.json")
    root = tmp_path / "runs"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "args.yaml").write_text("epochs: 3\n", encoding="utf-8")
    (root / "demo" / "results.csv").write_text(
        "epoch,time,train/box_loss,metrics/mAP50-95(B)\n1,10,1.5,0.31\n", encoding="utf-8")

    agent = Agent([root], "test")
    AGENTS.append(agent)
    srv = QuietServer(("127.0.0.1", 0), make_handler(agent))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", root
    finally:
        srv.shutdown()
        srv.server_close()
        agent.stop_watch()      # ★남은 감시 스레드가 뒤 시험(스윕)의 sweep.DIR을 읽어 시도를 가로챘다


def fetch(url, token=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.mark.parametrize("route", ["/schema?python=/bin/sh", "/pythons", "/names?path=/",
                                   "/health-check?data=/", "/jobs", "/jobs/x/log"])
def test_dangerous_gets_are_401_without_a_token(agent_url, route):
    """토큰 없이 프로세스를 띄우거나 남의 폴더를 걷게 두면 안 된다."""
    base, _ = agent_url
    status, body = fetch(base + route)
    assert status == 401, f"{route} 가 {status} 를 돌려줬다: {body[:200]!r}"


@pytest.mark.parametrize("route", ["/health", "/runs", "/system", "/events?since=0"])
def test_view_only_gets_work_without_a_token(agent_url, route):
    """웹 화면과 트레이는 토큰 없이 돌아간다."""
    base, _ = agent_url
    status, body = fetch(base + route)
    assert status == 200
    json.loads(body)


def test_the_page_itself_is_served(agent_url):
    base, _ = agent_url
    status, body = fetch(base + "/")
    assert status == 200 and b"<!doctype html>" in body[:40].lower()


def test_a_token_opens_the_protected_gets(agent_url):
    base, _ = agent_url
    status, _ = fetch(base + "/jobs", token=auth.token())
    assert status == 200


def test_posting_without_a_token_is_401(agent_url):
    base, _ = agent_url
    req = urllib.request.Request(base + "/meta", data=b'{"path":"/x","star":true}',
                                 headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 401


def test_run_detail_refuses_a_path_outside_the_watched_roots(agent_url, tmp_path):
    """이미 있던 방어. 잠금을 옮기면서 깨지지 않았는지 같이 본다."""
    base, root = agent_url
    outside = tmp_path / "somewhere_else"
    outside.mkdir()
    status, _ = fetch(base + "/run?path=" + urllib.parse.quote(str(outside)))
    assert status == 404
    status, _ = fetch(base + "/run?path=" + urllib.parse.quote(str(root / "demo")))
    assert status == 200


def test_file_refuses_a_path_outside_the_watched_roots(agent_url, tmp_path):
    base, _ = agent_url
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"\x89PNG not yours")
    status, _ = fetch(base + "/file?path=" + urllib.parse.quote(str(secret)))
    assert status == 404


def test_network_paths_are_refused_before_touching_the_network(agent_url):
    """윈도우는 \\서버\공유 경로를 exists()로 보기만 해도 그 서버에 로그인을 시도해 NTLM 해시를 보낸다.
    토큰 없는 /file·/run이 그렇게 했다. 글자로 먼저 막는다(파일 시스템을 안 건드리니 즉시 답한다)."""
    import time
    base, _ = agent_url
    for path in (r"\\attacker-host\share\a.png", "//attacker-host/share/a.png"):
        for route in ("/file?path=", "/run?path="):
            t = time.time()
            status, _ = fetch(base + route + urllib.parse.quote(path))
            assert status == 404 and time.time() - t < 0.5, (route, path, status)


def test_foreign_host_names_are_refused_without_a_token(agent_url):
    """DNS 리바인딩: 악성 페이지가 자기 도메인을 127.0.0.1로 돌려 학습 목록을 읽는다."""
    base, _ = agent_url
    req = urllib.request.Request(base + "/runs", headers={"Host": "evil.example"})
    try:
        urllib.request.urlopen(req, timeout=5)
        status = 200
    except urllib.error.HTTPError as e:
        status = e.code
    assert status == 403
    req.add_header("Authorization", f"Bearer {auth.token()}")          # 토큰이 있으면 이름은 상관없다(MagicDNS 등)
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200


def test_an_unauthorised_post_with_a_body_gets_a_clean_401(agent_url):
    """본문을 안 읽고 401을 보내면 윈도우에서 연결이 끊겨 401이 안 닿았다."""
    base, _ = agent_url
    for _ in range(20):
        req = urllib.request.Request(base + "/jobs", data=b"x" * 200_000, method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            status = 200
        except urllib.error.HTTPError as e:
            status = e.code
        assert status == 401


@pytest.mark.parametrize("header, ok", [
    ("127.0.0.1:8787", True), ("[::1]:8787", True), ("[::1]", True), ("192.168.0.5:8787", True),
    ("localhost:8787", True), ("localhost.:8787", True), ("", True),
    ("evil.example:8787", False), ("evil.example.", False), ("127.0.0.1.evil.example", False),
])
def test_host_names_that_point_at_this_machine(header, ok):
    """DNS 리바인딩은 막되, 이 기계를 가리키는 이름은 받는다. [::1]처럼 포트가 없는 것도."""
    from epokio.server import host_trusted
    assert host_trusted(header) is ok


def test_names_starting_with_this_machines_name_are_trusted(monkeypatch):
    """pc.lan·회사 도메인·Tailscale MagicDNS(pc.tailXXXX.ts.net)로 붙은 맥 앱·웹이 '꺼져 있다'로 보였다."""
    from epokio import server
    monkeypatch.setattr(server, "HOSTNAME", "gpu-box")
    for h in ("gpu-box", "GPU-BOX.lan:8787", "gpu-box.tail1234.ts.net:8787", "gpu-box.corp.example.com."):
        assert server.host_trusted(h), h
    assert not server.host_trusted("gpu-box-evil.example")
    monkeypatch.setenv("EPOKIO_ALLOWED_HOSTS", "trainer.example, other")
    assert server.host_trusted("trainer.example:8787")


@pytest.mark.parametrize("path", [r"\\host\share\a.png", "//host/share/a.png", r"\??\UNC\host\share\a.png",
                                  r"\\?\UNC\host\share\a.png", r"\\.\pipe\x"])
def test_every_windows_network_path_form_is_caught(path):
    r"""\??\UNC\ 는 //로 시작하지 않아 처음 막은 뒤에도 NTLM 해시가 샜다(리뷰에서 실측)."""
    from epokio.textnorm import is_network
    assert is_network(path)
    assert not is_network(r"C:\runs\a.png") and not is_network("/home/me/runs/a.png")


def test_events_and_health_say_which_boot_they_come_from(agent_url, tmp_path):
    """★다시 켜면 seq가 1부터 다시 세는데 그걸 알 방법이 없어, 받는 쪽이 새 알림을 옛 번호로 보고 건너뛰었다"""
    base, root = agent_url
    _, h = fetch(base + "/health")
    _, e = fetch(base + "/events?since=0")
    boot = json.loads(h)["boot"]
    assert boot and json.loads(e)["boot"] == boot
    again = Agent([root], "again")
    again.stop_watch()
    assert again.boot != boot


def test_lite_runs_leave_out_the_curve_history(agent_url):
    """★웹은 history를 안 쓰는데 학습마다 최대 60개씩 4초마다 받았다(학습 3,000개면 폰에 수 MB)"""
    base, _ = agent_url
    full = json.loads(fetch(base + "/runs")[1])["runs"]
    lite = json.loads(fetch(base + "/runs?lite=1")[1])["runs"]
    assert "history" in full[0] and "history" not in lite[0]
    assert lite[0]["path"] == full[0]["path"]
    assert "history" in json.loads(fetch(base + "/runs")[1])["runs"][0]    # 캐시가 가벼운 쪽으로 바뀌지 않았다


def test_scan_mode_exists_before_the_first_request(agent_url):
    """★pace를 감시 스레드가 첫 바퀴에서 만들어, 그 전 요청은 auto·뒤 요청은 배터리 따라 saver가 됐다(켠 직후 캐시 빗나감)"""
    assert getattr(AGENTS[-1], "pace", None) is not None


def test_the_same_run_list_is_encoded_once(agent_url, monkeypatch):
    """★보는 화면마다, 요청마다 학습 수천 개를 다시 직렬화·압축했다. 1초 안의 같은 목록은 한 번만"""
    from epokio import server
    base, _ = agent_url
    calls = []
    real = server.json.dumps
    # ★server.json은 json 모듈 자체라 다른 스레드(감시·상태 저장)의 dumps까지 셌다. 전체 실행 중에만 흔들렸다.
    #   학습 목록(runs가 든 응답)을 만든 횟수만 센다
    def counting(obj, *a, **k):
        if isinstance(obj, dict) and "runs" in obj:
            calls.append(1)
        return real(obj, *a, **k)
    monkeypatch.setattr(server.json, "dumps", counting)
    # ★캐시는 스캔 모드가 같을 때만 다시 쓴다. 모드는 배터리 판정(pmset)을 따르는데, 노트북이 배터리로 돌면
    #   부하 중 판정이 흔들려 auto와 saver 사이를 오가며 목록을 두 번 만들었다(간헐적). 이 시험은 배터리가 아니라
    #   '같은 목록은 한 번만'을 잰다. 배터리 판정의 경합은 test_pace.py가 따로 본다
    monkeypatch.setattr(AGENTS[-1].pace, "on_battery", lambda: False)
    for _ in range(3):
        assert fetch(base + "/runs?lite=1")[0] == 200
    assert len(calls) == 1


def test_the_data_index_uses_the_watchers_scan(tmp_path, monkeypatch):
    """★상세를 열 때마다 모든 폴더를 새로 훑었다. 감시 스레드가 방금 훑은 목록을 쓴다"""
    import time
    from epokio import agent as agent_mod
    a = Agent.__new__(Agent)
    a.roots = [tmp_path]
    monkeypatch.setattr(agent_mod, "scan", lambda root: (_ for _ in ()).throw(AssertionError("scanned again")))
    a._scanned = (time.time(), [str(tmp_path)], [])
    assert a._data_index() == {}


def test_nan_in_a_request_is_refused(agent_url):
    """★목표에 NaN을 넣으면 저장되고 /runs에 실려, 브라우저·맥이 목록 전체를 못 읽었다"""
    base, root = agent_url
    req = urllib.request.Request(base + "/meta", data=b'{"path": "%s", "goal": NaN}' % str(root / "demo").replace("\\", "/").encode(),
                                 method="POST", headers={"Authorization": f"Bearer {auth.token()}", "Content-Type": "application/json"})
    try:
        code = urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        code = e.code
    assert code == 400
    json.loads(fetch(base + "/runs")[1], parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))


def test_the_sweep_table_lists_only_settings_that_differ(agent_url):
    """★비교가 4개까지라 스윕 결과를 한 표에서 볼 수 없었다. 값이 다른 설정만 싣는다"""
    base, root = agent_url
    for i, lr in enumerate(("0.01", "0.001"), 1):
        d = root / f"sw{i}"
        d.mkdir()
        (d / "args.yaml").write_text(f"epochs: 3\nlr0: {lr}\nbatch: 8\nname: sw{i}\n", encoding="utf-8")
        (d / "results.csv").write_text(f"epoch,metrics/mAP50-95(B)\n1,0.{i}\n", encoding="utf-8")
    assert fetch(base + "/sweep")[0] == 401                             # 설정 전부(비밀일 수 있다)라 토큰이 있어야 한다
    code, body = _fresh_sweep(base)
    d = json.loads(body)
    assert code == 200 and "lr0" in d["keys"] and "batch" not in d["keys"] and "name" not in d["keys"]
    sw = {r["display"]: r for r in d["runs"]}
    assert sw["sw1"]["args"]["lr0"] == "0.01" and sw["sw2"]["best"] == 0.2


def test_the_sweep_table_hides_secrets_and_paths(agent_url):
    """★/sweep를 토큰 없이 열어 두어 hparams.yaml의 wandb 키·사용자 경로를 LAN의 누구나 읽었다"""
    base, root = agent_url
    for i in (1, 2):
        d = root / "lightning_logs" / f"version_{i}"
        d.mkdir(parents=True)
        (d / "hparams.yaml").write_text(f"lr: 0.{i}\nwandb_api_key: sk-live-{i}\nhf_token: t{i}\ndata_dir: /home/alice/d{i}\n",
                                        encoding="utf-8")
        (d / "metrics.csv").write_text(f"epoch,step,val_acc\n0,9,0.{i}\n", encoding="utf-8")
    body = _fresh_sweep(base)[1]
    d = json.loads(body)
    assert "lr" in d["keys"] and not {"wandb_api_key", "hf_token", "data_dir"} & set(d["keys"])
    assert b"sk-live" not in body and b"alice" not in body


def test_health_says_which_version_and_the_page_is_read_once(agent_url, monkeypatch, tmp_path):
    """★판을 알 수 없어 옛 도우미가 새 화면을 내주고 500이 나도 아무도 몰랐다. 화면은 켤 때 한 번 읽는다"""
    import epokio
    base, _ = agent_url
    h = json.loads(fetch(base + "/health")[1])
    assert h["epokio"] == epokio.__version__ and h["api"] >= 3
    page = fetch(base + "/")[1]
    assert b"<title>Epokio</title>" in page


def test_the_helper_stops_only_with_the_token(agent_url):
    """★창 없이 도는 도우미를 끌 방법이 없었다. 토큰이 있으면 /shutdown 으로 끈다"""
    import time
    base, _ = agent_url
    req = urllib.request.Request(base + "/shutdown", data=b"{}", method="POST")
    try:
        code = urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        code = e.code
    assert code == 401 and fetch(base + "/health")[0] == 200
    req = urllib.request.Request(base + "/shutdown", data=b"{}", method="POST",
                                 headers={"Authorization": f"Bearer {auth.token()}"})
    assert urllib.request.urlopen(req, timeout=5).status == 200
    time.sleep(1.0)
    with pytest.raises(OSError):
        urllib.request.urlopen(base + "/health", timeout=2)


def test_agent_server_never_does_reverse_dns(monkeypatch):
    """★http.server 의 server_bind 가 getfqdn(역방향 DNS)을 불러, 맥 CI 에서 agent 가 시작에서 30초 넘게 멈췄다"""
    import socket
    from epokio.server_cli import QuietServer
    from http.server import BaseHTTPRequestHandler
    monkeypatch.setattr(socket, "getfqdn", lambda *a, **k: (_ for _ in ()).throw(AssertionError("reverse DNS at bind")))
    srv = QuietServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    try:
        assert srv.server_name == "127.0.0.1" and srv.server_port == srv.server_address[1] > 0
    finally:
        srv.server_close()
