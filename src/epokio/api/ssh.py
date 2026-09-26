"""SSH 가벼운 모드 요청: 서버 목록(GET /ssh) · 추가(POST /ssh/add, 바로 한 번 읽어 결과를 돌려준다) · 빼기 · 다시 읽기. 본체는 ssh_source.py"""
from __future__ import annotations

from .. import ssh_source
from . import NOT_MINE


def get(agent, route: str, q: dict):
    if route == "/ssh":
        st = agent.ssh.status
        return {"hosts": [{**h, "status": st.get(h["host"])} for h in ssh_source.load()],
                "config_hosts": ssh_source.config_hosts()}
    return NOT_MINE


def post(agent, route: str, body: dict):
    if route == "/ssh/add":
        host = str(body.get("host", "")).strip()
        if not ssh_source.valid_host(host):
            return 400, {"error": "give an SSH host name from ~/.ssh/config or user@host"}
        paths = [str(p).strip() for p in (body.get("paths") or []) if str(p).strip()][:10]
        entry = {"host": host, "paths": paths, "auto": bool(body.get("auto", True)), "on": True}
        st = agent.ssh.poll_once(entry)                       # ★저장하기 전에 한 번 읽어 본다(안 되면 이유를 바로)
        if not st.get("ok"):
            return 400, {"error": st.get("error") or "could not connect"}
        ssh_source.save([h for h in ssh_source.load() if h["host"] != host] + [entry])
        agent._runs_cache = None
        return 200, {"ok": True, "status": st}
    if route == "/ssh/remove":
        ssh_source.remove(str(body.get("host", "")))
        agent.ssh.status.pop(str(body.get("host", "")), None)
        agent._runs_cache = None
        return 200, {"ok": True}
    if route == "/ssh/refresh":
        agent.ssh.wake()
        return 200, {"ok": True}
    return NOT_MINE
