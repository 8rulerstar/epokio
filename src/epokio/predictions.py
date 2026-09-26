"""예측 파일 가져오기: 어떤 프레임워크로 만든 모델이든 이미지별 정답·예측을 JSONL로 내보내면 검수 화면에서 연다.

한 줄에 이미지 하나. 첫 줄은 선택으로 {"names": {"0": "cat", ...}}.
  검출  {"image": "/abs/a.jpg", "gt": [{"cls": 0, "box": [cx, cy, w, h]}], "pred": [{"cls": 0, "box": [...], "conf": 0.91}]}
        box는 0~1 정규화(cx, cy, w, h). 픽셀이나 모서리 좌표면 "xyxy": [x1, y1, x2, y2]와 "width"/"height"를 준다
  분류  {"image": "/abs/a.jpg", "label": 2, "pred": 2, "conf": 0.87}      클래스는 번호나 이름
        또는 "probs": [0.1, 0.02, 0.87, …] (클래스마다 확률), 또는 "top": [[2, 0.87], [0, 0.1]]
결과는 평가 작업과 같은 원자료 모양이라 review.rescore가 그대로 채점한다.
"""
from __future__ import annotations

import json
from pathlib import Path

EXAMPLE = '''# 예: PyTorch 분류 모델의 검증 결과를 Epokio용 JSONL로
import json, torch
with open("predictions.jsonl", "w") as f:
    f.write(json.dumps({"names": {i: n for i, n in enumerate(dataset.classes)}}) + "\\n")
    for path, label in dataset.samples:                  # torchvision ImageFolder
        probs = torch.softmax(model(load(path)[None]), 1)[0].tolist()
        f.write(json.dumps({"image": path, "label": label, "probs": probs}) + "\\n")
'''


def _box(b: dict) -> list[float]:
    if "box" in b:
        v = [float(x) for x in b["box"]]
    elif "xyxy" in b:
        x1, y1, x2, y2 = (float(x) for x in b["xyxy"])
        w, h = float(b.get("width", 1)), float(b.get("height", 1))
        v = [(x1 + x2) / 2 / w, (y1 + y2) / 2 / h, (x2 - x1) / w, (y2 - y1) / h]
    else:
        raise ValueError("box needs 'box' [cx, cy, w, h] or 'xyxy' [x1, y1, x2, y2]")
    if len(v) != 4 or v[2] <= 0 or v[3] <= 0:
        raise ValueError("box must have four numbers with positive width and height")
    return v


def load(path: str | Path, limit: int = 100_000) -> dict:
    """JSONL → 평가 원자료. 틀린 줄은 줄 번호와 함께 ValueError"""
    names: dict[str, str] = {}
    rows, task = [], None
    idx = lambda c: int(c) if str(c).lstrip("-").isdigit() else _name_to_idx(c, names)
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    if text.lstrip().startswith("["):                           # JSON 배열 한 덩어리로 저장한 파일도 받는다
        try:
            items = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"not valid JSON ({e.msg}, line {e.lineno})") from None
        lines = [(i + 1, json.dumps(o)) for i, o in enumerate(items)]
    else:
        lines = list(enumerate(text.splitlines(), 1))
    for n, line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            o = json.loads(line)
            if not isinstance(o, dict):
                raise ValueError("each row must be a JSON object like {\"image\": ..., \"pred\": [...]}")
            if "names" in o and "image" not in o:
                nm = o["names"]
                names = {str(k): str(v) for k, v in (nm.items() if isinstance(nm, dict) else enumerate(nm))}
                continue
            img = str(o["image"])
            if "gt" in o or ("pred" in o and isinstance(o["pred"], list)):
                t = "detect"
                row = {"image": img, "label": "",
                       "gt": [{"cls": idx(b["cls"]), "box": _box(b), "kpts": []} for b in o.get("gt", [])],
                       "pred": [{"cls": idx(b["cls"]), "box": _box(b), "conf": float(b.get("conf", 1.0)), "kpts": []}
                                for b in o.get("pred", [])]}
            else:
                t = "classify"
                if "top" in o:
                    top = [[idx(c), float(p)] for c, p in o["top"]]
                elif "probs" in o:
                    top = sorted(([i, float(p)] for i, p in enumerate(o["probs"])), key=lambda x: -x[1])[:5]
                else:
                    top = [[idx(o["pred"]), float(o.get("conf", 1.0))]]
                truth = idx(o["label"]) if o.get("label") is not None else None
                row = {"image": img, "label": names.get(str(truth), str(truth)), "truth": truth, "top": top}
        except KeyError as e:                                # ★"'image'"만 보여 무슨 뜻인지 몰랐다
            raise ValueError(f"line {n}: missing field {e}") from None
        except json.JSONDecodeError as e:
            raise ValueError(f"line {n}: not valid JSON ({e.msg})") from None
        except (TypeError, ValueError) as e:
            raise ValueError(f"line {n}: {e}") from None
        if task and t != task:
            raise ValueError(f"line {n}: mixes {task} and {t} rows")
        task = t
        rows.append(row)
        if len(rows) >= limit:
            break
    if not rows:
        raise ValueError("no rows found (expected one JSON object per line, or a JSON array)")
    return {"task": task, "metric": "top-1 correct" if task == "classify" else "per-image F1", "images": len(rows), "mean": 0,
            "conf": 0.25 if task == "detect" else 0.0, "conf_floor": 0.0, "iou": 0.5, "names": names, "rows": rows,
            "source": str(path)}


def _name_to_idx(name, names: dict[str, str]) -> int:
    """이름으로 준 클래스를 번호로. 처음 보는 이름이면 새 번호를 붙인다"""
    for k, v in names.items():
        if v == str(name):
            return int(k)
    k = max((int(x) for x in names), default=-1) + 1
    names[str(k)] = str(name)
    return k
