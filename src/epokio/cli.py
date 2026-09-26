"""`epokio` 명령 하나로 모은다: setup · watch · agent · tray · autostart · mcp"""
from __future__ import annotations

import sys

HELP = """usage: epokio <command> [options]

  setup      set this machine up: find training folders, start the helper, open the page
  autostart  start the tray when you log in (Windows, Linux)
  watch      watch training runs in the terminal (good over SSH)
  agent      run the helper that the app, web page and terminal read from
  tray       training progress in the system tray (Windows, Linux)
  mcp        run the MCP server for AI assistants
  doctor     print what Epokio sees (versions, helper, folders, log) for a bug report

Run `epokio <command> -h` for options, `epokio --version` for the version."""


def main():
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
    elif cmd == "doctor":
        from .onboard import doctor as run
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
        try:
            from .mcp_server import main as run
        except ImportError:                       # ★예전엔 ModuleNotFoundError 트레이스백이 그대로 나왔다
            print("The MCP server needs the mcp package:  pip install \"epokio[mcp]\"")
            sys.exit(1)
        return run()
    else:
        print(HELP)
        sys.exit(2)
    run(rest)


if __name__ == "__main__":
    main()
