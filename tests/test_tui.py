"""터미널 화면: 한글 폭 맞춤, 흔한 이름 구분, 줄 길이."""
from pathlib import Path

from epokio import tui
from epokio.scan import Run


def _run(path, **kw):
    d = dict(name=Path(path).name, path=Path(path), epoch=5, total=10, elapsed=60, eta=30, metric=0.5,
             metric_name="m", best=0.6, best_epoch=4, state="running", idle=1)
    d.update(kw)
    return Run(**d)


def test_fit_counts_wide_chars():
    assert tui.cells("시선") == 4
    assert tui.cells(tui.fit("교통표지판_테스트/train", 12)) == 12
    assert tui.fit("abc", 5) == "abc  "


def test_generic_name_gets_parent():
    assert tui.display_name(_run("/x/defect_det/train")) == "defect_det/train"
    assert tui.display_name(_run("/x/runs/detect/train2")) == "x/train2"
    assert tui.display_name(_run("/x/coco8")) == "coco8"


def test_rows_same_width():
    a = tui.row(_run("/x/a/train"), 100)
    b = tui.row(_run("/x/교통표지판/train", state="done", total=150, epoch=150), 100)
    assert tui.cells(a) == tui.cells(b)          # 한글 이름이어도 막대 끝이 맞는다


def test_once_survives_a_console_that_cannot_print_the_bar(tmp_path):
    """파이프·파일로 받으면(한국어 윈도우 cp949, 영어 윈도우 cp1252) 막대 글자 █에서 죽었다."""
    import os
    import subprocess
    import sys
    d = tmp_path / "exp"
    d.mkdir()
    (d / "args.yaml").write_text("epochs: 10\n")
    (d / "results.csv").write_text("epoch,time,metrics/mAP50-95(B)\n1,1,0.1\n2,2,0.2\n")
    env = dict(os.environ, PYTHONIOENCODING="ascii")        # 막대 글자를 못 쓰는 콘솔
    r = subprocess.run([sys.executable, "-m", "epokio.tui", "--once", "--root", str(tmp_path)],
                       capture_output=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr.decode(errors="replace")[-400:]
    assert b"exp" in r.stdout
