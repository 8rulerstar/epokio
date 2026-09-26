"""파이썬 쪽 사용자 문구(tr(...)) 검사: 언어별 누락·남는 키·자리 이름 불일치.

맥 앱의 .strings는 tools/l10n_keys.py가 본다. 여기는 src/epokio/**.py의 tr() 호출과
src/epokio/locales/*.json만 본다(두 검사가 서로의 파일을 건드리지 않게 나눠 두었다).

    python tools/py_msgs.py            보고만 하고 0으로 끝난다
    python tools/py_msgs.py --strict   빠진 것이나 불일치가 있으면 1로 끝난다

tr()에 변수를 넘기는 자리가 몇 군데 있다(예: tr(split), tr(KINDS[kind][0])).
값이 코드의 상수 표에서 오므로 _INDIRECT가 그 표들을 읽어 키로 세어 준다.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PKG = SRC / "epokio"
LOC = PKG / "locales"

FIELD = re.compile(r"\{(\w+)")
BASE = "en"          # 키의 정본. 나머지 언어는 이 파일과 맞춰 본다


def _indirect() -> dict[str, str]:
    """tr()에 상수 표의 값이 들어가는 자리. 표를 읽어 키 → 출처로 돌려준다."""
    sys.path.insert(0, str(SRC))
    out: dict[str, str] = {}
    from epokio import notify, report
    for k, v in notify.KINDS.items():
        out[v[0]] = f"notify.KINDS[{k!r}]"
    for name in ("STATE_EN", "HEAD_NAME"):
        for k, v in getattr(report, name).items():
            out[v] = f"report.{name}[{k!r}]"
    out[report.FOOTNOTE] = "report.FOOTNOTE"
    for s in ("train", "val", "test"):          # health.py: tr(split)
        out[s] = "health.py split"
    return out


def _literals() -> dict[str, set[str]]:
    """소스의 tr("...") 원문 → 쓰인 파일 이름."""
    out: dict[str, set[str]] = {}
    for f in sorted(PKG.rglob("*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if fn == "tr" and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                out.setdefault(node.args[0].value, set()).add(f.name)
    return out


def check() -> int:
    lit = _literals()
    ind = _indirect()
    used = dict.fromkeys(list(lit) + list(ind))          # 순서 유지
    en = json.loads((LOC / f"{BASE}.json").read_text(encoding="utf-8"))
    problems = 0

    for t in used:
        if t not in en:
            src = ", ".join(sorted(lit.get(t, []))) or ind.get(t, "")
            print(f"[{BASE}] 키 없음 ({src}): {t!r}")
            problems += 1
    for t in en:
        if t not in used:
            print(f"[{BASE}] 코드에서 안 쓰임: {t!r}")
            problems += 1
    for k, v in en.items():
        if k != v:
            print(f"[{BASE}] 키와 값이 다름: {k!r} -> {v!r}")
            problems += 1

    sys.path.insert(0, str(SRC))
    from epokio import msg
    for lang in msg.LANGS:
        if lang == BASE:
            continue
        tbl = json.loads((LOC / f"{lang}.json").read_text(encoding="utf-8"))
        missing = [k for k in en if k not in tbl]
        extra = [k for k in tbl if k not in en]
        for k in missing:
            print(f"[{lang}] 번역 없음: {k!r}")
        for k in extra:
            print(f"[{lang}] 원문에 없는 키: {k!r}")
        bad = [k for k, v in tbl.items()
               if k in en and set(FIELD.findall(k)) != set(FIELD.findall(v))]
        for k in bad:
            print(f"[{lang}] 자리 이름 불일치: {k!r} -> {tbl[k]!r}")
        n = len(missing) + len(extra) + len(bad)
        problems += n
        print(f"{lang:8} {len(tbl):3}/{len(en)} 번역" + (f"  문제 {n}" if n else "  ok"))
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true", help="문제가 있으면 1로 끝낸다")
    a = ap.parse_args()
    n = check()
    print(f"\n문제 {n}개")
    sys.exit(1 if (n and a.strict) else 0)


if __name__ == "__main__":
    main()
