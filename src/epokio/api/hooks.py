"""웹후크(폰 알림) 설정: GET /webhooks(호스트만) · POST /webhooks(저장) · POST /webhooks/test(시험 알림)"""
from __future__ import annotations

import threading
from urllib.parse import urlsplit

from .. import jsonfile, msg
from ..watcher import DEFAULT_HOOK_KINDS
from . import NOT_MINE

_HOOKS_LOCK = threading.Lock()


def get(agent, route: str, q: dict):
    if route == "/webhooks":
        try:                                             # ★깨진 파일이면 500이 났다. 보기만 하므로 옮기지 않는다
            cfg = jsonfile.read(agent.HOOKS_FILE, {"urls": []}, move_broken=False)
        except (OSError, ValueError):
            cfg = {"urls": []}
        if not isinstance(cfg, dict):
            cfg = {"urls": []}
        return {"count": len(cfg.get("urls", [])),
                # 주소 전체는 비밀이라 호스트만. ★split으로 잘라 https://user:pass@host 의 user:pass가 토큰 없이 보였다
                "hosts": [urlsplit(u).hostname or "" for u in cfg.get("urls", []) if "//" in u]}
    return NOT_MINE


def _test(agent, body: dict):
    """저장된 웹후크마다(또는 body의 url 하나에) 시험 알림을 바로 보내고 주소별 결과를 돌려준다"""
    from .. import i18n, notify
    if body.get("url") is not None:
        if not notify.valid(body["url"]):
            return 400, {"error": "every webhook must start with https://"}
        urls = [body["url"]]
    else:
        try:
            cfg = jsonfile.read(agent.HOOKS_FILE, {}, move_broken=False)
        except (OSError, ValueError):
            cfg = {}
        urls = [u for u in (cfg.get("urls", []) if isinstance(cfg, dict) else []) if notify.valid(u)]
        if not urls:
            return 400, {"error": "no webhooks saved"}
    i18n.use(msg.tag())                                  # 시험을 누른 화면의 언어로
    # 하나씩 기다려 보낸다(주소마다 5초 한도). ★보내고 잊는 실제 알림과 달리, 시험은 결과를 바로 보여 줘야 한다
    return 200, {"results": [notify.send_test(u, getattr(agent, "label", None)) for u in urls]}


def post(agent, route: str, body: dict):
    if route == "/webhooks/test":
        return _test(agent, body)
    if route == "/webhooks":
        urls = body.get("urls", [])
        if not isinstance(urls, list):                 # ★문자열을 주면 글자별로 걸러져 기존 웹후크가 지워졌다
            return 400, {"error": "urls must be a list"}
        ok = [u for u in urls if isinstance(u, str) and u.startswith("https://")]
        if len(ok) != len(urls):
            return 400, {"error": "every webhook must start with https://", "accepted": len(ok)}
        # 읽고 고치고 쓰는 사이에 다른 요청이 끼면 한쪽이 사라졌다(★브라우저 탭 둘에서 동시에 더하면 200번 중 200번).
        with _HOOKS_LOCK:
            try:
                old = jsonfile.read(agent.HOOKS_FILE, {})
            except jsonfile.BrokenFile as e:      # ★깨진 파일을 '빈 것'으로 보고 덮어써 다른 웹후크가 다 지워졌다
                return 409, {"error": str(e), "hint": "Paste all your webhook addresses again."}
            # add: 있던 주소에 더한다(웹 화면). ★웹에서 하나를 저장하면 슬랙 등 다른 웹후크가 조용히 지워졌다
            if body.get("add"):
                ok = list(dict.fromkeys(old.get("urls", []) + ok))
            # 종류를 안 보내면 저장된 것을 그대로(★맥에서 끈 '멎음' 알림 등이 기본값으로 되돌아갔다).
            # 폰 알림 문구는 설정한 앱의 언어로. ★예전엔 언어를 고르는 곳이 없어 17개 언어 표가 있는데도 늘 영어였다
            cfg = {"urls": ok, "kinds": body.get("kinds") or old.get("kinds") or DEFAULT_HOOK_KINDS, "lang": msg.tag()}
            jsonfile.write(agent.HOOKS_FILE, cfg)
        return 200, {"ok": True, "count": len(cfg["urls"])}
    return NOT_MINE
