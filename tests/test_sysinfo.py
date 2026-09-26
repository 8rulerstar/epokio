"""sysinfo: 파서는 명령 출력 샘플 문자열로만 시험한다(실제 기기 값에 기대지 않는다).
끝의 몇 개는 CPU·메모리를 실제로 읽어 오는지 본다. 맥은 ps/vm_stat, 윈도우는 ctypes, 리눅스는 /proc."""
import platform
import time

import pytest

from epokio import sysinfo
from epokio.sysinfo import (Snapshot, parse_netstat_ib, parse_pmset_batt,
                            parse_power_supply, parse_proc_net_dev)

NETSTAT = """Name       Mtu   Network       Address            Ipkts Ierrs     Ibytes    Opkts Oerrs     Obytes  Coll
lo0        16384 <Link#1>                       2041897     0 3722544968  2041897     0 3722544968     0
lo0        16384 127           127.0.0.1        2041897     - 3722544968  2041897     - 3722544968     -
gif0*      1280  <Link#2>                             0     0          0        0     0          0     0
en0        1500  <Link#11>   a4:83:e7:00:00:01  900000     0 1000000000   500000     0  200000000     0
en0        1500  192.168.0     192.168.0.5       900000     - 1000000000   500000     -  200000000     -
utun0      1380  <Link#15>                           10     0       5000       20     0       7000     0
"""

PROC = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 9999999   100    0    0    0     0          0         0  9999999   100    0    0    0     0       0          0
  eth0: 123456    1000    0    0    0     0          0         0   65432     900    0    0    0     0       0          0
 wlan0:    100       1    0    0    0     0          0         0      50       1    0    0    0     0       0          0
"""


def test_netstat_counts_link_rows_once_and_skips_loopback():
    assert parse_netstat_ib(NETSTAT) == (1000000000 + 5000, 200000000 + 7000)


def test_netstat_garbage_is_none():
    assert parse_netstat_ib("") is None
    assert parse_netstat_ib("no header here\n") is None


def test_proc_net_dev():
    assert parse_proc_net_dev(PROC) == (123456 + 100, 65432 + 50)
    assert parse_proc_net_dev("") is None


def test_pmset_discharging():
    out = ("Now drawing from 'Battery Power'\n"
           " -InternalBattery-0 (id=22544483)\t80%; discharging; 2:28 remaining present: true\n")
    assert parse_pmset_batt(out) == (80.0, False)


def test_pmset_charging_and_charged():
    out = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t55%; charging; 1:02 remaining present: true\n"
    assert parse_pmset_batt(out) == (55.0, True)
    out = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t100%; charged; 0:00 remaining present: true\n"
    assert parse_pmset_batt(out) == (100.0, True)


def test_pmset_desktop_without_battery_is_none():
    assert parse_pmset_batt("Now drawing from 'AC Power'\n") == (None, None)
    assert parse_pmset_batt("") == (None, None)


def test_power_supply():
    assert parse_power_supply("73\n", "Discharging\n") == (73.0, False)
    assert parse_power_supply("100", "Full") == (100.0, True)
    assert parse_power_supply(None, None) == (None, None)
    assert parse_power_supply("x", "Charging") == (None, None)


def test_net_rate_diff_and_rewind(monkeypatch):
    monkeypatch.setattr(sysinfo, "_NET_LAST", {})
    assert sysinfo.net_rate(now=10.0, counters=(1000, 500)) == (None, None)
    assert sysinfo.net_rate(now=12.0, counters=(3000, 1500)) == (500.0, 1000.0)   # (업, 다운)
    assert sysinfo.net_rate(now=13.0, counters=(10, 10)) == (None, None)          # 카운터 되감김


def test_disk_bad_path_is_none():
    assert sysinfo.disk("/definitely/not/here/xyz") == (None, None)


def test_old_snapshot_dict_still_loads_and_keeps_keys():
    old = {"host": "h", "cpu": 1.0, "mem_used": 2.0, "mem_total": 4.0, "gpus": [], "at": 0.0}
    s = Snapshot.from_dict(old)
    assert s.battery is None and s.net_up is None
    d = s.to_dict()
    for k in ("host", "cpu", "mem_used", "mem_total", "gpus", "at",
              "disk_free", "disk_total", "net_up", "net_down", "battery", "charging"):
        assert k in d



def test_memory_is_read_on_this_platform():
    s = sysinfo.sample()
    assert s.mem_total and s.mem_total > 0.5, "메모리 총량을 못 읽었다"
    assert s.mem_used is not None and 0 <= s.mem_used <= s.mem_total


def test_cpu_needs_two_samples_then_gives_a_percentage():
    """CPU는 지난번과의 차이로 낸다. 첫 값이 None인 건 정상이고, 두 번째부터 값이 나온다."""
    if platform.system() not in ("Windows", "Linux", "Darwin"):
        pytest.skip("이 플랫폼은 CPU 읽는 방법을 안 넣었다")
    sysinfo.sample()
    time.sleep(0.3)
    cpu = sysinfo.sample().cpu
    assert cpu is not None, "CPU 사용률을 못 읽었다"
    assert 0.0 <= cpu <= 100.0


def test_cpu_delta_is_bounded_and_ignores_a_still_clock():
    assert sysinfo._cpu_delta("t", 0, 0) is None            # 첫 호출은 값이 없다
    assert sysinfo._cpu_delta("t", 50, 100) == 50.0
    assert sysinfo._cpu_delta("t", 50, 100) is None         # 시계가 안 움직이면 0으로 나누지 않는다
    assert sysinfo._cpu_delta("t", 1050, 1100) == 100.0     # 100을 넘지 않는다
