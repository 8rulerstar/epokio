"""`epokio setup`: 윈도우·리눅스 사용자가 치는 명령을 한 줄로 줄인다.

전에는 이랬다.
    pip install ...
    epokio-agent --host 0.0.0.0 --root D:\\어딘가\\runs      <- 경로를 알아야 하고, 플래그를 알아야 한다
    epokio-agent --show-token                               <- 이게 뭔지 알아야 한다
    (브라우저를 열고 주소를 친다)
    (컴퓨터를 껐다 켜면 처음부터 다시)

지금은 `epokio setup` 하나다. 폴더는 알아서 찾고, agent를 창 없이 띄우고, 브라우저를 열고,
원하면 로그인할 때 트레이가 뜨게 해 둔다.

★여기서 경로를 타이핑하게 하면 안 된다. discover.py 주석에 적힌 그대로, 거기서 대부분 포기한다.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import auth, autostart
from .autostart import cli
from .discover import find_roots, remember_roots, saved_roots  # noqa: F401  (onboard_parts가 onboard.<이름>으로 부른다)
from .onboard_parts import choose_port, found_roots, lan_ip, lock_reads, other_logins, owner, port_closed, systemd_unit, unit_file  # noqa: F401  (onboard.<이름>으로도 부른다)
from .port import agent_proof, may_send_token, url_for

PORT = 8787


def headless() -> bool:
    """화면이 없는 기계인가(SSH로 들어온 서버, 데스크톱 없는 리눅스).
    ★SSH_CONNECTION만 봐서 sudo·로컬 콘솔의 서버에서는 브라우저(w3m 등)를 띄우려 했다"""
    if os.name == "nt":
        return False
    if sys.platform == "darwin":
        return bool(os.environ.get("SSH_CONNECTION"))
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def sudo_warning() -> str:
    """sudo로 돌리면 홈이 root라 서비스·토큰·폴더가 전부 root 것이 된다(★`sudo epokio setup`은 root의 홈에 썼다)"""
    if os.name != "nt" and getattr(os, "geteuid", lambda: 1)() == 0 and os.environ.get("SUDO_USER"):
        return (f"  Running under sudo, so this sets Epokio up for root, not {os.environ['SUDO_USER']}. "
                "Run it again without sudo unless that is what you want.\n")
    return ""


def label_file() -> Path:
    """`epokio setup --label` 이 남기는 이 기계의 이름. 실행 시점에 홈을 본다(테스트가 홈을 바꾼다)"""
    return Path.home() / ".epokio" / "label"


def agent_alive(port: int = PORT, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return r.status == 200
    except (OSError, urllib.error.HTTPError):
        return False


def agent_health(port: int = PORT, timeout: float = 1.0) -> dict | None:
    """떠 있는 도우미의 /health(판·이름·boot). 없으면 None"""
    import json
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return json.loads(r.read())
    except (OSError, ValueError, urllib.error.HTTPError):
        return None


def add_roots_live(port: int, roots: list[Path]) -> bool:
    """떠 있는 도우미에 폴더를 더한다(POST /roots, 토큰). 다 받아들였으면 True.
    ★setup --root를 다시 돌리면 roots.json에만 적고 도는 도우미는 몰라, 껐다 켜기 전까지 목록이 비어 있었다
      (처음엔 폴더 없이 setup, 그다음 --root는 새 사용자가 가장 흔히 밟는 순서다). 재시작은 대기열 작업을 끊으니 요청으로 넘긴다"""
    import json
    if not may_send_token(port):                   # 토큰은 내 도우미임을 증명한 곳에만
        return False
    ok = True
    for r in roots:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/roots", data=json.dumps({"path": str(r)}).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {auth.token()}", "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=5).read()
        except (OSError, urllib.error.HTTPError):
            ok = False
    return ok


def stop_agent(port: int = PORT, seconds: float = 10, why: list | None = None) -> bool:
    """이 기계의 도우미를 끈다(토큰으로). 정말 꺼졌으면(포트가 닫혔으면) True. why를 주면 거절된 HTTP 코드를 담는다.
    ★토큰이 안 맞아(다른 HOME·옛 토큰) 401로 거절됐는데도, /health가 0.5초 안에 안 오면 '꺼졌다'고 해서
      `agent --stop`이 "Stopped."라고 했다. 거절이면 바로 False, 꺼졌는지는 /health가 아니라 포트로 본다"""
    if not may_send_token(port):                   # 토큰은 내 도우미임을 증명한 곳에만(남의 프로그램이면 거절로)
        if why is not None:
            why.append(403)
        return False
    req = urllib.request.Request(f"http://127.0.0.1:{port}/shutdown", data=b"{}", method="POST",
                                 headers={"Authorization": f"Bearer {auth.token()}", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=3).read()
    except urllib.error.HTTPError as e:
        if why is not None:
            why.append(e.code)
        return False
    except OSError:
        pass                                       # 끄는 도중 연결이 끊기는 것은 정상
    end = time.time() + seconds
    while time.time() < end:
        if port_closed(port):
            return True
        time.sleep(0.3)
    return False


def outdated(port: int = PORT) -> str | None:
    """떠 있는 도우미가 이 코드와 다른 판이면 그 판(옛 도우미는 'epokio'가 없어 'older'). 같거나 없으면 None"""
    from . import version
    h = agent_health(port)
    if h is None:
        return None
    theirs = h.get("epokio") or "older"
    if theirs != version():
        return theirs
    # 판 이름이 같아도 포트에 묶인 증명을 모르면 옛 도우미다(판을 안 올린 업데이트). ★'이미 돈다'로 두어 새 watch·MCP가 엉뚱한 안내를 했다
    return theirs + " (older security check)" if agent_proof(url_for(port)) == "old" else None


def start_agent(roots: list[Path], host: str, port: int = PORT, allow_run: bool = False) -> subprocess.Popen | None:
    """창 없이 띄운다. 이미 떠 있으면 아무것도 하지 않는다."""
    if agent_alive(port):
        return None
    cmd = autostart.self_command("agent") + ["--port", str(port), "--host", host] + (["--allow-run"] if allow_run else [])
    for r in roots:
        cmd += ["--root", str(r)]
    return subprocess.Popen(
        cmd, cwd=str(Path.home()), env=autostart.child_env(),
        # ★DETACHED_PROCESS 가 없으면 도우미가 부모 콘솔을 붙잡아 `epokio setup` 이 안 끝난다
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) or getattr(subprocess, "CREATE_NO_WINDOW", 0),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        # ★리눅스·맥에서 새 세션으로 떼지 않으면 SSH를 끊을 때 도우미도 같이 죽었다
        start_new_session=(os.name != "nt"), close_fds=True)


def wait_for_agent(port: int = PORT, seconds: float = 20) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if agent_alive(port, timeout=0.5):
            return True
        time.sleep(0.3)
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="epokio setup",
        description="Set Epokio up on this machine: find your training folders, "
                    "start the helper, and open the page.")
    ap.add_argument("--root", action="append", default=None,
                    help="a folder holding training runs (repeatable). Found automatically if omitted")
    ap.add_argument("--lan", action="store_true",
                    help="let other computers and phones on your network watch this one (the Mac app on this same Mac does not need it)")
    ap.add_argument("--allow-run", action="store_true",
                    help="with --lan: also run training and scripts sent from other machines (refused by default)")
    ap.add_argument("--autostart", action="store_true",
                    help="keep the helper running after logout and reboot, no sudo (systemd user service on Linux, "
                         "LaunchAgent on macOS, Startup folder on Windows)")
    ap.add_argument("--no-autostart", action="store_true", help="do not ask about --autostart")
    ap.add_argument("--no-lock-reads", action="store_true",
                    help="over SSH on Linux: do not ask for a token to view (other accounts on the server can read your runs)")
    ap.add_argument("--no-browser", action="store_true", help="do not open the page")
    ap.add_argument("--port", type=int, default=None, help=f"port for the helper (default {PORT}, or the next free one)")
    ap.add_argument("--label", help="name this machine shows as, e.g. 'lab-07' (default: the computer name). "
                                    "Handy when many machines are watched at once")
    a = ap.parse_args(argv)

    print("Epokio setup\n" + sudo_warning())
    if a.label:
        # 파일로 남긴다. 트레이·로그인 때 다시 띄우는 agent도 이 이름을 쓴다(★실습실 노트북 20대가 전부 DESKTOP-XXXX로 보였다)
        label_file().parent.mkdir(parents=True, exist_ok=True)
        label_file().write_text(a.label.strip(), encoding="utf-8")
        print(f"  This machine shows as: {a.label.strip()}\n")

    # 1. 학습 폴더
    # 사용자가 준 폴더만 도우미에 --root로 넘긴다. ★찾은 폴더를 --root로 넘기면 도우미의 5분마다 다시 찾기가 꺼져,
    #   나중에 생긴 runs 폴더가 영영 안 보였다(systemd 서비스에도 박혀 영구히). 뺀 폴더도 재시작 때마다 되살아났다.
    # 찾은 폴더는 roots.json(도우미가 뜰 때 읽는다)에 남기고, 도는 도우미에는 POST /roots로 준다. 찍은 목록 = 보는 목록.
    #   ★예전엔 찍기만 해서, 지금 폴더에서 찾은 프로젝트의 runs를 도우미(홈에서 뜬다)는 영영 안 봤다
    from .roots import is_glob
    roots = [p if is_glob(p := Path(r).expanduser()) else p.resolve() for r in (a.root or [])]   # 무늬('/data/*/runs')는 그대로
    shown = roots
    if not roots:
        print("  Looking for training folders...")
        shown = found_roots()                       # 저장해 둔 폴더 + 찾은 폴더(뺀 폴더는 빼고)
    if shown:
        remember_roots(shown)
        for r in shown[:6]:
            print(f"    found  {r}")
        if len(shown) > 6:
            print(f"    ... and {len(shown) - 6} more")
    else:
        print("    No training folders found yet. The helper looks again every 5 minutes (Desktop, Documents,")
        print("    Downloads, Projects, ~/runs). Runs somewhere else, like /data or /mnt? Pass --root <folder>.")

    # 2. agent
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    print()
    from . import service
    via_systemd = a.autostart and service.kind() in ("systemd", "launchd")    # the service starts the helper
    # 내 토큰을 증명한 도우미만 다시 쓴다. 남의 것(공용 서버)·다른 프로그램이면 다음 빈 포트에 내 것을 띄운다
    a.port, mine, note = choose_port(a.port or PORT, a.port is not None)
    if note:
        print(f"  {note}")
    if mine in ("theirs", "other"):
        return 1
    old = outdated(a.port) if mine in ("mine", "old") and not via_systemd else None
    if old:
        # pip으로 올린 뒤 옛 도우미가 돌고 있다. ★'이미 돌고 있다'고만 해서 옛 판이 새 화면을 내주고 500이 났다
        from . import version
        print(f"  An older helper ({old}) is running. Restarting it as {version()}...")
        if not stop_agent(a.port):
            print(f"  It did not stop. Close it (tray: Quit) and run setup again.")
            return 1
        mine = None
    if mine in ("mine", "old"):
        print("  The helper is already running.")
        if shown and not via_systemd:
            if add_roots_live(a.port, shown):
                print("  Added the folder to it." if roots else "  It watches the folders above.")
            else:
                print(f"  It did not take the folder. Restart it:  {cli('agent --stop')}  then  {cli('setup')}")
    elif via_systemd:
        # ★여기서 띄우고 아래 systemd 서비스도 켜면 같은 포트에 둘이 떠서 서비스가 '실패'로 끝났다. 서비스가 띄우게 둔다
        print("  The helper will be started as a service (see below).")
    else:
        print("  Starting the helper...")
        start_agent(roots, host, a.port, allow_run=a.allow_run)
        if not wait_for_agent(a.port):
            print("\n  The helper did not answer. Run this to see why:")
            print(f"    {cli('agent')} --port {a.port}")
            return 1
        print("  Started.")

    # 3. 로그아웃·재부팅 뒤에도 도우미가 돌게(service.py). ★알림은 도우미가 돌 때만 간다. SSH를 끊거나 다시 켜면 조용히 끊겼다
    if a.autostart:
        print()
        _autostart(roots, host, a.port, a.allow_run, via_systemd)
    elif not a.no_autostart and service.kind() and not service.status()["installed"]:
        print()
        if sys.stdin.isatty() and sys.stdout.isatty() and _yes("  Keep the helper running after logout and reboot? (no sudo needed) [Y/n] "):
            _autostart(roots, host, a.port, a.allow_run, False)
        else:
            print("  The helper stops at reboot" + (" and when you log out." if headless() else ".")
                  + " Alerts need it running. Keep it running (no sudo):")
            print(f"    {cli('setup --autostart')}")

    # 3b. 공용 서버: 다른 계정이 127.0.0.1로 내 학습을 읽지 못하게(onboard_parts.lock_reads). 화면 있는 기계·--lan(이미 토큰)은 그대로
    if headless() and sys.platform.startswith("linux") and not a.lan:
        lock_reads(a.no_lock_reads, sys.stdin.isatty() and sys.stdout.isatty())

    # 4. 어디서 보나
    url = f"http://127.0.0.1:{a.port}/"
    # ★브라우저엔 토큰 실은 주소를 열고 화면엔 맨 주소를 찍어, 그걸로 연 사람은 학습 탭이 잠겨 있었다.
    #   SSH 세션에는 싣지 않는다(터미널 기록에 남는다)
    # ★노트북·로그(터미널이 아닌 곳)로 받으면 토큰이 기록에 그대로 남았다. 그때는 맨 주소와 토큰 보는 명령만
    tty = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False
    print(f"\n  Open  {url if headless() or not tty else auth.page_url(url)}")
    if not tty:
        print(f"        (the token is not printed because this output is not a terminal; show it with  {cli('agent --show-token')})")
    if a.lan:
        ip = lan_ip()
        print(f"        http://{ip or '<this machine>'}:{a.port}/   from your phone or another computer")
        # 다른 기계에 주는 토큰은 보기 전용(read)으로 새로 만든다. ★이 기계의 실행 토큰(~/.epokio/token)을 그대로 찍어
        #   네트워크의 누구든 그 글자를 얻으면 학습·스크립트를 걸 수 있었다. 다시 돌리면 옛 것은 지우고 새로 준다
        from . import tokens
        tokens.revoke("setup-lan")
        view, _ = tokens.issue("setup-lan", tokens.READ)
        print("\n  To watch this machine from the Mac app or another computer, paste this view-only token:")
        print(f"    {view if tty else '(run ' + cli('agent --add-token NAME') + ' in a terminal)'}")
        print(f"  To start training from there too: {cli('agent --add-token NAME --scope run')} and run setup with --allow-run.")
        print("\n  Anyone on your network can reach the helper now. It has no TLS,")
        print("  so use this on a network you trust.")
        import shutil
        if sys.platform.startswith("linux") and (shutil.which("ufw") or shutil.which("firewall-cmd")):
            # ★방화벽이 켜진 서버에서는 위 주소가 그냥 시간 초과였다(안내는 README에만 있었다)
            print("\n  If that address does not open from another computer, allow the port in the firewall:")
            print(f"    sudo ufw allow {a.port}/tcp" if shutil.which("ufw")
                  else f"    sudo firewall-cmd --add-port={a.port}/tcp --permanent && sudo firewall-cmd --reload")

    if headless() and not a.no_browser:
        # ★SSH로 들어온 화면 없는 서버에서 브라우저를 열면 SSH 창 안에 글자 브라우저(w3m 등)가 떴다
        # --lan이면 위 주소로 열면 된다. 터널은 더 안전한 다른 길로만 알린다(★두 안내가 서로 어긋나 보였다)
        print("\n  This is an SSH session, so no browser was opened. "
              + ("Or, without opening the port to the network, run" if a.lan else "On your own computer run:"))
        # 내 컴퓨터 쪽은 다른 번호로. ★같은 8787이면 내 컴퓨터에도 Epokio가 떠 있을 때(맥 앱) 터널이 묶이지 못하고 내 컴퓨터 화면이 열렸다
        local = a.port + 10000 if a.port + 10000 <= 65535 else a.port
        print(f"    ssh -N -L {local}:127.0.0.1:{a.port} <this server>")
        print(f"  then open http://127.0.0.1:{local}/  (or run `epokio watch` here)")
    elif not a.no_browser:
        import webbrowser
        webbrowser.open(auth.page_url(url))        # 학습·대기열 탭이 잠금 없이 열린다

    if headless():                                   # 화면 없는 서버엔 트레이가 없다
        print(f"\n  Next:  {cli('watch')}    progress in this terminal")
    elif sys.platform == "darwin":                    # ★맥에서도 트레이를 권했다. 트레이는 윈도우·리눅스용이고 맥은 메뉴바 앱이다
        print("\n  Next:  the Mac app (menu bar), see the README")
        print(f"         {cli('watch')}    progress in this terminal")
    else:
        print(f"\n  Next:  {cli('tray')}     a tray icon with progress")
        print(f"         {cli('watch')}    the same thing in a terminal")
    return 0


def _yes(question: str) -> bool:
    try:
        return input(question).strip().lower() in ("", "y", "yes")
    except (EOFError, OSError):
        return False


def _autostart(roots: list[Path], host: str, port: int, allow_run: bool, via_service: bool) -> None:
    """--autostart: 서비스를 깔고 켠다. 못 켰는데 아무도 안 돌면 지금은 직접 띄운다(★systemd에 맡기고 아무것도 안 떠 있었다)"""
    from . import service
    if service.kind() is None:                      # systemctl 없는 리눅스: 옛 트레이 .desktop
        if not autostart.tray_ready():
            print("  This Linux has no systemd, and the tray needs one more package. Run:  " + autostart.pip_cmd('"epokio[tray]"'))
            print("  then run setup again with --autostart.")
            return
        try:
            autostart.enable()
            print("  The tray will start when you log in.")
            print(f"    turn it off with:  {cli('autostart --off')}")
        except OSError as e:
            print(f"  Could not set start at login: {e}")
        return
    up = service.install(roots, host, port, allow_run, running=agent_alive(port))
    if via_service and not up:
        start_agent(roots, host, port, allow_run=allow_run)
        print("  Started the helper for now." if wait_for_agent(port) else f"  The helper did not answer. Try:  {cli('agent')} --port {port}")


def doctor(argv: list[str] | None = None) -> int:
    from .doctor import doctor as run      # 400줄 상한으로 doctor.py에 떼어 냈다. 옛 이름도 되게
    return run(argv)


def autostart_main(argv: list[str] | None = None) -> int:
    from . import service
    ap = argparse.ArgumentParser(prog="epokio autostart",
                                 description="Keep the Epokio helper running after logout and reboot, without sudo.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--on", action="store_true", help="turn it on")
    g.add_argument("--off", action="store_true", help="turn it off")
    a = ap.parse_args(argv)
    if a.on:
        from .port import read_record
        rec = read_record()
        port = rec["port"] if rec and agent_alive(rec["port"]) else PORT
        _autostart([], "127.0.0.1", port, False, service.kind() in ("systemd", "launchd"))
        return 0
    if a.off:
        print("Off." if service.remove() else "It was not on.")
        return 0
    print(f"Start at login: {service.summary()}")
    print(f"  {cli('autostart --on')}    /    --off")
    return 0
