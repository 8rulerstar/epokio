"""agent 실행 요청의 입력 검사: 빈 경로·잘못된 값은 400으로 거절하고 아무것도 바꾸지 않는다."""
import os
import tempfile
from pathlib import Path

import pytest

from epokio.agent import Agent


def _can_symlink() -> bool:
    """윈도우는 개발자 모드나 관리자 권한이 있어야 심링크를 만든다(WinError 1314)."""
    with tempfile.TemporaryDirectory() as d:
        try:
            os.symlink(d, os.path.join(d, "probe"))
            return True
        except (OSError, NotImplementedError, AttributeError):
            return False


def _agent(tmp_path, monkeypatch):
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    monkeypatch.setattr(Agent, "HOOKS_FILE", tmp_path / "hooks.json")
    a = Agent.__new__(Agent)          # 백그라운드 스레드 없이 요청 처리만 시험한다
    a.roots, a.label = [], "t"
    return a


def test_empty_root_is_rejected(tmp_path, monkeypatch):
    a = _agent(tmp_path, monkeypatch)
    assert a.post("/roots", {})[0] == 400
    assert a.post("/roots", {"path": "  "})[0] == 400
    assert a.roots == []                       # ★예전엔 "."(홈 전체)가 들어갔다


def test_webhooks_must_be_a_list_and_not_wipe(tmp_path, monkeypatch):
    a = _agent(tmp_path, monkeypatch)
    assert a.post("/webhooks", {"urls": ["https://ntfy.sh/x"]})[0] == 200
    assert a.post("/webhooks", {"urls": "https://ntfy.sh/y"})[0] == 400
    assert a.post("/webhooks", {"urls": ["http://plain"]})[0] == 400
    assert "ntfy.sh/x" in a.HOOKS_FILE.read_text()   # 거절된 요청이 기존 값을 지우지 않는다


def test_jobs_need_their_params(tmp_path, monkeypatch):
    a = _agent(tmp_path, monkeypatch)
    assert a.post("/jobs", {"kind": "train"})[0] == 400
    assert a.post("/jobs", {"kind": "evaluate", "params": {"model": "m"}})[0] == 400
    assert a.post("/jobs", {"kind": "export", "params": {"model": "m", "format": "exe"}})[0] == 400


def test_setup_without_any_python_says_so(tmp_path, monkeypatch):
    """구운 exe 에 파이썬이 하나도 없으면 설치 작업을 대기열에 넣지 않고 무엇을 하라고 말한다."""
    from epokio import envs
    a = _agent(tmp_path, monkeypatch)
    monkeypatch.setattr(envs, "base_python", lambda: None)
    code, body = a.post("/jobs", {"kind": "setup"})
    assert code == 400 and "python.org" in body["error"]


def test_setup_script_installs_cuda_torch_on_windows_with_nvidia(tmp_path, monkeypatch):
    """윈도우 PyPI torch 는 CPU 전용이다. NVIDIA 가 있으면 CUDA 판을 먼저 깔아야 GPU 로 학습한다."""
    from epokio import jobs
    monkeypatch.setattr(jobs, "SCRIPTS", tmp_path)
    cmd = jobs.build_command(jobs.Job(id="s1", kind="setup", name="Set up Python", python="py"))
    src = Path(cmd[-1]).read_text(encoding="utf-8")
    compile(src, "setup.py", "exec")                                   # 틀 채우기가 문법을 깨지 않았다
    assert jobs.CUDA_INDEX in src and 'shutil.which("nvidia-smi")' in src
    assert src.index(jobs.CUDA_INDEX) < src.index('EPOKIO_ULTRALYTICS_SPEC')   # torch 가 먼저(ultralytics 는 판 고정으로 설치)


def test_report_folder_must_exist(tmp_path, monkeypatch):
    a = _agent(tmp_path, monkeypatch)
    assert a.post("/report", {"folder": str(tmp_path / "nope")})[0] == 400


def test_machine_warnings_once(tmp_path, monkeypatch):
    from types import SimpleNamespace
    a = _agent(tmp_path, monkeypatch)
    pushed = []
    a._push = lambda kind, before, run: pushed.append((kind, run["name"]))
    gpu = SimpleNamespace(name="RTX", temp=91.0, mem_used=23.5, mem_total=24.0, util=99)
    a.sampler = SimpleNamespace(latest=SimpleNamespace(gpus=[gpu]))
    from epokio import config
    monkeypatch.setattr(config, "FILE", tmp_path / "config.json")
    config.update({"disk_low_gb": 500})                   # 어떤 디스크든 "부족"으로 보게(허용 최댓값)
    monkeypatch.setattr("shutil.disk_usage", lambda p: type("U", (), {"free": 1 * 2**30})())
    a._check_machine([tmp_path])
    a._check_machine([tmp_path])                          # 30분 안에는 다시 알리지 않는다
    assert [k for k, _ in pushed] == ["disk_low", "gpu_hot", "gpu_mem"]
    assert "91" in pushed[1][1]



def test_fans_near_full_warn_only_when_it_lasts_during_training(tmp_path, monkeypatch):
    """잠깐 치솟는 건 흔하다(에폭 시작·검증). 학습 중 5분 넘게 이어질 때만, 학습이 없으면 다른 앱 탓이라 알리지 않는다."""
    from types import SimpleNamespace
    a = _agent(tmp_path, monkeypatch)
    pushed = []
    a._push = lambda kind, before, run: pushed.append((kind, run["name"]))
    hot, calm = SimpleNamespace(fan=96.0, fan_rpm=7500), SimpleNamespace(fan=40.0, fan_rpm=3100)
    a._mon = SimpleNamespace(runs=[])
    a._check_fan(hot, now=0); a._check_fan(hot, now=400)
    assert pushed == []                                    # 학습이 없다
    a._mon.runs = [SimpleNamespace(state="running")]
    a._check_fan(hot, now=1000); a._check_fan(calm, now=1100); a._check_fan(hot, now=1200)
    a._check_fan(hot, now=1200 + a.FAN_FULL_SEC - 1)
    assert pushed == []                                    # 중간에 식어서 다시 잰다
    a._check_fan(hot, now=1200 + a.FAN_FULL_SEC)
    assert [k for k, _ in pushed] == ["fan_max"] and "7500" in pushed[0][1] and "96" in pushed[0][1]
    a._check_fan(SimpleNamespace(), now=9000)             # 팬 없는 맥(옛 표본)도 죽지 않는다
    a._warned = {}
    gpu = SimpleNamespace(fan=97.0, fan_rpm=None, fan_source="gpu")
    a._check_fan(gpu, now=20000); a._check_fan(gpu, now=20000 + a.FAN_FULL_SEC)
    assert pushed[-1][0] == "fan_max" and "GPU" in pushed[-1][1] and "rpm" not in pushed[-1][1]   # 윈도우·리눅스 GPU 팬

@pytest.mark.skipif(not _can_symlink(), reason="심링크를 만들 수 없는 환경(윈도우 개발자 모드 꺼짐)")
def test_remove_root_matches_resolved_path(tmp_path, monkeypatch):
    a = _agent(tmp_path, monkeypatch)
    real = tmp_path / "runs"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    a.post("/roots", {"path": str(link)})            # 저장은 실제 경로로
    assert a.roots == [real.resolve()]
    a.post("/roots/remove", {"path": str(link)})     # 링크 경로로 빼도 빠진다
    assert a.roots == []


def test_config_limits_and_quiet_hours(tmp_path, monkeypatch):
    from datetime import datetime
    from epokio import config, scan
    monkeypatch.setattr(config, "FILE", tmp_path / "config.json")
    c = config.update({"stall_min": 9999, "gpu_hot_c": "hot", "quiet_from": 23, "quiet_to": 7, "bogus": 1})
    assert c["stall_min"] == 240 and c["gpu_hot_c"] == 85 and "bogus" not in c      # 범위로 자르고, 틀린 값은 무시
    config.apply(c)
    assert scan.STALE_SEC == 240 * 60
    at = lambda h: datetime(2026, 9, 22, h)
    assert config.quiet_now(c, at(23)) and config.quiet_now(c, at(3)) and not config.quiet_now(c, at(12))
    config.apply(config.update({"stall_min": 3}))                                     # 다른 테스트에 영향 없게 되돌림


def test_clear_finished_keeps_results_you_reopen(tmp_path):
    from epokio.jobs import Queue
    q = Queue(tmp_path / "jobs.json")
    a = q.add("train", "t", "py", {}); a.state = "done"
    b = q.add("evaluate", "e", "py", {}); b.state = "done"
    c = q.add("train", "q", "py", {})                          # 아직 대기
    d = q.add("evaluate", "f", "py", {}); d.state = "failed"
    assert q.clear_finished() == 2
    assert {j.name for j in q.jobs} == {"e", "q"}


def test_invalid_job_inputs_are_refused_before_the_queue(tmp_path, monkeypatch):
    """스크립트 인자에 숫자가 섞이면 대기열 스레드 안에서 터졌다. 받기 전에 거절한다."""
    a = _agent(tmp_path, monkeypatch)
    assert a.post("/jobs", {"kind": "script", "python": "py", "params": {"args": ["-c", 1]}})[0] == 400
    assert a.post("/jobs", {"kind": "script", "python": 3, "params": {"args": []}})[0] == 400
    assert a.post("/jobs", {"kind": "train", "params": "data.yaml"})[0] == 400


def test_machine_warnings_carry_a_source(tmp_path, monkeypatch):
    """디스크·GPU 경고 사건에 source가 없어서 맥 앱이 사건 목록을 못 읽고 알림이 영영 멈췄다."""
    from collections import deque
    a = _agent(tmp_path, monkeypatch)
    a.events, a.seq = deque(maxlen=200), 0
    monkeypatch.setattr(a, "_webhook", lambda *x: None)
    a._warn("disk_low", "3 GB free")
    run = a.events[-1]["run"]
    assert run["source"] == "t" and run["history"] == []


def test_a_removed_folder_is_not_found_again_and_found_folders_are_not_saved(tmp_path, monkeypatch):
    """5분마다 찾기가 사용자가 뺀 폴더를 되살렸고, 찾은 폴더까지 roots.json에 남겨 다음부터 찾기가 멈췄다."""
    a = _agent(tmp_path, monkeypatch)
    a.discovered, a.removed = set(), set()
    found, mine = tmp_path / "found", tmp_path / "mine"
    found.mkdir(); mine.mkdir()
    a.roots.append(found.resolve()); a.discovered.add(found.resolve())
    assert a.post("/roots", {"path": str(mine)})[0] == 200
    import json
    assert json.loads(a.ROOTS_FILE.read_text(encoding="utf-8")) == [str(mine.resolve())]
    a.post("/roots/remove", {"path": str(found)})
    assert found.resolve() in a.removed and found.resolve() not in a.roots


def test_saving_one_webhook_from_the_web_keeps_the_others(tmp_path, monkeypatch):
    """웹에서 하나를 저장하면 슬랙 등 다른 웹후크와 맥에서 고른 알림 종류가 조용히 지워졌다."""
    import json
    a = _agent(tmp_path, monkeypatch)
    a.post("/webhooks", {"urls": ["https://hooks.slack.com/x"], "kinds": ["finished", "goal"]})
    a.post("/webhooks", {"urls": ["https://ntfy.sh/mine"], "add": True})
    cfg = json.loads(a.HOOKS_FILE.read_text(encoding="utf-8"))
    assert cfg["urls"] == ["https://hooks.slack.com/x", "https://ntfy.sh/mine"] and cfg["kinds"] == ["finished", "goal"]


def test_webhook_listing_never_shows_credentials(tmp_path, monkeypatch):
    a = _agent(tmp_path, monkeypatch)
    a.post("/webhooks", {"urls": ["https://user:secret@ntfy.example/topic"]})
    assert a.get("/webhooks", {})["hosts"] == ["ntfy.example"]


def test_a_broken_notes_file_is_kept_not_wiped(tmp_path, monkeypatch):
    """runmeta.json을 못 읽으면 빈 것으로 보고 그 위에 써서 별표·메모가 전부 지워졌다."""
    from epokio import runmeta
    runmeta.FILE.parent.mkdir(parents=True, exist_ok=True)
    runmeta.FILE.write_text('{"C:/runs/a": {"star": true}, broken', encoding="utf-8")
    runmeta.update(str(tmp_path / "b"), {"star": True})
    kept = list(runmeta.FILE.parent.glob("runmeta.broken-*.json"))
    assert kept and "broken" in kept[0].read_text(encoding="utf-8")


def test_two_webhook_saves_at_once_keep_both(tmp_path, monkeypatch):
    """읽고 고치고 쓰는 사이에 다른 요청이 끼면 한쪽이 사라졌다(탭 둘에서 동시에 더하면 매번)."""
    import json, threading
    a = _agent(tmp_path, monkeypatch)
    ts = [threading.Thread(target=a.post, args=("/webhooks", {"urls": [f"https://ntfy.sh/t{i}"], "add": True})) for i in range(8)]
    for t in ts: t.start()
    for t in ts: t.join()
    assert len(json.loads(a.HOOKS_FILE.read_text(encoding="utf-8"))["urls"]) == 8


def test_a_damaged_webhooks_file_is_kept_and_reported(tmp_path, monkeypatch):
    a = _agent(tmp_path, monkeypatch)
    a.HOOKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    a.HOOKS_FILE.write_text('{"urls": ["https://hooks.slack.com/x"', encoding="utf-8")
    code, body = a.post("/webhooks", {"urls": ["https://ntfy.sh/y"], "add": True})
    assert code == 409 and list(a.HOOKS_FILE.parent.glob("*.broken-*.json"))


def test_resume_needs_a_checkpoint_and_not_a_busy_run(tmp_path, monkeypatch):
    import os
    from epokio.jobs import Job
    from epokio import envs
    a = _agent(tmp_path, monkeypatch)
    run = tmp_path / "runs" / "exp"
    (run / "weights").mkdir(parents=True)
    ckpt = run / "weights" / "last.pt"
    added = []

    class Q:
        jobs = []
        def add(self, *args):
            added.append(args)
            return Job(id="j", kind="train", name="n", python="py", params=args[3])
    monkeypatch.setattr(envs, "list_envs", lambda: [])
    a.queue = Q()
    body = {"kind": "train", "params": {"model": str(ckpt), "resume": True}}
    assert a.post("/jobs", body)[0] == 400                      # 파일이 없다
    ckpt.write_bytes(b"x")
    (run / "weights" / "best.pt").write_bytes(b"x")
    # best.pt는 안 된다(되감아 같은 에폭이 두 번 들어간다)
    assert a.post("/jobs", {"kind": "train", "params": {"model": str(run / "weights" / "best.pt"), "resume": True}})[0] == 400
    (run / "args.yaml").write_text("task: custom\n", encoding="utf-8")
    assert a.post("/jobs", body)[0] == 400                      # epokio.start()로 쓴 학습은 YOLO()가 못 읽는다
    (run / "args.yaml").write_text("task: detect\nsave_dir: runs/exp\n", encoding="utf-8")
    assert a.post("/jobs", body)[0] == 409                      # 방금 바뀌었다: 아직 돌고 있을 수 있다
    old = ckpt.stat().st_mtime - 3600
    os.utime(ckpt, (old, old))
    # 체크포인트는 오래됐어도 args.yaml을 방금 다시 썼다: 터미널에서 이어 하기로 다시 뜬 학습(첫 에폭이 끝나기 전)
    # ★그 사이에 '이어 하기'를 누르면 같은 폴더에 두 번째 학습이 붙었다
    assert a.post("/jobs", body)[0] == 409
    os.utime(run / "args.yaml", (old, old))
    code, err = a.post("/jobs", body)
    assert code == 400 and "Python" in err["error"]              # 쓸 파이썬이 없다
    monkeypatch.setattr(envs, "list_envs", lambda: [{"path": "py-ready", "ready": True}])
    assert a.post("/jobs", body)[0] == 200                      # data 없이도 된다
    assert added[0][2] == "py-ready"                            # 파이썬을 안 골랐으면 준비된 것으로
    assert added[0][4] == str(tmp_path)                         # save_dir(runs/exp)가 상대 경로면 처음 띄운 폴더에서
    Q.jobs = [Job(id="b", kind="train", name="n", python="py", params={"model": str(ckpt), "resume": True}, state="queued")]
    assert a.post("/jobs", body)[0] == 409                      # 아직 대기 중인 이어 하기(output이 비어 있어도)
    Q.jobs = [Job(id="c", kind="train", name="n", python="py", params={}, state="running", output=str(run))]
    assert a.post("/jobs", body)[0] == 409                      # 이미 그 폴더에 쓰는 중
    assert len(added) == 1


def test_changing_the_main_score_rescans_at_once(tmp_path, monkeypatch):
    """★감시 스레드가 다음에 훑을 때까지(최대 15초) 옛 대표 점수가 보였다"""
    import time
    a = _agent(tmp_path, monkeypatch)
    a.roots = [tmp_path]                                        # /meta는 지켜보는 폴더 안의 학습만 받는다
    a._scanned = (time.time(), [], [])
    assert a.post("/meta", {"path": str(tmp_path / "r"), "note": "x"})[0] == 200
    assert a._scanned is not None                               # 메모만 바꾸면 그대로
    assert a.post("/meta", {"path": str(tmp_path / "r"), "metric": "val/val_loss", "lower": True})[0] == 200
    assert a._scanned is None


def test_goals_and_thresholds_must_be_real_numbers(tmp_path, monkeypatch):
    """★goal: true 가 목표 1로, disk_low_gb에 NaN이 들어가 /config가 깨지고 디스크 경고가 멈췄다"""
    import math
    from epokio import config, runmeta
    runmeta.update(str(tmp_path / "r"), {"goal": True, "metric": "m" * 5000, "tags": ["t" * 500]})
    m = runmeta.get(str(tmp_path / "r"))
    assert "goal" not in m and len(m["metric"]) == 200 and len(m["tags"][0]) == 60
    runmeta.update(str(tmp_path / "r"), {"goal": float("inf")})
    assert "goal" not in runmeta.get(str(tmp_path / "r"))
    monkeypatch.setattr(config, "FILE", tmp_path / "config.json")
    c = config.update({"disk_low_gb": float("nan")})
    assert math.isfinite(c["disk_low_gb"])


def test_a_moved_run_is_not_resumed_into_its_old_place(tmp_path, monkeypatch):
    """★ultralytics는 체크포인트의 절대 save_dir에 이어 쓴다. 옮긴 학습을 이어 하면 옛 경로에 썼고 대기열은 새 폴더를 봤다"""
    import os
    from epokio.jobs import Job
    from epokio import envs
    a = _agent(tmp_path, monkeypatch)
    run = tmp_path / "moved" / "exp"
    (run / "weights").mkdir(parents=True)
    ckpt = run / "weights" / "last.pt"
    ckpt.write_bytes(b"x")
    old = ckpt.stat().st_mtime - 3600
    os.utime(ckpt, (old, old))
    monkeypatch.setattr(envs, "list_envs", lambda: [{"path": "py", "ready": True}])

    class Q:
        jobs = []
        def add(self, *args):
            return Job(id="j", kind="train", name="n", python="py", params=args[3])
    a.queue = Q()
    body = {"kind": "train", "params": {"model": str(ckpt), "resume": True}}
    (run / "args.yaml").write_text(f"task: detect\nsave_dir: {tmp_path / 'elsewhere' / 'exp'}\n", encoding="utf-8")
    code, err = a.post("/jobs", body)
    assert code == 409 and "moved" in err["error"]
    (run / "args.yaml").write_text(f"task: detect\nsave_dir: {run}\n", encoding="utf-8")
    os.utime(run / "args.yaml", (old, old))                  # 방금 쓴 args.yaml은 '다시 뜬 학습'으로 본다(409)
    assert a.post("/jobs", body)[0] == 200


def test_machine_warnings_follow_the_saved_language(tmp_path, monkeypatch):
    """★디스크·GPU 경고가 영어로만 만들어져 한국어 맥·폰·웹에서도 영어였다"""
    import json
    from types import SimpleNamespace
    from epokio import config, msg
    a = _agent(tmp_path, monkeypatch)
    pushed = []
    a._push = lambda kind, before, run: pushed.append(run["name"])
    a.HOOKS_FILE.write_text(json.dumps({"urls": [], "lang": "ko"}), encoding="utf-8")
    a.sampler = SimpleNamespace(latest=SimpleNamespace(gpus=[SimpleNamespace(name="RTX", temp=95.0, mem_used=1, mem_total=24)]))
    monkeypatch.setattr(config, "FILE", tmp_path / "config.json")
    a._check_machine([])
    assert pushed == ["RTX 온도 95 °C"]
    assert msg.tr("Missing: {what}", what="x") == "Missing: x"              # 이 스레드의 언어는 그대로


def test_a_report_without_a_desktop_goes_to_a_folder_of_its_own(tmp_path, monkeypatch):
    """★바탕화면이 없는 서버에서는 기본 폴더가 없어 'folder not found'였다(웹의 보고서 버튼이 늘 실패)"""
    from pathlib import Path
    a = _agent(tmp_path, monkeypatch)
    from types import SimpleNamespace
    from epokio.api import report as report_api
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # 빈 보고서는 400이라(맥 쪽 규칙) 학습 하나를 흉내 낸다. 여기서 보는 것은 저장 폴더뿐이다
    run = SimpleNamespace(path=tmp_path / "runs" / "exp", source="csv")
    monkeypatch.setattr(report_api, "scan", lambda root: [run])
    monkeypatch.setattr(report_api.report_mod, "save", lambda runs, folder, reviews=None: folder / "report.md")
    a.roots = [tmp_path / "runs"]
    (tmp_path / "runs").mkdir()
    code, body = a.post("/report", {"all": True})
    assert code == 200 and Path(body["path"]).parent == tmp_path / "epokio-reports"


def test_the_job_list_always_includes_running_and_waiting_jobs(tmp_path, monkeypatch):
    """★마지막 100개만 보내, 작업이 많으면 도는 작업이 빠져 화면에서 멈출 수 없었다"""
    from epokio.jobs import Job
    a = _agent(tmp_path, monkeypatch)
    jobs = [Job(id="run", kind="script", name="n", python="py", state="running")]
    jobs += [Job(id=f"q{i}", kind="script", name="n", python="py", state="queued") for i in range(120)]
    jobs += [Job(id=f"d{i}", kind="script", name="n", python="py", state="done") for i in range(300)]
    a.queue = type("Q", (), {"jobs": jobs})()
    ids = [j["id"] for j in a.get("/jobs", {})["jobs"]]
    assert "run" in ids and "q119" in ids and len([i for i in ids if i.startswith("d")]) == 100
