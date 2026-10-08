"""`epokio score <학습 또는 폴더> <열> [--lower]`: 대표 점수 열과 방향을 정한다(웹 화면의 '대표 점수'와 같은 runmeta).

* 학습 폴더면 그 학습만. 학습을 담은 폴더(감시 폴더, runs)면 그 아래 학습 전부의 기본값(그 열이 있는 학습만 따른다)
* --auto: 정한 것을 지우고 자동으로 돌린다
* 도우미가 돌고 있어도 된다. 도우미는 runmeta 파일이 바뀌면 1초 안에 다시 읽는다
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="epokio score", description=(
        "Choose which logged column is a run's main score and whether lower is better. "
        "Give a run folder for one run, or a folder of runs to set the default for every run under it."))
    ap.add_argument("path", help="a run folder, or a folder holding runs")
    ap.add_argument("column", nargs="?", help="the column, e.g. metrics/val_acc or val_loss (see `--list`)")
    ap.add_argument("--lower", action="store_true", help="lower is better (a loss or an error rate)")
    ap.add_argument("--auto", action="store_true", help="forget the choice and pick automatically again")
    ap.add_argument("--list", action="store_true", help="show the columns this run logged")
    a = ap.parse_args(argv)
    from . import adapters, runmeta
    d = Path(a.path).expanduser().resolve()
    if not d.is_dir():
        print(f"Not a folder: {d}")
        return 2
    got = adapters.load(d) if adapters.detect(d) else None
    cols = list(dict.fromkeys(k for r in got.rows for k in r if k not in ("epoch", "time"))) if got else []
    if a.list or (not a.column and not a.auto):
        if not got:
            print("Not a run folder (no log Epokio can read). Give a run folder to list its columns.")
            return 1 if a.list else 2
        from .scan import read_run
        r = read_run(d)
        print("\n".join(f"  {c}{'   <- main score' if r and c == r.metric_name else ''}" for c in cols))
        return 0
    if a.auto:
        runmeta.update(str(d), {"metric": None, "lower": False})
        print(f"Automatic again: {d}")
        return 0
    col = a.column
    if got and col not in cols:
        match = [c for c in cols if c.split("/", 1)[-1] == col]    # val_acc → metrics/val_acc
        if len(match) != 1:
            print(f"This run has no column {col!r}. Columns: {', '.join(cols)}")
            return 2
        col = match[0]
    runmeta.update(str(d), {"metric": col, "lower": bool(a.lower)})
    where = "this run" if got else "every run under this folder that logs it"
    print(f"Main score for {where}: {col} ({'lower' if a.lower else 'higher'} is better)")
    return 0
