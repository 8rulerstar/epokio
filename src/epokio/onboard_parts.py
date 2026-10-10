"""`epokio setup`의 조각: 누구의 도우미인가·어느 포트·어떤 폴더를 넘기나, systemd 서비스, LAN 주소.
onboard.py가 400줄 상한에 닿아 떼어 냈다. 시험이 바꿔 끼우는 이름(agent_alive·find_roots·saved_roots·owner)은
onboard.<이름>으로 부른다(doctor.py와 같은 방식)."""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path


def owner(port: int) -> str | None:
    """그 포트에서 누가 답하나. None = 아무도 · 'mine' = 내 토큰을 증명한 내 도우미 · 'old' = 내 옛 도우미(옛 증명) ·
    'theirs' = 증명 못 하는 Epokio(공용 서버의 다른 계정) · 'other' = Epokio가 아닌 프로그램.
    ★살아만 있으면 '이미 돈다'로 써서, 공용 서버에서 남의 8787 도우미에 붙고 터널에 남의 학습이 떴다"""
    from . import onboard, port as P
    url = P.url_for(port)
    if not onboard.agent_alive(port):
        return "other" if P.listening(port) else None
    if P.probe(url) != "epokio":
        return "other"
    return {"ok": "mine", "old": "old"}.get(P.agent_proof(url), "theirs")


def choose_port(want: int, explicit: bool) -> tuple[int, str | None, str]:
    """(쓸 포트, 거기 있는 것, 알릴 말). 남의 것이 차지했으면 내 도우미가 이미 떠 있는 포트, 아니면 다음 빈 포트.
    사용자가 --port를 직접 줬으면 옮기지 않는다(터널·방화벽이 그 번호를 믿는다. port.bind와 같은 규칙)"""
    from . import onboard, port as P
    st = onboard.owner(want)
    if st not in ("theirs", "other"):
        return want, st, ""
    what = "another account's Epokio helper" if st == "theirs" else "another program"
    if explicit:
        return want, st, f"Port {want} is used by {what}. Choose another one with --port, or leave --port out."
    rec = P.trusted_record()                   # 지난번에 옮겨 띄운 내 도우미부터
    for p in ([rec["port"]] if rec and rec.get("port") != want else []) + list(range(want + 1, want + P.SPAN + 1)):
        got = onboard.owner(p)
        if got in (None, "mine", "old"):
            return p, got, f"Port {want} is used by {what}, so your helper uses port {p}."
    return want, st, f"Port {want} is used by {what} and no port up to {want + P.SPAN} is free. Choose one with --port."


def found_roots() -> list[Path]:
    """setup이 'found'로 찍고 도우미에 넘기는 폴더: 저장해 둔 폴더 + 찾은 폴더. 사용자가 뺀 폴더와 이미 든 폴더 안의 폴더는 뺀다.
    ★찍기만 하고 넘기지 않아, 지금 폴더(프로젝트)에서 찾은 runs는 도우미가 영영 안 봤다(도우미는 홈에서 떠 홈 밖을 찾는다)"""
    from . import onboard
    from .agent import Agent
    from .roots import is_glob
    removed = {str(p) for p in onboard.saved_roots(Agent.REMOVED_FILE, quiet=True)}
    out: list[Path] = []
    for saved, p in [(True, p) for p in onboard.saved_roots(quiet=True)] + [(False, p) for p in onboard.find_roots()]:
        r = p if is_glob(p) else p.resolve()
        if (not saved and str(r) in removed) or any(r == q or q in r.parents for q in out):
            continue
        out.append(r)
    return out


def systemd_unit(roots: list[Path], host: str, port: int, allow_run: bool = False) -> str:
    """화면 없는 리눅스 서버에서 로그인·재부팅 뒤에도 도우미가 돌게 하는 systemd 사용자 서비스"""
    # systemd는 % 를 지정자로, $ 를 변수로, \ 를 이스케이프로 읽고, 따옴표 없는 공백에서 나눈다.
    # ★경로에 공백·%·$가 있으면(예: "my runs", venv가 "~/my venv") 서비스가 안 떴다. 전부 따옴표로 싸고 이스케이프한다
    def q(s) -> str:
        return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'
    args = " ".join([f"--port {port}", f"--host {host}"] + [f"--root {q(r)}" for r in roots] + (["--allow-run"] if allow_run else []))
    return ("[Unit]\nDescription=Epokio helper\nAfter=network-online.target\n\n"
            f"[Service]\nExecStart={q(sys.executable)} -m epokio agent {args}\nRestart=on-failure\n\n"
            "[Install]\nWantedBy=default.target\n")


def unit_file() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "epokio.service"


def lan_ip() -> str | None:
    """이 기계가 같은 네트워크에서 불릴 주소. 인터넷에 나가지 않고 알아낸다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))          # 보내지는 않는다, 커널에 경로만 물어보는 것
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def port_closed(port: int) -> bool:
    """이 기계의 그 포트에 아무도 안 듣는다(연결 거절). 응답이 느린 것은 닫힌 것이 아니다.
    윈도우는 닫힌 포트의 거절이 2초쯤 걸려 한도를 넉넉히 준다"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=4):
            return False
    except ConnectionRefusedError:
        return True
    except OSError:
        return False


def other_logins() -> bool | None:
    """이 기계에 로그인할 수 있는 다른 계정이 있나. None = 모른다(그때는 있다고 본다).
    pwd에 안 나오는 LDAP·SSSD 계정은 /home에 남의 폴더가 있는지로 본다(lost+found 등 root 것은 뺀다)"""
    try:
        import pwd
        me = os.getuid()
        users = pwd.getpwall()
    except (ImportError, AttributeError, OSError):
        return None
    shut = ("nologin", "false", "sync", "shutdown", "halt")
    if any(u.pw_uid != me and 1000 <= u.pw_uid < 65534 and u.pw_shell and Path(u.pw_shell).name not in shut
           for u in users):
        return True
    try:
        return any(d.is_dir() and d.stat().st_uid not in (0, me) for d in Path("/home").iterdir())
    except OSError:
        return None if not users else False


def lock_reads(skip: bool, interactive: bool) -> None:
    """SSH로 들어온 리눅스 서버: 보는 것(GET)에도 토큰이 필요하게(reads_token always). 다른 계정이 없다고 확실하면 안 묻는다.
    ★알리기만 해서(공용 서버에서 남이 127.0.0.1로 내 학습 목록·로그를 읽는다) 대부분 그대로 열려 있었다.
    auto일 때만 손댄다(always는 이미 잠김, never는 사용자가 고른 것). 도는 도우미에도 바로 먹는다(server.reads_locked)"""
    from . import config, onboard
    from .autostart import cli
    if config.load().get("reads_token") != "auto":
        return
    others = onboard.other_logins()
    if others is False:
        return
    who = "Other accounts on this server" if others else "This may be a shared server. Other accounts"
    print(f"\n  {who} can read your runs and logs from the helper on 127.0.0.1.")
    if skip:
        print(f"  Left open (--no-lock-reads). To ask for a token later:  {cli('config reads_token always')}")
        return
    if interactive and not onboard._yes("  Ask for a token to view them too? [Y/n] "):
        print(f"  Left open. To ask for a token later:  {cli('config reads_token always')}")
        return
    config.update({"reads_token": "always"})
    print("  Viewing now needs your token (the page asks once; the Mac app takes it with this server's address).")
    print(f"    show it with:  {cli('agent --show-token')}")
    if not interactive:
        print(f"  To undo:  {cli('config reads_token auto')}  (after the helper restarts)")
