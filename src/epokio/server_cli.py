"""agent를 켜는 명령(epokio-agent). 인자 읽기, 토큰 관리 명령, 포트 잡기, 폴더 찾기. HTTP 처리는 server.py"""
from __future__ import annotations

import argparse
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import auth, config, tokens
from .server import log, make_handler, setup_log


def main():
    from .agent import Agent
    # 도움말은 영어로(★한국어 도움말이 영어 콘솔에서 깨져 보였고, --port에는 설명이 없었다)
    ap = argparse.ArgumentParser(prog="epokio-agent", description="The helper the Mac app, web page and terminal read from.")
    ap.add_argument("--root", action="append", default=None, help="a folder holding training runs (repeatable)")
    ap.add_argument("--port", type=int, default=None,
                    help="default 8787; if busy, the next free port within +20. Given explicitly, it stops instead of moving")
    ap.add_argument("--host", default="127.0.0.1",
                    help="default: this machine only. 0.0.0.0 lets other machines on your network connect")
    ap.add_argument("--require-token", action="store_true",
                    help="ask for a token for viewing (GET) on this machine too. Recommended on shared servers")
    ap.add_argument("--open-reads", action="store_true",
                    help="let other machines view (GET) without a token. Only on a network you trust")
    ap.add_argument("--label", default=None, help="name this machine shows as (default: saved by `epokio setup --label`, else the computer name)")
    ap.add_argument("--show-token", action="store_true", help="print the token other machines need, then exit")
    ap.add_argument("--add-token", metavar="NAME",
                    help="issue a named token and show it once (--scope read|run, default run)")
    ap.add_argument("--scope", default=tokens.RUN, choices=list(tokens.SCOPES),
                    help="scope of the new token. read = view only, run = start and stop training too")
    ap.add_argument("--list-tokens", action="store_true", help="list issued tokens (their values cannot be shown again)")
    ap.add_argument("--revoke-token", metavar="ID_OR_NAME", help="revoke one token")
    ap.add_argument("--parent-pid", type=int, default=None,
                    help="exit when this PID (the app that started us) exits. Only the Mac app passes it")
    ap.add_argument("--stop", action="store_true", help="stop the helper running on --port, then exit")
    a = ap.parse_args()

    if a.show_token:
        print(auth.token())
        return
    if a.add_token:
        tok, entry = tokens.issue(a.add_token, a.scope)
        print(tok)              # ★여기서만 보인다. 파일에는 지문만 남는다
        print(f"  name: {entry['name']}   scope: {entry['scope']}   id: {entry['id']}", file=sys.stderr)
        return
    if a.list_tokens:
        print(f"{'id':10} {'scope':6} name")
        for e in tokens.listed():
            print(f"{e['id']:10} {e['scope']:6} {e['name']}")
        print(f"(plus the single token in {auth.TOKEN_FILE}, scope run)")
        return
    if a.revoke_token:
        print("revoked" if tokens.revoke(a.revoke_token) else "no such token")
        return
    if a.stop:                                # ★창 없이 도는 도우미를 끌 방법이 없었다(윈도우)
        from . import port as portmod
        from .onboard import agent_alive, stop_agent
        rec = portmod.read_record() or {}
        p = a.port or rec.get("port") or portmod.DEFAULT_PORT
        if not agent_alive(p):
            print(f"No helper is running on port {p}.")
        else:
            print("Stopped." if stop_agent(p) else "It did not stop. End it from the tray (Quit) or the task manager.")
        return

    from .onboard import label_file
    try:
        saved_label = label_file().read_text(encoding="utf-8").strip()
    except OSError:
        saved_label = ""
    label = a.label or saved_label or socket.gethostname()
    roots = [Path(r).expanduser().resolve() for r in (a.root or [])]
    saved = Agent.ROOTS_FILE
    from . import jsonfile
    try:                                     # 지난번에 사용자가 더한 폴더
        roots += [Path(r) for r in jsonfile.read(saved, []) if Path(r) not in roots]
    except (OSError, ValueError, TypeError) as e:
        # ★잠겨 있으면(OSError) 시작이 통째로 죽었다. 깨졌으면 옆에 남기고 없는 것처럼 시작한다
        print(f"! Could not read {saved.name} ({e}). Starting without the folders you added before.")
    # 포트부터 잡는다. ★같은 포트로 두 번 켜면 대기열 일꾼이 먼저 돌기 시작한 뒤에야 포트 오류로 죽었다
    srv, actual = bind_first(a.host, a.port)
    agent = Agent(roots, label)
    if not a.root:
        # 서버를 먼저 열고 탐색은 뒤에서. ★탐색을 기다리게 하면 앱이 '꺼져 있다'고 본다.
        # 5분마다 다시 찾는다. ★한 번만 찾아서, 켠 뒤에 처음 생긴 runs 폴더는 영영 안 보였다(setup은 "생기면 잡는다"고 했다).
        # 사용자가 뺀 폴더는 다시 넣지 않고, 찾은 폴더는 roots.json에 남기지 않는다
        import threading
        import time
        from .discover import find_roots

        def discover():
            while True:
                try:
                    for p in find_roots():
                        # 이미 보는 폴더 안의 것은 더하지 않는다(★~/proj를 더했는데 ~/proj/runs도 더해 학습이 두 번 보였다)
                        inside = any(r == p or r in p.parents for r in agent.roots)
                        if not inside and p not in agent.removed:
                            agent.discovered.add(p)
                            agent.roots.append(p)
                except Exception:
                    log.exception("finding training folders failed")
                time.sleep(300)
        threading.Thread(target=discover, daemon=True).start()

    if a.parent_pid:
        from . import parentwatch
        parentwatch.watch(a.parent_pid)
    auth.token()        # 처음이면 만든다
    exposed = not auth.is_loopback(a.host)
    mode = config.load().get("reads_token", "auto")          # auto·always·never (설정 → 일반, 공용 서버는 always)
    reads = a.require_token or mode == "always" or (mode != "never" and exposed and not a.open_reads)
    jsonfile.private_dir(Path.home() / ".epokio")      # 웹후크 비밀 주소·메모가 든 폴더는 나만(★먼저 생긴 폴더가 0755로 남았다)
    if exposed:
        # ★⚠ 는 cp949 콘솔을 파일로 받으면 UnicodeEncodeError라 !로 쓴다
        print("! Other machines on this network can reach this agent. Traffic is plain HTTP (not encrypted).")
        print("  Viewing needs the token too." if reads else "  ! --open-reads: anyone on this network can see run names, scores and images.")
        print("  Token for Epokio on your Mac:  epokio-agent --show-token")
        print("  Safer: keep the default 127.0.0.1 and use SSH (Epokio > Settings > Machines > Over SSH), an SSH tunnel or Tailscale.")
    from . import __version__
    logf = setup_log()
    log.info("start %s · %s · %s:%s · roots %s", __version__, label, a.host, actual, [str(r) for r in roots])
    print(f"epokio agent {__version__} · {label} · http://{a.host}:{actual}  (log: {logf})", flush=True)
    if getattr(agent.queue, "locked_out", False):
        print("! Another Epokio helper on this machine runs the queue, so this one only watches.", flush=True)
        log.warning("queue locked by another helper")
    srv.RequestHandlerClass = make_handler(agent, reads_need_token=reads)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def bind_first(host: str, want: int | None):
    """포트를 정해 열고(핸들러는 나중에 끼운다), 실제 포트를 ~/.epokio/agent.json 에 남긴다(끝나면 지운다).
    ★포트부터 잡는다: 같은 포트로 두 번 켜면 대기열 일꾼이 먼저 돌기 시작한 뒤에야 포트 오류로 죽었다"""
    import atexit
    import signal
    from . import port
    rec = port.read_record()
    if want is None and rec and port.probe(port.url_for(rec["port"])) == "epokio":
        raise SystemExit(f"An Epokio agent is already running at {port.url_for(rec['port'])}")
    try:
        srv, actual = port.bind(lambda h, p: ThreadingHTTPServer((h, p), BaseHTTPRequestHandler), host, want)
    except OSError as e:
        print(f"! Port {want or port.DEFAULT_PORT} is in use ({e}). Is another Epokio helper running? `epokio doctor` shows it.", flush=True)
        raise SystemExit(1)
    if actual != (want or port.DEFAULT_PORT):
        print(f"Port {port.DEFAULT_PORT} is busy, using {actual} instead.")
    port.write_record(actual, host)
    atexit.register(port.clear_record)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))    # terminate()로 끝나도 기록을 지운다
    return srv, actual
