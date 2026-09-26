"""맥 CPU 사용률: 눈금 차이 계산과 "못 재면 None" 규약."""
import platform

import pytest

from epokio import maccpu, sysinfo

# 코어 2개분 [user, system, idle, nice]
A = [100, 50, 800, 0, 100, 50, 800, 0]


def test_first_sample_is_none_not_zero():
    """비교할 직전 값이 없으면 0.0 이 아니라 None. 화면이 "–" 를 그리게."""
    assert maccpu.busy_pct(None, A) is None
    assert maccpu.busy_pct([], A) is None


def test_busy_is_share_of_non_idle_ticks():
    b = [c + d for c, d in zip(A, [100, 0, 100, 0, 0, 0, 200, 0])]
    # 늘어난 눈금 400 중 idle 300 → 25%
    assert maccpu.busy_pct(A, b) == pytest.approx(25.0)


def test_fully_busy_and_fully_idle():
    assert maccpu.busy_pct(A, [c + d for c, d in zip(A, [10, 10, 0, 0] * 2)]) == 100.0
    assert maccpu.busy_pct(A, [c + d for c, d in zip(A, [0, 0, 10, 0] * 2)]) == 0.0


def test_rewind_and_stall_are_none():
    assert maccpu.busy_pct(A, [x - 1 for x in A]) is None      # 32비트 눈금이 한 바퀴 돌았다
    assert maccpu.busy_pct(A, A) is None                        # 두 번 읽는 사이 눈금이 안 올랐다
    assert maccpu.busy_pct(A, A[:4]) is None                    # 코어 수가 바뀌었다


@pytest.mark.skipif(platform.system() != "Darwin" or platform.machine() != "arm64",
                    reason="애플 실리콘 맥에서만")
def test_live_reading_is_in_range_and_first_is_none():
    maccpu.reset()
    assert maccpu.cpu_percent() is None          # 첫 호출
    v = maccpu.cpu_percent()
    assert v is None or 0.0 <= v <= 100.0


def test_mac_cpu_ai_takes_total_from_ticks_and_ai_share_from_ps(monkeypatch):
    """★전체 CPU 는 눈금 차이에서(ps 의 %cpu 는 수명 평균이라 지금 값이 아니다),
    AI 몫은 그대로 ps 에서. ps 는 한 번만 부른다."""
    calls = []
    monkeypatch.setattr(sysinfo, "_run", lambda cmd, timeout=3: calls.append(cmd) or "  6.4 /a/claude\n 90.0 /b/kernel_task\n")
    monkeypatch.setattr(sysinfo.maccpu, "cpu_percent", lambda: 12.5)
    cpu, ai = sysinfo._mac_cpu_ai()
    assert cpu == 12.5                       # (6.4 + 90.0) / 12코어 같은 옛 계산이 아니다
    assert ai == pytest.approx(6.4)          # claude 프로세스 몫
    assert len(calls) == 1 and calls[0][:2] == ["ps", "-Ao"]


def test_mac_cpu_ai_passes_none_through(monkeypatch):
    """눈금을 못 재면 0 으로 위장하지 않고 None 을 그대로 넘긴다."""
    monkeypatch.setattr(sysinfo, "_run", lambda cmd, timeout=3: "")
    monkeypatch.setattr(sysinfo.maccpu, "cpu_percent", lambda: None)
    assert sysinfo._mac_cpu_ai() == (None, None)
