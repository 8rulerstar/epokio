"""보고서 요청(POST /report). 계산은 report.py

★범위가 기본으로 "감시 중인 폴더 전부"였다. 팝오버의 "Export report"가 인자 없이 부르므로
   여러 고객사 폴더의 학습이 한 장에 섞여 나갔다. 이제 범위를 반드시 정해야 한다:
   paths(학습 몇 개) · root(폴더 하나) · all=true(전부, 명시할 때만).
   아무것도 안 주면 감시 폴더가 하나뿐일 때만 그 폴더를 쓰고, 여럿이면 400으로 되묻는다.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from . import NOT_MINE, result_file as _result
from .. import report as report_mod
from .. import runmeta
from ..scan import scan, unique
from ..textnorm import resolve


def get(agent, route: str, q: dict):
    return NOT_MINE


def _nfc(p) -> str:
    return unicodedata.normalize("NFC", str(p))


def _roots(agent) -> list[Path]:
    seen, out = set(), []
    for r in agent.watch_roots():
        if _nfc(r) not in seen and r.exists():
            seen.add(_nfc(r))
            out.append(r)
    return out


def reviews_for(agent, runs) -> dict:
    """끝난 검수(evaluate 작업)를 그 학습에 붙인다. 모델이 <run>/weights/best.pt 에서 온 것만."""
    from .. import retrain
    want = {_nfc(r.path): str(r.path) for r in runs}
    got: dict[str, dict] = {}
    for j in getattr(getattr(agent, "queue", None), "jobs", []):
        if j.kind != "evaluate" or j.state != "done" or not j.output:
            continue
        w = Path(str(j.params.get("model", "")))
        run = w.parent.parent if w.parent.name == "weights" else None
        key = want.get(_nfc(run)) if run else None
        if not key or not _result(j, "eval"):
            continue
        try:
            s = retrain.review_summary(Path(j.output))
        except (OSError, ValueError):
            s = None
        if s:                                      # 같은 학습에 검수가 여럿이면 사람이 더 많이 본 것
            if key not in got or s["reviewed"] > got[key]["reviewed"]:
                got[key] = s
    return got


def post(agent, route: str, body: dict):
    if route != "/report":
        return NOT_MINE
    if body.get("folder"):
        folder = Path(resolve(str(body["folder"])))
    else:
        # 바탕화면이 없으면(리눅스 서버) ~/epokio-reports 에. ★'folder not found'로 웹에서 보고서를 못 만들었다
        folder = Path.home() / "Desktop"
        if not folder.is_dir():
            folder = Path.home() / "epokio-reports"
            folder.mkdir(parents=True, exist_ok=True)
    if not folder.is_dir():
        return 400, {"error": "folder not found"}

    roots = _roots(agent)
    if body.get("paths"):                          # 학습 몇 개만 (학습 상세의 "보고서 내보내기")
        # 보낸 쪽이 C:/x 로 적어도 찾아진다(runmeta.key: NFC·구분자·대소문자 맞춤)
        want = {runmeta.key(resolve(p)) for p in body["paths"]}
        runs = [r for root in roots for r in scan(root) if runmeta.key(r.path) in want]
    elif body.get("root"):                         # 폴더 하나 (고객사 하나)
        root = Path(resolve(str(body["root"])))
        if _nfc(root) not in {_nfc(x) for x in roots}:
            return 400, {"error": "root must be a folder this agent watches"}
        runs = scan(root)
    elif body.get("all"):                          # 전부는 명시할 때만
        runs = [r for root in roots for r in scan(root)]
    elif len(roots) == 1:
        runs = scan(roots[0])
    else:
        return 400, {"error": "choose what to report: pass paths, root, or all=true",
                     "roots": [str(r) for r in roots]}

    runs = unique(runs)                            # 겹친 감시 폴더에서 같은 학습이 두 번 나오지 않게
    if not runs:                                   # ★빈 보고서를 200으로 돌려주면 앱이 "Report ready"를 띄운다
        return 400, {"error": "no runs to report in that folder"}
    path = report_mod.save(runs, folder, reviews_for(agent, runs))
    return 200, {"path": str(path), "runs": len(runs)}
