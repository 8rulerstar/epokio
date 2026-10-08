"""`epokio alerts`: 폰 알림(웹후크)을 맥 앱 없이 터미널에서 더하고·빼고·보고·시험한다.

agent와 같은 파일(~/.epokio/webhooks.json, Agent.HOOKS_FILE)을 쓴다. 도우미가 안 돌아도 된다.
★예전엔 맥 앱이나 웹 화면에서만 켤 수 있어, SSH로만 들어가는 학습 서버에서는 켤 방법이 없었다
"""
from __future__ import annotations

import argparse

from . import i18n, jsonfile, notify


def hooks_file():
    from .agent import Agent
    return Agent.HOOKS_FILE                         # 시험은 conftest가 바꿔 둔다


def _label() -> str:
    """기계 이름: setup --label로 저장한 것, 없으면 컴퓨터 이름(agent와 같은 규칙)"""
    import socket
    from .onboard import label_file
    try:
        return label_file().read_text(encoding="utf-8").strip() or socket.gethostname()
    except OSError:
        return socket.gethostname()


def _show(url: str) -> str:
    """화면에는 호스트와 가린 경로만. ★경로 앞 12자를 보여 짧은 ntfy 주제·텔레그램 봇 토큰 앞부분이 터미널 기록에 남았다"""
    return notify.masked_url(url)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="epokio alerts", description=(
        "Phone alerts (ntfy, Slack, Discord, Telegram webhooks) sent by this machine when training "
        "finishes, fails or stalls. Writes the same settings the app and web page use; no helper needs to run."))
    ap.add_argument("--add", metavar="URL", action="append", default=[], help="add a webhook address (must start with https://)")
    ap.add_argument("--remove", metavar="URL", action="append", default=[], help="remove a webhook address")
    ap.add_argument("--list", action="store_true", help="show the saved webhooks")
    ap.add_argument("--test", action="store_true", help="send one test message to every saved webhook now")
    ap.add_argument("--lang", metavar="CODE", help="language of the alert text, e.g. en, ko, ja, de (saved)")
    a = ap.parse_args(argv)
    if not (a.add or a.remove or a.list or a.test or a.lang):
        a.list = True                                 # 아무것도 안 주면 목록만 보여 준다
    bad = [u for u in a.add if not notify.valid(u)]
    if bad:
        print(f"Not saved: every webhook must start with https:// ({', '.join(_show(u) for u in bad)})")
        return 2
    f = hooks_file()
    try:
        cfg = jsonfile.read(f, {})
    except jsonfile.BrokenFile as e:                  # ★깨진 파일을 빈 것으로 보고 덮어쓰면 웹후크가 다 지워진다
        print(f"{e}. Add your webhook addresses again.")
        return 1
    if not isinstance(cfg, dict):
        cfg = {}
    urls = [u for u in cfg.get("urls", []) if isinstance(u, str)]
    if a.add or a.remove or a.lang:
        gone = [u for u in a.remove if u not in urls]
        urls = [u for u in dict.fromkeys(urls + a.add) if u not in a.remove]
        from .watcher import DEFAULT_HOOK_KINDS
        cfg = {"urls": urls, "kinds": cfg.get("kinds") or DEFAULT_HOOK_KINDS,
               "lang": a.lang or cfg.get("lang") or i18n.system_language() or "en"}
        f.parent.mkdir(parents=True, exist_ok=True)
        jsonfile.write(f, cfg)
        for u in gone:
            print(f"Not in the list: {_show(u)}")
        print(f"Saved. Webhooks: {len(urls)}.")
    if a.list:
        if not urls:
            print("No phone alerts set. Add one:  epokio alerts --add https://ntfy.sh/your-long-random-topic")
        for u in urls:
            print(f"  {_show(u)}")
    if a.test:
        if not urls:
            print("Nothing to test. Add a webhook first with --add.")
            return 1
        i18n.use(cfg.get("lang"))
        machine, fails = _label(), 0
        for u in urls:
            r = notify.send_test(u, machine)
            fails += not r["ok"]
            print(f"  {'ok  ' if r['ok'] else 'FAIL'} {_show(u)}  {r.get('status', '')} {r.get('error', '')}".rstrip())
        return 1 if fails else 0
    return 0
