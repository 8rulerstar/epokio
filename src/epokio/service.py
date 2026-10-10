"""도우미가 로그아웃·재부팅 뒤에도 살아 있게 한다. 관리자 권한(sudo) 없이.

알림은 도우미가 돌 때만 간다. SSH를 끊거나 서버를 다시 켜면 도우미가 죽고, 사용자는 알림이 안 온 걸 학습이
끝난 뒤에야 안다. 그래서 `epokio setup`이 이것을 기본으로 권하고(터미널이면 묻고), `epokio doctor`가 한 줄로 보인다.

  리눅스  systemd 사용자 서비스 ~/.config/systemd/user/epokio.service (systemctl이 있으면 데스크톱이어도)
          로그아웃 뒤에도 돌려면 linger. `loginctl enable-linger`는 보통 자기 계정이면 sudo 없이 된다(polkit)
  맥      launchd LaunchAgent ~/Library/LaunchAgents/<LABEL>.plist (로그인해 있는 동안, 재부팅 뒤엔 로그인하면)
  윈도우  시작프로그램 폴더의 바로 가기(autostart.py). 트레이가 있으면 트레이, 없으면 도우미를 바로

★시험은 진짜 systemctl·launchctl·loginctl을 부르면 안 된다(이 기계에 서비스를 깐다). 바깥 명령은 전부 _run 하나를
  지나고, tests/conftest.py가 그것을 막아 둔다
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from . import autostart
from .onboard_parts import systemd_unit, unit_file

LABEL = "io.github.8rulerstar.epokio.helper"     # 맥 앱 번들 ID(io.github.8rulerstar.epokio) 아래


def kind() -> str | None:
    """이 기계에서 쓸 방식: systemd · launchd · startup · None(리눅스인데 systemctl이 없음: 옛 트레이 .desktop)"""
    if sys.platform == "win32":
        return "startup"
    if sys.platform == "darwin":
        return "launchd"
    try:
        return "systemd" if sys.platform.startswith("linux") and shutil.which("systemctl") else None
    except Exception:                    # ★sys.platform만 바꾼 시험에서 shutil.which가 윈도우 분기로 죽었다(autostart._on_path)
        return None


def plist_file() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def path(k: str | None = None) -> Path | None:
    k = k or kind()
    return {"systemd": unit_file, "launchd": plist_file, "startup": autostart.entry}.get(k, lambda: None)()


def name(k: str | None = None) -> str:
    return {"systemd": "systemd user service", "launchd": "launchd LaunchAgent",
            "startup": "Startup folder shortcut"}.get(k or kind() or "", "not available here")


def launchd_plist(roots: list[Path], host: str, port: int, allow_run: bool = False) -> str:
    """맥 LaunchAgent. plistlib이 이스케이프하므로 공백·&·< 경로도 그대로 된다"""
    args = [sys.executable, "-m", "epokio", "agent", "--port", str(port), "--host", host]
    for r in roots:
        args += ["--root", str(r)]
    if allow_run:
        args.append("--allow-run")
    log = str(Path.home() / ".epokio" / "launchd.log")
    body = {"Label": LABEL, "ProgramArguments": args, "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},   # 죽으면 다시, `epokio agent --stop`(정상 종료)이면 그대로
            "WorkingDirectory": str(Path.home()), "ProcessType": "Background",
            "StandardOutPath": log, "StandardErrorPath": log}
    return plistlib.dumps(body).decode("utf-8")


def _run(cmd: list[str], timeout: float = 20) -> tuple[bool, str]:
    """바깥 명령 하나. (성공, 출력). 없거나 시간이 넘으면 (False, 이유). 시험은 conftest가 바꿔 끼운다"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)


def _user() -> str:
    return os.environ.get("USER") or os.environ.get("LOGNAME") or "$USER"


def linger() -> bool | None:
    """로그아웃 뒤에도 내 systemd 서비스가 도나. 모르면 None"""
    ok, out = _run(["loginctl", "show-user", _user(), "--property=Linger"])
    return (out.strip().endswith("=yes")) if ok else None


def status() -> dict:
    """doctor가 보는 것: 방식·설치됨·켜짐(enabled/loaded, 모르면 None)·linger(리눅스만)"""
    k = kind()
    p = path(k)
    st = {"kind": k, "name": name(k), "installed": bool(p and p.exists()), "path": str(p) if p else None,
          "enabled": None, "linger": None}
    if k == "startup":
        st["installed"] = autostart.enabled()
        st["enabled"] = st["installed"]
    elif k == "systemd" and st["installed"]:
        ok, out = _run(["systemctl", "--user", "is-enabled", "epokio"])
        st["enabled"] = out.strip() == "enabled" if ok or out else None
        st["linger"] = linger()
    elif k == "launchd" and st["installed"]:
        ok, _ = _run(["launchctl", "list", LABEL])
        st["enabled"] = ok
    return st


def summary(st: dict | None = None) -> str:
    """한 줄: 'installed (systemd user service, enabled, keeps running after logout)' 같은 것"""
    st = st or status()
    if st["kind"] is None:
        return "not available here (no systemd)"
    if not st["installed"]:
        return f"not installed  -> {autostart.cli('setup --autostart')}"
    bits = [st["name"]]
    if st["enabled"] is not None:
        bits.append("enabled" if st["enabled"] else "installed but not enabled")
    if st["kind"] == "systemd":
        bits.append({True: "keeps running after logout", False: "stops at logout (linger off)",
                     None: "linger unknown"}[st["linger"]])
    return "installed (" + ", ".join(bits) + ")"


def install(roots: list[Path], host: str, port: int, allow_run: bool = False, running: bool = False) -> bool:
    """방식대로 깔고 켠다. 지금 도우미가 돌게 됐으면(또는 이미 돌았으면) True. 못 하면 손으로 할 명령을 찍는다.
    running: 이 포트에 이미 도우미가 떠 있다(바로 이 서비스일 수도, setup이 방금 띄운 것일 수도)"""
    k = kind()
    if k == "startup":
        try:
            p = autostart.enable()
        except OSError as e:
            print(f"  Could not set start at login: {e}")
            return running
        what = "the tray" if autostart.launcher() == autostart.self_command("tray") else "the helper"
        print(f"  {what[0].upper() + what[1:]} will start when you log in ({p}).")
        print(f"    turn it off with:  {autostart.cli('autostart --off')}")
        return running
    if k == "systemd":
        return _install_systemd(roots, host, port, allow_run, running)
    if k == "launchd":
        return _install_launchd(roots, host, port, allow_run, running)
    return running


def _install_systemd(roots, host, port, allow_run, running) -> bool:
    unit = unit_file()
    existed = unit.exists()
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(systemd_unit(roots, host, port, allow_run), encoding="utf-8")
    print(f"  Wrote a systemd user service (no sudo needed): {autostart.short_home(str(unit))}")
    if running and not existed:
        # 방금 setup이 띄운 도우미가 포트를 쥐고 있다. 다음 로그인·재부팅부터 서비스가 띄운다(겹쳐 띄우면 서비스가 '실패')
        ok, out = _run(["systemctl", "--user", "daemon-reload"])
        ok = ok and _run(["systemctl", "--user", "enable", "epokio"])[0]
        step = "enabled; it takes over from the next login or reboot" if ok else ""
    else:
        ok = _run(["systemctl", "--user", "daemon-reload"])[0]
        ok = ok and _run(["systemctl", "--user", "enable", "epokio"])[0]
        ok = ok and _run(["systemctl", "--user", "restart" if existed else "start", "epokio"])[0]
        step = "enabled and started" if ok else ""
    if ok:
        print(f"  The service is {step}.")
    else:
        print("  Could not talk to systemd from here. Turn it on yourself:")
        print("    systemctl --user daemon-reload && systemctl --user enable --now epokio")
    if linger() is not True:
        # 로그아웃하면 사용자 서비스도 멎는다. linger는 자기 계정이면 보통 sudo 없이 켜진다
        if _run(["loginctl", "enable-linger", _user()])[0] and linger() is not False:
            print("  Turned on linger, so it keeps running after you log out and starts at boot.")
        else:
            print("  To keep it running after you log out (and start at boot), run:")
            print("    loginctl enable-linger $USER")
            print("  If that is refused, ask an admin to run:  sudo loginctl enable-linger " + _user())
    else:
        print("  Linger is on, so it keeps running after you log out.")
    return running or ok


def _install_launchd(roots, host, port, allow_run, running) -> bool:
    p = plist_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(launchd_plist(roots, host, port, allow_run), encoding="utf-8")
    print(f"  Wrote a launchd LaunchAgent (no sudo needed): {autostart.short_home(str(p))}")
    if running:
        print("  It starts the helper at your next login (one is running now).")
        return True
    domain = f"gui/{os.getuid()}" if hasattr(os, "getuid") else "gui"
    _run(["launchctl", "bootout", f"{domain}/{LABEL}"])            # 옛 것이 실려 있으면 내린다(없으면 실패해도 된다)
    ok = _run(["launchctl", "bootstrap", domain, str(p)])[0] or _run(["launchctl", "load", "-w", str(p)])[0]
    if ok:
        print("  Loaded. It runs while you are logged in to this Mac, and comes back after a reboot once you log in.")
    else:
        print(f"  Could not load it from here (an SSH session has no login window). Load it with:\n    launchctl load -w {p}")
    return ok


def remove() -> bool:
    """깐 것을 끄고 지운다. 있었으면 True"""
    k = kind()
    if k == "startup":
        return autostart.disable()
    p = path(k)
    if not p or not p.exists():
        return False
    if k == "systemd":
        _run(["systemctl", "--user", "disable", "--now", "epokio"])
        p.unlink()
        _run(["systemctl", "--user", "daemon-reload"])
    else:
        _run(["launchctl", "unload", "-w", str(p)])
        p.unlink()
    return True
