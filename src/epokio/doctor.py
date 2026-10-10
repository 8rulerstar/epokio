"""`epokio doctor`: 문제 보고용 한눈 보기. onboard.py가 400줄을 넘어 떼어 냈다(onboard.doctor로도 부를 수 있다)."""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

from . import autostart, onboard, service   # agent_health 등은 onboard.<이름>으로 부른다(시험이 onboard 쪽을 바꿔 끼운다)


def doctor(argv: list[str] | None = None) -> int:
    """문제 보고용 한눈 보기(`epokio doctor`). 토큰은 싣지 않는다. --json 이면 JSON으로"""
    import json
    import platform
    from . import envs, jsonfile, version
    from .agent import Agent
    ap = argparse.ArgumentParser(prog="epokio doctor", description="Print what Epokio sees, for a bug report.")
    ap.add_argument("--port", type=int, default=None, help=f"the helper's port (default: the running one, else {onboard.PORT})")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    ap.add_argument("--test-alert", action="store_true",
                    help="also send a real test alert to every saved webhook, to confirm your phone gets it")
    a = ap.parse_args(argv)
    if a.port is None:
        # ★8787로 고정해, 다른 포트로 뜬 도우미를 '안 돈다'고 오진했다(epokio watch는 agent.json을 읽어 잘 찾았다)
        from .port import read_record
        rec = read_record()
        a.port = rec["port"] if rec and onboard.agent_alive(rec["port"]) else onboard.PORT
    h = onboard.agent_health(a.port)
    roots = []
    try:
        roots = [str(r) for r in jsonfile.read(Agent.ROOTS_FILE, [])]
    except (OSError, ValueError):
        pass
    # ★'알림이 안 와요' 보고에 웹후크가 저장돼 있는지가 안 보였다. 주소는 비밀이라 개수만
    from . import notify
    try:
        saved = jsonfile.read(Agent.HOOKS_FILE, {}, move_broken=False)
        urls = [u for u in saved.get("urls", []) if isinstance(u, str)] if isinstance(saved, dict) else []
        hooks = {"saved": len(urls), "usable": sum(map(notify.valid, urls))}
    except (OSError, ValueError):
        hooks = {"error": "webhooks.json could not be read"}
    runs_info = None
    if h:
        try:
            import json as _j
            with urllib.request.urlopen(f"http://127.0.0.1:{a.port}/runs?lite=1", timeout=5) as r:
                d = _j.loads(r.read())
            runs_info = {"runs": len(d.get("runs", [])), "roots": d.get("roots", [])}
        except (OSError, ValueError):
            runs_info = {"error": "could not read /runs"}
    logf = Path.home() / ".epokio" / "agent.log"
    try:
        tail = logf.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
    except OSError:
        tail = []
    info = {
        "epokio": version(), "python": sys.version.split()[0], "executable": sys.executable,
        "os": platform.platform(), "install": str(Path(__file__).parent),
        "helper": ({"running": True, "epokio": h.get("epokio", "older"), "api": h.get("api", h.get("version")),
                    "label": h.get("label"), "port": a.port} if h else {"running": False, "port": a.port}),
        "saved_folders": roots, "watching": runs_info,
        "webhooks": hooks,
        "token_file": (Path.home() / ".epokio" / "token").exists(),
        "allowed_hosts": os.environ.get("EPOKIO_ALLOWED_HOSTS", ""),
        "autostart": service.status(),
        "pythons": [{"path": e["path"], "ready": e["ready"]} for e in envs.list_envs()],
        "log_tail": tail,
    }
    # 한국어 윈도우 콘솔(cp949)에서 못 찍는 글자가 있어도 죽지 않게
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    # The output is meant to be pasted into a public issue: paths under the home folder become ~ (they hold the user name)
    def say(*parts):
        print(_private(" ".join(map(str, parts))))
    if a.json:
        print(json.dumps(_scrub(info), ensure_ascii=False, indent=1))
        return _test_alert() if a.test_alert else 0
    say(f"Epokio {info['epokio']} | Python {info['python']} | {info['os']}")
    say(status_line(info))
    say(f"  installed at {info['install']}")
    hp = info["helper"]
    if hp["running"]:
        warn = "" if hp["epokio"] == info["epokio"] else f"   ! different from this install; run `{autostart.cli('setup')}` to restart it"
        say(f"  helper: running on port {hp['port']} | {hp['epokio']} | label {hp['label']}{warn}")
    else:
        say(f"  helper: NOT running on port {hp['port']}  (start it with `{autostart.cli('setup')}`)")
    w = info["watching"] or {}
    if "runs" in w:
        say(f"  watching {w['runs']} runs in {len(w['roots'])} folders:")
        for r in w["roots"]:
            say(f"    {r}{'' if Path(r).exists() else '   ! missing'}")
    say(f"  saved folders: {', '.join(roots) or 'none'}")
    wh = info["webhooks"]
    say("  phone alerts: " + (wh["error"] if "error" in wh else f"{wh['saved']} webhooks saved"
                                + (f" ({wh['saved'] - wh['usable']} not usable)" if wh["usable"] < wh["saved"] else "")))
    say(f"  token file: {'yes' if info['token_file'] else 'no'} | allowed hosts: {info['allowed_hosts'] or '-'}")
    say(f"  pythons for training: " + (", ".join(f"{p['path']}{'' if p['ready'] else ' (no ultralytics)'}"
                                                 for p in info["pythons"]) or "none found"))
    say(f"\n  last lines of {logf}:" if tail else f"\n  no log yet at {logf}")
    for line in tail:
        # 옛 agent.log의 가운뎃점은 한국어 윈도우 콘솔·파이프에서 깨져 보였다(��). 출력 인코딩에 없는 글자는 ASCII로
        say("    " + _console_safe(line.replace("·", "|")))
    if a.test_alert:
        say()
        return _test_alert()
    if hooks.get("usable"):
        say(f"\n  To check that alerts reach your phone:  {autostart.cli('doctor --test-alert')}")
    return 0


def _private(text: str) -> str:
    """The home folder becomes ~ wherever it starts a path, also inside quotes (a report, not a command to paste back)"""
    import re
    home = os.path.expanduser("~").rstrip("\\/")
    if len(home) < 3:
        return text
    return re.sub(r"(?<![\w/\\.])" + re.escape(home) + r"(?=$|[\\/\s'\",\])])", "~", text, flags=re.I if os.name == "nt" else 0)


def _scrub(v):
    """JSON for a bug report: home paths become ~ in every string (user names stay off public issues)"""
    if isinstance(v, dict):
        return {k: _scrub(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_scrub(x) for x in v]
    return _private(v) if isinstance(v, str) else v


def status_line(info: dict) -> str:
    """한 줄: 도우미가 지금 도나 · 로그아웃·재부팅 뒤에도 도나(자동 시작) · 알림 주소가 있나.
    ★'알림이 안 와요'의 대부분이 이 셋 중 하나였는데, 예전 출력은 흩어져 있어 한눈에 안 보였다"""
    hp, wh = info["helper"], info["webhooks"]
    now = f"running now on port {hp['port']}" if hp["running"] else "NOT running"
    alerts = (wh["error"] if "error" in wh else
              f"{wh['usable']} webhook{'' if wh['usable'] == 1 else 's'}" if wh["usable"] else "none saved")
    line = f"  Helper: {now} | autostart: {service.summary(info['autostart'])} | phone alerts: {alerts}"
    todo = []
    if not hp["running"]:
        todo.append(f"start it: {autostart.cli('setup')}")
    if not wh.get("usable") and "error" not in wh:
        todo.append(f"add alerts: {autostart.cli('alerts --add https://ntfy.sh/<your-topic>')}")
    return line + ("\n  Next: " + " | ".join(todo) if todo else "")


def _test_alert() -> int:
    """저장한 모든 웹후크로 진짜 시험 알림을 보낸다(사용자가 --test-alert로 청했을 때만). 하나라도 실패하면 1"""
    from .alerts_cli import main as alerts
    print("Sending a test alert to every saved webhook:")
    return alerts(["--test"])


def _console_safe(text: str, enc: str | None = None) -> str:
    """Keep only what the console encoding can show; anything else becomes '?' instead of mojibake"""
    enc = enc or getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        return text.encode(enc, errors="replace").decode(enc, errors="replace")
    except LookupError:
        return text.encode("ascii", errors="replace").decode("ascii")
