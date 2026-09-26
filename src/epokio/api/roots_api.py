"""감시 폴더 더하기·빼기(POST /roots · /roots/remove)"""
from __future__ import annotations

from pathlib import Path

from ..textnorm import resolve
from . import NOT_MINE


def too_broad(path: Path) -> bool:
    """지켜보기엔 너무 넓은 폴더: 디스크 맨 위, 홈 자체와 그 위, 시스템 폴더"""
    home = Path.home().resolve()
    if path == home or path in home.parents or len(path.parts) <= 1:
        return True
    return str(path) in ("/System", "/Library", "/usr", "/Applications", "/Volumes", "/private", "/opt", "C:\\Windows")



def get(agent, route: str, q: dict):
    return NOT_MINE


def post(agent, route: str, body: dict):
    if route == "/roots":
        raw = str(body.get("path") or "").strip()
        if not raw:                                   # ★빈 경로는 "."(홈)이 되어 홈 전체를 훑었다
            return 400, {"error": "path required"}
        path = Path(resolve(raw)).expanduser().resolve()
        if not path.is_dir():
            return 400, {"error": "not a folder"}
        if too_broad(path):                           # ★"/"·홈 자체를 받으면 새로고침마다 디스크를 훑었다
            return 400, {"error": "that folder is too broad; choose the folder where runs are saved (usually 'runs')"}
        agent._runs_cache = None
        if path in getattr(agent, "removed", set()):
            agent.removed.discard(path)
            agent._save_removed()
        getattr(agent, "discovered", set()).discard(path)       # 사용자가 직접 더했으니 이제 기억한다
        if path not in agent.roots:
            agent.roots.append(path)
        agent._save_roots()
        return 200, {"roots": [str(r) for r in agent.roots]}
    if route == "/roots/remove":
        raw = str(body.get("path") or "").strip()
        if not raw:
            return 400, {"error": "path required"}
        # ★추가할 때 resolve()로 실제 경로(/tmp → /private/tmp)를 저장하므로 뺄 때도 똑같이 바꿔 비교한다
        want = {raw, str(Path(resolve(raw)).expanduser().resolve())}
        agent._runs_cache = None
        gone = [r for r in agent.roots if str(r) in want]
        agent.roots[:] = [r for r in agent.roots if str(r) not in want]
        if hasattr(agent, "removed"):
            agent.removed.update(gone)           # ★5분 뒤 자동 찾기가 뺀 폴더를 되살렸다(알림까지)
            agent._save_removed()
        agent._save_roots()
        return 200, {"roots": [str(r) for r in agent.roots]}
    return NOT_MINE
