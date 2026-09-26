"""데이터셋 건강 검진. 학습을 걸기 전에 데이터 문제를 짚는다.

레퍼런스 아이디어: Roboflow의 Health Check. (코드는 가져오지 않았다)
초보자가 학습을 망치는 가장 흔한 원인은 모델이 아니라 데이터다.

파일만 읽는다. 표준 라이브러리만 쓴다 (PyYAML은 있으면 쓰는 선택 의존성) (이미지 크기도 헤더만 읽어 구한다).
"""
from __future__ import annotations

from . import yamlish
from .msg import tr

import hashlib
import struct
import unicodedata
from collections import Counter
from pathlib import Path

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _parse_yaml(text: str) -> tuple[dict, list[str]]:
    """data.yaml을 읽어 path·train·val·test·names·kpt_shape만 정리한다. (설정, 경고)

    읽기는 yamlish(PyYAML이 있으면 그것, 없으면 표준 라이브러리 부분집합)에 맡긴다.
    Ultralytics check_det_dataset과 같게: names는 리스트·{번호: 이름} 둘 다, 없으면 nc로
    class_0.. 을 만들고, validation 키는 val로 본다. train·val·test는 문자열 또는 리스트.
    """
    data, warns = yamlish.load(text)
    if not isinstance(data, dict):
        return {}, warns + [tr("data.yaml is not a 'key: value' mapping.")]
    out: dict = {}
    if "val" not in data and "validation" in data:
        data["val"] = data["validation"]
    for k in ("path", "train", "val", "test"):
        v = data.get(k)
        if v is None:
            continue
        if isinstance(v, list):
            out[k] = [str(x) for x in v if x is not None]
        elif isinstance(v, (str, int, float)):
            out[k] = str(v)
        else:
            warns.append(f"'{k}' should be a path or a list of paths.")
    if isinstance(data.get("kpt_shape"), list):
        out["kpt_shape"] = data["kpt_shape"]
    names = data.get("names")
    if isinstance(names, dict):
        try:
            keyed = {int(k): v for k, v in names.items()}
        except (TypeError, ValueError):
            keyed = None
            warns.append("'names' keys should be class numbers (0, 1, 2 ...).")
        if keyed is not None:
            if sorted(keyed) != list(range(len(keyed))):
                warns.append("'names' numbers should run 0, 1, 2 ... without gaps.")
            out["names"] = [str(keyed[k]) for k in sorted(keyed)]
    elif isinstance(names, list):
        out["names"] = [str(x) for x in names]
    elif names is not None:
        warns.append("'names' should be a list or a {number: name} mapping.")
    if "names" not in out and names is None and isinstance(data.get("nc"), int):
        out["names"] = [f"class_{i}" for i in range(data["nc"])]
    if data.get("download"):                               # 첫 학습 때 ultralytics가 받는 데이터셋
        out["download"] = True
    return out, warns


def image_size(p: Path) -> tuple[int, int] | None:
    """JPEG·PNG 크기를 헤더만 읽어 구한다 (사진 전체를 열지 않는다)."""
    try:
        with open(p, "rb") as f:
            head = f.read(26)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", head[16:24])
            if head[:2] == b"\xff\xd8":
                f.seek(2)
                while True:
                    b = f.read(1)
                    while b and b != b"\xff":
                        b = f.read(1)
                    while b == b"\xff":
                        b = f.read(1)
                    if not b:
                        return None
                    if b[0] in (0xC0, 0xC1, 0xC2):
                        f.read(3)
                        h, w = struct.unpack(">HH", f.read(4))
                        return w, h
                    size = struct.unpack(">H", f.read(2))[0]
                    f.seek(size - 2, 1)
    except (OSError, struct.error):
        return None
    return None


def _spec_text(spec) -> str:
    return ", ".join(spec) if isinstance(spec, list) else str(spec)


def _images_of(spec, base: Path) -> list[Path]:
    if not spec:
        return []
    if isinstance(spec, list):                              # train: [a, b]
        return [x for one in spec for x in _images_of(one, base)]
    if isinstance(spec, str) and spec.startswith("["):     # 한 줄 문자열 "[a, b]"로 온 경우(stdlib 읽기)
        return [x for part in spec.strip("[]").split(",") if part.strip()
                for x in _images_of(part.strip().strip("'\""), base)]
    p = Path(spec)
    p = p if p.is_absolute() else base / p
    if p.suffix == ".txt" and p.is_file():                 # 이미지 목록 파일
        return [Path(l.strip()) if Path(l.strip()).is_absolute() else base / l.strip()
                for l in p.read_text(encoding="utf-8-sig", errors="replace").splitlines() if l.strip()]
    if p.is_dir():
        return sorted(x for x in p.rglob("*") if x.suffix.lower() in IMG_EXT)
    return []


def _label_of(img: Path) -> Path:
    parts = list(img.parts)
    if "images" in parts:
        i = len(parts) - 1 - parts[::-1].index("images")
        return Path(*parts[:i], "labels", *parts[i + 1:]).with_suffix(".txt")
    return img.with_suffix(".txt")


# 이미지 앞부분 서명. 무거운 디코딩 없이 "이미지 파일이 맞나"만 본다
_MAGIC = ((b"\xff\xd8\xff",), (b"\x89PNG\r\n\x1a\n",), (b"BM",), (b"II*\x00", b"MM\x00*"), (b"RIFF",))


def _header_ok(head: bytes) -> bool:
    if head.startswith(b"RIFF"):
        return head[8:12] == b"WEBP"
    return any(head.startswith(m) for ms in _MAGIC for m in ms)


def _fingerprint(img: Path, full: bool) -> tuple[str | None, bool]:
    """(가벼운 해시, 헤더가 이미지인가). 가벼운 해시 = 크기 + 앞 64KB + 끝 4KB. full이면 전체 내용.
    못 읽으면 (None, False)"""
    try:
        size = img.stat().st_size
        with open(img, "rb") as f:
            head = f.read(65536)
            h = hashlib.blake2b(str(size).encode() + head, digest_size=16)
            if full:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            elif size > 65536:
                f.seek(max(65536, size - 4096))
                h.update(f.read(4096))
    except OSError:
        return None, False
    return h.hexdigest(), size > 0 and _header_ok(head[:16])


def _row_bad(r: list[str], kpt: list | None) -> bool:
    """좌표 부분이 깨졌나. 박스(5칸)·pose(5 + 점수 x 차원)·seg 다각형(1 + 2n, n>=3) 모양을 본다"""
    try:
        v = [float(x) for x in r[1:]]
    except ValueError:
        return True
    if kpt and len(kpt) >= 2:
        k, d = int(kpt[0]), int(kpt[1])
        if len(v) != 4 + k * d:
            return True
        pts = [x for i in range(k) for x in v[4 + i * d: 4 + i * d + 2]]    # 가시성(3번째)은 0~2라 범위에서 뺀다
        return any(x < 0 or x > 1 for x in v[:4] + pts)
    if len(v) == 4:
        return any(x < 0 or x > 1 for x in v)
    if len(v) >= 6 and len(v) % 2 == 0:                     # seg 다각형: 좌표 전부
        return any(x < 0 or x > 1 for x in v)
    return True


def check(data_yaml: str, sample_sizes: int = 300, deep_limit: int | None = 20000, full_hash: bool = False) -> dict:
    """deep_limit: 분할마다 내용 검사(해시·헤더)할 최대 장수. None이면 전부. 파일명 겹침은 항상 전부 본다.
    full_hash: 겹침·중복을 가벼운 해시 대신 전체 내용 해시로(느림)"""
    y = Path(str(data_yaml).strip().strip('"').strip("'"))   # 탐색기 "경로로 복사"의 따옴표
    if y.is_dir():                                          # 폴더를 주면 그 안의 data.yaml(없으면 yaml 하나)
        found = [y / "data.yaml"] if (y / "data.yaml").is_file() else sorted(y.glob("*.yaml")) + sorted(y.glob("*.yml"))
        if len(found) == 1:
            y = found[0]
    if not y.is_file():
        # ★어느 경로를 봤는지 말한다. 예전엔 "data.yaml not found"뿐이라 뭐가 틀렸는지 몰랐다
        return {"ok": False, "error": tr("No data.yaml at {path}", path=str(y))}
    cfg, yaml_warns = _parse_yaml(y.read_text(encoding="utf-8-sig", errors="replace"))
    base = Path(cfg.get("path") or y.parent)
    if not base.is_absolute():
        base = (y.parent / base).resolve()
    names = cfg.get("names", [])
    report = {"ok": True, "data": str(y), "classes": names, "splits": {}, "warnings": [], "tips": []}   # data: 실제로 읽은 파일
    # 번역 표(msg.py)에 없는 문장이라 tr을 거치지 않는다. 읽기 문제는 영어 그대로 보여 준다
    report["warnings"] += [{"level": "warn", "text": w} for w in yaml_warns]
    per_class = Counter()
    sizes = []
    nfd_names = 0
    kpt = cfg.get("kpt_shape")
    stems: dict[str, set] = {}
    prints: dict[str, dict] = {}                            # 분할 -> {해시: 첫 파일}
    dup = unreadable = checked = total = 0

    split_imgs: dict[str, list[Path]] = {}
    for split in ("train", "val", "test"):
        imgs = split_imgs[split] = _images_of(cfg.get(split, ""), base)
        if not imgs and split != "test":
            # 못 찾아도 ultralytics는 찾을 수 있는 경우는 '확인' 수준으로(출발 전 점검이 막지 않게).
            # ★download: 가 있는 yaml(첫 학습 때 받는다)과 상대 path(ultralytics는 작업 폴더·datasets 폴더에서도 찾는다)를
            #   '오류'로 막아서 멀쩡한 데이터셋이 "그래도 시작"을 눌러야 했다
            soft = cfg.get("download") or (cfg.get("path") and not Path(cfg["path"]).is_absolute() and not base.exists())
            report["warnings"].append({"level": "warn" if soft else "error",
                                       "text": tr("No {split} images found at '{path}'.", split=tr(split), path=_spec_text(cfg.get(split, '')))})
        missing = empty = bad = 0
        split_class = Counter()
        for img in imgs:
            if img.name != _nfc(img.name):
                nfd_names += 1
            lab = _label_of(img)
            if not lab.exists():
                missing += 1
                continue
            rows = [r.split() for r in lab.read_text(encoding="utf-8", errors="ignore").splitlines() if r.strip()]
            if not rows:
                empty += 1
            for r in rows:
                # ★'0 0.5 0.5'처럼 잘린 줄은 r[1:5]가 오류 없이 짧게 잘려 멀쩡한 줄로 셌고, '1.7'은 1반으로 셌다
                if len(r) < 5:
                    bad += 1; continue
                try:
                    c = float(r[0])
                except ValueError:
                    bad += 1; continue
                if not c.is_integer():                      # '1.7'은 1반이 아니다(1.0은 된다)
                    bad += 1; continue
                c = int(c)
                if (names and not (0 <= c < len(names))) or _row_bad(r, kpt):
                    bad += 1; continue
                split_class[c] += 1
        per_class.update(split_class)
        stems[split] = {_nfc(i.name[: -len(i.suffix)] if i.suffix else i.name) for i in imgs}
        seen = prints.setdefault(split, {})
        todo = imgs if deep_limit is None else imgs[:deep_limit]
        total += len(imgs); checked += len(todo)
        for img in todo:
            fp, ok = _fingerprint(img, full_hash)
            if not ok:
                unreadable += 1
            if fp is None:
                continue
            if fp in seen:
                dup += 1
            else:
                seen[fp] = img
        for img in imgs[: max(sample_sizes // 2, 1)]:
            s = image_size(img)
            if s:
                sizes.append(s)
        report["splits"][split] = {"images": len(imgs), "missing_labels": missing, "empty_labels": empty,
                                   "bad_rows": bad, "instances": dict(split_class)}

    tr_n = report["splits"].get("train", {}).get("images", 0)
    va = report["splits"].get("val", {}).get("images", 0)
    W = report["warnings"]
    for split, s in report["splits"].items():
        if s["missing_labels"]:
            W.append({"level": "warn", "text": tr("{n} {split} images have no label file. They are treated as having nothing in them.", n=s['missing_labels'], split=tr(split))})
        if s["bad_rows"]:
            W.append({"level": "error", "text": tr("{n} label rows in {split} are broken (wrong class number, wrong number of values, or coordinates outside 0 to 1).", n=s['bad_rows'], split=tr(split))})
    if tr_n and va and va < max(10, tr_n * 0.05):
        W.append({"level": "warn", "text": tr("Only {va} validation images for {tr} training images. Scores will jump around. Aim for about 10 to 20 percent.", va=va, tr=tr_n)})
    for other in ("val", "test"):
        if not stems.get("train") or not stems.get(other):
            continue
        same_content = set(prints.get("train", {})) & set(prints.get(other, {}))
        same_name = stems["train"] & stems[other]
        if same_content:
            W.append({"level": "error", "text": tr("{n} {split} images are the same files as train images. The score will look better than it is.", n=len(same_content), split=tr(other))})
        elif same_name:
            ex = ", ".join(sorted(same_name)[:3])
            W.append({"level": "warn", "text": tr("{n} {split} images have the same file name as a train image (for example {ex}). Check that they are different photos.", n=len(same_name), split=tr(other), ex=ex)})
    if dup:
        W.append({"level": "warn", "text": tr("{n} images are exact copies of another image in the same split.", n=dup)})
    if unreadable:
        W.append({"level": "error", "text": tr("{n} image files are empty or not a known image format. Training will skip or fail on them.", n=unreadable)})
    if deep_limit is not None and checked < total:
        report["tips"].append(tr("Checked the contents of {c} of {t} images (duplicates, broken files). Run with no limit for a full check.", c=checked, t=total))
    train_class = Counter(report["splits"].get("train", {}).get("instances", {}))
    if per_class and names and tr_n:
        zero = [i for i in range(len(names)) if train_class.get(i, 0) == 0]
        nowhere = [names[i] for i in zero if per_class.get(i, 0) == 0]
        if nowhere:
            W.append({"level": "error", "text": tr("No training examples for: {names}. The model cannot learn these.", names=', '.join(nowhere[:6]))})
        for split in ("val", "test"):
            only = [names[i] for i in zero if report["splits"].get(split, {}).get("instances", {}).get(i, 0)]
            if only:
                W.append({"level": "error", "text": tr("These classes appear only in {split}, not in train: {names}. The model cannot learn them.", split=tr(split), names=', '.join(only[:6]))})
    if per_class and names:
        # 불균형은 **학습 분할**로 본다(학습 분할이 없으면 전체). ★전체로 세서 검증에만 있는 클래스가 섞였다
        counts = [(train_class if tr_n else per_class).get(i, 0) for i in range(len(names))]
        nz = [c for c in counts if c > 0]
        if len(nz) >= 2 and max(nz) >= 10 * min(nz):
            rare = names[counts.index(min(nz))]
            W.append({"level": "warn", "text": tr("Classes are very unbalanced. '{rare}' has only {lo} examples against {hi} for the largest class.", rare=rare, lo=min(nz), hi=max(nz))})
    if tr_n and tr_n < 100:
        report["tips"].append(tr("Fewer than 100 training images. Start with a small model (Nano) and expect the score to be noisy."))
    if nfd_names:
        W.append({"level": "warn", "text": tr("{n} file names use decomposed Unicode (made on a Mac). They can break when copied to Windows.", n=nfd_names)})
    if sizes:
        ws = sorted(w for w, _ in sizes)
        med = ws[len(ws) // 2]
        report["image_width_median"] = med
        if med < 320:
            report["tips"].append(tr("Images are small (median width {med}px). A training size (imgsz) of 320 or 416 may be enough and faster.", med=med))
        elif med > 2000:
            report["tips"].append(tr("Images are large (median width {med}px). Small objects may need imgsz 1024 or higher.", med=med))
    report["per_class"] = {names[i] if i < len(names) else str(i): c for i, c in sorted(per_class.items())}
    report["score"] = "good" if not any(w["level"] == "error" for w in W) and len(W) <= 1 else (
        "problems" if any(w["level"] == "error" for w in W) else "check")
    return report
