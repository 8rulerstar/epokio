"""윈도우 트레이의 글자·아이콘 규칙(트레이 없이 시험할 수 있는 부분)."""
from pathlib import Path

import pytest

from epokio import tray
from epokio.scan import Run


def _run(**kw):
    d = dict(name="coco8", path=Path("/r/coco8"), epoch=12, total=30, elapsed=360, eta=540, metric=0.6,
             metric_name="m", best=0.642, best_epoch=11, state="running", idle=1)
    d.update(kw)
    return Run(**d)


def test_info_text_follows_choices():
    r = _run()
    assert tray.info_text(r, ["pct", "eta", "best"], None) == "40% 9m 0.642"
    assert tray.info_text(r, ["epoch", "gpu"], 57.0) == "12/30 GPU 57%"
    assert tray.info_text(_run(state="done", eta=None), ["pct", "eta"], None) == "40%"   # 끝난 학습엔 남은 시간 없음


def test_chosen_run():
    a, b = _run(name="a"), _run(name="b", meta={"star": True})
    assert tray.chosen([a, b], "live", 0).name == "a"
    assert tray.chosen([a, b], "star", 0).name == "b"
    assert [tray.chosen([a, b], "cycle", t).name for t in range(3)] == ["a", "b", "a"]
    assert tray.chosen([_run(state="done")], "live", 0) is None


def test_icon_draws():
    pytest.importorskip("PIL")
    img = tray.draw_icon(0.4, "running")
    assert img.size == (64, 64) and img.getpixel((32, 32))[3] > 0


def test_a_long_emoji_name_does_not_freeze_the_tooltip():
    """★글자 수로 잘라 이모지가 있으면 UTF-16 128칸을 넘어 ValueError, 반복문이 삼켜 툴팁이 멈췄다"""
    s = tray.tooltip("🔥" * 100)
    assert len(s.encode("utf-16-le")) <= 254 and s == "🔥" * 63


def test_the_tray_speaks_korean_and_says_when_the_agent_is_down():
    """★한국어 윈도우에서도 메뉴·알림이 영어였고, agent가 꺼지면 '도는 학습 없음'처럼 보였다"""
    from epokio import i18n
    t = tray.Tray.__new__(tray.Tray)
    t.agent = "http://127.0.0.1:8787"
    t.feed = type("F", (), {"down": True})()
    try:
        i18n.use("ko_KR")
        assert "연결할 수 없습니다" in t._headline([])
        t.feed.down = False
        assert t._headline([]) == "Epokio · 도는 학습 없음"
        assert i18n.t(tray.TITLES["finished"]) == "학습이 끝났습니다"
    finally:
        i18n.use("en")


def test_mac_style_korean_folder_names_are_joined():
    """★맥에서 온(NFD) 한글 폴더 이름은 칸 수가 두 배로 세어져 터미널 표가 어긋났다"""
    import unicodedata
    from epokio import tui
    parent = unicodedata.normalize("NFD", "불량검출")
    r = _run(name="train")
    r.path = f"/data/{parent}/train"
    assert tui.display_name(r) == "불량검출/train" and tui.cells(tui.display_name(r)) == 14


def test_every_tray_phrase_is_used_and_no_language_has_extra_keys():
    """★옛 메뉴 막대 앱의 문구 약 30개가 17개 언어에 남아 있었다"""
    import pathlib
    import re
    from epokio import i18n
    src = "\n".join(p.read_text(encoding="utf-8") for p in pathlib.Path(i18n.__file__).parent.rglob("*.py")
                    if p.name != "i18n.py")
    dyn = re.findall(r"""["']([a-z_.]+\.)["']\s*\+""", src)
    unused = [k for k in i18n.EN if f'"{k}"' not in src and f"'{k}'" not in src and not any(k.startswith(d) for d in dyn)]
    assert not unused, unused
    for name, table in i18n.TABLE.items():
        assert set(table) <= set(i18n.EN), name


def test_double_clicking_the_exe_opens_the_page_but_login_start_does_not(monkeypatch):
    """★README는 '더블클릭하면 브라우저가 열린다'고 했지만 트레이 아이콘만 생겼다"""
    import sys
    import types
    import webbrowser
    from epokio import tray
    opened = []
    monkeypatch.setitem(sys.modules, "pystray", types.ModuleType("pystray"))
    monkeypatch.setitem(sys.modules, "PIL", types.ModuleType("PIL"))
    monkeypatch.setattr(tray, "ensure_agent", lambda url: (url, None))
    monkeypatch.setattr(tray, "Tray", lambda agent: types.SimpleNamespace(run=lambda: None))
    monkeypatch.setattr(webbrowser, "open", lambda u: opened.append(u))
    tray.main(["--agent", "http://127.0.0.1:8787", "--open"])
    assert len(opened) == 1 and opened[0].startswith("http://127.0.0.1:8787/")
    tray.main(["--agent", "http://127.0.0.1:8787"])                 # 로그인 자동 시작('tray')
    assert len(opened) == 1
