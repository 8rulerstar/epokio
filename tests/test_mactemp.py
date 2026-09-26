from epokio import mactemp
from epokio.mactemp import pick_cpu_temp


def test_picks_max_of_cpu_sensors():
    r = [("PMU tdie1", 61.2), ("PMU tdie8", 68.44), ("NAND CH0 temp", 80.0),
         ("gas gauge battery", 90.0), ("PMU tcal", 99.0)]
    assert pick_cpu_temp(r) == 68.4


def test_drops_unrealistic_values():
    r = [("PMU tdev1", -9201.1), ("PMU tdie1", 0.0), ("PMU tdie2", 150.0), ("PMU tdie3", 55.0)]
    assert pick_cpu_temp(r) == 55.0


def test_m1_names():
    r = [("pACC MTR Temp Sensor2", 47.0), ("eACC MTR Temp Sensor0", 41.0), ("SOC MTR Temp Sensor1", 52.5)]
    assert pick_cpu_temp(r) == 52.5


def test_none_when_nothing_matches():
    assert pick_cpu_temp([]) is None
    assert pick_cpu_temp([("NAND CH0 temp", 45.0), ("PMU tdev1", -9201.0)]) is None
    assert pick_cpu_temp([(None, 50.0), ("PMU tdie1", None)]) is None


def test_non_apple_silicon_returns_none(monkeypatch):
    monkeypatch.setattr(mactemp.platform, "system", lambda: "Linux")
    assert mactemp.cpu_temp() is None


def test_failure_is_silent_and_sticky(monkeypatch):
    monkeypatch.setattr(mactemp.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(mactemp.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(mactemp, "_state", {"reader": None, "failed": False, "at": 0.0, "value": None})
    calls = []

    def boom():
        calls.append(1)
        raise OSError("no")
    monkeypatch.setattr(mactemp, "_Reader", boom)
    assert mactemp.cpu_temp(now=1.0) is None
    assert mactemp.cpu_temp(now=100.0) is None
    assert calls == [1]


def test_cache(monkeypatch):
    monkeypatch.setattr(mactemp.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(mactemp.platform, "machine", lambda: "arm64")
    vals = iter([[("PMU tdie1", 60.0)], [("PMU tdie1", 70.0)]])

    class Fake:
        def read(self):
            return next(vals)
    monkeypatch.setattr(mactemp, "_state", {"reader": Fake(), "failed": False, "at": 0.0, "value": None})
    assert mactemp.cpu_temp(now=10.0) == 60.0
    assert mactemp.cpu_temp(now=12.0) == 60.0
    assert mactemp.cpu_temp(now=10.0 + mactemp.CACHE_SEC) == 70.0
