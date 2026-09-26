"""똑똑한 스윕(TPE): 학습 없이 흐름을 시험한다. 시도가 "끝나면" 합성 점수를 결과 파일로 쓴다."""
import math
import random
import statistics

import pytest

from epokio import sweep, tpe
from epokio.jobs import Queue

SPACE = [{"key": "lr0", "low": 1e-4, "high": 1e-1, "log": True}, {"key": "opt", "values": ["SGD", "AdamW"]}]


def _score(t):
    lr = 0.08 * (math.log10(t["lr0"]) - math.log10(3e-3)) ** 2 if "lr0" in t else 0
    return 0.9 - lr + (0.03 if t.get("opt") == "AdamW" else 0)


def _finish(q, tmp_path, spec):
    """기다리는 시도를 "끝낸다": 결과 파일을 쓰고 상태를 done으로"""
    for t in spec["trials"]:
        j = q.get(t["job"])
        if j.state == "queued":
            d = tmp_path / j.id
            d.mkdir()
            s = _score(t["trial"])
            (d / "results.csv").write_text("epoch,metrics/mAP50-95(B)\n" + "".join(f"{e},{s * e / 3:.4f}\n" for e in (1, 2, 3)))
            j.output, j.state = str(d), "done"


def test_smart_sweep_queues_one_at_a_time_up_to_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    q = Queue(tmp_path / "q.json")                       # 돌리지 않는 대기열(start 안 함)
    spec = sweep.create(q, "s", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3}, SPACE, "smart", trials=8, seed=1)
    assert len(spec["trials"]) == tpe.startup(SPACE)    # 처음엔 무작위 몇 개만
    assert sweep.advance(q) == []                        # 기다리는 게 있으면 더 넣지 않는다
    for _ in range(10):
        spec = sweep.load(spec["id"])
        _finish(q, tmp_path, spec)
        sweep.advance(q)
    spec = sweep.load(spec["id"])
    assert len(spec["trials"]) == 8                      # 예산에서 멈춘다
    s = sweep.summary(spec, q)
    assert s["total"] == 8 and len(s["best_so_far"]) == 8
    assert all(a is None or b >= a for a, b in zip(s["best_so_far"], s["best_so_far"][1:]))


def test_cancelled_smart_sweep_stops_proposing(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    q = Queue(tmp_path / "q.json")
    spec = sweep.create(q, "s", "/usr/bin/python3", {"data": "d.yaml"}, SPACE, "smart", trials=10, seed=2)
    spec["stopped"] = True
    sweep._save(spec)
    _finish(q, tmp_path, spec)
    assert sweep.advance(q) == []


def test_tpe_beats_random_on_a_synthetic_goal():
    """같은 16회에서 TPE가 무작위보다 더 좋은 값을 찾는 경우가 더 많다(200번 중)"""
    def run(n_startup, seed):
        hist = []
        for i in range(16):
            t = tpe.suggest(SPACE, hist, True, seed=seed * 100 + i, n_startup=n_startup)
            hist.append((t, _score(t) + random.Random(seed * 7 + i).gauss(0, 0.005)))
        return max(s for _, s in hist)
    wins = sum(run(4, s) > run(10 ** 9, s) for s in range(200))
    assert wins > 110, wins


def test_tpe_respects_bounds_and_types():
    space = [{"key": "batch", "low": 8, "high": 64, "int": True}, {"key": "lr0", "low": 1e-4, "high": 1e-2, "log": True}]
    hist = [({"batch": 16, "lr0": 1e-3}, 0.5), ({"batch": 32, "lr0": 5e-3}, 0.6), ({"batch": 60, "lr0": 1e-4}, 0.2),
            ({"batch": 8, "lr0": 1e-2}, 0.1), ({"batch": 24, "lr0": 2e-3}, 0.7)]
    for seed in range(50):
        t = tpe.suggest(space, hist, True, seed=seed)
        assert isinstance(t["batch"], int) and 8 <= t["batch"] <= 64 and 1e-4 <= t["lr0"] <= 1e-2
    assert statistics.mean(tpe.suggest(space, hist, False, seed=s)["batch"] for s in range(50)) != \
        statistics.mean(tpe.suggest(space, hist, True, seed=s)["batch"] for s in range(50))   # 낮을수록 좋음이면 다른 쪽을 고른다


def test_continuous_values_are_binned_for_by_value_and_importance(tmp_path, monkeypatch):
    """★무작위·똑똑한 스윕은 시도마다 값이 달라 "값별 평균"이 한 개짜리 막대로 흩어졌다 → 4구간"""
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    q = Queue(tmp_path / "q.json")
    spec = sweep.create(q, "s", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3}, SPACE, "smart", trials=12, seed=5)
    for _ in range(14):
        spec = sweep.load(spec["id"])
        _finish(q, tmp_path, spec)
        sweep.advance(q)
    s = sweep.summary(sweep.load(spec["id"]), q)
    lr = s["by_key"]["lr0"]["values"]
    assert len(lr) <= 4 and all("–" in str(v["value"]) for v in lr)
    assert [v["value"] for v in s["by_key"]["opt"]["values"]] == ["AdamW", "SGD"]   # 고른 값은 그대로


def test_smart_sweep_with_mixed_settings(tmp_path, monkeypatch):
    """설정 여러 개(범위·정수 범위·목록 섞기)도 한 시도에 전부, 맞는 형으로"""
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    q = Queue(tmp_path / "q.json")
    space = [{"key": "lr0", "low": 1e-4, "high": 1e-2, "log": True}, {"key": "batch", "low": 8, "high": 32, "int": True},
             {"key": "opt", "values": ["SGD", "AdamW"]}]
    spec = sweep.create(q, "m", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3}, space, "smart", trials=7, seed=4)
    for _ in range(9):
        spec = sweep.load(spec["id"])
        _finish(q, tmp_path, spec)
        sweep.advance(q)
    trials = [t["trial"] for t in sweep.load(spec["id"])["trials"]]
    assert len(trials) == 7
    for t in trials:
        assert set(t) == {"lr0", "batch", "opt"} and isinstance(t["batch"], int) and 8 <= t["batch"] <= 32
        assert 1e-4 <= t["lr0"] <= 1e-2 and t["opt"] in ("SGD", "AdamW")


def test_pareto_front():
    """점수는 높을수록, 두 번째(크기)는 낮을수록. 둘 다에서 밀리는 것만 빠진다"""
    pts = [("a", 0.9, 50.0), ("b", 0.8, 10.0), ("c", 0.7, 30.0), ("d", 0.9, 60.0), ("e", 0.6, 5.0)]
    assert sorted(sweep.pareto(pts, True)) == ["a", "b", "e"]          # c는 b에, d는 a에 밀린다
    assert sorted(sweep.pareto([("x", 1.0, 1.0), ("y", 1.0, 1.0)], True)) == ["x", "y"]   # 똑같으면 둘 다 남는다


def test_two_goal_sweep_reports_second_value_and_front(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    q = Queue(tmp_path / "q.json")
    spec = sweep.create(q, "g", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3}, SPACE, "smart", trials=6, seed=8, second="size")
    for _ in range(8):
        spec = sweep.load(spec["id"])
        for t in spec["trials"]:                                         # 결과 + best.pt(크기 = lr0이 클수록 크게 흉내)
            j = q.get(t["job"])
            if j.state == "queued":
                d = tmp_path / j.id
                (d / "weights").mkdir(parents=True)
                (d / "results.csv").write_text(f"epoch,metrics/mAP50-95(B)\n1,{_score(t['trial']) / 2}\n2,{_score(t['trial'])}\n")
                (d / "weights" / "best.pt").write_bytes(b"0" * int(1e6 * (1 + t["trial"]["lr0"] * 100)))
                j.output, j.state = str(d), "done"
        sweep.advance(q)
    s = sweep.summary(sweep.load(spec["id"]), q)
    assert s["second"] == "size" and all(r["second"] is not None for r in s["rows"])
    assert 1 <= len(s["pareto"]) <= len(s["rows"])


def test_pruned_trials_go_to_the_bad_group_not_the_ranking(tmp_path, monkeypatch):
    """멈춘 시도의 부분 최고값은 점수로 치지 않는다: 이력에서 빠지고 pruned 목록으로"""
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    q = Queue(tmp_path / "q.json")
    spec = sweep.create(q, "s", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3}, SPACE, "smart", trials=8, seed=1)
    _finish(q, tmp_path, spec)
    spec["pruned"] = [spec["trials"][0]["job"]]
    hist, _, pruned = sweep._history(q, spec)
    assert len(hist) == len(spec["trials"]) - 1 and pruned == [spec["trials"][0]["trial"]]
    rows = sweep.summary(spec, q)["rows"]
    assert rows[0]["pruned"] and rows[0]["state"] == "pruned" and not rows[1]["pruned"]


def test_pruned_region_is_avoided():
    """좋은 곳 옆에 멈춘 시도가 몰리면 그쪽은 덜 고른다"""
    space = [{"key": "x", "low": 0.0, "high": 1.0}]
    hist = [({"x": v}, s) for v, s in ((0.1, 0.5), (0.5, 0.9), (0.9, 0.4), (0.3, 0.6), (0.7, 0.6), (0.2, 0.5))]
    base = statistics.mean(tpe.suggest(space, hist, seed=s)["x"] for s in range(60))
    near = statistics.mean(tpe.suggest(space, hist, seed=s, pruned=[{"x": 0.55}, {"x": 0.6}, {"x": 0.58}])["x"] for s in range(60))
    assert near < base


def test_startup_grows_with_settings_and_log_range_is_checked():
    assert tpe.startup(SPACE) == 5 and tpe.startup(SPACE * 4) == 16
    import pytest
    with pytest.raises(ValueError, match="log range needs low > 0"):
        tpe.suggest([{"key": "lr0", "low": 0, "high": 1, "log": True}], [])
    with pytest.raises(ValueError, match="must be below"):
        tpe.validate_space([{"key": "b", "low": 5, "high": 5}])


# ---------------- 되풀이(repeats): 같은 설정을 씨앗만 바꿔 N번 ----------------

def _finish_noisy(q, tmp_path, spec, rng, sigma=0.04):
    """씨앗에 따라 흔들리는 점수로 "끝낸다"(진짜 학습의 씨앗 흔들림 흉내)"""
    for t in spec["trials"]:
        j = q.get(t["job"])
        if j.state == "queued":
            d = tmp_path / j.id
            d.mkdir()
            s = _score(t["trial"]) + rng.gauss(0, sigma)
            (d / "results.csv").write_text("epoch,metrics/mAP50-95(B)\n" + "".join(f"{e},{s * e / 3:.5f}\n" for e in (1, 2, 3)))
            j.output, j.state = str(d), "done"


def test_repeats_queue_each_config_n_times_with_different_seeds(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    q = Queue(tmp_path / "q.json")
    space = [{"key": "lr0", "values": [0.01, 0.02]}]
    spec = sweep.create(q, "r", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3, "seed": 100}, space, "grid", repeats=3)
    assert len(spec["trials"]) == 6 and spec["repeats"] == 3 and spec["budget"] == 6
    by = {}
    for t in spec["trials"]:
        by.setdefault(t["trial"]["lr0"], []).append((t["rep"], q.get(t["job"]).params["seed"]))
    assert by == {0.01: [(0, 100), (1, 101), (2, 102)], 0.02: [(0, 100), (1, 101), (2, 102)]}


def test_repeats_default_one_keeps_old_behaviour(tmp_path, monkeypatch):
    """기본값 1이면 예전 그대로: 시도 수도 seed도 건드리지 않는다"""
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    q = Queue(tmp_path / "q.json")
    spec = sweep.create(q, "r", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3}, [{"key": "lr0", "values": [0.01, 0.02]}], "grid")
    assert len(spec["trials"]) == 2 and spec["repeats"] == 1
    assert all("seed" not in q.get(t["job"]).params for t in spec["trials"])
    assert sweep.summary(spec, q)["repeats"] == 1


def test_repeats_group_by_mean_std_and_n(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    q = Queue(tmp_path / "q.json")
    space = [{"key": "opt", "values": ["SGD", "AdamW"]}]
    spec = sweep.create(q, "r", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3}, space, "grid", repeats=3)
    _finish_noisy(q, tmp_path, spec, random.Random(3))
    s = sweep.summary(spec, q)
    assert len(s["groups"]) == 2 and s["repeats"] == 3
    for g in s["groups"]:
        assert g["n"] == 3 and g["std"] > 0 and not g["low_n"] and len(g["jobs"]) == 3
        assert min(r["best"] for r in s["rows"] if r["trial"] == g["trial"]) <= g["mean"] <= g["best"]
    assert [g["rank"] for g in s["groups"]] == [1, 2] and s["groups"][0]["mean"] > s["groups"][1]["mean"]
    assert [r["rank"] for r in sorted(s["rows"], key=lambda r: r["rank"])][:3] == [1, 2, 3]
    top = s["groups"][0]["trial"]                       # 1~3위는 전부 평균 1등 설정의 되풀이다
    assert all(r["trial"] == top for r in s["rows"] if r["rank"] <= 3)


def test_repeats_give_tpe_one_mean_per_config(tmp_path, monkeypatch):
    """★같은 설정 N개를 그대로 넣으면 좋음/나쁨 그룹이 한 설정으로 채워진다"""
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    q = Queue(tmp_path / "q.json")
    space = [{"key": "opt", "values": ["SGD", "AdamW"]}]
    spec = sweep.create(q, "r", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3}, space, "grid", repeats=3)
    _finish_noisy(q, tmp_path, spec, random.Random(4))
    hist, higher, _ = sweep._history(q, spec)
    assert len(hist) == 2 and higher
    got = {t["opt"]: s for t, s in hist}
    want = {g["trial"]["opt"]: g["mean"] for g in sweep.summary(spec, q)["groups"]}
    assert got == {k: pytest.approx(v) for k, v in want.items()}


def test_smart_sweep_fills_repeats_before_picking_a_new_value(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    q = Queue(tmp_path / "q.json")
    spec = sweep.create(q, "s", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3}, SPACE, "smart", trials=4, seed=1, repeats=2)
    assert spec["budget"] == 8
    for _ in range(12):
        spec = sweep.load(spec["id"])
        _finish(q, tmp_path, spec)
        sweep.advance(q)
    trials = [t["trial"] for t in sweep.load(spec["id"])["trials"]]
    assert len(trials) == 8
    assert all(a == b for a, b in zip(trials[::2], trials[1::2]))       # 이웃한 둘이 같은 설정
    assert [t["rep"] for t in sweep.load(spec["id"])["trials"]] == [0, 1] * 4


def test_importance_carries_n_and_flags_small_samples(tmp_path, monkeypatch):
    """n=2에서도 막대는 그려진다: 데이터에 low_n을 담아 화면이 "표본 적음"을 달 수 있게"""
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")
    q = Queue(tmp_path / "q.json")
    space = [{"key": "opt", "values": ["SGD", "AdamW"]}]
    spec = sweep.create(q, "few", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3}, space, "grid")
    _finish(q, tmp_path, spec)
    s = sweep.summary(spec, q)
    imp = s["importance"][0]
    assert imp["key"] == "opt" and imp["n"] == 2 and imp["min_n"] == 1 and imp["groups"] == 2
    assert imp["low_n"] and s["low_n"] and s["min_n"] == 3
    assert all(v["n"] == 1 and v["low_n"] and v["std"] is None for v in s["by_key"]["opt"]["values"])

    spec2 = sweep.create(q, "many", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3}, space, "grid", repeats=3)
    _finish_noisy(q, tmp_path, spec2, random.Random(5))
    s2 = sweep.summary(spec2, q)
    v = s2["by_key"]["opt"]["values"]
    # 값별 표본은 "시도"가 아니라 "설정"이다: 되풀이 3번을 3개 표본으로 세지 않는다
    assert [x["n"] for x in v] == [1, 1] and s2["importance"][0]["low_n"]


def test_repeats_pick_the_true_best_more_often_on_a_synthetic_goal(tmp_path, monkeypatch):
    """합성 목표(진짜 학습 아님) + 씨앗 잡음. 같은 예산 12회에서, 돌려 본 설정 중 진짜 1등을 1위로 올리는 비율.
    ★되풀이는 "덜 틀린 순위"를 주지만 설정을 덜 훑는다: 12설정x1 → 4설정x3이면 고른 설정의 참 점수는 오히려 조금 낮다.
    실측(120번, 잡음 sigma=0.04): 참 1등 적중 14% → 72%, 후회 0.0108 → 0.0044, 참 점수 0.9115 → 0.9006"""
    monkeypatch.setattr(sweep, "DIR", tmp_path / "sweeps")

    def hits(trials, reps, n=25):
        ok = 0
        for seed in range(n):
            d = tmp_path / f"{trials}_{reps}_{seed}"
            d.mkdir()
            q = Queue(d / "q.json")
            rng = random.Random(seed * 977)
            spec = sweep.create(q, "n", "/usr/bin/python3", {"data": "d.yaml", "epochs": 3}, SPACE, "smart",
                                trials=trials, seed=seed, repeats=reps)
            for _ in range(trials * reps + 4):
                spec = sweep.load(spec["id"])
                _finish_noisy(q, d, spec, rng)
                sweep.advance(q)
            g = sweep.summary(sweep.load(spec["id"]), q)["groups"]
            ok += _score(g[0]["trial"]) == max(_score(x["trial"]) for x in g)
        return ok / n
    once, thrice = hits(12, 1), hits(4, 3)
    assert thrice > once + 0.2, (once, thrice)
