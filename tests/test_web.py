"""웹 화면이 패키지에 들어 있고, 외부 주소를 부르지 않는지(오프라인 LAN에서도 되어야 한다). ntfy 판별."""
import re
from pathlib import Path

from epokio import notify

PAGE = Path(__file__).resolve().parent.parent / "src" / "epokio" / "web" / "index.html"
WEB = PAGE.parent
# index.html이 부르는 순서(lang.js가 먼저, main.js가 마지막)
SCRIPTS = ("lang.js", "app.js", "compare.js", "alerts.js", "train.js", "queue.js", "versions.js", "review.js", "sweeps.js", "table.js", "main.js")


def _all():
    """화면 코드 전부(index.html + 나눈 스크립트). 문자열 검사는 파일이 어디로 옮겨 가도 따라가게 이것을 본다"""
    return "\n".join([PAGE.read_text(encoding="utf-8")] + [(WEB / f).read_text(encoding="utf-8") for f in SCRIPTS])


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
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(a))
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
global.S={{picks:[],sel:null}}; global.STATE={{}}; global.esc=s=>String(s); global.dur=s=>String(s); global.display=r=>r.name;
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
    assert "function valLossLow" in js and "mark: S.curve === 0" in js
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
    assert 'api("webhooks", "POST", urls.length ? { urls, add: true } : { urls })' in html   # 더하기(다른 웹후크를 지우지 않는다)


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
