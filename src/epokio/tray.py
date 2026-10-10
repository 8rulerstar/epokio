"""윈도우·리눅스 트레이: 맥 메뉴바와 같은 역할. `epokio-tray` 또는 `epokio tray`.

* agent에 붙는다(없으면 직접 띄운다). 원격도 된다: epokio-tray --agent http://gpu-pc:8787
* 아이콘 = 맥 메뉴바와 같은 학습곡선 + 진행률 원. 도는 동안만 진행률이 찬다
* 마우스를 올리면 고른 정보(진행률·남은 시간·끝날 시각·에폭·최고 점수·GPU)
* 메뉴: 학습 목록 · 대시보드(웹 화면) · 폴더 · 표시 설정 · 알림 · 끝
* 설정은 ~/.epokio/tray.json. 맥 앱 설정과 같은 이름(show·which·notify)

⚠맥에서 개발했다. 윈도우에서 아이콘·알림·메뉴 셋을 처음 돌릴 때 확인할 것(인계 문서 체크리스트).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from . import auth, autostart, i18n
from .i18n import t
from .scan import Run
from .notify import KINDS as NOTIFY_KINDS, title as notify_title
from .tui import Feed, display_name, order

CONFIG = Path.home() / ".epokio" / "tray.json"
DEFAULTS = {"show": ["pct", "eta"], "which": "live", "notify": True}
INFOS = ["pct", "eta", "clock", "epoch", "best", "gpu"]
# 알림 제목은 i18n 키로(★영어로만 박혀 있어 한국어 윈도우에서도 'Training finished'였다)
TITLES = {"finished": "notify.done", "failed": "notify.failed", "stalled": "notify.stalled",
          "stopped_early": "notify.stopped_early", "job_done": "notify.job_done", "job_failed": "notify.job_failed",
          "goal": "notify.goal", "disk_low": "notify.disk_low", "gpu_hot": "notify.gpu_hot", "gpu_mem": "notify.gpu_mem", "fan_max": "notify.fan_max",
          "started": "notify.started", "recovered": "notify.recovered"}


def tooltip(s: str) -> str:
    """윈도우 툴팁은 UTF-16으로 128칸(끝 0 포함)까지. ★글자 수로 잘라 이모지·드문 한자가 있으면 ValueError가 나고,
    그 오류를 반복문이 삼켜 툴팁이 조용히 멈췄다"""
    return s.encode("utf-16-le")[:254].decode("utf-16-le", "ignore")


def load_config() -> dict:
    try:
        return {**DEFAULTS, **json.loads(CONFIG.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_config(c: dict):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(c, indent=1), encoding="utf-8")


def short(s: float | None) -> str:
    """툴팁용 짧은 시간(빈칸 없이). 트레이 언어의 단위로"""
    from .scan import fmt_dur
    return fmt_dur(s, sep="")


def info_text(r: Run, show: list[str], gpu: float | None) -> str:
    """맥 메뉴바의 barText와 같은 규칙"""
    parts = []
    for k in show:
        if k == "pct" and r.progress is not None:
            parts.append(f"{int(round(r.progress * 100))}%")
        elif k == "eta" and r.state == "running" and r.eta:
            parts.append(short(r.eta))
        elif k == "clock" and r.state == "running" and r.eta:
            parts.append((datetime.now() + timedelta(seconds=r.eta)).strftime("%H:%M"))
        elif k == "epoch":
            parts.append(f"{r.epoch}/{r.total or '?'}")
        elif k == "best" and r.best is not None:
            parts.append(f"{r.best:.3f}")
        elif k == "gpu" and gpu is not None:
            parts.append(f"GPU {int(gpu)}%")
    return " ".join(parts)


def chosen(runs: list[Run], which: str, tick: int) -> Run | None:
    live = [r for r in runs if r.state in ("running", "starting")]
    if not live:
        return None
    if which == "star":
        return next((r for r in live if (r.meta or {}).get("star")), live[0])
    if which == "cycle":
        return live[tick % len(live)]
    return live[0]


def e_stroke(q: float, cx: float, cy: float, R: float, w: float, n: int = 48) -> list[tuple[float, float]]:
    """앱 아이콘의 한 획 e: 가로획 → 원 320°. q(0~1)만큼의 점들 (화면 좌표, y 아래로)"""
    bar, arc = 2 * R - w / 2, math.radians(320) * R
    L = (bar + arc) * max(min(q, 1), 0.03)
    pts = [(cx - R + w / 2, cy), (cx - R + w / 2 + min(L, bar), cy)]
    if L > bar:
        deg = math.degrees((L - bar) / R)
        pts += [(cx + R * math.cos(math.radians(-deg * i / n)), cy + R * math.sin(math.radians(-deg * i / n))) for i in range(1, n + 1)]
    return pts


def draw_icon(progress: float | None, state: str = "idle", size: int = 64):
    """맥 앱 아이콘과 같은 한 획 e. 도는 동안 진행률만큼 진하게, 끝점은 상태 색"""
    from PIL import Image, ImageDraw
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([S * .03, S * .03, S * .97, S * .97], radius=S * .24, fill=(28, 31, 61, 255))   # 앱 아이콘 배경색
    color = {"running": (34, 211, 238), "starting": (192, 132, 252), "stalled": (242, 140, 40),
             "failed": (229, 72, 77)}.get(state, (34, 211, 238))
    cx = cy = S / 2
    R, w = S * .35, S * .13
    q = 1.0 if progress is None else progress
    d.line(e_stroke(1, cx, cy, R, w), fill=(255, 255, 255, 70), width=int(w), joint="curve")
    done = e_stroke(q, cx, cy, R, w)
    d.line(done, fill="white", width=int(w), joint="curve")
    for x, y in (done[0],):                                    # 둥근 끝
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill="white")
    x, y = done[-1]
    r = w * .85
    d.ellipse([x - r, y - r, x + r, y + r], fill=color)
    return img.resize((size, size), Image.LANCZOS)


def ensure_agent(url: str) -> tuple[str, subprocess.Popen | None]:
    """이 기계 agent가 없으면 띄운다(맥 앱의 AgentLauncher와 같은 역할). 돌려주는 값: (실제 주소, 띄운 프로세스)
    다른 판이 돌고 있으면 끄고 새로 띄운다(★pip으로 올린 뒤에도 옛 도우미가 계속 돌았다)"""
    from . import port
    from .onboard import outdated, stop_agent
    if port.probe(url) == "epokio":
        n = int(url.rsplit(":", 1)[-1])
        if not outdated(n) or not stop_agent(n):
            return url, None
    default = url.rstrip("/") == port.url_for(port.DEFAULT_PORT)
    if default and port.probe(url) == "other":
        print(port.other_program_message(), "Starting Epokio on a free port.", file=sys.stderr)
    # 검은 창도 없고, 부모 콘솔도 안 붙잡는다
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) or getattr(subprocess, "CREATE_NO_WINDOW", 0)
    args = [] if default else ["--port", url.rsplit(":", 1)[-1]]   # 기본 주소면 agent가 빈 포트를 고른다
    proc = subprocess.Popen(autostart.self_command("agent") + args, cwd=str(Path.home()), creationflags=flags,
                            close_fds=True, env=autostart.child_env(),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return (port.wait_local() or url) if default else url, proc


def open_path(path: Path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


class Tray:
    def __init__(self, agent: str):
        import pystray
        self.agent = agent.rstrip("/")
        # 폴더를 직접 읽지 않는다. ★agent가 꺼지면 작업 폴더(자동 시작이면 홈)를 훑어 '도는 학습 없음'처럼 보였다
        self.feed = Feed(self.agent, [])
        self.cfg = load_config()
        self.runs: list[Run] = []
        self.gpu: float | None = None
        self.seq = None                    # 마지막으로 본 사건 번호(처음엔 옛 사건을 쏟아내지 않는다)
        self.tick = 0
        self.icon = pystray.Icon("epokio", icon=draw_icon(None), title="Epokio", menu=pystray.Menu(self._menu))

    # 메뉴는 열 때마다 새로 만든다 → 항상 최신
    def _menu(self):
        import pystray as P
        live = [r for r in self.runs if r.state in ("running", "starting")]
        yield P.MenuItem(self._headline(live), None, enabled=False)
        yield P.Menu.SEPARATOR
        for r in self.runs[:10]:
            mark = "▶ " if r.state == "running" else "✓ " if r.state == "done" else "! " if r.state in ("failed", "stalled") else "  "
            text = f"{mark}{display_name(r)}  {info_text(r, ['pct', 'best'], None)}"
            yield P.MenuItem(text, self._open_folder(r))
        yield P.Menu.SEPARATOR
        yield P.MenuItem(t("tray.dashboard"), lambda: webbrowser.open(auth.page_url(self.agent)), default=True)   # 아이콘을 누르면 이것
        yield P.MenuItem(t("tray.tooltip"), P.Menu(*[
            P.MenuItem(t("info." + k), self._toggle_info(k), checked=lambda _i, k=k: k in self.cfg["show"]) for k in INFOS]))
        yield P.MenuItem(t("tray.which"), P.Menu(*[
            P.MenuItem(t("tray.which." + k), self._set_which(k), radio=True, checked=lambda _i, k=k: self.cfg["which"] == k)
            for k in ("live", "star", "cycle")]))
        yield P.MenuItem(t("menu.notify"), self._toggle_notify, checked=lambda _i: self.cfg["notify"])
        if autostart.supported():
            yield P.MenuItem(t("tray.login"), self._toggle_autostart,
                             checked=lambda _i: autostart.enabled())
        yield P.Menu.SEPARATOR
        yield P.MenuItem(t("menu.quit"), lambda: self.icon.stop())

    def _headline(self, live) -> str:
        if self.feed.down:
            return t("tray.down", agent=self.agent)
        return t("tray.training", n=len(live)) if live else t("tray.nothing")

    def _open_folder(self, r: Run):
        return (lambda: open_path(Path(r.path))) if r.source in ("local", "") and Path(r.path).exists() else None

    def _toggle_info(self, k):
        def f():
            s = self.cfg["show"]
            self.cfg["show"] = [x for x in INFOS if (x in s) != (x == k)]
            save_config(self.cfg); self._paint()
        return f

    def _set_which(self, k):
        def f():
            self.cfg["which"] = k; save_config(self.cfg); self._paint()
        return f

    def _toggle_notify(self):
        self.cfg["notify"] = not self.cfg["notify"]; save_config(self.cfg)

    def _toggle_autostart(self):
        """켜고 끄는 건 시작프로그램 폴더의 바로 가기 하나다. 사용자가 탐색기에서 직접 지울 수도 있다."""
        try:
            autostart.disable() if autostart.enabled() else autostart.enable()
        except OSError:
            pass                        # 정책으로 막힌 환경에서도 트레이는 살아 있어야 한다

    def _paint(self):
        r = chosen(self.runs, self.cfg["which"], self.tick)
        self.icon.icon = draw_icon(r.progress if r else None, r.state if r else "idle")
        live = [x for x in self.runs if x.state in ("running", "starting")]
        tip = f"{display_name(r)}  {info_text(r, self.cfg['show'], self.gpu)}" if r else self._headline(live)
        self.icon.title = tooltip(tip)

    def _events(self):
        try:
            # 학습 목록과 같은 길로(내 도우미면 토큰을 싣는다). ★토큰 없이 불러 reads_token always인 도우미에선 알림이 조용히 끊겼다
            d = self.feed._get("events", since=self.seq or 0)
        except OSError:
            return
        first = self.seq is None
        self.seq = d.get("seq", self.seq)
        if first or not self.cfg["notify"]:
            return
        for e in d.get("events", []):
            if e["kind"] in NOTIFY_KINDS:
                run = e.get("run", {})
                body = (run.get("display") or run.get("name", "")) + (f" · {t('best')} {run['best']:.4f}" if run.get("best") is not None else "")
                try:
                    self.icon.notify(body, t(TITLES[e["kind"]]) if e["kind"] in TITLES else notify_title(e["kind"]))
                except Exception:            # 알림 미지원 환경에서도 트레이는 살아야 한다
                    pass

    def _loop(self):
        while True:
            try:
                self.runs = order(self.feed.runs())
                sysnow = self.feed.system() if "gpu" in self.cfg["show"] else None
                self.gpu = ((sysnow or {}).get("gpus") or [{}])[0].get("util")
                self._events()
                self._paint()
            except Exception:
                pass
            self.tick += 1
            live = any(r.state == "running" for r in self.runs)
            time.sleep(5 if live else 15)       # 쉴 때는 천천히(배터리·CPU)

    def run(self):
        threading.Thread(target=self._loop, daemon=True).start()
        self.icon.run()


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(prog="epokio tray", description="Training progress in the system tray (Windows, Linux).")
    ap.add_argument("--agent", default=None, help="agent address (default: this machine, started automatically)")
    ap.add_argument("--open", action="store_true", help=argparse.SUPPRESS)   # exe를 더블클릭했을 때: 웹 화면도 연다
    a = ap.parse_args(argv)
    try:
        import pystray  # noqa: F401
        import PIL      # noqa: F401
    except ImportError:
        sys.exit("The tray needs pystray and Pillow:  " + autostart.pip_cmd('"epokio[tray]"'))
    i18n.use(i18n.system_language())            # 윈도우 표시 언어를 따른다
    agent, proc = a.agent, None
    if agent is None:
        from . import port
        agent = port.local_url()
    if "127.0.0.1" in agent or "localhost" in agent:
        agent, proc = ensure_agent(agent)
    if a.open:
        # ★README는 '더블클릭하면 브라우저가 열린다'고 했는데 트레이 아이콘만 생겨(윈11은 ^ 안에 숨는다) 아무것도 안 뜬 것처럼 보였다.
        #   로그인 자동 시작은 'tray' 인자로 켜지므로 여기 오지 않는다
        import webbrowser
        from . import auth
        webbrowser.open(auth.page_url(agent))
    try:
        Tray(agent).run()
    finally:
        if proc:
            proc.terminate()                      # 트레이가 띄운 agent는 같이 끈다


if __name__ == "__main__":
    main()
