"""The training process sends phone notifications itself, without the helper (`epokio.start(..., notify=True)`). For Colab,
notebooks and other places where the helper cannot run.

* Same settings as the helper (~/.epokio/webhooks.json: urls, kinds, language, quiet hours) and same body (notify.body_of)
* finished at the end, failed when killed by an exception (reason "RuntimeError: ...")
* Avoiding duplicates: before sending, a CLAIM file ("finished" or "failed") is written to the run folder.
  It precedes the finished/failed marker, so a helper watching the run sees the CLAIM by the time it sees the marker.
  On a matching CLAIM the helper skips the webhook (inbox, Mac alert still happen). On send failure the CLAIM is removed
  so the helper sends instead
* Standard library only. Training never dies even without network (all exceptions swallowed, 5 s limit)
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

CLAIM = "epokio_notified"


def claim(run_dir: Path, kind: str) -> None:
    try:
        (Path(run_dir) / CLAIM).write_text(kind, encoding="utf-8")
    except OSError:
        pass


def claimed(path: str | os.PathLike | None, kind: str) -> bool:
    """Has the training process already sent (or is sending) this result (finished or failed)? Checked by the helper"""
    if not path or kind not in ("finished", "failed"):
        return False
    try:
        return (Path(path) / CLAIM).read_text(encoding="utf-8").strip() == kind
    except OSError:
        return False


def _hooks() -> dict:
    from .agent import Agent                          # same file as the helper (tests swap it in conftest)
    try:
        cfg = json.loads(Agent.HOOKS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def send(run_dir: Path, kind: str, timeout: float = 5.0) -> int:
    """Send right away (blocking) to every configured webhook. Returns the count sent. Never raises, whatever happens"""
    try:
        return _send(Path(run_dir), kind, timeout)
    except Exception:                                  # noqa: BLE001  never kill training
        return 0


def _send(run_dir: Path, kind: str, timeout: float) -> int:
    from . import config, i18n, notify
    from .monitor import Event
    from .scan import read_run
    from .watcher import DEFAULT_HOOK_KINDS
    cfg = _hooks()
    urls = [u for u in cfg.get("urls", []) if isinstance(u, str) and notify.valid(u)]
    if not urls or kind not in cfg.get("kinds", DEFAULT_HOOK_KINDS) or config.quiet_now():
        _unclaim(run_dir, kind)
        return 0
    r = read_run(run_dir)
    if r is None:
        _unclaim(run_dir, kind)
        return 0
    i18n.use(cfg.get("lang"))
    from .alerts_cli import _label
    ev = Event(kind, r, "running")
    req_head, body = notify.title(kind), notify.body_of(ev, machine=_label())
    sent = 0
    for u in urls:
        try:
            with urllib.request.urlopen(notify._request(u, req_head, body, kind in notify.URGENT), timeout=timeout):
                sent += 1
        except Exception:                              # noqa: BLE001
            continue
    if not sent:
        _unclaim(run_dir, kind)                        # if the helper is running, it sends instead
    return sent


def _unclaim(run_dir: Path, kind: str) -> None:
    if claimed(run_dir, kind):
        try:
            (run_dir / CLAIM).unlink()
        except OSError:
            pass
