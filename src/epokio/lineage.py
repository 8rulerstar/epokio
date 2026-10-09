"""버전 관리 깊이: 계보(누가 누구에서 나왔나) · 데이터셋 차이 · 모델 단계와 등록부.

* 계보   학습의 args.yaml `model`이 다른 학습의 weights/*.pt면 그 학습이 부모다. 거꾸로 찾으면 자식들.
* 데이터 목록(매니페스트)  데이터 지문을 처음 잴 때 파일 목록을 ~/.epokio/datasets/<지문>.json 에 적어 둔다.
         이미지는 크기·수정 시각, 라벨은 내용 해시(작다)와 클래스별 박스 수. 두 지문의 목록을 비교하면
         더해진·빠진·바뀐 파일이 나온다.
         ★목록은 Epokio가 그 데이터를 처음 본 때의 모습이다. 그 전에 바뀐 것은 알 수 없다(화면에 적는다).
* 모델 등록부  "배포"로 올리면 best.pt를 ~/.epokio/models/<이름>/v<N>/ 에 복사하고 model.json(어느 학습·데이터·점수)을 남긴다.
         원본 학습 폴더는 건드리지 않는다. 단계(후보·배포·보관)는 runmeta의 stage 칸.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import unicodedata
from pathlib import Path

from . import versions

DATA_DIR = Path.home() / ".epokio" / "datasets"
MODEL_DIR = Path.home() / ".epokio" / "models"
IMG = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
MAX_FILES = 200_000


# ── 데이터 목록 ─────────────────────────────────────

def _yaml_dirs(yaml_path: Path) -> list[Path]:
    """학습·검증 폴더(+라벨 폴더). ★train과 val이 같은 폴더면 두 번 훑었다(3만 장 기준 시간 두 배)"""
    text = yaml_path.read_text(encoding="utf-8", errors="ignore")
    seen, out = set(), []
    for d in versions._yaml_paths(text, yaml_path.parent):
        k = str(d.resolve()) if d.exists() else None
        if k and k not in seen:
            seen.add(k)
            out.append(d)
    return out


def manifest(yaml_path: Path) -> dict:
    """{상대 경로: [종류, 크기 또는 해시, {클래스: 박스 수}]}"""
    files: dict[str, list] = {}
    for d in _yaml_dirs(yaml_path):
        base = d.parent.parent if d.parent.name in ("images", "labels") else d.parent
        walk = [(str(d), [], [d.name])] if d.is_file() else os.walk(d)
        for root, _, names in walk:
            for n in names:
                p = Path(root) / n if d.is_dir() else d
                ext = p.suffix.lower()
                # 구분자는 /로 통일. ★윈도우는 labels\\train\\1.txt로 적어, 같은 데이터를 맥·윈도우에서 비교하면 전부 바뀐 것으로 보였다
                rel = unicodedata.normalize("NFC", p.relative_to(base).as_posix() if d.is_dir() else p.name)
                try:
                    if ext == ".txt":
                        raw = p.read_bytes()
                        per: dict[str, int] = {}
                        for line in raw.decode("utf-8", "ignore").splitlines():
                            v = line.split()
                            if v:
                                per[v[0]] = per.get(v[0], 0) + 1
                        files[rel] = ["label", hashlib.sha1(raw).hexdigest()[:10], per]
                    elif ext in IMG:
                        st = p.stat()
                        files[rel] = ["image", f"{st.st_size}:{int(st.st_mtime)}", {}]
                except OSError:
                    continue
                if len(files) >= MAX_FILES:
                    return files
    return files


_pending: set[str] = set()
_lock = threading.Lock()


def _write(fp: str, y: Path):
    try:
        f = DATA_DIR / f"{fp}.json"
        if not f.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps({"fingerprint": fp, "yaml": str(y), "recorded": time.time(), "files": manifest(y)},
                                      ensure_ascii=False), encoding="utf-8")
            tmp.replace(f)
            _index_add(fp, y)
    except OSError:
        pass
    finally:
        with _lock:
            _pending.discard(fp)


def record(yaml_path: str | Path, background: bool = False) -> str | None:
    """지문을 재고, 그 지문의 목록이 없으면 적어 둔다. 지문을 돌려준다.
    background=True면 목록은 따로 스레드에서 쓴다. ★3만 장이면 3초 걸려 학습 상세 첫 열기가 멈췄다(요청 중에 쓰던 때)"""
    y = Path(yaml_path)
    fp = versions.data_fingerprint(y)
    if not fp or (DATA_DIR / f"{fp}.json").exists():
        return fp
    if not background:
        _write(fp, y)
        return fp
    with _lock:
        if fp in _pending:
            return fp
        _pending.add(fp)
    threading.Thread(target=_write, args=(fp, y), daemon=True).start()
    return fp


def _index() -> dict:
    """{지문: {"yaml", "recorded"}}. 목록 파일(수만 줄)을 다 읽지 않고 버전 번호를 매기려고 따로 둔다.
    없으면(이 기능 전에 적힌 목록들) 한 번 목록들을 읽어 만든다"""
    f = DATA_DIR / "index.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    idx = {}
    for m in (DATA_DIR.glob("*.json") if DATA_DIR.is_dir() else []):
        if m.name == "index.json":
            continue
        try:
            d = json.loads(m.read_text(encoding="utf-8"))
            idx[d["fingerprint"]] = {"yaml": d.get("yaml"), "recorded": d.get("recorded", 0)}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    _save_index(idx)
    return idx


def _save_index(idx: dict):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = DATA_DIR / "index.tmp"
        tmp.write_text(json.dumps(idx), encoding="utf-8")
        tmp.replace(DATA_DIR / "index.json")
    except OSError:
        pass


def _index_add(fp: str, y: Path):
    with _lock:
        idx = _index()
        idx.setdefault(fp, {"yaml": str(y), "recorded": time.time()})
        _save_index(idx)


def data_version(fp: str | None) -> dict | None:
    """같은 data.yaml의 몇 번째 버전인가: {"n": 3, "of": 4}. 처음 본 순서(목록을 적은 시각)로 센다"""
    e = _index().get(fp or "")
    if not e:
        return None
    same = sorted((v.get("recorded") or 0, k) for k, v in _index().items() if v.get("yaml") == e.get("yaml"))
    return {"n": [k for _, k in same].index(fp) + 1, "of": len(same)}


def recording(fp: str) -> bool:
    with _lock:
        return fp in _pending


def load_manifest(fp: str) -> dict | None:
    if not re.fullmatch(r"[0-9a-f]{8}", fp or ""):
        return None
    try:
        return json.loads((DATA_DIR / f"{fp}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def diff(a: str, b: str, limit: int = 300) -> dict:
    """데이터 지문 a(옛) → b(새). 더해진·빠진·바뀐 파일과 클래스별 박스 수 변화"""
    ma, mb = load_manifest(a), load_manifest(b)
    if not ma or not mb:
        if recording(a) or recording(b):
            raise ValueError("still reading the file list of this data version, try again in a few seconds")
        raise ValueError("no file list for one of these data versions (it is recorded the first time Epokio sees a run)")
    fa, fb = ma["files"], mb["files"]
    added = sorted(set(fb) - set(fa))
    removed = sorted(set(fa) - set(fb))
    changed = sorted(k for k in set(fa) & set(fb) if fa[k][1] != fb[k][1])

    def boxes(files):
        tot: dict[str, int] = {}
        for kind, _, per in files.values():
            if kind == "label":
                for c, n in per.items():
                    tot[c] = tot.get(c, 0) + n
        return tot
    ba, bb = boxes(fa), boxes(fb)
    cls = sorted(set(ba) | set(bb), key=lambda c: (len(c), c))
    count = lambda ks, files, kind: sum(1 for k in ks if files[k][0] == kind)
    return {"from": a, "to": b, "recorded": [ma.get("recorded"), mb.get("recorded")],
            "images": {"added": count(added, fb, "image"), "removed": count(removed, fa, "image"), "changed": count(changed, fb, "image"),
                       "before": sum(1 for v in fa.values() if v[0] == "image"), "after": sum(1 for v in fb.values() if v[0] == "image")},
            "labels": {"added": count(added, fb, "label"), "removed": count(removed, fa, "label"), "changed": count(changed, fb, "label")},
            "boxes": [{"cls": c, "before": ba.get(c, 0), "after": bb.get(c, 0)} for c in cls],
            "added": added[:limit], "removed": removed[:limit], "changed": changed[:limit],
            "truncated": max(len(added), len(removed), len(changed)) > limit}


# ── 계보 ────────────────────────────────────────────

def start_weights(run_dir: Path) -> str | None:
    """args.yaml의 model (시작 가중치). 상대 경로는 학습 폴더 기준"""
    try:
        text = (run_dir / "args.yaml").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    m = re.search(r"^model:\s*(.+)$", text, re.M)
    if not m:
        return None
    v = m.group(1).split(" #")[0].strip().strip("'\"")
    return v or None


def _run_of_weights(w: str) -> Path | None:
    """…/<학습>/weights/best.pt → <학습> (그 폴더가 있을 때만)"""
    p = Path(w)
    if p.suffix != ".pt" or p.parent.name != "weights":
        return None
    run = p.parent.parent
    return run if (run / "args.yaml").exists() or (run / "results.csv").exists() else None


def lineage(run_dir: Path, all_runs: list[Path]) -> dict:
    w = start_weights(run_dir)
    parent = _run_of_weights(w) if w else None
    norm = lambda p: unicodedata.normalize("NFC", str(Path(p).resolve()))
    me = norm(run_dir)
    # 제 가중치(weights/last.pt)에서 시작했으면 이어 한 학습이다(`yolo train resume`). 부모도 자식도 아니고, 처음부터 학습한 것도 아니다.
    # ★자기를 자기 자식으로 보였고 '사전 학습 가중치에서 시작'이라 했다
    resumed = bool(parent) and norm(parent) == me
    if resumed:
        parent = None
    kids = []
    for r in all_runs:
        sw = start_weights(r)
        pr = _run_of_weights(sw) if sw else None
        if pr and norm(pr) == me and norm(r) != me:
            kids.append({"path": str(r), "name": r.name})
    chain, seen, cur = [], {me}, parent
    while cur and len(chain) < 12:                          # 조상 사슬 (돌고 도는 경우 막기)
        if norm(cur) in seen:
            break
        seen.add(norm(cur))
        chain.append({"path": str(cur), "name": cur.name})
        sw = start_weights(cur)
        cur = _run_of_weights(sw) if sw else None
    return {"weights": w, "parent": chain[0] if chain else None, "ancestors": chain, "children": kids,
            "pretrained": bool(w) and parent is None and not resumed}


# ── 모델 등록부 ──────────────────────────────────────

def _safe(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", unicodedata.normalize("NFC", name)).strip("._") or "model"


def promote(run_dir: Path, name: str | None, info: dict, root: Path | None = None) -> dict:
    """best.pt를 등록부의 새 버전으로 복사한다. 원본은 그대로."""
    best = run_dir / "weights" / "best.pt"
    if not best.exists():
        raise ValueError("this run has no weights/best.pt")
    root = root or MODEL_DIR
    d = root / _safe(name or run_dir.name)
    d.mkdir(parents=True, exist_ok=True)
    n = 1 + max((int(m.group(1)) for x in d.iterdir() if (m := re.fullmatch(r"v(\d+)", x.name))), default=0)
    v = d / f"v{n}"
    v.mkdir()
    shutil.copy2(best, v / "best.pt")
    meta = {"name": d.name, "version": n, "run": str(run_dir), "promoted": time.time(),
            "model_fingerprint": versions.model_fingerprint(best), **info}
    (v / "model.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return {**meta, "path": str(v / "best.pt")}


def registry(root: Path | None = None) -> list[dict]:
    root = root or MODEL_DIR
    out = []
    if root.is_dir():
        for f in sorted(root.glob("*/v*/model.json")):
            try:
                out.append({**json.loads(f.read_text(encoding="utf-8")), "path": str(f.parent / "best.pt")})
            except (OSError, ValueError):
                continue
    out.sort(key=lambda m: (m.get("name", ""), -m.get("version", 0)))
    return out
