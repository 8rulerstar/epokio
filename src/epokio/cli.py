"""`epokio` 명령 하나로 모은다: setup · watch · agent · tray · autostart · mcp · alerts · doctor · config · score"""
from __future__ import annotations

import sys

HELP = """usage: epokio <command> [options]

  setup      set this machine up: find training folders, start the helper, open the page
  autostart  keep the helper running after logout and reboot (on, off, status)
  watch      watch training runs in the terminal (good over SSH)
  agent      run the helper that the app, web page and terminal read from
  tray       training progress in the system tray (Windows, Linux)
  mcp        run the MCP server for AI assistants
  alerts     phone alerts (webhooks): --add URL, --remove URL, --list, --test, --lang
  doctor     check the helper, start at login and alerts; --test-alert sends one (paste the output into a bug report)
  config     show or change settings, e.g. `config launch_runs on` to start training from the web page
  score      choose a run's (or a folder's) main score column: score <run> <column> [--lower], --auto, --list

Run `epokio <command> -h` for options, `epokio --version` for the version."""


def _main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(HELP)
        return
    if sys.argv[1] in ("-V", "--version"):          # ★예전엔 도움말을 찍고 종료 코드 2로 끝났다
        from . import version
        print(f"epokio {version()}")
        return
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "setup":
        from .onboard import main as run
        sys.exit(run(rest))
    elif cmd == "alerts":
        from .alerts_cli import main as run
        sys.exit(run(rest))
    elif cmd == "score":
        from .score_cli import main as run
        sys.exit(run(rest))
    elif cmd == "config":
        from .config_cli import main as run
        sys.exit(run(rest))
    elif cmd == "doctor":
        from .doctor import doctor as run
        sys.exit(run(rest))
    elif cmd == "autostart":
        from .onboard import autostart_main as run
        sys.exit(run(rest))
    elif cmd == "watch":
        from .tui import main as run
    elif cmd == "agent":
        from .agent import main as run
        sys.argv = ["epokio agent"] + rest
        return run()
    elif cmd == "tray":
        from .tray import main as run
    elif cmd == "mcp":
        return mcp_main()
    else:
        print(HELP)
        sys.exit(2)
    run(rest)


def mcp_main():
    """`epokio mcp`와 `epokio-mcp` 둘 다. ★epokio-mcp는 mcp가 없으면 트레이스백만 냈다. 안내는 stderr로(stdout은 MCP 통로)"""
    try:
        from .mcp_server import main as run
    except ImportError:
        print("The MCP server needs the mcp package:  pip install \"epokio[mcp]\"", file=sys.stderr)
        sys.exit(1)
    return run()


def main():
    """★~/.epokio가 읽기 전용이거나, 같은 이름의 파일이 있거나, 디스크가 차면 파이썬 트레이스백이 그대로 나왔다.
    무엇을 못 썼는지와 할 일을 한 줄로"""
    try:
        _main()
    except OSError as e:
        from .autostart import short_home
        where = short_home(str(e.filename)) if e.filename else ""
        print(f"epokio: could not use {where or 'a file'}: {e.strerror or e}. "
              "Check that the folder is writable and the disk is not full.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
