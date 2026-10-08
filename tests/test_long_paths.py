"""윈도우 경로 260자 제한(LongPathsEnabled가 꺼진 기본값).
★scan._walk가 WinError 3을 삼켜, 깊은 곳의 학습 폴더가 목록에서 말없이 사라졌다. 이제 /runs의 too_long으로 알린다."""
import os
import shutil

import pytest

from epokio import scan
from epokio.agent import Agent

LONG = "\\\\?\\"          # 긴 경로를 만들고 지울 때만 쓰는 접두어


def _deep_run(root) -> str:
    """root 아래 260자를 넘는 곳에 학습 폴더 하나(results.csv·args.yaml)"""
    deep = str(root)
    while len(deep) < 262:
        deep += "\\" + "d" * 120
        os.mkdir(LONG + deep)
    run = deep + "\\run1"
    os.mkdir(LONG + run)
    with open(LONG + run + "\\results.csv", "w", encoding="utf-8") as f:
        f.write("epoch,metrics/mAP50-95(B)\n1,0.1\n2,0.2\n")
    with open(LONG + run + "\\args.yaml", "w", encoding="utf-8") as f:
        f.write("epochs: 5\n")
    return run


@pytest.mark.skipif(os.name != "nt", reason="윈도우 경로 한도")
def test_a_run_folder_past_the_windows_path_limit_is_reported_not_dropped(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    _deep_run(root)
    try:
        found = [r for r in scan.scan(root) if r.name == "run1"]
        a = Agent.__new__(Agent)
        a.roots, a.label = [root], "t"
        got = a.get("/runs", {})
        if not found:          # 긴 경로가 꺼진 윈도우(기본값): 사라지지 않고 이름이 나온다
            long = scan.TOO_LONG.get(str(root), [])
            assert long and all(len(x) > 247 for x in long)
            assert got["too_long"] == long
        else:                  # 긴 경로를 켠 윈도우(CI 러너 등): 그냥 보인다
            assert any(r["name"] == "run1" for r in got["runs"])
    finally:
        shutil.rmtree(LONG + str(root), ignore_errors=True)
        scan.TOO_LONG.pop(str(root), None)


def test_short_paths_are_never_reported_as_too_long(tmp_path):
    (tmp_path / "r" / "a").mkdir(parents=True)
    (tmp_path / "r" / "a" / "results.csv").write_text("epoch,metrics/mAP50(B)\n1,0.1\n", encoding="utf-8")
    assert [r.name for r in scan.scan(tmp_path / "r")] == ["a"] and scan.TOO_LONG[str(tmp_path / "r")] == []
