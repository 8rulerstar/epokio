"""클래스별 성능(epokio_classes.json)을 읽어 화면이 그대로 그릴 모양으로.

파일은 학습 대기열이 학습 끝에 쓰거나(source "train"), "클래스별로 계산" 작업이 best.pt로 검증해 쓴다("val").
값의 이름은 results.csv 열 이름과 같다(metrics/mAP50-95(B)). 머리는 괄호 속 글자: B 박스 · P 자세 · M 마스크.

약한 클래스: 그 머리의 주 점수(mAP50-95)가 클래스 평균의 WEAK_SHARE 미만. 사례가 FEW 미만이면 점수보다
"사례가 적다"가 먼저라 따로 표시한다(적은 사례의 점수는 흔들린다).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FILE = "epokio_classes.json"
WEAK_SHARE = 0.7
FEW = 10
HEADS = {"B": "box", "P": "pose", "M": "mask", "OBB": "obb"}
_KEY = re.compile(r"^metrics/(precision|recall|mAP50|mAP50-95)\((\w+)\)$")


def read(run_dir: Path) -> dict | None:
    try:
        d = json.loads((Path(run_dir) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = [r for r in d.get("rows", []) if isinstance(r, dict) and r.get("name") is not None]
    if not rows:
        return None
    heads: dict[str, dict[str, str]] = {}           # "box" -> {"mAP50-95": "metrics/mAP50-95(B)", ...}
    for k in d.get("keys") or [k for k in rows[0] if k.startswith("metrics/")]:
        m = _KEY.match(k)
        if m:
            heads.setdefault(HEADS.get(m.group(2), m.group(2).lower()), {})[m.group(1)] = k
    out_heads = []
    for head, cols in heads.items():
        main = cols.get("mAP50-95") or cols.get("mAP50")
        if not main:
            continue
        vals = [r[main] for r in rows if isinstance(r.get(main), (int, float))]
        mean = sum(vals) / len(vals) if vals else None
        table = []
        for r in rows:
            v = r.get(main)
            few = isinstance(r.get("instances"), int) and r["instances"] < FEW
            weak = mean is not None and isinstance(v, (int, float)) and len(vals) > 1 and v < mean * WEAK_SHARE
            table.append({"name": r["name"], "instances": r.get("instances"), "images": r.get("images"),
                          **{c: r.get(k) for c, k in cols.items()}, "weak": weak, "few": few})
        table.sort(key=lambda t: (t.get("mAP50-95", t.get("mAP50")) is None, t.get("mAP50-95", t.get("mAP50")) or 0))
        out_heads.append({"head": head, "main": "mAP50-95" if "mAP50-95" in cols else "mAP50",
                          "mean": round(mean, 4) if mean is not None else None, "rows": table})
    return {"source": d.get("source"), "at": d.get("at"), "heads": out_heads} if out_heads else None


def note(c: dict | None) -> tuple[str, str] | None:
    """해설 한 줄(관찰, 다음에 해 볼 것): 가장 약한 클래스들. 없으면 None"""
    if not c or not c["heads"]:
        return None
    h = c["heads"][0]
    weak = [r for r in h["rows"] if r["weak"]]
    if not weak:
        return None
    from .msg import tr
    names = ", ".join(r["name"] for r in weak[:3]) + (f" +{len(weak) - 3}" if len(weak) > 3 else "")
    obs = tr("Weakest classes: {names}, well below the class average of {mean}.", names=names, mean=f"{h['mean']:.3f}")
    few = [r["name"] for r in weak if r["few"]]
    if few:
        return obs, tr("Under {n} examples of {names}. Add more of them before tuning settings.",
                      names=", ".join(few[:3]), n=FEW)
    return obs, tr("Check their labels on the review screen, or add examples that look like the ones it misses.")
