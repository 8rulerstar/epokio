import time

from epokio import demo


def _rows(p):
    return len((p / "results.csv").read_text().splitlines()) - 1


def test_live_rows_grow_and_finish(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "DIR", tmp_path / "demo")
    d = demo.DIR / demo.LIVE
    demo.start_live(n=5, sec=0.05)
    try:
        deadline = time.time() + 5
        while _rows(d) < 5 and time.time() < deadline:
            time.sleep(0.02)
        assert _rows(d) == 5
        assert "epochs: 5" in (d / "args.yaml").read_text()
    finally:
        demo.stop_live()


def test_remove_stops_writer(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "DIR", tmp_path / "demo")
    monkeypatch.setattr(demo, "LIVE_SEC", 0.05)
    monkeypatch.setattr(demo, "LIVE_EPOCHS", 1000)
    made = demo.create()
    assert len(made) == 4 and demo.live_running()
    time.sleep(0.2)
    assert demo.remove()
    assert not demo.live_running()
    time.sleep(0.2)
    assert not demo.DIR.exists()          # 스레드가 폴더를 다시 만들지 않는다
