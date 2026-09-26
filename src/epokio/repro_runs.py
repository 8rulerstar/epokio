"""재현성 스냅샷을 작업·끝난 run에 붙이고, 두 run을 비교한다. 계산은 repro.py.

대기열 학습은 시작 순간 run 폴더가 아직 없다. 미리 만들면 ultralytics(exist_ok=False)가 이름을
name2로 바꿔 버린다. 그래서 시작 때는 ~/.epokio/repro/<작업id>/에 두고, 끝나면 run 폴더로 옮긴다.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import repro

PENDING = Path.home() / ".epokio" / "repro"


def pending_dir(job_id: str, root: Path | None = None) -> Path:
    return (root or PENDING) / job_id


def for_job(job, freeze: bool = False, full_data_hash: bool = False, root: Path | None = None) -> Path | None:
    """대기열 작업 시작 직전에 부른다. 학습 코드 위치 = 스크립트 작업은 첫 인자, 아니면 작업 폴더."""
    params = dict(getattr(job, "params", {}) or {})
    code = None
    if job.kind == "script" and params.get("args"):
        first = Path(params["args"][0])
        code = first if first.is_absolute() else Path(job.cwd or ".") / first
    elif job.cwd:
        code = Path(job.cwd)
    snap = repro.snapshot(code=code, python=job.python, params=params, data=params.get("data"),
                          full_data_hash=full_data_hash)
    snap["job"] = {"id": job.id, "kind": job.kind, "name": job.name}
    lock = repro.pip_freeze(job.python) if freeze else None
    return repro.write(pending_dir(job.id, root), snap, lock)


def adopt(job_id: str, run_dir: str | Path, root: Path | None = None) -> Path | None:
    """작업이 끝나면 대기 중 스냅샷을 run 폴더 안으로. run 폴더가 없으면 그대로 둔다."""
    src, dst = pending_dir(job_id, root), Path(run_dir)
    if not (src / repro.FILE).exists() or not dst.is_dir():
        return None
    for name in (repro.FILE, repro.LOCK_FILE):
        if (src / name).exists():
            shutil.move(str(src / name), str(dst / name))
    shutil.rmtree(src, ignore_errors=True)
    return dst / repro.FILE


def posthoc(run_dir: str | Path, python: str | None = None, code: str | Path | None = None,
            write: bool = True) -> dict:
    """이미 끝난 run의 부분 스냅샷. 되짚을 수 있는 것만: args.yaml의 시드·data, 그 data의 지금 지문.
    코드는 주면 지금 상태를 적는다(학습 당시와 다를 수 있어 partial=True). 파이썬은 주면만."""
    d = Path(run_dir)
    args = repro._read_flat_yaml(d / "args.yaml")
    snap = repro.snapshot(code=code, python=python, data=args.get("data"),
                          args_yaml=d / "args.yaml", partial=True)
    snap["note"] = "made after training; code, packages and data reflect now, not the training time"
    if write and repro.read(d) is None:          # 시작 때 찍은 진짜 스냅샷은 덮지 않는다
        repro.write(d, snap)
    return snap


# ── 비교 ─────────────────────────────────────────

FIELDS = {
    "code": ("commit", "branch", "dirty", "diff_sha256"),
    "python": ("version", "executable"),
    "seed": ("seed", "deterministic"),
    "data": ("yaml_sha256", "images", "bytes", "listing_sha256", "content_sha256"),
    "system": ("os", "os_version", "chip", "cuda"),
}


def compare(a: dict | None, b: dict | None) -> dict:
    """두 스냅샷에서 달라진 것만. 한쪽에만 있는 칸은 unknown으로 따로(모르는 것 ≠ 같다)."""
    a, b = a or {}, b or {}
    diffs, unknown = [], []
    for sec, keys in FIELDS.items():
        sa, sb = a.get(sec) or {}, b.get(sec) or {}
        for k in keys:
            va, vb = sa.get(k), sb.get(k)
            if va is None and vb is None:
                continue
            if va is None or vb is None:
                unknown.append(f"{sec}.{k}")
            elif va != vb:
                diffs.append({"field": f"{sec}.{k}", "a": va, "b": vb})
    pa = (a.get("python") or {}).get("packages") or {}
    pb = (b.get("python") or {}).get("packages") or {}
    for name in sorted(set(pa) | set(pb)):
        if pa.get(name) != pb.get(name):
            diffs.append({"field": f"package.{name}", "a": pa.get(name), "b": pb.get(name)})
    ga = [g.get("name") for g in (a.get("system") or {}).get("gpus", [])]
    gb = [g.get("name") for g in (b.get("system") or {}).get("gpus", [])]
    if ga != gb and (ga or gb):
        diffs.append({"field": "system.gpus", "a": ga, "b": gb})
    return {"same": bool(a and b) and not diffs, "have": [bool(a), bool(b)], "diffs": diffs, "unknown": unknown,
            "partial": bool(a.get("partial") or b.get("partial"))}


def compare_runs(run_a: str | Path, run_b: str | Path) -> dict:
    return compare(repro.read(run_a), repro.read(run_b))
