"""`epokio doctor`: 문제 보고용 한눈 보기. onboard.py가 400줄을 넘어 떼어 냈다(onboard.doctor로도 부를 수 있다)."""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

from . import autostart, onboard   # agent_health 등은 onboard.<이름>으로 부른다(시험이 onboard 쪽을 바꿔 끼운다)


def doctor(argv: list[str] | None = None) -> int:
    """문제 보고용 한눈 보기(`epokio doctor`). 토큰은 싣지 않는다. --json 이면 JSON으로"""
    import json
    import platform
    from . import envs, version
    from .agent import Agent
    ap = argparse.ArgumentParser(prog="epokio doctor", description="Print what Epokio sees, for a bug report.")
    ap.add_argument("--port", type=int, default=None, help=f"the helper's port (default: the running one, else {onboard.PORT})")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    a = ap.parse_args(argv)
    if a.port is None:
        # ★8787로 고정해, 다른 포트로 뜬 도우미를 '안 돈다'고 오진했다(epokio watch는 agent.json을 읽어 잘 찾았다)
        from .port import read_record
        rec = read_record()
        a.port = rec["port"] if rec and onboard.agent_alive(rec["port"]) else onboard.PORT
    h = onboard.agent_health(a.port)
    roots = []
    try:
        from . import jsonfile
        roots = [str(r) for r in jsonfile.read(Agent.ROOTS_FILE, [])]
    except (OSError, ValueError):
        pass
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
        "token_file": (Path.home() / ".epokio" / "token").exists(),
        "allowed_hosts": os.environ.get("EPOKIO_ALLOWED_HOSTS", ""),
        "autostart": autostart.enabled() if autostart.supported() else None,
        "pythons": [{"path": e["path"], "ready": e["ready"]} for e in envs.list_envs()],
        "log_tail": tail,
    }
    # 한국어 윈도우 콘솔(cp949)에서 못 찍는 글자가 있어도 죽지 않게
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    if a.json:
        print(json.dumps(info, ensure_ascii=False, indent=1))
        return 0
    print(f"Epokio {info['epokio']} | Python {info['python']} | {info['os']}")
    print(f"  installed at {info['install']}")
    hp = info["helper"]
    if hp["running"]:
        warn = "" if hp["epokio"] == info["epokio"] else f"   ! different from this install; run `epokio setup` to restart it"
        print(f"  helper: running on port {hp['port']} | {hp['epokio']} | label {hp['label']}{warn}")
    else:
        print(f"  helper: NOT running on port {hp['port']}  (start it with `epokio setup`)")
    w = info["watching"] or {}
    if "runs" in w:
        print(f"  watching {w['runs']} runs in {len(w['roots'])} folders:")
        for r in w["roots"]:
            print(f"    {r}{'' if Path(r).exists() else '   ! missing'}")
    print(f"  saved folders: {', '.join(roots) or 'none'}")
    print(f"  token file: {'yes' if info['token_file'] else 'no'} | allowed hosts: {info['allowed_hosts'] or '-'}"
          f" | start at login: {info['autostart']}")
    print(f"  pythons for training: " + (", ".join(f"{p['path']}{'' if p['ready'] else ' (no ultralytics)'}"
                                                 for p in info["pythons"]) or "none found"))
    print(f"\n  last lines of {logf}:" if tail else f"\n  no log yet at {logf}")
    for line in tail:
        print("    " + line)
    return 0
