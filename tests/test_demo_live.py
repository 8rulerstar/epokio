import time

from epokio import demo


def _rows(p):
    # 윈도우: 쓰는 쪽이 바꿔치기하는 순간에 열면 PermissionError(또는 잠깐 없음). 그때는 다시 본다
    for _ in range(50):
        try:
            return len((p / "results.csv").read_text().splitlines()) - 1
        except (PermissionError, FileNotFoundError):
            time.sleep(0.01)
    return -1


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


def test_a_refused_swap_is_retried(tmp_path, monkeypatch):
    """★윈도우에서 읽는 쪽이 results.csv를 연 순간 바꿔치기가 거절되면 기록기가 멈춰 연습 학습이 그 자리에 섰다"""
    from pathlib import Path
    real, refused = Path.replace, []

    def flaky(self, target):
        if len(refused) < 3:
            refused.append(target)
            raise PermissionError("in use")
        return real(self, target)

    monkeypatch.setattr(Path, "replace", flaky)
    monkeypatch.setattr(demo, "DIR", tmp_path / "demo")
    d = demo.DIR / demo.LIVE
    demo.start_live(n=3, sec=0.02)
    try:
        deadline = time.time() + 5
        while _rows(d) < 3 and time.time() < deadline:
            time.sleep(0.02)
        assert len(refused) == 3 and _rows(d) == 3
    finally:
        demo.stop_live()
