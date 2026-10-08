"""로그인할 때 트레이를 알아서 띄운다.

윈도우 사용자가 포기하는 자리가 여기다. 맥은 `.dmg`를 끌어다 놓으면 끝인데 윈도우는 켤 때마다
검은 창을 열고 `epokio-agent --host 0.0.0.0 --root ...`를 다시 쳐야 했다.
"초보자가 터미널을 열 일이 없어야 한다"는 원칙이 윈도우에서만 안 지켜지고 있었다.

무엇을 쓰나
  윈도우 : 시작프로그램 폴더의 바로 가기(.lnk). 레지스트리(Run 키)를 건드리지 않는다.
           사용자가 탐색기에서 직접 보고 지울 수 있는 자리여야 한다.
           만드는 건 PowerShell의 WScript.Shell, 파이썬에 COM 의존성을 더하지 않으려는 것이다.
  리눅스 : ~/.config/autostart 의 .desktop (XDG 표준)
  맥     : 하지 않는다. 맥은 앱이 알아서 하고, 로그인 항목은 시스템 설정에서 사용자가 정한다.

창이 뜨지 않게 pythonw.exe(윈도우)로 띄운다. python.exe로 띄우면 로그인할 때마다 검은 창이 남는다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path, PureWindowsPath

NAME = "Epokio"


def supported() -> bool:
    return sys.platform in ("win32", "linux")


def folder() -> Path:
    """자동 시작 항목이 놓이는 자리."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart"


def entry(where: Path | None = None) -> Path:
    where = where or folder()
    return where / (f"{NAME}.lnk" if sys.platform == "win32" else f"{NAME.lower()}.desktop")


def self_command(sub: str = "tray") -> list[str]:
    """이 프로그램을 다시 부르는 명령.

    ★exe(PyInstaller)로 굳으면 sys.executable 이 Epokio.exe 다. 거기에 `-m epokio.agent` 를
    붙이면 파이썬 인자로 안 먹고 그냥 흘러간다(2026-09-23에 빌드해서 실제로 밟았다).
    굳었을 때는 exe 자신을 부른다: Epokio.exe agent / Epokio.exe tray.

    안 굳었으면 창이 안 뜨는 pythonw 를 고른다. python.exe 로 띄우면 검은 창이 남는다.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, sub]
    exe = Path(sys.executable)
    if sys.platform == "win32":
        quiet = exe.with_name("pythonw.exe")
        if quiet.exists():
            exe = quiet
    return [str(exe), "-m", f"epokio.{sub}"]


def cli(rest: str = "") -> str:
    """사용자가 터미널에 그대로 쳐서 되는 명령. ★윈도우에선 Scripts 폴더가 PATH에 없어 `epokio`가
    '인식되지 않는 명령'이었고, exe 사용자에게는 epokio 명령 자체가 없었다"""
    if getattr(sys, "frozen", False):
        head = ".\\" + (PureWindowsPath(sys.executable).name or "Epokio.exe")   # PowerShell은 .\ 없이 현재 폴더 exe를 안 찾는다
    elif sys.platform == "win32":
        head = "py -m epokio"
    else:
        head = "epokio"
    return f"{head} {rest}".strip()


def pip_cmd(rest: str) -> str:
    """pip 설치 안내. 윈도우는 py 런처, 그 밖은 python3 -m pip"""
    return f"{'py' if sys.platform == 'win32' else 'python3'} -m pip install {rest}"


def child_env() -> dict:
    """자식 프로세스에 물려줄 환경.

    ★PyInstaller onefile 은 자기 자신을 임시 폴더에 풀고 그 경로를 `_MEIPASS2` 로 환경에 심는다.
    그 환경을 그대로 물려받은 자식은 **부모의** 임시 폴더를 자기 것으로 쓴다. 부모가 끝나면
    그 폴더가 지워지고, 자식은 번들된 파일을 잃는다.

    2026-09-23 실측: `Epokio.exe setup` 이 띄운 agent 가 /health(코드)는 200인데 /(번들된
    web/index.html)에서는 응답 없이 연결이 끊겼다. 자식은 자기 걸 새로 풀어야 한다.
    """
    env = dict(os.environ)
    for k in ("_MEIPASS2", "_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL"):
        env.pop(k, None)
    return env


def launcher() -> list[str]:
    """로그인할 때 띄울 명령."""
    return self_command("tray")


def enabled(where: Path | None = None) -> bool:
    return entry(where).exists()


_DESKTOP_RESERVED = set(' \t\n"\'\\><~|&;$*?#()`')


def _desktop_quote(arg: str) -> str:
    """Desktop Entry 규칙대로 따옴표를 친다. ★빈칸이 있는 venv 경로(/home/lab user/my venv/...)가 둘로 갈라져 안 떴다"""
    if not _DESKTOP_RESERVED & set(arg):
        return arg
    for c in ('\\', '"', '`', '$'):
        arg = arg.replace(c, '\\' + c)
    return f'"{arg}"'


def enable(where: Path | None = None) -> Path:
    """로그인할 때 트레이가 뜨게 한다. 이미 있으면 새 경로로 다시 쓴다(파이썬을 옮겼을 수 있다)."""
    if not supported():
        raise OSError("자동 시작은 윈도우·리눅스에서만 만든다")
    where = where or folder()
    where.mkdir(parents=True, exist_ok=True)
    path = entry(where)
    exe, *args = launcher()
    if sys.platform == "win32":
        _write_lnk(path, exe, args)
    else:
        path.write_text(
            "[Desktop Entry]\nType=Application\nName=Epokio\n"
            f"Exec={' '.join(_desktop_quote(x) for x in [exe, *args])}\n"
            "Comment=Watch training runs from the system tray\n"
            "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")
    return path


def disable(where: Path | None = None) -> bool:
    p = entry(where)
    if not p.exists():
        return False
    p.unlink()
    return True


def _write_lnk(path: Path, exe: str, args: list[str]) -> None:
    """PowerShell로 바로 가기를 만든다. 실패하면 .cmd 로 물러선다.

    WindowStyle 7(최소화)은 pythonw 가 실패해 python 으로 떨어졌을 때를 위한 보험이다.
    """
    ps = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:EPOKIO_LNK); "
        "$s.TargetPath = $env:EPOKIO_EXE; "
        "$s.Arguments = $env:EPOKIO_ARGS; "
        "$s.WorkingDirectory = $env:EPOKIO_CWD; "
        "$s.WindowStyle = 7; "
        "$s.Description = 'Epokio: watch training runs from the system tray'; "
        "$s.Save()"
    )
    env = {**os.environ,
           "EPOKIO_LNK": str(path), "EPOKIO_EXE": exe,
           "EPOKIO_ARGS": subprocess.list2cmdline(args), "EPOKIO_CWD": str(Path.home())}
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, errors="replace", timeout=30, env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))   # 트레이 메뉴에서 켤 때 창이 번쩍이지 않게
        if r.returncode == 0 and path.exists():
            return
    except (OSError, subprocess.SubprocessError):
        pass
    # PowerShell이 막힌 환경(실행 정책·보안 정책)에서도 무언가는 되게 한다.
    fallback = path.with_suffix(".cmd")
    fallback.write_text(f'@echo off\r\nstart "" {subprocess.list2cmdline([exe, *args])}\r\n',
                        encoding="utf-8")
