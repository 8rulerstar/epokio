"""웹 화면: 검수·스윕 탭의 한국어, 늦게 온 답, 낮을수록 좋은 점수의 맞바꿈 그림, 창(dialog)·알림의 접근성, 글자 대비(WCAG AA).
(7차 점검의 한국어 초보자·화면 읽기·디자이너 점검에서 실제로 잡힌 것)"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "src" / "epokio" / "web"


def _js(name):
    return (WEB / name).read_text(encoding="utf-8")


def test_review_and_sweeps_speak_korean():
    """★한국어 화면에서도 검수·스윕 탭은 버튼·제목·빈 화면·창이 통째로 영어였다(번역 검사는 t()로 감싼 문장만 본다)"""
    review, sweeps = _js("review.js"), _js("sweeps.js")
    for s in ("New check", "Missed something", "Not reviewed", "Open a predictions file", "Start check", "Retrain set", "{n} selected"):
        assert f't("{s}"' in review, s
    for s in ("New sweep", "No sweeps yet.", "Stop sweep", "What mattered most", "Best trade-offs", "Queue sweep", "{done} of {total} runs"):
        assert f't("{s}"' in sweeps, s
    for js in (review, sweeps):                      # 사람이 읽는 영어가 따옴표째 남아 있지 않다
        for s in ('＋ New check<', '<option>No checks yet</option>', '■ Stop sweep<', '"Smart search" :', '? "Model size (MB)"', 'title: "Undo"'):
            assert s not in js, s


def test_review_and_sweeps_ignore_late_answers():
    """★느린 응답이 그사이 연 다른 탭을 덮었다(표 탭과 같은 그리기 세대 S.gen)"""
    review, sweeps = _js("review.js"), _js("sweeps.js")
    assert 'const reviewHere = (g) => g === S.gen && S.tab === "review";' in review
    assert review.count("if (!reviewHere(g)) return;") >= 2
    assert 'const sweepsHere = (g) => g === S.gen && S.tab === "sweeps";' in sweeps
    assert sweeps.count("sweepsHere(g") >= 3


def _node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    return node


def test_tradeoff_chart_puts_the_best_score_on_top_for_lower_is_better():
    """★두 목표 스윕의 맞바꿈 그림이 손실·rmse(낮을수록 좋음)에서 가장 좋은 학습을 맨 아래에 그렸다"""
    probe = f"""
const src=require("fs").readFileSync({json.dumps(str(WEB / "sweeps.js"))},"utf8"); global.esc=s=>String(s); global.W={{}}; global.S={{}};
global.t=(s,v)=>v?s.replace(/\\{{(\\w+)\\}}/g,(m,k)=>String(v[k])):s;
eval(src.replace(/^"use strict";/,""));
const rows=[{{job:"a",trial:{{}},best:0.24,second:600}},{{job:"b",trial:{{}},best:0.40,second:150}},{{job:"c",trial:{{}},best:0.31,second:300}}];
const cy=(h)=>Object.fromEntries([...h.matchAll(/cy="([\\d.]+)"[^>]*><title>[^<]*→ ([\\d.]+)/g)].map(m=>[m[2],+m[1]]));
console.log(JSON.stringify([cy(paretoHTML({{rows,higher:false,second:"time",pareto:["a","b","c"]}},"val_rmse")),
                            cy(paretoHTML({{rows,higher:true,second:"time",pareto:["a","b","c"]}},"mAP"))]));
"""
    low, high = json.loads(subprocess.run([_node(), "-e", probe], capture_output=True, text=True, check=True).stdout)
    assert low["0.2400"] < low["0.3100"] < low["0.4000"]          # 위(작은 y) = 좋음
    assert high["0.4000"] < high["0.3100"] < high["0.2400"]


def test_windows_are_dialogs_and_toasts_are_announced():
    """★창이 div라 초점이 뒤에 남고 Esc가 안 먹었다(데이터 차이 창은 닫는 단추도 없었다). 알림(저장·실패)은 소리 없이 지나갔다"""
    every = "\n".join(_js(f.name) for f in WEB.glob("*.js"))
    assert 'm.className = "modal"' not in every.replace('m.className = "modal"; m.setAttribute("aria-label"', "")
    app = _js("app.js")
    assert 'document.createElement("dialog"); m.className = "modal"' in app and "m.showModal()" in app
    assert '$(bad ? "#sra" : "#sr")' in app
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert '<span id="sra" class="sr" role="alert"></span>' in html
    assert "data-close" in _js("versions.js")
    assert 'role="alert" style="--c:var(--red)' in _js("train.js")      # 틀린 토큰은 바로 읽힌다


def test_rows_say_which_one_is_open_and_which_are_picked():
    app = _js("app.js")
    assert "aria-current=\"true\"" in app and "aria-pressed=\"${S.picks.includes(r.path)}\"" in app


# ── 대비: 토큰 값으로 WCAG 2 대비를 계산한다(밝은·어두운 화면) ──

def _vars(css):
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", css))


def _hex(c):
    c = c.strip().lstrip("#")
    c = "".join(x * 2 for x in c) if len(c) == 3 else c
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, p):          # color-mix(in srgb, a, b p%)
    return tuple(round(x * (1 - p) + y * p) for x, y in zip(a, b))


def _lum(c):
    v = [x / 255 for x in c]
    v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]


def _cr(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _themes():
    style, tokens = (WEB / "style.css").read_text(encoding="utf-8"), (WEB / "tokens.css").read_text(encoding="utf-8")
    s_light, s_dark = style.split("@media (prefers-color-scheme: dark)", 1)
    t_light, t_dark = tokens.split("@media (prefers-color-scheme: dark)", 1)
    light = {**_vars(t_light), **_vars(s_light.split("}", 1)[0])}
    dark = {**light, **_vars(t_dark), **_vars(s_dark.split("}\n}", 1)[0])}
    return {"light": light, "dark": dark}


def test_text_contrast_meets_wcag_aa_in_both_themes():
    """★어두운 화면에서 흰 글자/초록 바탕 2.2:1, 흰 글자/청록 2.9:1(밝은 화면), 상태 글자(경고·금색) 2.6~3.1:1이었다.
    색 글자는 본문 색을 섞고(--ink-mix), 색 바탕 위 글자는 바탕을 어둡게(--fill-shade) 하거나 짙은 글자(--on-fill)를 쓴다"""
    style = (WEB / "style.css").read_text(encoding="utf-8")
    assert "color: #fff" not in style.replace("color: #fff; padding: 2px 8px", "")      # 흰 글자는 --on-fill로(사진 위 확대 배율 표시만 예외)
    fails = []
    for name, v in _themes().items():
        ink, soft, black = _hex(v["ink"]), _hex(v["soft"]), (0, 0, 0)
        mix_ink, shade = float(v["ink-mix"].rstrip("%")) / 100, float(v["fill-shade"].rstrip("%")) / 100
        on = _hex(v["on-fill"])
        for bg in ("bg", "panel", "panel2"):
            fails += [(name, "soft on " + bg, _cr(soft, _hex(v[bg])))]
            fails += [(name, "ink on " + bg, _cr(ink, _hex(v[bg])))]
        fails += [(name, "soft on selected row", _cr(soft, _mix(_hex(v["panel"]), _hex(v["brand"]), .14)))]
        for c in ("brand", "brand2", "good", "warn", "bad", "mixup", "gold", "info"):
            col = _hex(v[c])
            text = _mix(col, ink, mix_ink)
            for bg in ("bg", "panel", "panel2"):
                fails += [(name, f"{c} text on {bg}", _cr(text, _hex(v[bg])))]
            fails += [(name, f"{c} pill text on its tint", _cr(text, _mix(_hex(v["panel"]), col, .16)))]
            fails += [(name, f"text on {c} fill", _cr(on, _mix(col, black, shade)))]
    bad = [f for f in fails if f[2] < 4.5]
    assert not bad, bad


def test_tabs_follow_the_aria_tab_pattern():
    """★탭을 Tab으로 아홉 번 지나야 했고 화살표가 안 먹었다. tablist 안에 탭이 아닌 '더 보기' 단추가 있었고, 탭이 무엇을
    바꾸는지(aria-controls)·패널 이름이 없었다. 뱃지 숫자가 이름에 붙어 'Alerts3'으로 읽혔다"""
    page = (WEB / "index.html").read_text(encoding="utf-8")
    nav = page[page.index("<nav>"):page.index("</nav>")]
    tl = nav[nav.index('role="tablist"'):nav.index("</div>")]
    tabs = re.findall(r"<button role=\"tab\"[^>]*>", tl)
    assert len(tabs) == 8 and all('aria-controls="main"' in b and 'id="tab-' in b for b in tabs)
    assert sum('tabindex="-1"' in b for b in tabs) == 7 and 'id="more"' not in tl and 'id="more"' in nav
    assert '<main id="main" role="tabpanel" aria-labelledby="tab-runs">' in page
    main, app = _js("main.js"), _js("app.js")
    assert "ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1" in main and "b.offsetParent !== null" in main
    assert "b.tabIndex = on ? 0 : -1;" in app and '$("#main").setAttribute("aria-labelledby", "tab-" + name);' in app
    assert 't("Alerts, {n} new", { n })' in app and 't("Queue, {n} running or waiting", { n })' in app


def test_loading_lost_connection_and_motion_are_announced_or_calmed():
    """★처음 불러오는 스켈레톤이 아무 말도 안 했고, 연결이 끊긴 것을 머리말 글자로만 알렸고, el.animate·SVG <animate>는
    움직임 줄이기에도 움직였다(CSS로는 못 막는다). 비교 열 고르기(#ck)에는 이름이 없었다"""
    page, app = (WEB / "index.html").read_text(encoding="utf-8"), _js("app.js")
    assert 'class="layout skel" aria-busy="true" role="status"><span class="sr" id="skeltext">' in page
    assert "if (!wasDown) say($(\"#where\").textContent, true);" in app and 'if (wasDown) say(t("Connected to {machine} again"' in app
    for f in WEB.glob("*.js"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if ".animate?.(" in line or ".animate(" in line or "<animate " in line:
                assert "calm()" in line, (f.name, line.strip()[:80])
    assert 'id="ck" aria-label="${t("Column to compare")}"' in _js("compare.js")


def test_the_image_viewer_is_a_named_dialog():
    """★그림 크게 보기가 div라 초점이 뒤 화면에 남았고(Tab이 안 보이는 곳을 돌았다) 이름 없는 그림이었다"""
    app = _js("app.js")
    lb = app[app.index("function lightbox("):app.index("function tab(")]
    assert "modal(name ||" in lb and 'alt="${esc(name || "")}"' in lb and "openModal(m, m.querySelector(\".lbclose\"))" in lb
    assert 'lightbox(f.dataset.src, f.getAttribute("aria-label"))' in app and 'lightbox(f.dataset.src, f.getAttribute("aria-label"))' in _js("snapshots.js")


def test_a_new_token_in_the_address_of_an_open_tab_is_used():
    """★'#t='는 처음 열 때만 읽어, 이미 열린 탭에 트레이가 새 주소를 줘도(또는 붙여 넣어도) 옛 토큰으로 잠겨 있었다"""
    main = _js("main.js")
    assert 'addEventListener("hashchange", () => { if (takeHashToken()) { S.lastMain = ""; refresh(); } });' in main
    assert "S.token = m[1]; S.locked = false;" in main


def test_destructive_buttons_ask_first():
    """★'스윕 멈추기'와 폰 알림 '끄기'가 확인 없이 바로 되돌릴 수 없는 일을 했다(끄기는 맥 앱·터미널의 주소까지 지웠다)"""
    assert 'if (confirm(t("Stop this sweep?' in _js("sweeps.js")
    alerts = _js("alerts.js")
    assert 'if (!confirm(t("Turn off phone alerts?' in alerts and 'title: t("Undo"), run: () => save({ restore: true })' in alerts
