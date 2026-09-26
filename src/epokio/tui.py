"""터미널 화면: `epokio watch`.

리눅스 서버에 SSH로 들어가 한 줄이면 학습 진행이 보인다. 추가 설치 없음(표준 라이브러리 curses).
  * agent가 떠 있으면 거기서 받는다(원격도: --agent http://서버:8787)
  * 없으면 폴더를 직접 읽는다(--root, 기본은 지금 폴더). 서버에 agent를 안 띄워도 된다

키: ↑↓ 또는 j/k 고르기 · Enter 상세 · Tab 손실/점수 · Esc 뒤로 · r 새로 고침 · q 끝
`--once`는 표 한 번만 찍고 끝낸다(스크립트·로그용).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from . import rundetail, schema, sysinfo
from .scan import Run, fmt_dur, scan
from .scan import display_name as _display_name

BLOCKS = "▁▂▃▄▅▆▇█"
STATE = {"running": ("▶", "Training"), "starting": ("…", "Starting"), "stalled": ("‖", "Stalled"),
         "failed": ("✗", "Failed"), "stopped": ("■", "Stopped"), "done": ("✓", "Done")}


# ── 데이터: agent 또는 폴더 ─────────────────────────────

class Feed:
    def __init__(self, agent: str | None, roots: list[Path]):
        self.agent = agent.rstrip("/") if agent else None
        self.roots = roots
        self.where = ""
        self.down = False                # agent에 닿지 않는다(트레이가 '도는 학습 없음' 대신 이것을 보인다)

    def _get(self, route: str, **q):
        url = f"{self.agent}/{route}" + ("?" + urllib.parse.urlencode(q) if q else "")
        with urllib.request.urlopen(url, timeout=4) as r:
            return json.loads(r.read())

    def runs(self) -> list[Run]:
        if self.agent:
            try:
                d = self._get("runs")
                self.down = False
                self.where = f"agent {self.agent} ({d.get('label', '')})"
                return [Run.from_dict(x) for x in d["runs"]]
            except OSError:
                self.down = True
                self.where = f"agent {self.agent} not reachable, reading folders"
        else:
            self.where = "folders: " + ", ".join(str(r) for r in self.roots)
        out = []
        for r in self.roots:
            if r.exists():
                out += scan(r)
        return out

    def system(self) -> dict | None:
        if self.agent:
            try:
                return (self._get("system") or {}).get("now")
            except OSError:
                pass
        return sysinfo.sample().to_dict()

    def detail(self, run: Run) -> dict | None:
        if self.agent:
            try:
                return self._get("run", path=str(run.path))
            except OSError:
                pass
        return rundetail.detail(Path(run.path))


def order(runs: list[Run]) -> list[Run]:
    rank = {"running": 0, "starting": 1, "stalled": 2, "failed": 3, "stopped": 4, "done": 5}
    return sorted(runs, key=lambda r: (rank.get(r.state, 9), r.idle))


# ── 글자 도구 ───────────────────────────────────────────

def dur(s: float | None) -> str:
    return fmt_dur(s)


def bar(p: float | None, width: int) -> str:
    if p is None or width <= 0:
        return " " * max(width, 0)
    n = p * width
    full = int(n)
    return "█" * full + ("▌" if n - full >= 0.5 and full < width else "") + "·" * (width - full - (1 if n - full >= 0.5 and full < width else 0))


def spark(vals: list, width: int) -> str:
    v = [x for x in vals if x is not None]
    if not v or width <= 0:
        return ""
    if len(v) > width:                       # 폭에 맞게 고르게 뽑는다
        v = [v[int(i * len(v) / width)] for i in range(width)]
    lo, hi = min(v), max(v)
    span = (hi - lo) or 1
    return "".join(BLOCKS[min(7, int((x - lo) / span * 7.999))] for x in v)


def cells(t: str) -> int:
    """터미널에서 차지하는 칸 수. 한글·한자는 두 칸이다"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in t)


def fit(t: str, width: int) -> str:
    """칸 수 기준으로 자르고 채운다. 넘치면 앞을 줄인다(끝의 run 이름이 더 중요)"""
    if cells(t) > width:
        while cells(t) > width - 1:
            t = t[1:]
        t = "…" + t
    return t + " " * (width - cells(t))


display_name = _display_name                  # 이름 규칙은 scan 한 곳에(웹·트레이·보고서·알림과 같게)


def row(r: Run, width: int) -> str:
    icon, _ = STATE.get(r.state, ("?", r.state))
    pct = f"{int(r.progress * 100):3d}%" if r.progress is not None else "   ?"
    when = f"{dur(r.eta)} left" if r.state == "running" else f"{dur(r.idle)} ago"
    ep = f"{r.epoch}/{r.total or '?'}"
    best = f"best {r.best:.4f}" if r.best is not None else ""
    tail = f" {pct}  ep {ep:>9}  {when:>11}  {best:<11}"          # 폭을 고정해 막대 끝이 줄마다 같다('17h 13m ago'가 11칸)
    name_w = max(12, min(40, width // 3))
    bar_w = max(0, width - name_w - len(tail) - 4)
    star = "★" if (getattr(r, "meta", None) or {}).get("star") else " "
    return f"{icon}{star}{fit(display_name(r), name_w)} {bar(r.progress, bar_w)}{tail}"


def sys_line(s: dict | None) -> str:
    if not s:
        return ""
    g = (s.get("gpus") or [{}])[0]
    mem = (s["mem_used"] / s["mem_total"] * 100) if s.get("mem_used") and s.get("mem_total") else None
    f = lambda v: f"{v:.0f}%" if v is not None else "-"
    return f"GPU {f(g.get('util'))}  CPU {f(s.get('cpu'))}  MEM {f(mem)}  {g.get('name', '')}"


def detail_lines(r: Run, d: dict | None, curve: int, width: int) -> list[str]:
    _, state = STATE.get(r.state, ("?", r.state))
    out = [display_name(r), f"{state} · epoch {r.epoch}/{r.total or '?'} · took {dur(r.elapsed)} · {r.source}", ""]
    if not d:
        return out + ["(no details)"]
    head_name = schema.HEADS
    if d.get("heads"):
        out.append(f"{'':6}{'Precision':>10}{'Recall':>9}{'F1':>8}{'mAP50':>8}{'mAP50-95':>10}{'best ep':>9}")
        f = lambda v: f"{v:.3f}" if v is not None else "-"
        for h in d["heads"]:
            out.append(f"{head_name.get(h['head'], h['head']):6}{f(h['precision']):>10}{f(h['recall']):>9}"
                       f"{f(h['f1']):>8}{f(h['map50']):>8}{f(h['map5095']):>10}{h['best_epoch']:>9}")
        out.append("")
    cols = d.get("columns", {})
    info = d.get("column_info") or schema.column_info(cols)          # 옛 agent는 column_info가 없다
    keys = sorted(k for k in cols if info.get(k, {}).get("kind") == ("loss" if curve == 0 else "score"))
    label = {k: schema.pretty(k) for k in keys}
    out.append("Curves: " + ("loss" if curve == 0 else "scores") + "   (Tab to switch)")
    lw = max(len(label[k]) for k in keys) if keys else 0
    for k in keys:
        vals = [v for v in cols[k] if v is not None]
        last = f"{vals[-1]:.4f}" if vals else "-"
        out.append(f"  {label[k]:<{lw}}  {spark(cols[k], max(10, width - lw - 16))}  {last}")
    if d.get("notes"):
        out += ["", "What stands out"]
        for n in d["notes"]:
            out += [f"  • {n['observation']}", f"    → {n['try']}"]
    return out


# ── 화면 ───────────────────────────────────────────────

def run_curses(feed: Feed, every: float):
    import os
    os.environ.setdefault("ESCDELAY", "25")      # ★없으면 Esc가 1초 늦게 먹는다(ncurses 기본값)
    import curses

    def main(scr):
        curses.curs_set(0)
        curses.use_default_colors()
        for i, c in enumerate([curses.COLOR_GREEN, curses.COLOR_YELLOW, curses.COLOR_RED, curses.COLOR_CYAN], 1):
            curses.init_pair(i, c, -1)
        color = {"running": 1, "starting": 4, "stalled": 2, "failed": 3, "done": 4}
        scr.timeout(200)
        sel, view, curve, scroll, top = 0, "list", 1, 0, 0
        runs, sysnow, det, last = [], None, None, 0.0
        picked = None                            # 고른 학습의 경로. ★줄 번호로 들고 있으면 갱신마다 순서가 바뀌어 다른 학습으로 넘어갔다
        while True:
            now = time.time()
            if now - last > every:
                runs, sysnow, last = order(feed.runs()), feed.system(), now
                paths = [str(r.path) for r in runs]
                if picked in paths:
                    sel = paths.index(picked)
                sel = min(sel, max(len(runs) - 1, 0))
                if view == "detail" and runs:
                    det = feed.detail(runs[sel])
            picked = str(runs[sel].path) if runs else None
            h, w = scr.getmaxyx()
            scr.erase()
            live = sum(r.state in ("running", "starting") for r in runs)
            scr.addnstr(0, 0, f" Epokio  {live} active  {len(runs)} runs   {sys_line(sysnow)}", w - 1, curses.A_BOLD)
            scr.addnstr(1, 0, " " + feed.where, w - 1, curses.A_DIM)
            if view == "list":
                if not runs:
                    scr.addnstr(3, 2, "No runs found. Use --root <folder with runs> or --agent http://host:8787", w - 3)
                rows_h = max(h - 5, 1)                   # 고른 줄이 늘 보이게 목록을 민다(★예전엔 화면 밖으로 사라졌다)
                top = min(max(top, sel - rows_h + 1), sel)
                for i, r in enumerate(runs[top: top + rows_h]):
                    attr = curses.color_pair(color.get(r.state, 0))
                    if top + i == sel:
                        attr |= curses.A_REVERSE
                    scr.addnstr(3 + i, 1, row(r, w - 2), w - 2, attr)
                scr.addnstr(h - 1, 0, " ↑↓ select  Enter details  r refresh  q quit", w - 1, curses.A_DIM)
            else:
                r = runs[sel] if runs else None
                lines = detail_lines(r, det, curve, w - 4) if r else []
                for i, line in enumerate(lines[scroll: scroll + h - 5]):
                    scr.addnstr(3 + i, 2, line, w - 3, curses.A_BOLD if i + scroll == 0 else 0)
                scr.addnstr(h - 1, 0, " Esc back  Tab loss/scores  ↑↓ scroll  q quit", w - 1, curses.A_DIM)
            scr.refresh()
            k = scr.getch()
            if k in (ord("q"), ord("Q")):
                return
            if k == ord("r"):
                last = 0
            elif view == "list":
                if k in (curses.KEY_DOWN, ord("j")):
                    sel = min(sel + 1, max(len(runs) - 1, 0))
                elif k in (curses.KEY_UP, ord("k")):
                    sel = max(sel - 1, 0)
                elif k in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT) and runs:
                    view, scroll, det = "detail", 0, feed.detail(runs[sel])
            else:
                if k in (27, curses.KEY_BACKSPACE, 127, curses.KEY_LEFT):
                    view = "list"
                elif k == 9:
                    curve = 1 - curve
                elif k in (curses.KEY_DOWN, ord("j")):
                    scroll += 1
                elif k in (curses.KEY_UP, ord("k")):
                    scroll = max(0, scroll - 1)

    curses.wrapper(main)


def print_once(feed: Feed, width: int = 100):
    runs = order(feed.runs())
    print(f"Epokio  {sum(r.state in ('running', 'starting') for r in runs)} active  {len(runs)} runs   {sys_line(feed.system())}")
    print(feed.where)
    for r in runs:
        print(row(r, width))


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(prog="epokio watch", description="Watch training runs in the terminal.")
    ap.add_argument("--agent", help="agent address, default: this machine's agent (falls back to reading folders)")
    ap.add_argument("--root", action="append", help="folder with runs (repeatable). Default: current folder")
    ap.add_argument("--every", type=float, default=2.0, help="refresh seconds")
    ap.add_argument("--once", action="store_true", help="print the table once and exit")
    a = ap.parse_args(argv)
    # ★파이프·파일로 받으면(한국어 윈도우는 cp949) 막대 글자 █에서 UnicodeEncodeError로 죽었다. --once가 바로 그 용도다
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    roots = [Path(r).expanduser() for r in (a.root or ["."])]
    if a.agent or a.root:
        agent = a.agent
    else:
        from . import port
        agent = port.local_url(warn=True)     # ~/.epokio/agent.json → 기본 8787
    feed = Feed(agent, roots)
    if a.once or not sys.stdout.isatty():
        print_once(feed)
    else:
        try:
            import curses  # noqa: F401  윈도우 파이썬엔 없다(windows-curses가 빠진 설치)
        except ImportError:
            print("curses is not available (on Windows: pip install windows-curses). Showing the table once.",
                  file=sys.stderr)
            print_once(feed)
            return
        run_curses(feed, a.every)


if __name__ == "__main__":
    main()
