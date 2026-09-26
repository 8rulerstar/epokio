"""가벼운 데이터·모델 버전: 학습마다 "무슨 데이터로, 어떤 모델이 나왔나"를 짧은 지문으로.

MLflow·DVC처럼 파일을 복사해 보관하지 않는다. 지문만 잰다:
  데이터 = data.yaml 내용 + 학습·검증 폴더의 파일 수·전체 크기·가장 최근 수정 시각
  모델   = best.pt 크기 + 수정 시각 (내용 해시는 수백 MB를 읽어야 해서 쓰지 않는다)
지문이 같으면 같은 데이터로 학습한 것이다. 라벨 하나만 고쳐도 지문이 바뀐다(수정 시각·크기).
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path

_cache: dict[tuple, str] = {}


def _dir_stats(d: Path) -> tuple[int, int, float]:
    n = size = 0
    newest = 0.0
    for root, _, files in os.walk(d):
        for f in files:
            try:
                st = os.stat(os.path.join(root, f))
            except OSError:
                continue
            n += 1
            size += st.st_size
            newest = max(newest, st.st_mtime)
    return n, size, newest


def _yaml_paths(text: str, base: Path) -> list[Path]:
    """data.yaml의 path·train·val에서 폴더를 찾는다(목록·파일 목록 형식은 그 파일만)."""
    get = lambda k: (re.search(rf"^{k}\s*:\s*([^#\n]+)", text, re.M) or [None, None])[1]
    root = (get("path") or "").strip().strip("'\"")
    rootp = Path(root) if root and Path(root).is_absolute() else base / root if root else base
    out = []
    for k in ("train", "val"):
        v = (get(k) or "").strip().strip("'\"")
        if not v or v.startswith("["):
            continue
        p = Path(v) if Path(v).is_absolute() else rootp / v
        out.append(p)
        lab = Path(str(p).replace(f"{os.sep}images", f"{os.sep}labels"))   # YOLO 라벨 폴더도(라벨만 고쳐도 바뀌게)
        if lab != p:
            out.append(lab)
    return out


def data_fingerprint(yaml_path: str | Path) -> str | None:
    y = Path(yaml_path)
    try:
        st = y.stat()
        text = y.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    dirs = [d for d in _yaml_paths(text, y.parent) if d.exists()]
    # 캐시 열쇠: yaml·폴더들의 수정 시각(폴더 안에 파일이 더해지거나 빠지면 폴더 시각이 바뀐다)
    # ★폴더 시각은 안의 파일 내용만 바뀌면 그대로다(라벨 한 줄 고치기). 그래서 60초가 지나면 다시 잰다
    key = (str(y), st.st_mtime, tuple((str(d), d.stat().st_mtime) for d in dirs), int(time.time() // 60))
    if key in _cache:
        return _cache[key]
    h = hashlib.sha1(text.encode())
    for d in dirs:
        h.update(repr((d.name, _dir_stats(d) if d.is_dir() else (1, d.stat().st_size, d.stat().st_mtime))).encode())
    fp = h.hexdigest()[:8]
    if len(_cache) > 2000:           # 데이터가 바뀔 때마다 새 열쇠가 생긴다. 옛것은 버린다(★끝없이 늘었다)
        _cache.clear()
    _cache[key] = fp
    return fp


def model_fingerprint(pt: str | Path) -> str | None:
    try:
        st = Path(pt).stat()
    except OSError:
        return None
    return hashlib.sha1(f"{st.st_size}:{int(st.st_mtime)}".encode()).hexdigest()[:8]
