"""폰으로 가는 웹후크(Slack·Discord·Telegram·ntfy). 학습 기계의 agent가 직접 보낸다.

사건마다 무엇을 보낼지는 여기 한곳에서 정한다. 맥 화면 알림은 스위프트(Notifier.swift)가 한다.
웹후크는 knockknock(⭐2,826)에서 배운 것, 자리를 비웠을 때 폰으로 받는 게 핵심이다.
"""
from __future__ import annotations

import base64
import json
import threading
import urllib.request

from .monitor import Event
from . import i18n

# 사건 → 제목 키(i18n.py). ★알림 제목은 여기 한 곳. 언어는 웹후크를 건 앱의 언어(watcher가 i18n.use로 고른다)
KINDS = {
    "finished": "notify.done",
    "failed": "notify.failed",
    "stalled": "notify.stalled",
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
URGENT = {"failed", "stalled", "job_failed"}             # ntfy 우선순위 높음
MACHINE_KINDS = {"disk_low", "gpu_hot", "gpu_mem", "fan_max"}      # 학습이 아니라 기계 상태 경고


def title(kind: str) -> str:
    return i18n.t(KINDS[kind]) if kind in KINDS else "Epokio"      # ★모르는 사건이 "학습 완료"로 떴다


def body_of(e: Event, machine: str | None = None) -> str:
    """폰에 가는 본문. 어느 기계의 무슨 점수인지까지. ★기계 이름(로컬이면 빠졌다)과 지표 이름이 없어 '최고 0.6000'만 왔다"""
    r = e.run
    where = r.source if r.source not in ("local", "로컬") else machine
    if e.kind in MACHINE_KINDS:
        return " · ".join(x for x in (r.name, where) if x)
    from .scan import display_name
    from .scan_names import x_count
    parts = [display_name(r), f"{i18n.t(getattr(r, 'x_axis', 'epoch'))} {x_count(r)}"]   # step 학습은 'step 12,000/100,000'
    if r.best is not None:
        metric = (r.metric_name or "").split("/", 1)[-1]
        parts.append(f"{i18n.t('best')} {metric + ' ' if metric else ''}{r.best:.4f}")
    if where:
        parts.append(where)
    return " · ".join(parts)


def is_ntfy(url: str) -> bool:
    """ntfy.sh 또는 직접 둔 ntfy 서버(주소에 /ntfy/ 가 들어가거나 ntfy. 로 시작)"""
    host = url.split("//")[-1].split("/")[0]
    return host == "ntfy.sh" or host.startswith("ntfy.") or "/ntfy/" in url


def _request(url: str, head: str, body: str, urgent: bool = False) -> urllib.request.Request:
    """주소 종류에 맞는 요청 하나. 실제 알림과 시험 알림이 같은 모양을 쓴다"""
    text = f"*{head}*\n{body}"
    if is_ntfy(url):      # ntfy: 폰 푸시 앱(무료, 직접 서버를 둘 수도 있다). 본문은 글자, 제목은 머리말
        return urllib.request.Request(url, data=body.encode(), headers={
            # 머리말은 ASCII만 되므로 한글 제목은 RFC 2047로 싼다(ntfy가 푼다)
            "Title": "=?UTF-8?B?" + base64.b64encode(f"Epokio: {head}".encode()).decode() + "?=",
            "Tags": "warning" if urgent else "white_check_mark",
            "Priority": "high" if urgent else "default"})
    # Slack은 text, Discord는 content. 텔레그램(...sendMessage?chat_id=...)은 text만
    payload = {"text": text} if "api.telegram.org" in url else {"text": text, "content": text}
    return urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})


def valid(url) -> bool:
    """웹후크 주소 검사(API·CLI 같은 규칙). https만 받는다"""
    return isinstance(url, str) and url.startswith("https://")


def send_test(url: str, machine: str | None = None, timeout: float = 5) -> dict:
    """시험 알림 하나를 바로(기다려서) 보낸다. 결과 {url, ok, status 또는 error}. 언어는 부르는 쪽이 i18n.use로 고른다"""
    req = _request(url, i18n.t("notify.test"), i18n.t("notify.test_body", machine=machine or "Epokio"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"url": url, "ok": True, "status": getattr(r, "status", 200)}
    except Exception as ex:                       # HTTPError도 여기로(상태 코드를 같이 돌려준다)
        out = {"url": url, "ok": False, "error": str(ex)[:200]}
        if getattr(ex, "code", None):
            out["status"] = ex.code
        return out


def webhook(url: str, e: Event, machine: str | None = None):
    """Slack·Discord·일반 웹후크에 한 번에 맞는 모양으로 보낸다. 실패해도 앱은 계속 돈다."""
    # ★문구는 여기서 다 만든다. 보내는 스레드 안에서 만들면 그 사이 다른 사건이 언어를 바꿀 수 있다
    req = _request(url, title(e.kind), body_of(e, machine), e.kind in URGENT)

    def send():
        try:
            urllib.request.urlopen(req, timeout=6).read()
        except Exception as ex:                          # ★실패해도 아무 기록이 없어, 폰 알림이 왜 안 오는지 알 길이 없었다
            import logging
            logging.getLogger("epokio").warning("webhook to %s failed: %s", url.split("?")[0][:60], ex)
    threading.Thread(target=send, daemon=True).start()
