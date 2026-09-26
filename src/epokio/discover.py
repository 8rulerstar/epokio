"""아무 인자 없이 켰을 때 학습 폴더를 알아서 찾는다.

초보자에게 경로를 타이핑하게 하면 안 된다, 거기서 대부분 포기한다.
"""
from __future__ import annotations

from pathlib import Path

# 사람들이 실제로 학습을 돌리는 자리. 위에 있을수록 먼저 본다.
def _cwd_if_safe() -> list[Path]:
    """현재 폴더는 홈 아래일 때만 본다.
    ★앱(GUI)이 띄운 프로세스는 작업 폴더가 '/'라서, 그대로 두면 디스크 전체를 훑었다."""
    try:
        c = Path.cwd().resolve()
    except OSError:
        return []
    home = Path.home().resolve()
    return [c] if c != home and home in c.parents else []


CANDIDATES = [
    *_cwd_if_safe(),
    Path.home() / "runs",
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Projects",
    Path.home() / "Downloads",
]

MAX_DEPTH = 5   # Desktop/프로젝트/하위폴더/runs 까지 닿으려면 이 정도는 필요하다
MAX_HITS = 40


def _looks_like_run(d: Path) -> bool:
    from . import adapters
    return adapters.detect(d) is not None          # Ultralytics·Hugging Face·Lightning·Keras


def _walk(root: Path, depth: int, hits: list[Path]):
    if depth < 0 or len(hits) >= MAX_HITS:
        return
    try:
        entries = [e for e in root.iterdir() if e.is_dir()]
    except OSError:
        return
    for e in entries:
        if e.name.startswith(".") or e.name in {"node_modules", "venv", ".venv", "images", "labels"}:
            continue
        if _looks_like_run(e):
            hits.append(root)          # run 폴더가 아니라 그 부모(= runs 폴더)를 잡는다
            return
        _walk(e, depth - 1, hits)


def find_roots() -> list[Path]:
    """학습 결과가 모여 있는 폴더들을 찾는다. 없으면 빈 목록."""
    hits: list[Path] = []
    seen = set()
    for c in CANDIDATES:
        if not c.exists():
            continue
        found: list[Path] = []
        _walk(c, MAX_DEPTH, found)
        for f in found:
            key = str(f.resolve())
            if key not in seen:
                seen.add(key)
                hits.append(f)
    return hits[:5]
