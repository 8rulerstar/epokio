import ctypes
import platform

import pytest

from epokio import macfan
from epokio.macfan import fan_pct


def test_the_fastest_fan_decides():
    assert fan_pct([(4775.4, 7826.0), (5141.3, 7826.0)]) == (65.7, 5141)


def test_drops_fans_it_cannot_read_sensibly():
    assert fan_pct([(3000.0, 0.0), (-5.0, 7000.0), (99999.0, 7000.0), (3500.0, 7000.0)]) == (50.0, 3500)


def test_none_when_there_is_nothing_to_read():
    assert fan_pct([]) is None


def test_a_little_over_max_reads_as_full():
    assert fan_pct([(7900.0, 7826.0)]) == (100.0, 7900)


def test_the_smc_struct_matches_the_c_layout():
    """keyInfo 뒤 패딩이 빠지면 크기는 같아도 필드가 밀려 모든 호출이 실패했다(kIOReturnBadArgument)."""
    assert ctypes.sizeof(macfan._KeyData) == 80
    assert macfan._KeyData.result.offset == 40 and macfan._KeyData.bytes.offset == 48


def test_non_apple_silicon_returns_none(monkeypatch):
    monkeypatch.setattr(macfan.platform, "system", lambda: "Linux")
    assert macfan.fan() is None


def test_a_mac_without_fans_stops_asking(monkeypatch):
    monkeypatch.setattr(macfan.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(macfan.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(macfan, "_state", {"reader": None, "failed": False, "at": 0.0, "value": None})
    monkeypatch.setattr(macfan, "_Reader", lambda: type("R", (), {"count": 0, "read": lambda self: []})())
    assert macfan.fan(now=1.0) is None
    assert macfan._state["failed"] is True


@pytest.mark.skipif(platform.system() != "Darwin" or platform.machine() != "arm64", reason="애플 실리콘 맥에서만")
def test_reads_this_mac_without_crashing():
    v = macfan.fan()
    assert v is None or (0 <= v[0] <= 100 and v[1] >= 0)
