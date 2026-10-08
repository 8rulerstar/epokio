"""Webhooks to your phone (Slack, Discord, Telegram, ntfy). Sent directly by the agent on the training machine.

What to send for each event is decided here, in one place. Mac on-screen notifications are done in Swift (Notifier.swift).
Webhooks were learned from knockknock (⭐2,826): the point is getting it on your phone when you are away.
"""
from __future__ import annotations

import base64
import json
import threading
import urllib.request

from .monitor import Event
from . import i18n

# Event -> title key (i18n.py). Titles live only here. Language: that of the app that set the webhook (via i18n.use)
KINDS = {
    "finished": "notify.done",
    "failed": "notify.failed",
    "stalled": "notify.stalled",
    "quiet": "notify.quiet",          # a run with unknown planned epochs stopped logging (finished or stuck). Not urgent
    "stopped_early": "notify.stopped_early",
    "recovered": "notify.recovered",
    "started": "notify.started",
    "goal": "notify.goal",
    "pruned": "notify.pruned",
    "disk_low": "notify.disk_low",
    "gpu_hot": "notify.gpu_hot",
    "gpu_mem": "notify.gpu_mem",
    "fan_max": "notify.fan_max",
    "job_done": "notify.job_done",
    "job_failed": "notify.job_failed",
}
URGENT = {"failed", "stalled", "job_failed"}             # high ntfy priority
MACHINE_KINDS = {"disk_low", "gpu_hot", "gpu_mem", "fan_max"}      # machine-state warnings, not about training


def title(kind: str) -> str:
    return i18n.t(KINDS[kind]) if kind in KINDS else "Epokio"      # previously an unknown event showed as "training done"


def body_of(e: Event, machine: str | None = None) -> str:
    """Body sent to the phone, including which machine and which metric. Previously the machine name (missing for local)
    and the metric name were absent, so only 'best 0.6000' arrived"""
    r = e.run
    where = r.source if r.source not in ("local", "로컬") else machine
    if e.kind in MACHINE_KINDS:
        return " · ".join(x for x in (r.name, where) if x)
    from .scan import display_name
    from .scan_names import x_count
    parts = [display_name(r), f"{i18n.t(getattr(r, 'x_axis', 'epoch'))} {x_count(r)}"]   # step-based runs: 'step 12,000/100,000'
    if r.best is not None:
        metric = (r.metric_name or "").split("/", 1)[-1]
        parts.append(f"{i18n.t('best')} {metric + ' ' if metric else ''}{r.best:.4f}")
    if e.kind == "failed" and getattr(r, "error", ""):
        parts.append(r.error[:120])                    # previously why it died (OOM etc.) never reached the phone
    if where:
        parts.append(where)
    return " · ".join(parts)


def is_ntfy(url: str) -> bool:
    """ntfy.sh or a self-hosted ntfy server (address contains /ntfy/ or the host starts with ntfy.)"""
    host = url.split("//")[-1].split("/")[0]
    return host == "ntfy.sh" or host.startswith("ntfy.") or "/ntfy/" in url


def _request(url: str, head: str, body: str, urgent: bool = False) -> urllib.request.Request:
    """One request shaped for the address type. Real and test notifications use the same shape"""
    text = f"*{head}*\n{body}"
    if is_ntfy(url):      # ntfy: phone push app (free, can be self-hosted). Body is plain text, title is a header
        return urllib.request.Request(url, data=body.encode(), headers={
            # headers are ASCII-only, so a non-ASCII title is wrapped in RFC 2047 (ntfy decodes it)
            "Title": "=?UTF-8?B?" + base64.b64encode(f"Epokio: {head}".encode()).decode() + "?=",
            "Tags": "warning" if urgent else "white_check_mark",
            "Priority": "high" if urgent else "default"})
    # Slack uses text, Discord uses content. Telegram (...sendMessage?chat_id=...) takes only text
    payload = {"text": text} if "api.telegram.org" in url else {"text": text, "content": text}
    return urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})


def valid(url) -> bool:
    """Webhook address check (same rule for API and CLI). Only https is accepted"""
    return isinstance(url, str) and url.startswith("https://")


def safe_url(url: str) -> str:
    """For logs and output: scheme and host only. Previously the first 60 chars of the path were logged, leaking
    ntfy topics and Telegram bot tokens into agent.log and doctor output"""
    from urllib.parse import urlsplit
    try:
        p = urlsplit(url)
        host = p.hostname or ""
    except ValueError:
        return "(bad address)"
    return f"{p.scheme}://{host}" if p.scheme and host else "(bad address)"


def masked_url(url: str) -> str:
    """For lists: host + masked path. A 4-char path fingerprint tells apart two webhooks on the same host"""
    import hashlib
    from urllib.parse import urlsplit
    try:
        p = urlsplit(url)
        host = p.hostname or ""
    except ValueError:
        return "(bad address)"
    rest = url[url.find(host) + len(host):] if host else url
    if not rest.strip("/"):
        return host
    return f"{host}/*** ({hashlib.sha1(rest.encode('utf-8')).hexdigest()[:4]})"


def send_test(url: str, machine: str | None = None, timeout: float = 5) -> dict:
    """Send one test notification now (blocking). Returns {url, ok, status or error}. Caller picks language via i18n.use"""
    req = _request(url, i18n.t("notify.test"), i18n.t("notify.test_body", machine=machine or "Epokio"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"url": url, "ok": True, "status": getattr(r, "status", 200)}
    except Exception as ex:                       # HTTPError lands here too (status code is returned as well)
        from .textnorm import err_text
        out = {"url": url, "ok": False, "error": err_text(ex)[:200]}
        if getattr(ex, "code", None):
            out["status"] = ex.code
        return out


def webhook(url: str, e: Event, machine: str | None = None):
    """Send in a shape that fits Slack, Discord and generic webhooks at once. The app keeps running on failure."""
    # Build all text here. If built inside the sending thread, another event could switch the language meanwhile
    req = _request(url, title(e.kind), body_of(e, machine), e.kind in URGENT)

    def send():
        try:
            urllib.request.urlopen(req, timeout=6).read()
        except Exception as ex:                          # previously silent: no way to tell why phone alerts never came
            import logging
            from .textnorm import err_text
            logging.getLogger("epokio").warning("webhook to %s failed: %s", safe_url(url), err_text(ex))
    threading.Thread(target=send, daemon=True).start()
