"""잘못 준 --root: 시작할 때 경고하고, /runs의 missing_roots로 웹 빈 화면이 이름을 보인다.
★없는 폴더를 아무 말 없이 지켜봐서 '학습 0개'로만 보였다. PowerShell은 "C:\\my runs\\" 를 C:\\my runs" 로 넘긴다."""
import sys
from pathlib import Path

import pytest

from epokio import server_cli, tui
from epokio.agent import Agent
from epokio.roots import clean_root


def test_a_stray_trailing_quote_from_powershell_is_dropped(tmp_path):
    d = tmp_path / "my runs"
    d.mkdir()
    assert clean_root(str(d) + '"') == d                       # PowerShell: "C:\my runs\" → C:\my runs"
    assert clean_root(f'  {d}"  ') == d
    assert clean_root(str(d)) == d
    assert clean_root('a"b"') == Path('a"b"')                  # 짝이 맞는 따옴표는 건드리지 않는다


def test_the_agent_warns_about_each_root_that_does_not_exist(tmp_path, monkeypatch, capsys):
    good, bad = tmp_path / "runs", tmp_path / "nope"
    good.mkdir()

    class Stop(Exception):
        pass

    def stop(*a, **k):
        raise Stop()
    monkeypatch.setattr(server_cli, "bind_first", stop)        # 폴더를 읽은 뒤, 포트를 잡기 전에 멈춘다
    monkeypatch.setattr(sys, "argv", ["epokio agent", "--root", str(good), "--root", str(bad) + '"'])
    with pytest.raises(Stop):
        server_cli.main()
    out = capsys.readouterr().out
    assert "does not exist" in out and str(bad) in out and str(good) not in out and '"' not in out.split(str(bad))[1][:2]


def test_watch_warns_about_a_missing_root(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tui, "print_once", lambda feed: None)
    tui.main(["--root", str(tmp_path / "nope"), "--once"])
    err = capsys.readouterr().err
    assert "does not exist" in err and "nope" in err


def test_runs_names_the_roots_that_do_not_exist(tmp_path):
    good, bad = tmp_path / "runs", tmp_path / "nope"
    good.mkdir()
    a = Agent.__new__(Agent)
    a.roots, a.label = [good, bad], "t"
    got = a.get("/runs", {})
    assert got["missing_roots"] == [str(bad)]


def test_the_web_empty_state_names_missing_roots():
    js = (Path(__file__).resolve().parents[1] / "src" / "epokio" / "web" / "app.js").read_text(encoding="utf-8")
    assert "missing_roots" in js and "This folder does not exist:" in js


def test_a_root_pattern_is_expanded_on_every_scan(tmp_path, monkeypatch):
    """--root '/data/*/runs': 새 사람·새 실험 폴더가 다시 켜지 않아도 보인다"""
    import io
    from pathlib import Path
    from epokio.agent import Agent
    from epokio.roots import warn_missing
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    pat = Path(str(tmp_path / "data" / "*" / "runs"))
    out = io.StringIO()
    assert warn_missing([pat], out) == [pat] and "pattern" in out.getvalue()
    a = Agent.__new__(Agent)
    a.roots, a.label = [pat], "t"
    assert a.get("/runs", {})["missing_roots"] == [str(pat)]
    for who in ("alice", "bob"):
        d = tmp_path / "data" / who / "runs" / "exp"
        d.mkdir(parents=True)
        (d / "results.csv").write_text("epoch,train/box_loss,metrics/mAP50-95(B)\n1,1.0,0.1\n", encoding="utf-8")
    a._runs_cache = None
    got = a.get("/runs", {})
    assert sorted(Path(r["path"]).parent.parent.name for r in got["runs"]) == ["alice", "bob"]
    assert got["missing_roots"] == []
    assert tmp_path / "data" / "alice" / "runs" in a.watch_roots()


def test_a_root_pattern_can_be_added_live_but_not_a_bare_star(tmp_path, monkeypatch):
    from epokio.agent import Agent
    from epokio.api import roots_api
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label = [], "t"
    code, body = roots_api.post(a, "/roots", {"path": str(tmp_path / "data" / "*" / "runs")})
    assert code == 200 and body["roots"] == [str(tmp_path / "data" / "*" / "runs")]
    assert roots_api.post(a, "/roots", {"path": str(tmp_path / "*")})[0] == 400
