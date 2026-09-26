"""쉬는 상태 전력: 간격이 늘고, 바뀌면 줄고, 절전·배터리·수동이 제대로 고른다"""
import pytest

from epokio import config, pace


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FILE", tmp_path / "config.json")
    return config


def test_auto_grows_when_idle_and_resets_on_change(cfg):
    p = pace.Pace(battery=lambda: (None, None))
    assert [p.interval(False, False) for _ in range(5)] == [15, 30, 60, 60, 60]
    assert p.interval(False, True) == 8                       # 무엇이 바뀌면 바로 짧게
    assert p.interval(True, False) == 8                       # 도는 학습이 있으면 짧게


def test_saver_and_battery(cfg):
    cfg.update({"scan_mode": "saver"})
    p = pace.Pace(battery=lambda: (None, None))
    assert p.interval(True, False) == 30 and p.interval(False, False) == 120
    cfg.update({"scan_mode": "auto"})
    on_batt = pace.Pace(battery=lambda: (55.0, False))
    assert on_batt.mode() == "saver"                           # 배터리면 저절로 절전
    cfg.update({"saver_on_battery": False})
    assert pace.Pace(battery=lambda: (55.0, False)).mode() == "auto"


def test_manual_does_not_scan(cfg):
    cfg.update({"scan_mode": "manual"})
    p = pace.Pace(battery=lambda: (None, None))
    assert not p.should_scan() and p.interval(False, False) == 8     # 대기열·스윕은 계속 챙긴다


def test_config_rejects_unknown_choices(cfg):
    c = cfg.update({"scan_mode": "turbo", "saver_on_battery": "yes"})
    assert c["scan_mode"] == "auto" and c["saver_on_battery"] is True


def test_wake_resets(cfg):
    p = pace.Pace(battery=lambda: (None, None))
    p.interval(False, False); p.interval(False, False)
    p.wake.set()
    assert p.sleep(5) is True and p.step == 0


def test_stall_limits_follow_epoch_time():
    from epokio import scan
    rows = [{"epoch": str(i), "time": str(i * 600)} for i in range(1, 8)]          # 에폭당 10분
    assert scan.recent_epoch_sec(rows) == 600
    stale, ended = scan.stall_limits(600)
    assert stale >= 30 * 60 and ended >= 100 * 60                                   # 3분 고정이면 매 에폭 "멈춤"이었다
    assert scan.stall_limits(None) == (scan.STALE_SEC, scan.ENDED_SEC)              # 시간 열 없으면 설정값 그대로
    assert scan.stall_limits(5)[0] == scan.STALE_SEC                                # 빠른 학습은 설정값이 바닥


def test_battery_value_is_never_read_before_it_is_known():
    """★읽기 전에 시각부터 적어, 읽는 사이 다른 스레드가 기본값(전원 연결)을 받았다"""
    import threading, time
    from epokio.pace import Pace
    started, release = threading.Event(), threading.Event()

    def slow_battery():
        started.set(); release.wait(2)
        return 50, False                      # 배터리로 도는 중
    p = Pace(battery=slow_battery)
    t = threading.Thread(target=p.on_battery); t.start()
    started.wait(2)
    seen = []
    reader = threading.Thread(target=lambda: seen.append(p.on_battery()))   # 읽는 도중에 묻는다
    reader.start(); time.sleep(0.05); release.set()
    t.join(2); reader.join(2)
    assert seen == [True]
