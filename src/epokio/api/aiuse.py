"""AI 사용량 창구. 본체는 aiuse.py.

  GET  /ai            지금 값·출처·알아보는 도구 목록 (보기)
  POST /ai/report     {"activity": 0~100, "by": "claude-code"}  도구가 스스로 알린다 (토큰 필수)
  POST /ai/tools      {"tools": ["ollama", ...]}  알아볼 도구 목록 바꾸기 (토큰 필수)

POST는 server.py가 토큰을 먼저 확인한다(보기는 통과, 실행은 Bearer). 여기서는 값만 의심한다.
"""
from __future__ import annotations

from .. import aiuse
from . import NOT_MINE


def get(agent, route: str, q: dict):
    if route == "/ai":
        s = agent.sampler.latest
        return {**aiuse.status(), "now": s.ai if s else None, "source": s.ai_from if s else "none"}
    return NOT_MINE


def post(agent, route: str, body: dict):
    if route == "/ai/report":
        try:
            v = aiuse.report(body.get("activity"), by=body.get("by") or "")
        except aiuse.TooOften as e:
            return 429, {"error": str(e)}
        except (ValueError, TypeError) as e:
            return 400, {"error": str(e)}
        agent.sampler.touch()                     # 다음 샘플을 바로 뜨게: 캐릭터가 곧장 반응한다
        return 200, {"ok": True, "activity": v, "fresh_sec": aiuse.FRESH_SEC}
    if route == "/ai/tools":
        got = body.get("tools")
        if not isinstance(got, list):
            return 400, {"error": "tools must be a list of names"}
        return 200, {"ok": True, "tools": aiuse.save_tools(got)}
    return NOT_MINE
