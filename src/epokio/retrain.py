"""검수 결과로 파일을 쓰는 쪽: 고친 라벨(labels_fixed/), 판정(review.csv), 재학습 세트(retrain/).

★원본 라벨·이미지는 절대 덮어쓰지 않는다. 새 파일은 전부 평가 결과 폴더 안에 쓴다.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
from pathlib import Path


def fixed_dir(out: Path) -> Path:
    return out / "labels_fixed"


def fix_label(out: Path, image: str, boxes: list[dict]) -> Path:
    """고친 라벨을 평가 폴더의 labels_fixed/<이미지 이름>.txt 에 쓴다. 원본은 건드리지 않는다."""
    lines = []
    for b in boxes:
        try:                                              # ★"invalid literal for int()"이 그대로 화면에 나갔다
            c = int(b["cls"])
            if len(b["box"]) != 4:
                raise ValueError
            x, y, w, h = (min(max(float(v), 0.0), 1.0) for v in b["box"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("each box needs a class number and box [cx, cy, w, h]") from None
        if w <= 0 or h <= 0 or c < 0:
            raise ValueError("box must have a class and a positive size")
        lines.append(f"{c} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
    d = fixed_dir(out)
    d.mkdir(parents=True, exist_ok=True)
    f = d / (_stem(Path(image)) + ".txt")                  # ★splitext 금지(파일명의 마침표). 확장자 없으면 name[:-0]이 ""였다
    f.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return f


def fixed_labels(out: Path) -> dict[str, list[dict]]:
    """이미지 이름(확장자 뺀 것) → 고친 박스들"""
    d = fixed_dir(out)
    res = {}
    if d.is_dir():
        for f in d.glob("*.txt"):
            boxes = []
            for line in f.read_text(encoding="utf-8").splitlines():
                v = line.split()
                if len(v) >= 5:
                    boxes.append({"cls": int(float(v[0])), "box": [float(x) for x in v[1:5]]})
            res[f.name[:-4]] = boxes
    return res


REVIEW_CSV = "review.csv"
META = "# epokio review"          # 첫 줄. 문턱을 CSV 안에 남긴다(열로 넣으면 앱의 두 칸 파서가 깨진다)


def _meta_line(conf, iou) -> str:
    bits = [META]
    if conf is not None:
        bits.append(f"conf={float(conf):.3f}")
    if iou is not None:
        bits.append(f"iou={float(iou):.3f}")
    bits.append("saved=" + time.strftime("%Y-%m-%d %H:%M:%S"))
    return " ".join(bits)


def _rows(f: Path):
    """메타 줄(#로 시작)을 건너뛰고 읽는다. BOM이 있든 없든 읽힌다(utf-8-sig)."""
    text = f.read_text(encoding="utf-8-sig")
    body, meta = [], {}
    for line in text.splitlines():
        if line.startswith("#"):
            for kv in line.split():
                if "=" in kv:
                    k, _, v = kv.partition("=")
                    meta[k] = v
            continue
        body.append(line)
    return list(csv.DictReader(body)), meta


def verdicts(out: Path) -> dict[str, str]:
    f = out / REVIEW_CSV
    if not f.exists():
        return {}
    rows, _ = _rows(f)
    return {r["image"]: r["verdict"] for r in rows if r.get("image") and r.get("verdict")}


def thresholds(out: Path) -> dict:
    """review.csv에 적힌 conf·iou 문턱(옛 파일은 빈 사전)"""
    f = out / REVIEW_CSV
    if not f.exists():
        return {}
    _, meta = _rows(f)
    got = {}
    for k in ("conf", "iou"):
        try:
            got[k] = float(meta[k])
        except (KeyError, ValueError):
            pass
    return got


def write_csv(path: Path, header: list[str], rows, conf=None, iou=None) -> Path:
    """검수 CSV 한 벌. csv 모듈이 따옴표를 처리하고, BOM(utf-8-sig)으로 엑셀 한글이 안 깨진다."""
    buf = io.StringIO()
    buf.write(_meta_line(conf, iou) + "\n")
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    text = buf.getvalue()
    if path is not None:
        path.write_text(text, encoding="utf-8-sig")
    return text


def save_verdicts(out: Path, v: dict[str, str], conf=None, iou=None) -> int:
    write_csv(out / REVIEW_CSV, ["image", "verdict"], ([k, v[k]] for k in sorted(v)), conf, iou)
    return len(v)


def export_csv(data: dict, verds: dict[str, str]) -> str:
    """검수 화면의 "내보내기": 점수와 판정을 한 표로. 문턱은 첫 줄에 적힌다."""
    head = ["image", "score", "correct", "extra", "missed", "verdict"]
    rows = ([r.get("image", ""), f"{float(r.get('score') or 0):.4f}", r.get("tp", ""), r.get("fp", ""),
             r.get("fn", ""), verds.get(r.get("image", ""), "")] for r in data.get("rows", []))
    return write_csv(None, head, rows, data.get("conf"), data.get("iou"))


VERDICTS = ("model_wrong", "label_wrong", "unsure", "ok")


def review_summary(out: Path, top: int = 5) -> dict | None:
    """보고서에 실을 검수 요약: 판정 수치 + 점수가 낮은 오답 몇 개. 판정이 없으면 None"""
    ev = out / "epokio_eval.json"
    verds = verdicts(out)
    if not verds or not ev.exists():
        return None
    try:
        data = json.loads(ev.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    from . import review as _review
    thr = thresholds(out)
    try:
        data = _review.rescore(data, thr.get("conf"), float(thr.get("iou") or data.get("iou") or 0.5))
    except Exception:                                  # 옛 결과(gt·pred 없음)는 그대로 쓴다
        pass
    counts = {k: sum(1 for x in verds.values() if x == k) for k in VERDICTS}
    rows = [r for r in data.get("rows", []) if verds.get(r.get("image")) in ("model_wrong", "label_wrong", "unsure")]
    rows.sort(key=lambda r: float(r.get("score") or 0))
    worst = [{"image": Path(r["image"]).name, "score": r.get("score"), "verdict": verds.get(r["image"]),
              "extra": r.get("fp"), "missed": r.get("fn")} for r in rows[:top]]
    return {"reviewed": len(verds), "images": data.get("images") or len(data.get("rows", [])),
            "counts": counts, "conf": data.get("conf"), "iou": data.get("iou"),
            "fixed": len(fixed_labels(out)), "worst": worst, "folder": str(out)}


IMG = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def _link(src: Path, dst: Path):
    """하드링크 → 심볼릭 링크 → 복사 (공간을 거의 안 쓴다)"""
    try:
        os.link(src, dst)
    except OSError:
        try:
            dst.symlink_to(src)
        except OSError:
            dst.write_bytes(src.read_bytes())


def _stem(p: Path) -> str:
    return p.name[: -len(p.suffix)] if p.suffix else p.name          # ★splitext 금지


def _yaml_field(text: str, key: str) -> str | None:
    m = re.search(rf"^{key}:\s*(.+)$", text, re.M)
    return m.group(1).split(" #")[0].strip().strip("'\"") if m else None


def _base_data(model: str) -> Path | None:
    """runs/…/weights/best.pt → 그 학습의 args.yaml에 적힌 data (yaml 파일이거나 분류 데이터 폴더)"""
    run = Path(model).parent.parent
    try:
        v = _yaml_field((run / "args.yaml").read_text(encoding="utf-8", errors="ignore"), "data")
    except OSError:
        return None
    if not v:
        return None
    p = Path(v) if Path(v).is_absolute() else run / v
    return p if p.exists() else None


def _inside(p: Path, d: Path) -> bool:
    try:
        p.resolve().relative_to(d.resolve())
        return True
    except (ValueError, OSError):
        return False


def build_retrain(out: Path, model: str, want: list[str], repeat: int = 2) -> dict:
    """검수 결과로 재학습 세트를 만든다.
    * 고른 판정(want: model_wrong·label_wrong·unsure)의 이미지 + 라벨을 고친 모든 이미지
    * 라벨은 고친 것이 있으면 그것, 없으면 원래 라벨. 어려운 이미지는 repeat번 넣는다(링크라 공간을 거의 안 쓴다)
    * ★검수는 보통 검증 이미지로 한다. 그 이미지를 학습에 더하고 검증은 그대로 두면 학습한 걸로 채점하게 된다(누수).
      그래서 검증 폴더에서 고른 이미지는 학습으로 "옮기고" 새 검증 목록에서 뺀다(moved_from_val로 알린다)
    * 분류는 클래스 폴더 구조(train/<클래스>/, val/<클래스>/)로, 검출·자세·분할은 data.yaml로"""
    ev = out / "epokio_eval.json"
    if not ev.exists():                                   # ★FileNotFoundError 경로가 그대로 나갔다
        raise ValueError("this check has no results yet")
    data = json.loads(ev.read_text(encoding="utf-8"))
    if data.get("source"):
        raise ValueError("imported predictions have no YOLO label files; use Export to get the list of images instead")
    task = data.get("task") or ("classify" if data.get("rows") and "top" in data["rows"][0] else "detect")
    vd = verdicts(out)
    fixed = fixed_labels(out)
    pick = [r for r in data.get("rows", []) if vd.get(r["image"]) in want or _stem(Path(r["image"])) in fixed]
    if not pick:
        raise ValueError("nothing to add: mark some images or fix a label first")
    root = out / "retrain"
    if root.exists():
        import shutil
        shutil.rmtree(root)
    root.mkdir(parents=True)
    base = _base_data(model)
    if task == "classify":
        return _retrain_classify(root, base, pick, fixed, data, repeat)
    return _retrain_yolo(root, base, pick, fixed, data, repeat)


def _retrain_yolo(root: Path, base: Path | None, pick, fixed, data, repeat) -> dict:
    (root / "images").mkdir()
    (root / "labels").mkdir()
    n = 0
    for r in pick:
        img = Path(r["image"])
        lab = Path(r["label"]) if r.get("label") else None
        fix = fixed.get(_stem(img))
        text = "\n".join(f"{b['cls']} {' '.join(f'{v:.6f}' for v in b['box'])}" for b in fix) + "\n" if fix is not None \
            else (lab.read_text(encoding="utf-8") if lab and lab.exists() else "")
        for k in range(max(repeat, 1)):
            name = f"{_stem(img)}__r{k}" if k else _stem(img)
            _link(img, root / "images" / (name + img.suffix))
            (root / "labels" / (name + ".txt")).write_text(text, encoding="utf-8")
            n += 1
    lines = [f"# Epokio 재학습 세트: 검수에서 고른 {len(pick)}장(×{repeat}) + 원래 학습 데이터", f"path: {root}"]
    moved, warning = 0, None
    if base and base.is_file():
        btext = base.read_text(encoding="utf-8", errors="ignore")
        bp = _yaml_field(btext, "path")
        bpath = Path(bp) if bp and Path(bp).is_absolute() else base.parent / (bp or "")
        absify = lambda v: Path(v) if Path(v).is_absolute() else bpath / v
        tr = _yaml_field(btext, "train")
        trains = [str(absify(v.strip().strip("'\""))) for v in tr.strip("[] ").split(",")] if tr else []
        lines.append("train: [" + ", ".join(json.dumps(t) for t in trains + [str(root / "images")]) + "]")
        va = _yaml_field(btext, "val")
        vdir = absify(va) if va else None
        if vdir and vdir.is_dir():
            picked = {str(Path(r["image"]).resolve()) for r in pick}
            keep = sorted(str(p) for p in vdir.rglob("*") if p.suffix.lower() in IMG and str(p.resolve()) not in picked)
            moved = sum(1 for r in pick if _inside(Path(r["image"]), vdir))
            (root / "val.txt").write_text("\n".join(keep) + "\n", encoding="utf-8")
            lines.append(f"val: {json.dumps(str(root / 'val.txt'))}   # 원래 검증에서 학습으로 옮긴 {moved}장을 뺀 목록")
        elif va:
            lines.append(f"val: {json.dumps(str(vdir))}")
            warning = "validation is not a folder, so images picked from it could not be removed (check for overlap)"
        names = re.search(r"^names:.*?(?=^\S|\Z)", btext, re.M | re.S)
        if names:
            lines.append(names.group(0).rstrip())
    else:
        lines += ["train: images", "val: images   # ★원래 data.yaml을 못 찾았다. 검증 폴더를 직접 바꿔 넣을 것"]
        warning = "the original data.yaml was not found; set the validation folder yourself before training"
        if data.get("names"):
            lines.append("names:\n" + "\n".join(f"  {k}: {v}" for k, v in sorted(data["names"].items(), key=lambda t: int(t[0]))))
    y = root / "data.yaml"
    y.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"data": str(y), "images": len(pick), "files": n, "base": str(base) if base else None,
            "moved_from_val": moved, "warning": warning}


def _retrain_classify(root: Path, base: Path | None, pick, fixed, data, repeat) -> dict:
    """분류: 원래 train/ 전부 + 고른 이미지(고친 클래스로, repeat번) → retrain/train/<클래스>/, val/은 고른 이미지를 뺀 원래 val/"""
    names = {int(k): v for k, v in (data.get("names") or {}).items()}
    if not base or not base.is_dir() or not (base / "train").is_dir():
        raise ValueError("could not find the original classification dataset (a folder with train/ and val/)")
    picked = {str(Path(r["image"]).resolve()) for r in pick}
    n = moved = 0
    for split in ("train", "val"):
        for cdir in sorted(p for p in (base / split).iterdir() if p.is_dir()):
            dst = root / split / cdir.name
            dst.mkdir(parents=True, exist_ok=True)
            for img in cdir.iterdir():
                if img.suffix.lower() not in IMG:
                    continue
                if split == "val" and str(img.resolve()) in picked:
                    moved += 1                                  # 학습으로 옮긴다(아래). 검증에서는 뺀다
                    continue
                _link(img, dst / img.name)
    for r in pick:
        img = Path(r["image"])
        fix = fixed.get(_stem(img))
        cls = fix[0]["cls"] if fix else r.get("truth")
        cname = names.get(cls, str(cls)) if cls is not None else img.parent.name
        dst = root / "train" / cname
        dst.mkdir(parents=True, exist_ok=True)
        for k in range(max(repeat, 1)):
            f = dst / (f"{_stem(img)}__epokio{k}{img.suffix}")
            if not f.exists():
                _link(img, f)
                n += 1
    return {"data": str(root), "images": len(pick), "files": n, "base": str(base), "moved_from_val": moved, "warning": None}
