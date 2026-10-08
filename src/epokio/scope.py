"""Makes a folder-scoped token (`agent --add-token alice --scope read --root /data/alice/runs`) see only runs inside that folder.

* During one request, LIMIT (a contextvar) holds the token's folders (server.py sets and resets it). None if unscoped: as before
* Views: /runs, /runs/table, /events keep only runs inside the folders; /run, /file outside them do not exist (404)
* Other views (/jobs, /sweep, /webhooks, /config etc., which carry others' run commands and config) and all execution (POST) get 403
* The list caches (_runs_cache, _scanned) are shared. Filter after building the cache, and never put filtered results in it
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from pathlib import Path

LIMIT: contextvars.ContextVar = contextvars.ContextVar("epokio_scope", default=None)

ALLOWED_GET = ("/health", "/system", "/runs", "/runs/table", "/run", "/events", "/file")
DENIED = (403, {"error": "this token can see only some folders, and not this"})


@contextmanager
def limited(roots):
    tok = LIMIT.set(roots)
    try:
        yield
    finally:
        LIMIT.reset(tok)


def current():
    lim = LIMIT.get()
    if lim is None:
        return None
    from .roots import expand
    return expand(lim)


def allows(path) -> bool:
    lim = current()
    if lim is None:
        return True
    if not path:
        return False
    from .rundetail import inside
    return inside(Path(str(path)), lim)


def get(agent, route: str, q: dict, inner):
    """Wraps Agent.get. Passes straight through when there is no folder limit"""
    if LIMIT.get() is None:
        return inner(route, q)
    if route not in ALLOWED_GET:
        return DENIED
    if route == "/run" and not allows(q.get("path", [""])[0]):
        return None                                   # as if missing (404). Does not even reveal whether the outside path exists
    lim = current()
    tok = LIMIT.set(None)                             # build the cache unfiltered
    try:
        got = inner(route, q)
    finally:
        LIMIT.reset(tok)
    with limited(lim):
        if route == "/runs" and isinstance(got, dict):
            return {**got, "runs": [r for r in got.get("runs", []) if allows(r.get("path"))],
                    "roots": [str(r) for r in lim], "missing_roots": [],
                    "too_long": [x for x in got.get("too_long", []) if allows(x)],
                    "slow_roots": [x for x in got.get("slow_roots", []) if allows(x)]}
        if route == "/runs/table" and isinstance(got, dict):
            return {**got, "rows": [r for r in got.get("rows", []) if allows(r.get("path"))]}
        if route == "/events" and isinstance(got, dict):
            return {**got, "events": [e for e in got.get("events", []) if allows((e.get("run") or {}).get("path"))]}
    return got
