"""웹 화면이 패키지에 들어 있고, 외부 주소를 부르지 않는지(오프라인 LAN에서도 되어야 한다). ntfy 판별."""
from epokio.server_cli import QuietServer
import re
from pathlib import Path

import pytest          # ★없으면 node가 없는 기계에서 pytest.skip이 NameError로 실패했다(test_every_web_script_parses)

from epokio import notify

PAGE = Path(__file__).resolve().parent.parent / "src" / "epokio" / "web" / "index.html"
WEB = PAGE.parent
# index.html이 부르는 순서(lang.js가 먼저, main.js가 마지막)
SCRIPTS = ("lang.js", "app.js", "compare.js", "alerts.js", "train.js", "queue.js", "versions.js", "review.js", "sweeps.js", "table.js", "main.js")


def _all():
    """화면 코드 전부(index.html + 나눈 스크립트). 문자열 검사는 파일이 어디로 옮겨 가도 따라가게 이것을 본다"""
    # ★SCRIPTS만 읽어 classes·machine·ssh·snapshots.js의 문장은 번역 검사를 빠져나갔다. 폴더의 스크립트 전부를 본다
    rest = sorted(f.name for f in WEB.glob("*.js") if f.name not in SCRIPTS)
    return "\n".join([PAGE.read_text(encoding="utf-8")] + [(WEB / f).read_text(encoding="utf-8") for f in (*SCRIPTS, *rest)])


def test_page_exists_and_is_self_contained():
    html = PAGE.read_text(encoding="utf-8")
    assert "<title>Epokio</title>" in html
    assert not re.search(r'(src|href)="https?://', html)          # CDN·외부 스크립트 없음
    js = _all()
    assert 'fetch(p' in js and 'api("runs?lite=1")' in js           # 같은 agent의 API만 부른다
    for f in SCRIPTS + ("style.css", "tokens.css"):
        assert f in html                                           # 나눈 파일을 다 불러온다
    assert html.index("web/lang.js") < html.index("web/app.js") < html.index("web/main.js")   # 언어가 먼저, 시작은 마지막


def test_page_asks_the_agent_in_its_own_language():
    """검진·해설 문장은 화면과 같은 언어로 받아야 한다. 안 실으면 브라우저 언어로 와서
    영어 틀 안에 한국어 문장이 섞였다(2026-09-25 윈도우 실측). 화면 언어(LANG)를 그대로 싣는다."""
    html = _all()
    assert '"Accept-Language": LANG' in html
    assert '"Accept-Language": "en"' not in html
    assert 'startsWith("ko") ? "ko" : "en"' in html       # 화면이 아는 언어는 둘뿐. agent도 같은 둘로 답한다
    assert '"en-GB"' not in html.replace('LANG === "ko" ? "ko-KR" : "en-GB"', "")   # 시각도 화면 언어로


_CALL = re.compile(r"""\bt\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|`((?:[^`\\]|\\.)*)`)""")
_CTX = re.compile(r"""\btc\(\s*"(\w+)",\s*"((?:[^"\\]|\\.)*)\"""")
_KEY = re.compile(r"""^\s*"((?:[^"\\]|\\.)*)"\s*:|,\s*"((?:[^"\\]|\\.)*)"\s*:""", re.M)


def _ko_keys(html):
    block = html[html.index("const KO = {"):]
    block = block[:block.index("\n};")]
    return {a or b for a, b in _KEY.findall(block)}


def test_every_page_string_has_korean():
    """화면 문장은 t("영어")로 쓰고 KO 표에 한국어를 둔다(msg.py와 같은 방식). 빠지면 한국어 화면에 영어가 섞인다."""
    html = _all()
    ko = _ko_keys(html)
    used = {next(g for g in m.groups() if g is not None) for m in _CALL.finditer(html)}
    used = {s for s in used if "${" not in s}
    assert len(used) > 150                                          # 정규식이 조용히 아무것도 못 잡는 일이 없게
    missing = sorted(s for s in used if s not in ko)
    missing += sorted(f"{c}|{s}" for c, s in _CTX.findall(html) if f"{c}|{s}" not in ko and s not in ko)
    assert not missing, missing


def test_korean_keeps_the_placeholders():
    html = _all()
    block = html[html.index("const KO = {"):]
    block = block[:block.index("\n};")]
    pair = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*\n?\s*"((?:[^"\\]|\\.)*)"')
    field = re.compile(r"\{(\w+)\}")
    pairs = pair.findall(block)
    assert len(pairs) > 150
    for en, ko in pairs:
        assert set(field.findall(en)) == set(field.findall(ko)), en


def test_token_goes_in_a_header_not_the_address():
    """학습 시작·대기열은 토큰이 필요하다. 주소(?token=)에 실으면 기록·로그에 남는다."""
    html = _all()
    assert 'headers.Authorization = "Bearer " + S.token' in html
    assert "LS.epokioToken = t" in html        # 붙여 넣은 토큰은 이 브라우저에만(LS = 막혔으면 빈 객체인 localStorage)
    assert not re.search(r"[?&]token=", html)


def test_periodic_refresh_leaves_the_train_form_alone():
    """4초마다 전체를 다시 그리는데, 학습 폼까지 다시 그리면 입력하던 값이 지워진다."""
    html = _all()
    assert "refresh(true); }, 4000)" in html
    assert "if (!periodic) drawTrain();" in html


def test_tiny_sample_trains_briefly():
    """샘플은 8장이다. 칸 기본값(100에폭) 그대로 두면 의미 없이 오래 돈다. 맥 앱처럼 10에폭."""
    html = _all()
    assert '$("#f_epochs").value = 10' in html


def test_web_can_set_up_python_and_waits_for_it():
    html = _all()
    assert 'api("jobs", "POST", { kind: "setup" })' in html
    assert "else watchSetup();" in html                  # 끝나면 목록을 다시 찾는다(폼은 안 건드린다)


def test_start_checks_the_data_first_but_can_be_overridden():
    """데이터에 진짜 오류가 있으면 몇 분 뒤 실패하기 전에 막는다. 그래도 하겠다면 할 수 있다."""
    html = _all()
    assert 'w.level === "error"' in html and "startTraining(sc, true)" in html


def test_failed_jobs_show_why():
    html = _all()
    assert '"/diagnose"' in html


def test_train_again_does_not_reuse_the_old_output_folder():
    """다시 학습은 새 폴더에. project·name·resume 을 옮기면 예전 결과를 덮거나 이어 붙인다."""
    html = _all()
    assert 'const AGAIN_SKIP = ["project", "name", "exist_ok", "resume"' in html


def test_ntfy_detection():
    assert notify.is_ntfy("https://ntfy.sh/my-topic")
    assert notify.is_ntfy("https://ntfy.example.com/topic")
    assert not notify.is_ntfy("https://hooks.slack.com/services/x")


def test_goal_and_job_have_their_own_titles():
    from epokio import i18n
    try:
        for lang in ("en", "ko"):
            i18n.use(lang)
            titles = [notify.title(k) for k in notify.KINDS]
            assert len(set(titles)) == len(titles), lang       # 사건마다 제목이 다르다
            assert not any(x.startswith("notify.") for x in titles), lang   # 키가 그대로 새지 않는다(번역이 빠지지 않았다)
    finally:
        i18n.use("en")



def _serve(tmp_path, monkeypatch):
    """실제 HTTP 서버(백그라운드 스레드)를 띄운다. 큐·루트는 임시 폴더"""
    import threading
    from http.server import ThreadingHTTPServer
    from epokio.agent import Agent
    from epokio.jobs import Queue
    from epokio.server import make_handler
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label, a.queue = [], "t", Queue(tmp_path / "jobs.json")
    srv = QuietServer(("127.0.0.1", 0), make_handler(a))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, a


def test_get_errors_keep_their_status_code(tmp_path, monkeypatch):
    """★(코드, 내용)을 돌려주는 조회가 상태 200에 배열로 나갔다"""
    import json
    import urllib.error
    import urllib.request
    from epokio import auth
    monkeypatch.setattr(auth, "get_needs_token", lambda route: False)   # 잠긴 보기 검사는 따로 시험한다(test_server)
    srv, _ = _serve(tmp_path, monkeypatch)
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{srv.server_port}/data-diff?a=zz&b=yy")
        raise AssertionError("should fail")
    except urllib.error.HTTPError as e:
        assert e.code == 400 and "error" in json.loads(e.read())
    finally:
        srv.shutdown()


def test_web_scripts_are_served_and_nothing_else(tmp_path, monkeypatch):
    import urllib.error
    import urllib.request
    srv, _ = _serve(tmp_path, monkeypatch)
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        for name in SCRIPTS + ("style.css", "tokens.css"):
            r = urllib.request.urlopen(f"{base}/web/{name}")
            assert r.status == 200 and ("javascript" in r.headers["Content-Type"] or "css" in r.headers["Content-Type"])
        for bad in ("/web/../agent.py", "/web/index.html", "/web/x.py"):
            try:
                urllib.request.urlopen(base + bad)
                raise AssertionError(bad)
            except urllib.error.HTTPError as e:
                assert e.code in (400, 401, 404)                   # 401: 이름을 정해 둔 파일 밖은 잠긴 보기로 떨어진다
    finally:
        srv.shutdown()


def test_web_files_have_no_external_urls():
    """CDN·외부 주소 없음(오프라인 LAN). SVG 이름공간(www.w3.org)은 요청이 아니라 빼고 본다"""
    import re as _re
    for f in PAGE.parent.glob("*.*"):
        # ntfy 주소는 사용자에게 보여 주는 예시 글자다(요청하지 않는다)
        text = f.read_text(encoding="utf-8").replace("http://www.w3.org/2000/svg", "").replace("https://ntfy.sh/", "")
        assert not _re.search(r"https?://(?!127\.0\.0\.1|localhost)", text), f.name


def test_post_rejects_negative_or_huge_content_length(tmp_path, monkeypatch):
    """음수 길이는 연결이 닫힐 때까지 읽었고, 아주 큰 길이는 메모리에 다 올렸다(2026-09-22)"""
    import http.client
    from epokio import auth
    monkeypatch.setattr(auth, "check", lambda h: True)          # 토큰 검사는 따로 시험한다
    srv, _ = _serve(tmp_path, monkeypatch)
    try:
        for length, want in (("-1", 413), ("999999999999", 413), ("abc", 400)):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=3)
            c.putrequest("POST", "/jobs"); c.putheader("Content-Length", length); c.endheaders()
            assert c.getresponse().status == want, length
            c.close()
    finally:
        srv.shutdown()


def test_parallel_coords_puts_best_on_top_and_missing_values_apart():
    """손실(낮을수록 좋음)의 최고 학습이 아래에, 값이 없는 학습이 가운데(없는 값처럼)에 그려졌다(2026-09-22). node로 실제 JS를 돌린다"""
    import json
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    js = PAGE.parent / "sweeps.js"
    probe = f"""
const src=require("fs").readFileSync({json.dumps(str(js))},"utf8"); global.esc=s=>String(s); global.W={{}}; global.S={{}};
global.t=(s,v)=>v?s.replace(/\\{{(\\w+)\\}}/g,(m,k)=>String(v[k])):s;
eval(src.replace(/^"use strict";/,""));
const rows=[{{job:"a",trial:{{opt:"SGD"}},best:0.9}},{{job:"b",trial:{{}},best:0.2}},{{job:"c",trial:{{opt:"AdamW"}},best:0.5}}];
const h=parallelHTML({{rows,higher:false}},["opt"],"val loss");
console.log(JSON.stringify([...h.matchAll(/d="M[\\d.]+,([\\d.]+) L[\\d.]+,([\\d.]+)"/g)].map(m=>[+m[1],+m[2]])));
"""
    ys = json.loads(subprocess.run([node, "-e", probe], capture_output=True, text=True, check=True).stdout)
    a, b, c = ys                                                # 선 하나 = [설정 축 y, 점수 축 y], 위가 작다
    assert b[1] < c[1] < a[1]                                   # 0.2(최고)가 맨 위, 0.9가 맨 아래
    assert b[0] not in (a[0], c[0])                             # 값이 없는 학습은 자기 칸("–")


def test_run_row_hides_bar_when_total_unknown():
    """총 에폭을 모르는 학습(100/?)에 빈 막대가 0%처럼 보였다(2026-09-22)"""
    import json
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    js = PAGE.parent / "app.js"
    probe = f"""
const src=require("fs").readFileSync({json.dumps(str(js))},"utf8");
const start=src.indexOf("function rowHTML"), end=src.indexOf("\\n}}", start)+2;
const o0=src.indexOf("const originOf"), o1=src.indexOf("\\n}};", o0)+3; eval(src.slice(o0,o1).replace("const originOf","global.originOf"));
global.S={{picks:[],sel:null}}; global.STATE={{}}; global.esc=s=>String(s); global.dur=s=>String(s); global.display=r=>r.name;
global.stateOf=r=>[r.state,""]; global.xprog=r=>"epoch "+r.epoch+"/"+(r.total??"?");
global.t=(s,v)=>v?s.replace(/\\{{(\\w+)\\}}/g,(m,k)=>String(v[k])):s;
eval(src.slice(start,end));
const base={{name:"a",path:"/a",state:"stopped",epoch:100,best:null,idle:5,source:"local",meta:null}};
console.log(JSON.stringify([rowHTML({{...base,total:null}},0), rowHTML({{...base,total:200}},0)]));
"""
    unknown, known = json.loads(subprocess.run([node, "-e", probe], capture_output=True, text=True, check=True).stdout)
    assert "visibility:hidden" in unknown and "width:50%" in known


def test_chart_tooltip_pace_and_overfit_mark_are_wired():
    """곡선 툴팁(키보드 포함) · 속도 줄 · 최저 검증 손실 점선이 화면 코드에 붙어 있다"""
    js = _all()
    css = (PAGE.parent / "style.css").read_text(encoding="utf-8")
    assert "function bindCharts" in js and js.count("bindCharts();") >= 2
    assert "ArrowLeft" in js and 'tabindex="0"' in js               # 키보드로 읽는다
    assert "function valLossLow" in js and "mark: cv === 0" in js
    assert "function paceHTML" in js and "/epoch" in js
    assert ".tip" in css and ".mark-line" in css and "prefers-reduced-motion" in css


def test_compare_default_column_follows_server_metric():
    """비교 탭 기본 열은 서버 대표 점수(metric_name)를 따르고, 없을 때만 첫 mAP50-95로 폴백(2026-09-22)"""
    import json
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    js = PAGE.parent / "compare.js"
    probe = f"""
const src=require("fs").readFileSync({json.dumps(str(js))},"utf8");
const start=src.indexOf("function headlineKey"), end=src.indexOf("\\n}}", start)+2;
eval(src.slice(start,end));
const keys=["metrics/mAP50-95(B)","metrics/mAP50-95(M)","train/box_loss"];
console.log(JSON.stringify([
  headlineKey([{{metric_name:"metrics/mAP50-95(M)"}}], keys),
  headlineKey([{{metric_name:""}},{{metric_name:"metrics/mAP50-95(M)"}}], keys),
  headlineKey([{{metric_name:"metrics/gone"}}], keys),
  headlineKey([{{}}], ["train/box_loss"]),
]));
"""
    out = json.loads(subprocess.run([node, "-e", probe], capture_output=True, text=True, check=True).stdout)
    assert out == ["metrics/mAP50-95(M)", "metrics/mAP50-95(M)", "metrics/mAP50-95(B)", "train/box_loss"]


def test_review_cards_and_cells_work_from_the_keyboard():
    """검수 카드·클래스 표·혼동 행렬이 click 전용이면 Tab·VoiceOver로 못 쓴다(2026-09-22 접근성 점검)"""
    js = (WEB / "review.js").read_text(encoding="utf-8")
    assert 'class="shot' in js and 'tabindex="0" role="button"' in js
    assert js.count('class="cellbtn"') >= 2 and "aria-label=" in js
    assert 'el.onkeydown' in js and 'e.key === "Enter"' in js
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert ".cellbtn:focus-visible" in css and ".shot:focus-visible" in css


def test_compare_shows_what_changed_and_exports():
    html = _all()
    assert "function settingsDiff(" in html and "used different data" in html
    assert '"\\ufeff"' in html                     # 엑셀이 한글을 안 깨게 BOM
    assert 'id="q"' in html


def test_phone_alerts_can_be_set_from_the_web():
    """폰 알림 설정이 맥 앱에만 있어서 윈도우·폰 사용자는 켤 방법이 없었다."""
    html = _all()
    assert 'save({ urls: [u], add: true })' in html and 'api("webhooks", "POST", body)' in html   # 더하기(다른 웹후크를 지우지 않는다)
    # 끄기는 묻고(맥 앱·터미널의 주소까지 지운다) 되돌리기를 준다. ★한 번 누르면 확인 없이 전부 사라졌다
    assert 'if (!confirm(t("Turn off phone alerts?' in html and "save({ restore: true })" in html


def test_a_local_page_can_carry_the_token_after_the_hash_only():
    """트레이·setup이 연 주소의 #t= 는 저장하고 주소창에서 바로 지운다. 서버로 가는 ?token= 은 절대 안 된다."""
    html = _all()
    assert "location.hash.match(" in html and "history.replaceState(" in html
    assert not re.search(r"[?&]token=", html)


def test_nothing_hides_the_translation_function():
    """const [t, c, ic] 가 번역 함수 t()를 가려서, 학습이 붙은 알림이 있으면 알림 탭 전체가 TypeError로 안 그려졌다
    (웹 한국어화 직후, 알림이 0개인 화면으로만 확인해서 놓쳤다). t·tc 라는 이름으로 변수·매개변수를 만들지 않는다."""
    script = _all().replace("const tc = (ctx,", "")   # tc 자신의 정의
    bad = re.findall(r"(?:\b(?:const|let|var)\s+(?:\[\s*)?(?:t|tc)\b|\(\s*(?:t|tc)\s*(?:,[^)]*)?\)\s*=>|\b(?:t|tc)\s*=>)", script)
    assert not bad, bad


def test_the_page_survives_a_browser_that_blocks_storage():
    """사이트 데이터를 막으면 localStorage를 읽기만 해도 예외라 페이지가 통째로 비었다. 모두 LS를 거친다."""
    script = _all()
    code = "\n".join(l for l in script.splitlines() if not l.lstrip().startswith("//"))
    assert "const LS = (() => { try {" in code
    assert code.count("localStorage") == 1                         # LS를 만드는 그 한 곳뿐


def test_events_reset_when_the_agent_restarts_and_polls_do_not_overlap():
    """에이전트를 다시 켜면 boot가 바뀌고 커서를 0으로. 새로 고침은 한 번에 하나만"""
    html = _all()
    assert "e.boot !== S.boot" in html
    assert "if (refreshing)" in html and "refreshOnce(periodic)" in html


def test_resume_is_offered_only_where_it_can_work():
    """★'멎음'(에폭이 긴 학습은 도는 중에도 뜬다)에도 이어 하기가 떠서 도는 학습에 두 번째 학습을 붙였다.
    파이썬은 보내지 않는다(agent가 처음 띄운 파이썬을 고른다)"""
    html = _all()
    line = next(l for l in html.splitlines() if "const canResume" in l)
    assert '"stalled"' not in line and 'r.framework === "ultralytics"' in line
    call = next(l for l in html.splitlines() if "resume: true" in l)
    assert "python" not in call


def test_setup_button_comes_back_after_an_error_and_messages_are_announced():
    html = _all()
    assert "b.disabled = false;" in html.split("function wireSetup")[1].split("function watchSetup")[0]
    for box in ("rootmsg", "hookmsg", "trainmsg", "health"):
        assert f'id="{box}" role="status"' in html
    assert 'data-op="cancel"' in html and 'aria-label="${j.state === "running"' in html


def test_a_long_run_list_draws_a_window_and_one_click_handler():
    html = _all()
    body = html.split("async function drawRuns")[1].split("\nasync function ")[0]
    assert "ordered.slice(0, S.allRows" in body and 'id="morerows"' in body
    assert 'querySelectorAll(".row")' not in body


def test_a_resume_error_survives_the_next_refresh_and_a_bad_token_goes_to_unlock():
    """★오류를 목록 밖에 끼워 넣어 4초 뒤 새로 고침에 지워졌다. 틀린 토큰이면 토큰을 넣는 곳으로 간다"""
    html = _all()
    assert "S.resumeMsg = { path: r.path" in html and "S.resumeMsg?.path === r.path" in html
    assert 'if (e instanceof Locked) { S.locked = true; needToken(); return; }' in html


def test_the_main_score_can_be_chosen_on_the_web():
    html = _all()
    assert 'id="mcol"' in html and 'id="mdir"' in html
    assert 'const body = { path: r.path, metric: col || null' in html and 'api("meta", "POST", body)' in html


def test_a_target_can_be_set_on_the_web_and_follows_the_direction():
    """★웹에서는 목표를 정할 수 없었고, 낮을수록 좋은 점수에도 '≥'로 보였다"""
    html = _all()
    assert 'id="mgoal"' in html and "if (g !== (r.meta?.goal ?? null)) body.goal = g;" in html
    assert '${r.lower ? "≤" : "≥"}' in html                     # scan이 실제로 쓴 방향


def test_compare_shows_the_main_score_and_its_winner_in_the_right_direction():
    """★비교표가 F1만 봐서 Keras·HF 학습끼리는 1등도 점수 열도 없었다"""
    html = _all()
    body = html.split("async function drawCompare")[1].split("\nfunction ")[0]
    assert "runs[0].lower ? Math.min(...vals) : Math.max(...vals)" in body and '<th>${t("Score")}</th>' in body


def test_sweep_review_fixes_on_the_web():
    """★#태그로 거르면 하나도 안 걸렸고, CSV는 거른 뒤에도 전부 나갔고, 다섯 번째 고르기는 말없이 무시됐고,
    목록의 점수에 '낮을수록 좋음' 표시가 없었고, 데이터 칸·눌린 버튼은 화면 읽기 프로그램에 이름·상태가 없었다"""
    html = _all()
    assert '.map((g) => "#" + g)' in html and "const rows = filteredRuns().map" in html
    assert 'Up to 8 runs. Untick one first.' in html          # 표 탭과 같게 8개까지
    assert '(r.lower ? " ↓" : "")' in html
    assert 'aria-labelledby="l_data"' in html and 'aria-pressed="${k === on}"' in html
    assert "h.focus({ preventScroll: true })" in html and "~/.epokio/token" in html


def test_runs_sort_by_score_tags_are_editable_and_reports_can_be_made():
    """★스윕의 1등이 위로 오지 않았고, 웹에서 태그를 붙일 수 없었고, 보고서를 만들 수 없었다"""
    html = _all()
    assert 'id="sortscore"' in html and "(a.lower ? a.best - b.best : b.best - a.best)" in html
    assert 'id="mtags"' in html and "body.tags = $(\"#mtags\")" in html
    assert 'api("report", "POST", { paths })' in html


def test_the_unread_badge_counts_machine_warnings_too():
    html = _all()
    body = html.split("function drawBadge")[1].split("\nfunction ")[0]
    assert "e.kind in EV" in body


def test_compare_has_a_settings_table_for_every_shown_run():
    html = _all()
    assert 'id="sweepbtn"' in html and 'api("sweep")' in html and "data-sk=" in html
    assert "...keys.map((k) => cell(args.get(r.path)?.[k]))" in html          # CSV에도 설정 열


def test_the_settings_table_ranks_each_score_on_its_own_and_loads_once():
    """★점수 없는 학습이 방향 투표에 끼어 손실이 가장 큰 학습이 1등이었고, 처음 열 때 두 번 받았다"""
    html = _all()
    body = html.split("function settingsTableHTML")[1].split("function downloadCSV")[0]
    assert "const tops = new Set(order.map" in body and "(a == null) - (b == null)" in body
    assert "if (!settingsLoading) settingsLoading = api(\"sweep\")" in body and "S.sweepDesc" in body


def test_queue_cancel_asks_the_header_counts_jobs_folders_can_be_added_and_offline_is_obvious():
    """★'제거'가 묻지도 않고 취소했고, 머리글은 도는 작업이 있어도 '0개 진행 중'이었고, 학습이 있으면 폴더를 더할 수 없었고,
    끊겨도 작은 회색 글씨뿐이라 옛 값이 살아 있는 것처럼 보였다"""
    html = _all()
    assert 'op === "cancel" && !b.dataset.stop && !confirm(' in html and 't("Remove")' not in html
    assert 'queue: {r} running, {q} waiting' in html
    assert 'id="addfolder"' in html and "async function addFolder()" in html
    assert 'classList.add("down")' in html and "if (!s || S.down)" in html


def test_the_token_is_asked_where_it_is_needed():
    """★토큰이 필요한 곳마다 '대기열 탭에서 잠금을 푸세요'라 해서, 하던 일을 두고 탭을 옮겨야 했다"""
    html = _all()
    assert "Open the Queue tab" not in html and 'tab("queue"); return; }' not in html
    assert "function needToken(why)" in html and "d.showModal()" in html and 'type="password"' in html
    assert html.count("await needToken(") >= 5 and 'id="sweepunlock"' in html


def test_the_run_list_can_be_filtered():
    html = _all()
    body = html.split("async function drawRuns")[1].split("\nasync function ")[0]
    assert 'id="runq"' in body and "const base = filteredRuns();" in body and "S.sel = base[0].path" in body and "No runs match {q}." in html


def test_common_train_settings_are_explained_in_our_words():
    """★Ultralytics 설명 원문이 한국어 화면에도 그대로 나왔다"""
    import re
    html = _all()
    helps = re.findall(r'^  \w+: (".*"),$', html.split("const HELP = {")[1].split("};")[0], re.M)
    assert len(helps) >= 30
    ko = html.split("const KO = {")[1].split("\n};")[0]
    missing = [h for h in helps if h + ":" not in ko]
    assert not missing, missing
    assert "own ? t(own) : (f.help" in html


def test_split_scripts_do_not_redefine_each_others_names():
    """스크립트는 한 전역을 나눠 쓴다. 뒤 파일이 같은 이름을 다시 만들면 앞 것을 조용히 덮는다
    (★합칠 때 비교 탭의 설정 표 sweepHTML이 스윕 탭의 sweepHTML에 덮여 비교 탭이 통째로 안 그려졌다)"""
    names = []
    for f in SCRIPTS:
        names += re.findall(r"^(?:async )?(?:function|const|let|class) ([A-Za-z_$][\w$]*)", (WEB / f).read_text(encoding="utf-8"), re.M)
    dup = sorted({n for n in names if names.count(n) > 1})
    assert not dup, dup


def test_images_get_the_cookie_and_forgetting_the_token_clears_it_here():
    """그림(<img>)은 머리말을 못 보내서 맞는 토큰이면 HttpOnly 쿠키를 받는다(login). 토큰은 주소에 싣지 않는다"""
    js = _all()
    assert 'fetch("login", { method: "POST", headers: { Authorization: "Bearer " + S.token } })' in js
    assert "await login();" in js and "delete LS.epokioToken" in js
    assert "document.cookie" not in js                              # HttpOnly라 읽을 수도 없다. 읽으려 하지 않는다


def test_the_package_ships_every_file_the_page_loads():
    """★package-data가 web/*.html만 담아, pip으로 설치한 웹 화면이 js·css 없이 빈 페이지였다(0.4.0~0.4.2)"""
    import fnmatch
    import re
    root = PAGE.parents[3]
    line = re.search(r'^epokio = (\[.*?\])', (root / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)   # 3.10엔 tomllib이 없다
    pats = re.findall(r'"([^"]+)"', line)
    html = PAGE.read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="web/([^"]+)"', html)
    assert refs
    missing = [f for f in refs if not any(fnmatch.fnmatch("web/" + f, p) for p in pats)]
    assert not missing, missing


def test_web_shows_ssh_servers_like_the_mac_app():
    """SSH 서버 상태(연결·마지막으로 읽은 때·오류·학습 수·건너뛴 큰 로그)가 맥 앱에만 있었다(2026-10-01). 같은 GET /ssh를 읽는다"""
    js = (WEB / "ssh.js").read_text(encoding="utf-8")
    html = PAGE.read_text(encoding="utf-8")
    assert "web/ssh.js" in html and html.index("web/ssh.js") < html.index("web/main.js")
    assert 'api("ssh")' in js and 'apiPost("ssh/refresh")' in js
    for k in ("st.ok", "st.error", "st.at", "st.runs", "st.skipped", "x.name", "x.size"):
        assert k in js, k
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert "await loadSSH()" in app and "${sshHTML()}" in app and "wireSSH();" in app
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert ".sshrow:hover" in css and ".sshn.bump" in css and ":not(.sshn)" in css


def test_ssh_api_status_carries_skipped(monkeypatch):
    """웹 칸이 읽는 모양: hosts[].status.skipped = [{path,name,size}]"""
    from epokio.api import ssh as ssh_api
    from epokio import ssh_source
    monkeypatch.setattr(ssh_source, "load", lambda: [{"host": "gpu1", "paths": [], "auto": True, "on": True}])
    monkeypatch.setattr(ssh_source, "config_hosts", lambda: ["gpu1"])
    st = {"ok": True, "error": None, "runs": 3, "at": 1.0, "skipped": [{"path": "/r", "name": "big.csv", "size": 99}]}
    agent = type("A", (), {"ssh": type("P", (), {"status": {"gpu1": st}})()})()
    out = ssh_api.get(agent, "/ssh", {})
    assert out["hosts"][0]["status"]["skipped"][0] == {"path": "/r", "name": "big.csv", "size": 99}


def test_the_lineage_panel_speaks_korean():
    """★계보·단계 칸이 영어로 박혀 있어 한국어 화면에 'Where it came from'·'Put in use'가 섞였다"""
    js = (WEB / "versions.js").read_text(encoding="utf-8")
    for s in ("Where it came from", "Stage", "Put in use", "No stage", "Candidate", "Images added", "Stage saved"):
        assert f't("{s}")' in js, s
    assert ">Where it came from<" not in js and '"No stage", "var' not in js and ">Put in use<" not in js
    assert "Same data as ${" not in js and "runs started from this one</p>" not in js


def test_the_token_help_names_a_command_that_runs_here():
    """★잠금 카드가 epokio-agent --show-token(윈도우 PATH에 없음)을 안내했다. 이 기계가 알려 준 명령(/health token_cmd)을 쓴다"""
    html = _all()
    assert "epokio-agent --show-token" not in html
    assert "S.tokenCmd" in (WEB / "train.js").read_text(encoding="utf-8") and "h.token_cmd" in (WEB / "main.js").read_text(encoding="utf-8")


def test_the_ssh_list_is_asked_only_with_a_token():
    """★토큰 없는 화면이 4초마다 GET /ssh를 불러 401이 콘솔에 쌓였다. node로 실제 loadSSH를 돌린다"""
    import json
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    js = (WEB / "ssh.js").read_text(encoding="utf-8")
    probe = ("class Locked extends Error {}; const S = {}; const calls = [];"
             "async function api(p) { calls.push(p); if (S.token !== 'good') throw new Locked('x'); return { hosts: [{ host: 'h' }] }; }\n"
             + js + "\n(async () => { await loadSSH(); const a = calls.length, n0 = S.ssh.length;"
             "S.token = 'good'; await loadSSH(); const b = calls.length, n1 = S.ssh.length;"
             "S.token = 'bad'; await loadSSH(); const locked = !!S.locked; await loadSSH();"
             "console.log(JSON.stringify([a, n0, b, n1, locked, calls.length])); })();")
    got = json.loads(subprocess.run([node, "-e", probe], capture_output=True, text=True, check=True).stdout)
    assert got == [0, 0, 1, 1, True, 2]          # 토큰 없음: 안 부름 · 맞는 토큰: 부름 · 틀린 토큰: 한 번 뒤 잠김



def test_side_features_are_out_of_the_default_tabs_but_reachable():
    """곁가지(검수·스윕)는 기본 탭에서 숨기고 '더 보기'로 켠다. 코드는 그대로"""
    import re
    page = PAGE.read_text(encoding="utf-8")
    tabs = re.findall(r'<button role="tab" data-tab="(\w+)"( data-adv)?', page)
    assert {t for t, adv in tabs if adv} == {"review", "sweeps"}
    assert {t for t, adv in tabs if not adv} == {"runs", "table", "train", "queue", "compare", "inbox"}
    css = (PAGE.parent / "style.css").read_text(encoding="utf-8")
    js = (PAGE.parent / "main.js").read_text(encoding="utf-8")
    assert "body:not(.adv) nav [data-adv] { display: none; }" in css
    assert 'id="more"' in page and "LS.epokioAdv" in js and "drawReview" in (PAGE.parent / "app.js").read_text(encoding="utf-8")


def test_score_curve_hint_follows_the_score_direction():
    """eval_loss처럼 낮을수록 좋은 점수에도 '점수는 오르다가 평평해져야'라고 했다"""
    from pathlib import Path
    web = Path(__file__).resolve().parent.parent / "src" / "epokio" / "web"
    app, lang = (web / "app.js").read_text(encoding="utf-8"), (web / "lang.js").read_text(encoding="utf-8")
    msg = "This score is better when lower, so it should go down and level off."
    assert f'r.lower ? t("{msg}")' in app and f'"{msg}":' in lang


def test_curves_fall_back_to_loss_when_there_is_no_score_yet():
    """★HF 첫 평가 전에는 점수 탭(기본)이 '아직 데이터가 없습니다'만 보여 손실 곡선이 있는 줄 몰랐다"""
    js = _all()
    assert "const cv = S.curve === 1 && S.curvePick !== r.path && !curveKeys(1).length && curveKeys(0).length ? 0 : S.curve;" in js
    assert "const keys = curveKeys(cv);" in js


def test_every_web_script_parses():
    """★한 함수 안에 같은 이름 const를 두 번 두자 app.js 전체가 SyntaxError로 멈춰 목록이 비었는데, 문자열 시험은 다 통과했다"""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    for f in sorted(PAGE.parent.glob("*.js")):
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, f"{f.name}: {r.stderr[-400:]}"


def _node_or_skip():
    import shutil
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    return node


def test_a_read_only_token_hides_what_it_cannot_change():
    """★보기 전용 토큰에도 저장·단계·폴더·학습 단추가 보였고, 누르면 영어 'this token is read-only'가 잠깐 떴다
    다음 새로 고침에 사라졌다. /login의 scope와 403 code로 알고, CSS가 .needs-run을 숨긴다"""
    html, css = _all(), (WEB / "style.css").read_text(encoding="utf-8")
    assert "body.readonly .needs-run { display: none !important; }" in css and "body.readonly .ro-note { display: block; }" in css
    assert 'if (r.status === 403 && j.code === "read_only") setReadOnly(true);' in html
    assert 'setReadOnly(j.scope !== "run")' in html and "if (!takeHashToken() && S.token) login();" in html
    for marker in ('<div class="needs-run"><div class="inrow wrap"', 'id="addfolder" class="needs-run"', '<div class="actions needs-run"',
                   '`<select id="vset" class="needs-run"', 'class="btn primary needs-run" id="vpromote"', 'class="btn needs-run" id="clscalc"',
                   'needs-run" style="margin-left:12px" id="newrun"', 'data-op="cancel"', '<div class="inrow needs-run"><input class="in" id="hookurl"',
                   'class="btn small needs-run" id="report"', "if (S.readOnly) {"):
        assert marker in html, marker
    assert 'class="btn small danger needs-run" data-op="cancel"' in html


def test_a_read_only_403_switches_the_page_and_keeps_the_message():
    """node로 실제 api()를 돌린다: 403 read_only면 보기 전용으로 바뀌고, 오류 문장(agent가 화면 언어로 준 것)이 그대로 올라온다"""
    import json
    import subprocess
    node = _node_or_skip()
    js = WEB / "app.js"
    probe = f"""
const src=require("fs").readFileSync({json.dumps(str(js))},"utf8");
const cut=(a,b)=>src.slice(src.indexOf(a), src.indexOf(b, src.indexOf(a)));
global.LANG="ko"; global.t=(s)=>s; global.S={{token:"x",readOnly:false}}; let cls=null, ro={{hidden:true}};
global.document={{body:{{classList:{{toggle:(c,on)=>{{cls=[c,on];}}}}}}}}; global.$=(q)=>q==="#ro"?ro:null;
global.fetch=async()=>({{status:403, ok:false, json:async()=>({{error:"이 토큰은 보기 전용입니다.", code:"read_only"}})}});
eval(cut("class Locked", "/// 실행 요청(POST)")); eval(cut("function setReadOnly", "/// 파이썬 환경 목록"));
api("meta","POST",{{}}).catch((e)=>console.log(JSON.stringify({{msg:e.message, ro:S.readOnly, cls, hidden:ro.hidden}})));
"""
    out = json.loads(subprocess.run([node, "-e", probe], capture_output=True, text=True, check=True, encoding="utf-8").stdout)
    assert out == {"msg": "이 토큰은 보기 전용입니다.", "ro": True, "cls": ["readonly", True], "hidden": False}
    html = _all()
    # 대표 점수 저장 실패 문구는 상태에 남아 다음 새로 고침에도 보인다(★4초 뒤 지워졌다). 저장되면 짧은 알림
    assert "S.metaMsg = { path: r.path, text: e.message }; toast(e.message, true);" in html
    assert 'S.metaMsg?.path === r.path' in html and 'toast(t("Saved"))' in html


def test_the_main_score_line_appears_once():
    """★'대표 점수:' 줄이 이유 줄과 펼침 줄로 두 번 보였다. 이유는 펼침 줄 안에, 고를 열이 없을 때만 따로"""
    html = _all()
    assert html.count('id="scorewhy"') == 1 and "if (!pick.length && why) h += `<p class=\"hint\" id=\"scorewhy\">${mainLine}</p>`;" in html
    assert "<summary>${mainLine}</summary>" in html


def test_loading_empty_offline_and_state_changes_have_their_own_look():
    """처음 불러오는 동안 자리(스켈레톤), 빈 화면·끊김 그림과 다시 시도, 상태가 바뀐 줄 반짝임. 움직임 줄이기면 전부 멈춘다"""
    page, html, css = PAGE.read_text(encoding="utf-8"), _all(), (WEB / "style.css").read_text(encoding="utf-8")
    assert 'class="layout skel" aria-busy="true"' in page
    assert "${ART.empty}" in html and "${ART.offline}" in html and 'id="retry"' in html and "${ART.bell}" in html and "${ART.queue}" in html
    assert 'const flip = S.was && S.was[r.path] && S.was[r.path] !== r.state ? " flip" : "";' in html
    rm = [b for b in re.findall(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\}\s*(?:\}|$)", css, re.S)]
    assert any(".skel i" in b and ".row.flip" in b for b in rm), "움직임 줄이기에서 스켈레톤·반짝임이 멈추지 않는다"
    assert "@media (prefers-reduced-motion: no-preference) {\n  #main#main.static .row.flip" in css     # 갱신 중에도 반짝이되, 줄이기면 안 한다
    # 움직임 토큰은 '시간 이징' 한 덩어리라 calc에 넣으면 무효다. ★.row.flip이 그래서 선언째 버려져 반짝이지 않았다
    assert "calc(var(--m-" not in css


def test_phone_header_keeps_the_language_button_whole_and_detail_clears_it():
    """★폰(375)에서 보기 전용 칩이 붙으면 '한국어' 단추가 두 줄로 꺾였고, 학습을 누르면 상세가 붙박이 머리말 밑으로 스크롤돼 제목·점수가 가려졌다"""
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert re.search(r"#lang \{[^}]*white-space: nowrap", css)
    assert re.search(r"@media \(max-width: 820px\) \{[^\n]*\.detail \{ scroll-margin-top: \d+px; \}", css)


def test_chart_width_follows_its_box_so_phone_labels_are_not_squeezed():
    """★폰에서 640 폭 그림을 310px로 줄여(preserveAspectRatio=none) 축 글자가 옆으로 눌렸다"""
    html = _all()
    assert "const W = chartWidth(), H = 240" in html and "function chartWidth()" in html


def test_review_new_check_fills_its_own_python_list():
    """★fillPythons가 그림 크게 보기(openShot)에 있어 New check의 파이썬 목록이 'Looking for Python…'에 멈췄고 400이 났다"""
    js = (WEB / "review.js").read_text(encoding="utf-8")
    shot, new = js.index("function openShot"), js.index("async function newCheck")
    fill = js.index('fillPythons(m.querySelector("#np"))')
    assert fill > new and js.count('fillPythons(m.querySelector("#np"))') == 1 and not (shot < fill < new)


def test_the_table_tab_speaks_korean_and_ignores_late_answers():
    """★표 탭의 머리·개수·'비교'·'3분 ago'가 한국어 화면에 영어로 남았고, 늦게 온 표가 다른 탭을 덮었다"""
    js = (WEB / "table.js").read_text(encoding="utf-8")
    for s in ('t("{n} of {total}"', 't("Compare {n}"', 't("Run")', 't("Score")', 't("{d} ago"', 't("Pick up to {n} runs"', "if (r.display) return r.display;"):
        assert s in js, s
    assert 'if (g !== S.gen || S.tab !== "table") return;' in js
    assert "+ \" ago\"" not in js and "`Compare ${" not in js


def test_rows_do_not_say_local_on_every_line():
    """★목록·상세의 모든 줄에 'local'이 붙어 한국어 화면에도 영어가 섞였다. 이 기계가 아닌 출처(SSH)만 보인다"""
    import json
    import subprocess
    node = _node_or_skip()
    js = WEB / "app.js"
    probe = f"""
const src=require("fs").readFileSync({json.dumps(str(js))},"utf8");
const start=src.indexOf("function rowHTML"), end=src.indexOf("\\n}}", start)+2;
const o0=src.indexOf("const originOf"), o1=src.indexOf("\\n}};", o0)+3; eval(src.slice(o0,o1).replace("const originOf","global.originOf"));
global.S={{picks:[],sel:null}}; global.esc=s=>String(s); global.dur=s=>String(s); global.display=r=>r.name;
global.stateOf=r=>[r.state,""]; global.xprog=r=>"epoch "+r.epoch; global.t=(s,v)=>v?s.replace(/\\{{(\\w+)\\}}/g,(m,k)=>String(v[k])):s;
eval(src.slice(start,end));
const base={{name:"a",path:"/a",state:"stopped",epoch:3,total:5,best:null,idle:5,meta:null}};
console.log(JSON.stringify([rowHTML({{...base,source:"local"}},0), rowHTML({{...base,source:"local",ssh:{{host:"gpu1",path:"/r/a"}}}},0),
  rowHTML({{...base,source:"ssh:gpu1"}},0)]));
"""
    local, ssh, event = json.loads(subprocess.run([node, "-e", probe], capture_output=True, text=True, check=True).stdout)
    # ★/runs는 SSH 학습을 source "local" + ssh 칸으로 보낸다. 'local'이 아닌 source만 봐서 서버 이름이 어디에도 없었다(사건은 "ssh:<서버>")
    assert "local" not in local and "gpu1 (SSH)" in ssh and "gpu1 (SSH)" in event


def test_a_long_run_draws_without_running_out_of_stack_and_redraws_only_on_change():
    """★2만 에폭 x 열 7개(14만 점)면 Math.min(...점)이 RangeError라 학습 상세가 통째로 안 그려졌다. 선마다 점 2만 개라
    상세 HTML이 950KB였고, 그림마다 새 번호라 바뀐 것이 없어도 4초마다 다시 그렸다(번호 배열도 끝없이 늘었다). node로 실제 chart()"""
    import json
    import subprocess
    node = _node_or_skip()
    js = WEB / "app.js"
    probe = f"""
const src=require("fs").readFileSync({json.dumps(str(js))},"utf8");
const a=src.indexOf("const CHARTS"), b=src.indexOf("function bindCharts");
global.t=(s,v)=>v?s.replace(/\\{{(\\w+)\\}}/g,(m,k)=>String(v[k])):s; global.esc=(s)=>String(s);
eval(src.slice(a,b).replace("const CHARTS","global.CHARTS").replace("function chart(","global.chart=function(").replace("function thin(","global.thin=function("));
const n=20000, x=Array.from({{length:n}},(_,i)=>i+1);
const series=Array.from({{length:10}},(_,k)=>({{name:"s"+k,color:"red",x,y:x.map((e)=>Math.sin(e/500+k)+(e===12345?9:0))}}));
let err=null, h1="", h2="", h3="";
try {{ h1=chart(series); h2=chart(series); series[0].y[5]=0.123456; h3=chart(series); }} catch(e) {{ err=String(e); }}
const c=CHARTS.get(h1.match(/data-chart="([^"]+)"/)[1]), top=Math.min(...h1.match(/d="M[^"]*"/)[0].slice(4,-1).split(" L").map((q)=>+q.split(",")[1]));
const xs2=x.slice(); xs2[100]=99999; const nm=(chart([{{name:"n",color:"red",x:xs2,y:x.map(Math.sin)}}]).match(/d="M[^"]*"/)[0]).split(" L").length;
for (let i=0;i<60;i++) chart([{{name:"z",color:"red",x:[1,2],y:[i,i+1]}}]);
const pts=(h)=>(h.match(/d="M[^"]*"/g)||[]).map((d)=>d.split(" L").length);
console.log(JSON.stringify({{err, nm, same:h1===h2, changed:h1!==h3, kb:Math.round(h1.length/1024), pts:pts(h1), spike:Math.abs(top-c.Y(Math.max(...series[0].y.slice(0,20000))))<1,
  size:CHARTS.size, small:pts(chart([{{name:"a",color:"red",x:[1,2,3],y:[1,null,3]}}]))}}));
"""
    out = json.loads(subprocess.run([node, "-e", probe], capture_output=True, text=True, check=True, encoding="utf-8").stdout)
    assert out["err"] is None
    assert out["same"] and out["changed"]                       # 같은 자료면 같은 HTML(다시 안 그림), 값이 바뀌면 다른 그림
    assert max(out["pts"]) <= 4 * 600 and len(out["pts"]) == 10 and out["kb"] < 300
    assert out["spike"]                                         # 튀는 점(2만 점 중 하나)도 남는다
    assert out["nm"] <= 4 * 600                                 # x가 되돌아가는 기록(이어 한 학습)도 줄인다
    assert out["size"] <= 40 and out["small"] == [2]            # 기억은 40개까지. 짧은 선은 그대로(빈 값은 건너뛴다)


def test_the_first_screen_shows_the_list_before_the_detail_arrives():
    """★처음 고른 학습(도는 학습이 맨 위)의 상세를 받을 때까지 목록도 안 보였다. 2만 줄 학습이면 1초 넘게 스켈레톤만 있었다"""
    js = (WEB / "app.js").read_text(encoding="utf-8")
    early = js.index('if (first && !S.detail[r.path]) setMain(')
    assert early < js.index("const d = await detail(r);", early) and '<div class="card detail skel" aria-busy="true">' in js
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert ".detail.skel i.w40" in css and ".detail.skel i.tall" in css


def test_zooming_an_image_does_not_leave_window_listeners_behind():
    """★검수에서 그림을 열 때마다 window에 mousemove·mouseup 손잡이가 둘씩 쌓였다(닫은 그림을 붙든 채)"""
    js = (WEB / "review.js").read_text(encoding="utf-8")
    z = js[js.index("function zoomable("):]
    assert z.count('window.addEventListener(') == 2 and z.count("}, on);") == 2 and "if (!area.isConnected) return ac.abort();" in z
