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
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import auth, autostart
from .discover import find_roots, remember_roots, saved_roots

PORT = 8787


def headless() -> bool:
    """화면이 없는 기계인가(SSH로 들어온 서버, 데스크톱 없는 리눅스).
    ★SSH_CONNECTION만 봐서 sudo·로컬 콘솔의 서버에서는 브라우저(w3m 등)를 띄우려 했다"""
    if os.name == "nt":
        return False
    if sys.platform == "darwin":
        return bool(os.environ.get("SSH_CONNECTION"))
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def systemd_unit(roots: list[Path], host: str, port: int) -> str:
    """화면 없는 리눅스 서버에서 로그인·재부팅 뒤에도 도우미가 돌게 하는 systemd 사용자 서비스"""
    # systemd는 % 를 지정자로, $ 를 변수로, \ 를 이스케이프로 읽고, 따옴표 없는 공백에서 나눈다.
    # ★경로에 공백·%·$가 있으면(예: "my runs", venv가 "~/my venv") 서비스가 안 떴다. 전부 따옴표로 싸고 이스케이프한다
    def q(s) -> str:
        return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'
    args = " ".join([f"--port {port}", f"--host {host}"] + [f"--root {q(r)}" for r in roots])
    return ("[Unit]\nDescription=Epokio helper\nAfter=network-online.target\n\n"
            f"[Service]\nExecStart={q(sys.executable)} -m epokio agent {args}\nRestart=on-failure\n\n"
            "[Install]\nWantedBy=default.target\n")


def label_file() -> Path:
    """`epokio setup --label` 이 남기는 이 기계의 이름. 실행 시점에 홈을 본다(테스트가 홈을 바꾼다)"""
    return Path.home() / ".epokio" / "label"


def lan_ip() -> str | None:
    """이 기계가 같은 네트워크에서 불릴 주소. 인터넷에 나가지 않고 알아낸다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))          # 보내지는 않는다, 커널에 경로만 물어보는 것
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


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
    ok = True
    for r in roots:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/roots", data=json.dumps({"path": str(r)}).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {auth.token()}", "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=5).read()
        except (OSError, urllib.error.HTTPError):
            ok = False
    return ok


def stop_agent(port: int = PORT, seconds: float = 10) -> bool:
    """이 기계의 도우미를 끈다(토큰으로). 꺼졌으면 True"""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/shutdown", data=b"{}", method="POST",
                                 headers={"Authorization": f"Bearer {auth.token()}", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=3).read()
    except (OSError, urllib.error.HTTPError):
        pass
    end = time.time() + seconds
    while time.time() < end:
        if not agent_alive(port, timeout=0.5):
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
    return None if theirs == version() else theirs


def start_agent(roots: list[Path], host: str, port: int = PORT) -> subprocess.Popen | None:
    """창 없이 띄운다. 이미 떠 있으면 아무것도 하지 않는다."""
    if agent_alive(port):
        return None
    cmd = autostart.self_command("agent") + ["--port", str(port), "--host", host]
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
                    help="let other machines on your network watch this one (needed for the Mac app)")
    ap.add_argument("--autostart", action="store_true", help="also start the tray when you log in")
    ap.add_argument("--no-browser", action="store_true", help="do not open the page")
    ap.add_argument("--port", type=int, default=PORT, help=f"port for the helper (default {PORT})")
    ap.add_argument("--label", help="name this machine shows as, e.g. 'lab-07' (default: the computer name). "
                                    "Handy when many machines are watched at once")
    a = ap.parse_args(argv)

    print("Epokio setup\n")
    if a.label:
        # 파일로 남긴다. 트레이·로그인 때 다시 띄우는 agent도 이 이름을 쓴다(★실습실 노트북 20대가 전부 DESKTOP-XXXX로 보였다)
        label_file().parent.mkdir(parents=True, exist_ok=True)
        label_file().write_text(a.label.strip(), encoding="utf-8")
        print(f"  This machine shows as: {a.label.strip()}\n")

    # 1. 학습 폴더
    # 사용자가 준 폴더만 도우미에 --root로 넘긴다. 찾은 폴더는 보여 주기만 하고 도우미가 스스로 찾게 둔다.
    # ★찾은 폴더를 --root로 넘기면 도우미의 5분마다 다시 찾기가 꺼져, 나중에 생긴 runs 폴더가 영영 안 보였다
    #   (systemd 서비스에도 박혀 영구히). 뺀 폴더도 재시작 때마다 --root로 되살아났다
    roots = [Path(r).expanduser().resolve() for r in (a.root or [])]
    if roots:
        remember_roots(roots)
    shown = roots
    if not roots:
        print("  Looking for training folders...")
        saved = saved_roots(quiet=True)             # ★저장해 둔 폴더가 있는데도 'No training folders found'라고 했다
        shown = saved + [r for r in find_roots() if r not in saved]
    if shown:
        for r in shown[:6]:
            print(f"    found  {r}")
        if len(shown) > 6:
            print(f"    ... and {len(shown) - 6} more")
    else:
        print("    No training folders found yet. The helper looks again every 5 minutes (home, Desktop,")
        print("    Documents, Downloads, ~/runs). Runs somewhere else, like /data or /mnt? Pass --root <folder>.")

    # 2. agent
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    print()
    via_systemd = a.autostart and headless() and autostart.supported()
    old = outdated(a.port) if not via_systemd else None
    if old:
        # pip으로 올린 뒤 옛 도우미가 돌고 있다. ★'이미 돌고 있다'고만 해서 옛 판이 새 화면을 내주고 500이 났다
        from . import version
        print(f"  An older helper ({old}) is running. Restarting it as {version()}...")
        if not stop_agent(a.port):
            print(f"  It did not stop. Close it (tray: Quit) and run setup again.")
            return 1
    if agent_alive(a.port):
        print("  The helper is already running.")
        if roots and not via_systemd:
            if add_roots_live(a.port, roots):
                print("  Added the folder to it.")
            else:
                print("  It did not take the folder. Restart it:  epokio agent --stop  then  epokio setup")
    elif via_systemd:
        # ★여기서 띄우고 아래 systemd 서비스도 켜면 같은 포트에 둘이 떠서 서비스가 '실패'로 끝났다. systemd가 띄우게 둔다
        print("  The helper will be started by systemd (see below).")
    else:
        print("  Starting the helper...")
        start_agent(roots, host, a.port)
        if not wait_for_agent(a.port):
            print("\n  The helper did not answer. Run this to see why:")
            print(f"    epokio agent --port {a.port}")
            return 1
        print("  Started.")

    # 3. 로그인할 때 트레이
    if a.autostart:
        print()
        import importlib.util
        if not autostart.supported():
            print("  Start at login is for Windows and Linux only.")
        elif headless():
            # ★화면 없는 서버에 트레이 바로 가기(.desktop)를 만들고 "로그인 때 뜬다"고 했지만 영영 안 떴다
            unit = Path.home() / ".config" / "systemd" / "user" / "epokio.service"
            existed = unit.exists()
            unit.parent.mkdir(parents=True, exist_ok=True)
            unit.write_text(systemd_unit(roots, host, a.port), encoding="utf-8")
            print(f"  No desktop here, so instead of a tray this wrote a systemd service: {unit}")
            print("  Turn it on. The first line keeps it running after you log out and after reboots:")
            print("    sudo loginctl enable-linger $USER")
            print("    systemctl --user daemon-reload && systemctl --user enable --now epokio")
            if agent_alive(a.port) and existed:
                # ★도는 도우미가 바로 이 서비스인데 '먼저 끄라'고만 해서, --lan을 뺀 뒤에도 옛 도우미가 0.0.0.0에 계속 열려 있었다
                print("  The service is already running with the old settings. Apply the new ones now:")
                print("    systemctl --user daemon-reload && systemctl --user restart epokio")
            elif agent_alive(a.port):
                print(f"  A helper is already running on port {a.port}. Stop it first, or the service cannot start.")
        elif not getattr(sys, "frozen", False) and importlib.util.find_spec("pystray") is None:
            # ★트레이 패키지 없이 켜 두면 로그인 때 트레이가 조용히 꺼져, 재부팅 뒤 아무것도 안 돌았다
            print("  The tray needs one more package. Run:  python -m pip install \"epokio[tray]\"")
            print("  then run setup again with --autostart.")
        else:
            try:
                autostart.enable()
                print("  The tray will start when you log in.")
                print("    turn it off with:  epokio autostart --off")
            except OSError as e:
                print(f"  Could not set start at login: {e}")

    # 4. 어디서 보나
    url = f"http://127.0.0.1:{a.port}/"
    # ★브라우저엔 토큰 실은 주소를 열고 화면엔 맨 주소를 찍어, 그걸로 연 사람은 학습 탭이 잠겨 있었다.
    #   SSH 세션에는 싣지 않는다(터미널 기록에 남는다)
    print(f"\n  Open  {url if headless() else auth.page_url(url)}")
    if a.lan:
        ip = lan_ip()
        print(f"        http://{ip or '<this machine>'}:{a.port}/   from your phone or another computer")
        print("\n  To watch this machine from the Mac app, add it in Settings and paste this token:")
        print(f"    {auth.token()}")
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
        print(f"    ssh -L {a.port}:127.0.0.1:{a.port} <this server>")
        print(f"  then open http://127.0.0.1:{a.port}/  (or run `epokio watch` here)")
    elif not a.no_browser:
        import webbrowser
        webbrowser.open(auth.page_url(url))        # 학습·대기열 탭이 잠금 없이 열린다

    if headless():                                   # 화면 없는 서버엔 트레이가 없다
        print("\n  Next:  epokio watch    progress in this terminal")
    elif sys.platform == "darwin":                    # ★맥에서도 트레이를 권했다. 트레이는 윈도우·리눅스용이고 맥은 메뉴바 앱이다
        print("\n  Next:  the Mac app (menu bar), see the README")
        print("         epokio watch    progress in this terminal")
    else:
        print("\n  Next:  epokio tray     a tray icon with progress")
        print("         epokio watch    the same thing in a terminal")
    return 0


def doctor(argv: list[str] | None = None) -> int:
    from .doctor import doctor as run      # 400줄 상한으로 doctor.py에 떼어 냈다. 옛 이름도 되게
    return run(argv)


def autostart_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="epokio autostart",
                                 description="Start the Epokio tray when you log in.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--on", action="store_true", help="turn it on")
    g.add_argument("--off", action="store_true", help="turn it off")
    a = ap.parse_args(argv)

    if not autostart.supported():
        print("Start at login is for Windows and Linux only.")
        print("On a Mac the app handles this, and you can change it in System Settings, Login Items.")
        return 1
    if a.on and headless() and sys.platform.startswith("linux"):
        # ★화면 없는 서버에 트레이 바로 가기를 만들고 "로그인 때 뜬다"고 했지만 영영 안 떴다(setup은 이미 고쳤다)
        print("This machine has no desktop, so a tray cannot start here. Use a systemd service instead:")
        print("  epokio setup --autostart")
        return 1
    if a.on:
        p = autostart.enable()
        print(f"On. The tray will start when you log in.\n  {p}")
    elif a.off:
        print("Off." if autostart.disable() else "It was not on.")
    else:
        print(f"{'On' if autostart.enabled() else 'Off'}.  ({autostart.entry()})")
        print("  epokio autostart --on    /    --off")
    return 0
