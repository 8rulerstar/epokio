"""학습 레시피: 자주 쓰는 학습 설정에 이름을 붙여 둔다(단축어 모음처럼). ~/.epokio/recipes.json
앱·웹 어디서 만들어도 같은 목록이다. 값은 학습 설정 그대로(task·model·epochs·imgsz… 와 data는 선택)."""
from __future__ import annotations

import json
import time
from pathlib import Path

FILE = Path.home() / ".epokio" / "recipes.json"
ALLOWED = (str, int, float, bool)


def load() -> list[dict]:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(rs: list[dict]):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(rs, ensure_ascii=False, indent=1), encoding="utf-8")


def save(name: str, params: dict) -> list[dict]:
    name = str(name).strip()[:60]
    if not name or not isinstance(params, dict) or not params:
        raise ValueError("a recipe needs a name and settings")
    clean = {str(k)[:40]: v for k, v in params.items() if isinstance(v, ALLOWED)}
    rs = [r for r in load() if r["name"] != name] + [{"name": name, "params": clean, "saved": time.time()}]
    _save(rs[-50:])
    return rs


def delete(name: str) -> list[dict]:
    rs = [r for r in load() if r["name"] != name]
    _save(rs)
    return rs
