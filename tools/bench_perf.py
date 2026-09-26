"""Micro-benchmark for paths the agent calls often. Fake runs only (demo.py rows + fixtures), no training.
usage: PYTHONPATH=src python tools/bench_perf.py [N_RUNS]"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import timeit
from pathlib import Path

from epokio import adapters, analysis, demo, monitor, rundetail, scan, sysinfo
from epokio.api import table

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "formats"


def make(root: Path) -> list[Path]:
    old = time.time() - 3600
    runs = []
    for i in range(N):
        d = root / f"run{i:03d}"
        (d / "weights").mkdir(parents=True)
        (d / "results.csv").write_text(demo._rows(100 + i % 200, 0.5, i % 3 == 0), encoding="utf-8")
        (d / "args.yaml").write_text(f"task: detect\nmodel: yolo11n.pt\ndata: d/x.yaml\nepochs: 300\nimgsz: 640\nname: run{i}\n")
        for f in d.rglob("*"):
            os.utime(f, (old, old))
        runs.append(d)
    return runs


def t(fn, n=5):
    return min(timeit.repeat(fn, number=1, repeat=n)) * 1000


def main():
    root = Path(tempfile.mkdtemp())
    try:
        runs = make(root)
        fx = [p for p in FIX.iterdir() if p.is_dir()]

        class A:
            label = "bench"
            def get(self, route, q):
                return {"runs": [{"path": str(r), "name": r.name, "state": "done", "epoch": 1} for r in runs]}

        res = {
            f"adapters.load x{N}": t(lambda: [adapters.load(r) for r in runs]),
            f"analysis.analyze x{N}": t(lambda: [analysis.analyze(r) for r in runs]),
            f"rundetail.detail x{N}": t(lambda: [rundetail.detail(r) for r in runs]),
            f"rundetail.detail fixtures x{len(fx)}": t(lambda: [rundetail.detail(r) for r in fx]),
            f"table.get /runs/table ({N} runs)": t(lambda: table.get(A(), "/runs/table", {})),
            f"scan.scan ({N} runs, warm)": t(lambda: scan.scan(root)),
            "sysinfo.sample": t(sysinfo.sample, 3),
        }
        for k, v in res.items():
            print(f"{k:40s} {v:9.1f} ms")
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
