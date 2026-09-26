"""스윕: 격자·무작위 펼치기, 대기열에 넣기, 순위·영향도, 가망 없는 시도 조기 중단."""
import pytest

from epokio import sweep
from epokio.agent import Agent
from epokio.jobs import Queue


def test_grid_is_every_combination():
    t = sweep.expand([{"key": "lr0", "values": ["0.01", "0.001"]}, {"key": "imgsz", "values": [480, 640]}], "grid")
    assert len(t) == 4 and {"lr0": 0.01, "imgsz": 640} in t


def test_random_log_range_stays_inside_and_is_reproducible():
    sp = [{"key": "lr0", "low": 1e-4, "high": 1e-2, "log": True}, {"key": "batch", "low": 8, "high": 32, "int": True}]
    a = sweep.expand(sp, "random", 20, seed=1)
    assert a == sweep.expand(sp, "random", 20, seed=1)
    assert all(1e-4 <= x["lr0"] <= 1e-2 and isinstance(x["batch"], int) for x in a)
    assert min(x["lr0"] for x in a) < 1e-3 < max(x["lr0"] for x in a)          # 로그: 자릿수가 고르게 나온다


@pytest.mark.parametrize("space,mode", [([], "grid"), ([{"key": "lr0", "values": []}], "grid"),
                                        ([{"key": "lr0", "low": 0, "high": 1, "log": True}], "random"),
                                        ([{"key": "lr0", "values": list(range(100))}], "grid")])
def test_bad_spaces_are_refused(space, mode):
    with pytest.raises(ValueError):
        sweep.expand(space, mode)


def _queue(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    return Queue(tmp_path / "jobs.json")                  # start() 안 함: 실제로 돌리지 않는다


def _run(d, scores):
    d.mkdir(parents=True)
    (d / "args.yaml").write_text("epochs: 10\n")
    (d / "results.csv").write_text("epoch,metrics/mAP50-95(B)\n" + "".join(f"{i},{v}\n" for i, v in enumerate(scores, 1)))


def test_create_summary_and_model_size(tmp_path, monkeypatch):
    q = _queue(tmp_path, monkeypatch)
    spec = sweep.create(q, "s", "py", {"data": "d.yaml", "model": "yolo11n-pose.pt", "epochs": 10},
                        [{"key": "model", "values": ["n", "s"]}, {"key": "lr0", "values": [0.01, 0.001]}])
    jobs = [q.get(t["job"]) for t in spec["trials"]]
    assert len(jobs) == 4 and all(j.sweep == spec["id"] for j in jobs)
    assert {j.params["model"] for j in jobs} == {"yolo11n-pose.pt", "yolo11s-pose.pt"}
    for j, top in zip(jobs, [0.5, 0.7, 0.4, 0.6]):
        j.output, j.state = str(tmp_path / j.id), "done"
        _run(tmp_path / j.id, [top / 2, top])
    s = sweep.summary(sweep.load(spec["id"]), q)
    assert s["best"]["best"] == 0.7 and s["best"]["rank"] == 1 and s["done"] == 4
    assert s["importance"][0]["key"] in ("model", "lr0") and abs(sum(x["share"] for x in s["importance"]) - 1) < 1e-9


def test_prune_stops_a_trial_below_the_median(tmp_path, monkeypatch):
    q = _queue(tmp_path, monkeypatch)
    spec = sweep.create(q, "s", "py", {"data": "d", "epochs": 10}, [{"key": "lr0", "values": [1, 2, 3, 4]}], prune=True, prune_at=0.3)
    a, b, c, d = [q.get(t["job"]) for t in spec["trials"]]
    for j, v in ((a, 0.5), (b, 0.6), (c, 0.55)):
        j.output, j.state = str(tmp_path / j.id), "done"
        _run(tmp_path / j.id, [v] * 10)
    d.output, d.state = str(tmp_path / d.id), "running"
    _run(tmp_path / d.id, [0.1, 0.1, 0.1])                 # 3에폭(확인 지점)에서 중앙값 0.55보다 한참 낮다
    assert sweep.check_prune(q) == [d.id]
    assert q.get(d.id).state == "cancelled" and sweep.summary(sweep.load(spec["id"]), q)["rows"][3]["state"] == "pruned"


def test_prune_needs_two_finished_to_compare(tmp_path, monkeypatch):
    q = _queue(tmp_path, monkeypatch)
    spec = sweep.create(q, "s", "py", {"data": "d", "epochs": 10}, [{"key": "lr0", "values": [1, 2]}], prune=True)
    a, b = [q.get(t["job"]) for t in spec["trials"]]
    a.output, a.state = str(tmp_path / a.id), "done"; _run(tmp_path / a.id, [0.9] * 10)
    b.output, b.state = str(tmp_path / b.id), "running"; _run(tmp_path / b.id, [0.1] * 3)
    assert sweep.check_prune(q) == []


def test_sweep_route_validates(tmp_path, monkeypatch):
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label, a.queue = [], "t", _queue(tmp_path, monkeypatch)
    assert a.post("/sweeps", {"python": "py", "space": []})[0] == 400
    assert a.post("/sweeps", {"python": "py", "base": {"data": "d"}, "space": [{"key": "lr0", "values": [1]}], "prune_at": 2})[0] == 400
    code, body = a.post("/sweeps", {"python": "py", "base": {"data": "d"}, "space": [{"key": "lr0", "low": 0.001, "high": 0.1, "log": True}],
                                    "mode": "random", "trials": 3})
    assert code == 200 and body["runs"] == 3
    assert a.get(f"/sweeps/{body['id']}", {})["total"] == 3


def test_prune_median_keeps_already_pruned_trials(tmp_path, monkeypatch):
    """멈춘 시도도 비교군에 남는다: 빼면 살아남은 좋은 시도만 남아 중앙값이 올라간다"""
    q = _queue(tmp_path, monkeypatch)
    spec = sweep.create(q, "s", "py", {"data": "d", "epochs": 10}, [{"key": "lr0", "values": [1, 2, 3, 4]}], prune=True, prune_at=0.3)
    a, b, c, d = [q.get(t["job"]) for t in spec["trials"]]
    for j, v in ((a, 0.9), (b, 0.2)):
        j.output, j.state = str(tmp_path / j.id), "done"
        _run(tmp_path / j.id, [v] * 10)
    c.output, c.state = str(tmp_path / c.id), "cancelled"
    _run(tmp_path / c.id, [0.1] * 3)
    spec["pruned"] = [c.id]
    sweep._save(spec)
    d.output, d.state = str(tmp_path / d.id), "running"
    _run(tmp_path / d.id, [0.3] * 3)                      # 중앙값(0.9, 0.2, 0.1) = 0.2 → 0.3은 앞선다
    assert sweep.check_prune(q) == []


def test_prune_checks_later_rungs(tmp_path, monkeypatch):
    """30%에선 괜찮다가 70%에서 뒤처지면 그때 멈춘다"""
    q = _queue(tmp_path, monkeypatch)
    spec = sweep.create(q, "s", "py", {"data": "d", "epochs": 10}, [{"key": "lr0", "values": [1, 2, 3]}], prune=True, prune_at=0.3)
    a, b, c = [q.get(t["job"]) for t in spec["trials"]]
    for j in (a, b):
        j.output, j.state = str(tmp_path / j.id), "done"
        _run(tmp_path / j.id, [0.5] * 10)
    c.output, c.state = str(tmp_path / c.id), "running"
    _run(tmp_path / c.id, [0.6] * 3)
    assert sweep.check_prune(q) == []
    import shutil
    shutil.rmtree(tmp_path / c.id)
    _run(tmp_path / c.id, [0.6] * 3 + [0.1] * 4)
    assert sweep.check_prune(q) == [c.id]
    assert sweep.load(spec["id"])["prune_log"][-1]["epoch"] == 7
