"""작업 시작(학습·대기열·스윕·검사)은 기본으로 꺼져 있다. 켜는 길은 `epokio config launch_runs on`(이 기계), --launch-runs(맥 앱이
띄운 도우미), EPOKIO_LAUNCH_RUNS=1 셋뿐이다. 웹(POST /config)으로는 못 켠다. conftest가 켜 두므로 여기서는 끈다."""
import sys
from pathlib import Path

import pytest

from epokio import config, config_cli
from epokio.agent import Agent
from epokio.jobs_queue import Queue

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "epokio" / "web"


@pytest.fixture(autouse=True)
def _off(monkeypatch):
    monkeypatch.delenv("EPOKIO_LAUNCH_RUNS", raising=False)


def _agent(tmp_path):
    a = Agent.__new__(Agent)
    a.roots, a.label, a.boot = [tmp_path], "t", "b"
    a.queue = Queue(tmp_path / "jobs.json")
    return a


def test_starting_jobs_is_off_by_default():
    assert config.DEFAULTS["launch_runs"] is False
    assert config.load()["launch_runs"] is False and not config.launch_runs()
    assert Agent.launch_flag is False


def test_an_off_helper_refuses_every_way_to_start_a_job_and_says_how_to_turn_it_on(tmp_path):
    a = _agent(tmp_path)
    for route, body in (("/jobs", {"kind": "train", "params": {}}), ("/jobs", {"kind": "setup"}),
                        ("/jobs", {"kind": "practice", "params": {"epochs": 1}}), ("/sweeps", {}),
                        ("/predict", {}), ("/classes", {"path": str(tmp_path)})):
        code, got = a.post(route, body)
        assert code == 403 and got["code"] == "launch_off", route
        assert "config launch_runs on" in got["cmd"] and got["cmd"] in got["error"]
    assert a.queue.jobs == []
    assert a.get("/health", {})["launch_runs"] is False


def test_managing_jobs_already_queued_stays_open(tmp_path):
    a = _agent(tmp_path)
    for route in ("/jobs/clear", "/jobs/nope/cancel", "/jobs/reorder"):
        got = a.post(route, {"ids": []})
        assert not (isinstance(got, tuple) and got[0] == 403), route


def test_config_command_turns_it_on_and_off_without_restarting_the_helper(tmp_path, capsys):
    a = _agent(tmp_path)
    assert config_cli.main(["launch_runs", "on"]) == 0
    assert "Reload the web page" in capsys.readouterr().out
    assert config.launch_runs() and a.get("/health", {})["launch_runs"] is True
    code, _ = a.post("/jobs", {"kind": "practice", "params": {"epochs": 1}})
    assert code == 200
    assert config_cli.main(["launch_runs", "off"]) == 0
    assert a.post("/jobs", {"kind": "practice", "params": {"epochs": 1}})[0] == 403


def test_config_command_lists_settings_and_rejects_bad_values(capsys):
    assert config_cli.main([]) == 0
    out = capsys.readouterr().out
    assert "launch_runs" in out and "off" in out
    assert config_cli.main(["launch_runs", "maybe"]) == 2
    assert config_cli.main(["no_such_thing", "1"]) == 2
    assert config_cli.main(["stall_min", "abc"]) == 2
    assert config_cli.main(["stall_min", "10"]) == 0 and config.load()["stall_min"] == 10


def test_the_web_page_cannot_turn_it_on(tmp_path):
    a = _agent(tmp_path)
    code, c = a.post("/config", {"launch_runs": True, "stall_min": 7})
    assert code == 200 and c["launch_runs"] is False and c["stall_min"] == 7
    assert not config.launch_runs()


def test_the_flag_and_the_env_var_turn_it_on(tmp_path, monkeypatch):
    a = _agent(tmp_path)
    a.launch_flag = True                   # --launch-runs
    assert a.post("/jobs", {"kind": "practice", "params": {"epochs": 1}})[0] == 200
    monkeypatch.setenv("EPOKIO_LAUNCH_RUNS", "1")
    assert config.launch_runs()


def test_agent_command_line_has_the_flag_and_the_mac_app_passes_it():
    src = (ROOT / "src" / "epokio" / "server_cli.py").read_text(encoding="utf-8")
    assert '"--launch-runs"' in src and "agent.launch_flag = a.launch_runs" in src
    swift = (ROOT / "mac" / "Sources" / "Epokio" / "AgentLauncher.swift").read_text(encoding="utf-8")
    assert '"--launch-runs"' in swift


def test_the_web_page_hides_train_queue_and_sweeps_when_off():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for name in ("train", "queue", "sweeps"):
        tag = next(line for line in html.splitlines() if f'data-tab="{name}"' in line)
        assert "data-launch" in tag, name
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "body.nolaunch nav [data-launch]" in css and "body.nolaunch .launch-note" in css
    main = (WEB / "main.js").read_text(encoding="utf-8")
    assert "h.launch_runs !== false" in main            # 옛 도우미(값 없음)는 예전처럼
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'j.code === "launch_off"' in app and "launch-note" in app


def test_mcp_tools_that_start_jobs_say_it_may_be_off():
    src = (ROOT / "src" / "epokio" / "mcp_server.py").read_text(encoding="utf-8")
    assert "epokio config launch_runs on" in src and src.count("+ LAUNCH_NOTE") == 2


def test_cli_lists_the_config_command(capsys, monkeypatch):
    from epokio import cli
    monkeypatch.setattr(sys, "argv", ["epokio"])
    cli._main()
    assert "config" in capsys.readouterr().out


# 맥 앱이 기대는 약속. 앱은 pip 도우미(작업 시작 끔)를 그대로 쓸 때 /health의 launch_runs를 보고 켜는 버튼을 띄우고,
# 누르면 ~/.epokio/config.json에 launch_runs: true를 직접 쓴다(LaunchGate.swift). 아래가 깨지면 그 버튼이 조용히 안 듣는다
SWIFT = ROOT / "mac" / "Sources" / "Epokio"


def test_a_config_file_written_like_the_mac_app_turns_it_on_without_a_restart(tmp_path):
    import json
    a = _agent(tmp_path)
    config.update({"stall_min": 12, "disk_low_gb": 7.5})
    assert a.get("/health", {})["launch_runs"] is False
    assert a.post("/jobs", {"kind": "practice", "params": {"epochs": 1}})[1]["code"] == "launch_off"
    # JSONSerialization(.prettyPrinted, .sortedKeys)처럼: 다른 값은 그대로, 실수가 정수로 바뀔 수 있다, 모르는 열쇠도 남는다
    c = json.loads(config.FILE.read_text(encoding="utf-8"))
    c.update({"launch_runs": True, "disk_low_gb": 7, "from_a_newer_app": 1})
    config.FILE.write_text(json.dumps(c, indent=2, sort_keys=True), encoding="utf-8")
    assert a.get("/health", {})["launch_runs"] is True
    assert a.post("/jobs", {"kind": "practice", "params": {"epochs": 1}})[0] == 200
    assert config.load()["stall_min"] == 12 and config.load()["disk_low_gb"] == 7


def test_the_web_page_cannot_turn_it_off_or_on_after_the_app_turned_it_on(tmp_path):
    config.FILE.parent.mkdir(parents=True, exist_ok=True)
    config.FILE.write_text('{"launch_runs": true}', encoding="utf-8")
    a = _agent(tmp_path)
    code, c = a.post("/config", {"launch_runs": False, "stall_min": 9})
    assert code == 200 and c["launch_runs"] is True and config.launch_runs()


def test_only_a_real_true_counts(tmp_path):
    config.FILE.parent.mkdir(parents=True, exist_ok=True)
    for raw in ('{"launch_runs": "true"}', '{"launch_runs": 1}', "{broken"):
        config.FILE.write_text(raw, encoding="utf-8")
        assert not config.launch_runs(), raw


def test_the_mac_app_reads_health_and_writes_the_same_file_and_key():
    gate = (SWIFT / "LaunchGate.swift").read_text(encoding="utf-8")
    rel = config.FILE.relative_to(config.FILE.parents[1]).as_posix()      # .epokio/config.json
    assert f'"{rel}"' in gate and 'c["launch_runs"] = true' in gate and 'obj["launch_runs"] as? Bool' in gate
    assert '"' + "epokio " + config.LAUNCH_CMD + '"' in gate
    client = (SWIFT / "AgentClient.swift").read_text(encoding="utf-8")
    assert '"launch_off"' in client and 'obj["cmd"]' in client
    for view in ("TrainView.swift", "QueueView.swift"):
        assert "LaunchOffCard(" in (SWIFT / view).read_text(encoding="utf-8"), view
