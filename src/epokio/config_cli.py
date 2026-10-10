"""`epokio config`: 설정(~/.epokio/config.json)을 터미널에서 보고 바꾼다.
특히 launch_runs(도우미로 학습·대기열·스윕을 시작하기)는 웹으로는 못 켜고 여기서만 켠다(config.py)."""
from __future__ import annotations

import argparse

from . import config

HELP = {
    "launch_runs": "start training, queue jobs and sweeps from the web page, the Mac app's helper and MCP",
    "stall_min": "minutes with no new epoch before a run counts as stalled",
    "quiet_from": "no phone alerts from this hour (0-23)",
    "quiet_to": "until this hour (same as quiet_from: never quiet)",
    "reads_token": "ask for a token to view too: auto, always (shared servers) or never",
    "scan_mode": "auto, saver (alerts can come a few minutes late) or manual (no alerts)",
}


def _value(key: str, text: str):
    """'on'·'off'·'true'·'3'·'auto'를 그 설정의 타입으로. 못 바꾸면 ValueError"""
    kind = config.DEFAULTS[key]
    low = text.strip().lower()
    if isinstance(kind, bool):
        if low in ("on", "true", "yes", "1"):
            return True
        if low in ("off", "false", "no", "0"):
            return False
        raise ValueError(f"{key} is on or off")
    if key in config.CHOICES:
        if low not in config.CHOICES[key]:
            raise ValueError(f"{key} is one of: {', '.join(config.CHOICES[key])}")
        return low
    return type(kind)(float(low))


def _show(key: str, value) -> str:
    v = ("on" if value else "off") if isinstance(value, bool) else value
    return f"  {key:<17} {v}" + (f"    {HELP[key]}" if key in HELP else "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="epokio config", description="Show or change Epokio settings (~/.epokio/config.json).")
    ap.add_argument("key", nargs="?", help="a setting, e.g. launch_runs")
    ap.add_argument("value", nargs="?", help="its new value, e.g. on or off")
    a = ap.parse_args(argv)
    c = config.load()
    if not a.key:
        print("Settings:")
        for k in config.DEFAULTS:
            print(_show(k, c[k]))
        print("\nChange one with:  epokio config <setting> <value>")
        return 0
    if a.key not in config.DEFAULTS:
        print(f"No setting named {a.key}. Settings: {', '.join(config.DEFAULTS)}")
        return 2
    if a.value is None:
        print(_show(a.key, c[a.key]))
        return 0
    try:
        new = _value(a.key, a.value)
    except ValueError as e:
        print(str(e).replace("could not convert string to float", f"{a.key} is a number, not"))
        return 2
    c = config.update({a.key: new})
    print(_show(a.key, c[a.key]))
    if a.key == "reads_token":
        print("  The helper asks for a token to view from now on (`epokio agent --show-token` prints it)." if c[a.key] == "always"
              else "  Takes effect the next time the helper starts.")
    if a.key == "launch_runs":
        print("  The helper picks this up right away. Reload the web page to see the Train, Queue and Sweeps tabs."
              if c[a.key] else "  The helper no longer starts new jobs. Jobs already in the queue still run.")
    return 0
