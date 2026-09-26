"""윈도우용 Epokio.exe 하나를 굽는다. 파이썬을 모르는 사람이 받아서 두 번 누르면 끝이어야 한다.

    python tools/build_windows.py            # dist/Epokio.exe
    python tools/build_windows.py --console  # 검은 창을 띄워 로그를 보며 디버깅

무엇이 들어가나
  트레이 + agent + 웹 화면. 즉 **보는 쪽 전부**. 외부 패키지는 pystray·Pillow 둘뿐이라 작다.
  ultralytics·torch는 넣지 않는다. 학습은 사용자의 파이썬이 별도 프로세스로 돌린다(`jobs.py`).
  그래서 이 exe 가 있어도 학습 환경은 그대로고, 이 exe 때문에 torch 가 깨질 일이 없다.

무엇이 안 되나
  이 exe 로는 `epokio watch`(터미널 뷰)를 쓰지 않는다. 창 없는 모드로 굽기 때문이다.
  터미널 뷰가 필요하면 `pip install epokio` 쪽을 쓴다.

맥은 여기서 굽지 않는다. `mac/build_app.sh --dmg` 가 따로 있다.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "build" / "_epokio_main.py"

# exe 를 두 번 눌렀을 때 하는 일. setup 과 같은 자리로 모은다.
LAUNCHER = '''"""Epokio.exe 가 시작하는 자리. 두 번 누르면 도우미가 뜨고 트레이가 붙는다."""
import multiprocessing
import sys


def _show_output_if_launched_from_a_terminal():
    """창 없는 exe 는 print 가 어디로도 안 간다. 터미널에서 불렀으면 그 터미널에 붙는다.

    두 번 눌러서 켰을 때는 붙을 콘솔이 없어서 그냥 조용히 지나간다(검은 창이 안 뜬다).
    이게 없으면 `Epokio.exe setup` 이 아무 말도 없이 끝나 사용자가 됐는지 안 됐는지 모른다.
    """
    if sys.platform != "win32":
        return
    import ctypes
    if not ctypes.windll.kernel32.AttachConsole(-1):      # -1 = 나를 띄운 콘솔
        return
    for name, stream, mode in (("stdout", 1, "w"), ("stderr", 2, "w")):
        try:
            setattr(sys, name, open("CONOUT$", mode, buffering=1, encoding="utf-8", errors="replace"))
        except OSError:
            pass


if __name__ == "__main__":
    multiprocessing.freeze_support()      # ★없으면 자식 프로세스가 exe 를 다시 실행해 무한 증식한다
    args = sys.argv[1:]
    if args:
        _show_output_if_launched_from_a_terminal()
    if args and args[0] == "agent":
        from epokio.agent import main
        sys.argv = ["epokio-agent"] + args[1:]
        sys.exit(main())
    if args and args[0] == "setup":
        from epokio.onboard import main
        sys.exit(main(args[1:]))
    if args and args[0] == "autostart":
        from epokio.onboard import autostart_main
        sys.exit(autostart_main(args[1:]))
    from epokio.tray import main            # 인자 없이 누르면 트레이(agent 는 알아서 띄운다)
    sys.exit(main(args[1:] if args and args[0] == "tray" else args))
'''


def main() -> int:
    # ★안내문이 한국어다. 영어 윈도우 콘솔(cp1252, GitHub 러너)에서는 print가 UnicodeEncodeError로 죽었다
    #   (exe는 다 구운 뒤였는데 실패로 끝났다). 어느 콘솔에서든 깨질지언정 죽지는 않게
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--console", action="store_true", help="검은 창을 띄운다(디버깅)")
    ap.add_argument("--clean", action="store_true", help="build/ dist/ 를 지우고 시작")
    a = ap.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller 가 필요하다:  pip install pyinstaller")
        return 1

    if a.clean:
        for d in ("build", "dist"):
            shutil.rmtree(ROOT / d, ignore_errors=True)

    ENTRY.parent.mkdir(parents=True, exist_ok=True)
    ENTRY.write_text(LAUNCHER, encoding="utf-8")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "Epokio",
        "--onefile",
        "--console" if a.console else "--noconsole",
        "--noconfirm",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build" / "pyi"),
        "--specpath", str(ROOT / "build"),
        # 웹 화면은 패키지 데이터라 직접 넣어 준다
        "--add-data", f"{ROOT / 'src' / 'epokio' / 'web'}{';' if sys.platform == 'win32' else ':'}epokio/web",
        "--paths", str(ROOT / "src"),
        # 안 쓰는 큰 것들을 빼서 용량을 줄인다
        *sum([["--exclude-module", m] for m in
              ("tkinter", "curses", "_curses", "unittest", "pydoc", "doctest",
               "numpy", "torch", "ultralytics", "matplotlib", "PIL.ImageQt")], []),
        str(ENTRY),
    ]
    print("$", " ".join(cmd), "\n")
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        return r.returncode

    exe = ROOT / "dist" / ("Epokio.exe" if sys.platform == "win32" else "Epokio")
    if not exe.exists():
        print("빌드는 끝났는데 결과물이 없다.")
        return 1
    print(f"\n  {exe}   {exe.stat().st_size / 2**20:.1f} MB")
    print("\n  두 번 누르면 트레이가 뜬다. 명령으로도 쓸 수 있다:")
    print("    Epokio.exe setup --autostart")
    print("    Epokio.exe agent --host 0.0.0.0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
