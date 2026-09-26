"""대기열 순서 바꾸기 · 학습 레시피 · 예시 학습."""
from epokio import demo, lineage, recipes, scan
from epokio.jobs import Queue


def test_reorder_only_accepts_every_waiting_job(tmp_path):
    q = Queue(tmp_path / "j.json")
    a, b, c = (q.add("train", n, "py", {}) for n in "abc")
    done = q.add("train", "d", "py", {}); done.state = "done"
    assert not q.reorder([a.id, b.id])                          # 하나 빠짐
    assert q.reorder([c.id, a.id, b.id])
    assert [j.name for j in q.jobs if j.state == "queued"] == ["c", "a", "b"]


def test_recipes_save_replace_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(recipes, "FILE", tmp_path / "r.json")
    recipes.save("fast", {"epochs": 10, "imgsz": 480, "junk": {"x": 1}})
    rs = recipes.save("fast", {"epochs": 20})
    assert len(rs) == 1 and rs[0]["params"] == {"epochs": 20}
    assert recipes.save("big", {"epochs": 300})[-1]["name"] == "big"
    assert [r["name"] for r in recipes.delete("fast")] == ["big"]
    import pytest
    with pytest.raises(ValueError):
        recipes.save(" ", {"epochs": 1})


def test_demo_runs_scan_and_show_lineage(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "DIR", tmp_path / "demo")
    made = demo.create()
    runs = {r.name: r for r in scan.scan(demo.DIR)}
    assert set(runs) == {"helmet_first", "helmet_overfit", "helmet_finetune", demo.LIVE}
    assert all(r.state in ("done", "stopped") for n, r in runs.items() if n != demo.LIVE)
    print("live state:", runs[demo.LIVE].state)
    from epokio import analysis
    assert any("overfit" in n[0].lower() for n in analysis.analyze(demo.DIR / "helmet_overfit").notes)   # 과적합 해설이 나온다
    lin = lineage.lineage(demo.DIR / "helmet_finetune", [__import__("pathlib").Path(p) for p in made])
    assert lin["parent"]["name"] == "helmet_first"
    assert demo.remove() and not demo.DIR.exists()


def test_denied_watch_folder_is_reported_not_silently_empty(tmp_path):
    """권한이 막힌 폴더는 "학습 0개"가 아니라 slow_roots로 알려야 한다(2026-09-22)"""
    import os
    import pytest
    from epokio.roots import scan_one
    d = tmp_path / "locked"
    d.mkdir()
    os.chmod(d, 0)
    try:
        if os.access(d, os.R_OK):
            pytest.skip("root에서는 권한 막기가 안 된다")
        with pytest.raises(PermissionError):
            scan_one(d)
    finally:
        os.chmod(d, 0o755)


def test_slow_watch_folder_does_not_stall_the_list(tmp_path):
    """한 폴더가 오래 걸려도 나머지는 한도 안에 돌아오고, 느린 폴더는 slow로 알린다"""
    import time
    from epokio.roots import RootScanner
    fast, slow = tmp_path / "fast", tmp_path / "slow"

    def fake(root):
        if root == slow:
            time.sleep(1.0)
            return ["late"]
        return ["ok"]

    rs = RootScanner(budget=0.2, scan_fn=fake)
    t = time.time()
    runs, stuck = rs.scan([fast, slow])
    assert time.time() - t < 0.6 and runs == ["ok"] and stuck == [str(slow)]
    time.sleep(1.0)                                   # 다 끝난 뒤에는 결과가 들어온다
    runs, stuck = rs.scan([fast, slow])
    assert sorted(runs) == ["late", "ok"] and stuck == []
