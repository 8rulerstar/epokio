"""학습 메모(별표·태그·메모·목표): 저장 형식, 빈 값 정리, 목표는 한 번만 알림."""
from pathlib import Path

from epokio import runmeta
from epokio.scan import Run


def _run(path, best):
    return Run(name="r", path=Path(path), epoch=3, total=10, elapsed=1, eta=1, metric=best, metric_name="m",
               best=best, best_epoch=3, state="running", idle=1)


def test_update_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(runmeta, "FILE", tmp_path / "meta.json")
    m = runmeta.update("/r/a", {"star": True, "tags": [" best ", "yolo", "best", ""], "note": "hi", "bogus": 1})
    assert m == {"star": True, "tags": ["best", "yolo"], "note": "hi"}
    assert runmeta.update("/r/a", {"star": False, "tags": [], "note": ""}) == {}
    assert runmeta.load() == {}                                    # 다 비우면 줄 자체가 사라진다
    assert runmeta.update("/r/a", {"star": "yes"}) == {}           # 형식이 틀린 값은 무시


def test_goal_fires_once(tmp_path, monkeypatch):
    monkeypatch.setattr(runmeta, "FILE", tmp_path / "meta.json")
    runmeta.update("/r/a", {"goal": 0.8})
    assert runmeta.goals_reached([_run("/r/a", 0.7)]) == []
    assert len(runmeta.goals_reached([_run("/r/a", 0.85)])) == 1
    assert runmeta.goals_reached([_run("/r/a", 0.9)]) == []        # 이미 알렸다
    runmeta.update("/r/a", {"goal": 0.95})                        # 목표를 바꾸면 다시 지켜본다
    assert len(runmeta.goals_reached([_run("/r/a", 0.96)])) == 1


def test_key_is_same_for_every_spelling_of_one_folder():
    """윈도우는 한 폴더를 여러 가지로 적을 수 있다. 전부 한 키로 모여야 한다.

    이게 깨지면 별표·메모가 저장은 되는데 화면에 안 뜨고, 목표 알림이 영영 안 울린다.
    """
    import os
    base = os.path.normpath("/tmp/runs/demo")
    same = [base, str(Path(base)), base + os.sep, os.path.join(base, "")]
    if os.name == "nt":
        same += [base.replace("\\", "/"), base.lower(), base.upper()]
    assert len({runmeta.key(p) for p in same}) == 1, [(p, runmeta.key(p)) for p in same]
    assert runmeta.key("/tmp/runs/demo") != runmeta.key("/tmp/runs/other")


def test_meta_survives_a_differently_spelled_path(tmp_path, monkeypatch):
    """쓰는 쪽(사람이 보낸 글자)과 읽는 쪽(scan이 만든 Path)의 표기가 달라도 이어져야 한다."""
    monkeypatch.setattr(runmeta, "FILE", tmp_path / "meta.json")
    folder = tmp_path / "runs" / "demo"
    runmeta.update(str(folder).replace("\\", "/"), {"star": True})     # 앱이 슬래시로 보냈다
    assert runmeta.get(str(folder)) == {"star": True}                  # scan이 만든 표기로 찾는다
    assert len(runmeta.load()) == 1                                    # 한 폴더가 두 줄로 쌓이지 않는다


def test_goal_fires_for_a_differently_spelled_path(tmp_path, monkeypatch):
    monkeypatch.setattr(runmeta, "FILE", tmp_path / "meta.json")
    folder = tmp_path / "runs" / "demo"
    runmeta.update(str(folder).replace("\\", "/"), {"goal": 0.8})
    assert len(runmeta.goals_reached([_run(str(folder), 0.85)])) == 1
    assert runmeta.goals_reached([_run(str(folder), 0.9)]) == []        # 이미 알렸다


def test_old_file_with_unnormalised_keys_is_still_found(tmp_path, monkeypatch):
    """정규화 전에 저장된 runmeta.json 도 그대로 읽힌다(이행)."""
    import json
    f = tmp_path / "meta.json"
    monkeypatch.setattr(runmeta, "FILE", f)
    folder = tmp_path / "runs" / "demo"
    f.write_text(json.dumps({str(folder).replace("\\", "/") + "/": {"note": "old"}}), encoding="utf-8")
    assert runmeta.get(str(folder)) == {"note": "old"}
    runmeta.update(str(folder), {"star": True})                        # 한 번 쓰면 파일이 스스로 낫는다
    assert list(json.loads(f.read_text(encoding="utf-8"))) == [runmeta.key(folder)]
