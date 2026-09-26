"""학습 하나의 상세: 에폭별 곡선, 종류별 성적, 자동 해설, 결과 이미지 목록, 주요 설정.

앱의 학습 상세 화면과 비교 화면이 이것 하나로 그린다. 원격 기계도 같은 모양으로 돌려준다.
기록 파일(어댑터)·args.yaml·그림 파일만 읽는다.
"""
from __future__ import annotations

import unicodedata
from dataclasses import asdict
from pathlib import Path

from . import analysis, schema

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
# 화면에 먼저 보여 줄 순서. 나머지 그림은 이름순으로 뒤에 붙는다
FIRST = ["results.png", "confusion_matrix_normalized.png", "confusion_matrix.png",
         "BoxPR_curve.png", "BoxF1_curve.png", "PosePR_curve.png", "PoseF1_curve.png",
         "MaskPR_curve.png", "MaskF1_curve.png", "PR_curve.png", "F1_curve.png",
         "val_batch0_labels.jpg", "val_batch0_pred.jpg", "val_batch1_labels.jpg", "val_batch1_pred.jpg",
         "labels.jpg"]
ARG_KEYS = ["task", "model", "data", "epochs", "imgsz", "batch", "device", "optimizer", "lr0", "patience", "name"]


def _args(run_dir: Path, keys: list[str] | None = ARG_KEYS) -> dict:
    """args.yaml에서 한 줄짜리 값만. yaml 의존성을 만들지 않는다. keys=None이면 전부."""
    return _args_file(run_dir / "args.yaml", keys)


def _args_file(path: Path, keys: list[str] | None = None) -> dict:
    """한 줄짜리 'key: value'만 읽는다(args.yaml·Lightning hparams.yaml)"""
    out = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ":" in line and not line.startswith((" ", "-")):
                k, v = line.split(":", 1)
                if keys is None or k in keys:
                    out[k] = v.split(" #")[0].strip()
    except OSError:
        pass
    return out


def _env(run_dir: Path) -> dict:
    """epokio_env.json(파이썬·torch·ultralytics·CUDA·GPU·git 커밋·패키지 지문). 없으면 빈 것."""
    import json
    try:
        d = json.loads((run_dir / "epokio_env.json").read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if isinstance(v, (str, int, float, bool)) or v is None} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _columns(run_dir: Path) -> dict[str, list]:
    rows = [r for r in analysis._load(run_dir) if r.get("epoch")]
    cols: dict[str, list] = {}
    names = list(dict.fromkeys(k for r in rows for k in r))      # ★첫 줄의 열만 봐서 나중에 생긴 열(HF 평가 값·epokio.log)이 빠졌다
    for name in names:
        vals = [analysis._f(r.get(name)) for r in rows]
        if any(v is not None for v in vals):
            cols[name] = vals
    return cols


def images(run_dir: Path) -> list[str]:
    have = {p.name for p in run_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS}
    first = [n for n in FIRST if n in have]
    media = run_dir / "epokio_media"                      # epokio.image()로 남긴 그림(최근 것 먼저, 60장까지)
    logged = sorted((p for p in media.iterdir() if p.suffix.lower() in IMAGE_EXTS), key=lambda p: p.name, reverse=True)[:60] \
        if media.is_dir() else []
    return first + sorted(have - set(first)) + [f"epokio_media/{p.name}" for p in logged]


def _notes_with_next(a, args: dict, weights: str | None, framework: str) -> list[dict]:
    """해설마다 "다음 학습" 제안(바꿀 설정)을 붙인다. 울트라리틱스 학습만(다른 프레임워크는 인자 이름이 다르다)"""
    if not a:
        return []
    out = []
    for i, (o, t) in enumerate(a.notes):
        kind = a.kinds[i] if i < len(a.kinds) else {}
        nxt = analysis.next_run(kind, args, weights) if framework == "ultralytics" else None
        out.append({"observation": o, "try": t, "next": nxt})
    return out


def detail(run_dir: Path) -> dict | None:
    from . import adapters
    got = adapters.load(run_dir)
    if got is None and not (run_dir / "args.yaml").exists():
        return None
    a = analysis.analyze(run_dir)
    best = run_dir / "weights" / "best.pt"
    return {
        "path": str(run_dir),
        "name": run_dir.name,
        "framework": got.framework if got else "ultralytics",
        "columns": (cols := _columns(run_dir) if got else {}),
        "column_info": schema.column_info(cols),        # 화면은 열 이름을 직접 해석하지 않는다
        "heads": [{k: v for k, v in asdict(h).items() if k != "f1_curve"} for h in a.heads] if a else [],
        "notes": _notes_with_next(a, _args(run_dir) or (got.args if got else {}), str(best) if best.exists() else None,
                                  got.framework if got else "ultralytics"),
        "images": images(run_dir),
        "args": _args(run_dir) or (got.args if got else {}),      # 화면에 보여 줄 주요 설정
        # "다시 학습"이 채울 모든 설정. ★주요 11개만 옮겨서 seed·lrf·mosaic·close_mosaic 등이 기본값으로 돌아갔다
        "all_args": _args(run_dir, None),
        "env": _env(run_dir),                                     # 어떤 환경에서 돌았나(epokio_env.json, Epokio 대기열 학습만)
        "weights": str(best) if best.exists() else None,
        "weights_mb": round(best.stat().st_size / 1e6, 2) if best.exists() else None,   # 두 목표 스윕("작은 모델")이 읽는다
        # 이어 하기에 쓸 체크포인트(ultralytics가 에폭마다 쓴다). 멈추거나 끊긴 학습을 처음부터 다시 돌리지 않게
        "last": str(run_dir / "weights" / "last.pt") if (run_dir / "weights" / "last.pt").exists() else None,
        "versions": _versions(run_dir, best),
        "format_warnings": list(getattr(got, "warnings", []) or []) if got else [],
        "explain": _explain(run_dir),
        "repro": _repro(run_dir),
    }


def _repro(run_dir: Path) -> dict | None:
    """재현 기록(epokio_repro.json). 학습이 이 앱 대기열에서 돌았으면 있다. 없으면 지금 상태로 대충 채운 것(partial)"""
    from . import repro, repro_runs
    try:
        return repro.read(run_dir) or repro_runs.posthoc(run_dir, write=False)
    except Exception:
        return None


def _explain(run_dir: Path) -> dict | None:
    """끝난 학습의 해설 한 문단(explain.py) + Jev로 다듬을 요청 본문(켰을 때만 앱이 보낸다). 실패해도 상세는 나온다"""
    from . import explain
    from .scan import read_run
    try:
        r = read_run(run_dir)
        status = {"failed": "failed", "stalled": "stalled"}.get(r.state if r else "", "finished")
        res = explain.explain(run_dir, status)
        return {**res, "jev_request": explain.jev_request(res)}
    except Exception:
        return None


def detail_versions(run_dir: Path) -> dict:
    return _versions(run_dir, run_dir / "weights" / "best.pt")


def _versions(run_dir: Path, best: Path) -> dict:
    """데이터·모델 지문(짧은 해시). 같은 데이터 지문 = 같은 데이터로 학습"""
    from . import versions
    data = _args(run_dir).get("data", "").strip("'\"")
    out = {}
    if data and data.endswith((".yaml", ".yml")):
        p = Path(data) if Path(data).is_absolute() else run_dir / data
        from . import lineage
        fp = lineage.record(p, background=True)    # 지문 + 처음 보면 파일 목록도(데이터셋 차이용, 따로 스레드에서)
        if fp:
            out["data"] = fp
    if best.exists():
        out["model"] = versions.model_fingerprint(best)
    return out


def inside(path: Path, roots: list[Path]) -> bool:
    """경로가 지켜보는 폴더 안인지. 밖의 파일은 절대 내주지 않는다(../ 우회 포함).
    ★한글 경로는 macOS가 NFD로, 앱이 NFC로 들고 있어 글자가 달라 보인다. 둘 다 NFC로 맞춰 비교한다."""
    from .textnorm import is_network
    if is_network(str(path)):
        # 네트워크 경로는 파일 시스템을 건드리기 전에(=접속하기 전에) 글자로만 판단한다.
        # 감시 폴더 자체가 네트워크 공유일 때만, 그 아래 경로를 받는다
        import ntpath
        norm = lambda s: ntpath.normcase(ntpath.normpath(unicodedata.normalize("NFC", str(s))))
        p = norm(path)
        if ".." in p.replace("/", "\\").split("\\"):
            return False
        return any(is_network(str(r)) and (p + "\\").startswith(norm(r).rstrip("\\") + "\\") for r in roots)
    try:
        p = Path(unicodedata.normalize("NFC", str(path.resolve())))
    except OSError:
        return False
    for r in roots:
        try:
            p.relative_to(Path(unicodedata.normalize("NFC", str(r.resolve()))))
            return True
        except (ValueError, OSError):
            continue
    return False
