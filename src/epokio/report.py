"""학습 보고서를 마크다운 한 장으로.

사수에게 "어떻게 됐어?"를 들었을 때 그대로 붙여 넣을 수 있게 하는 것이 목적이다.
그림은 run 폴더에 이미 있는 것을 보고서 옆 폴더로 복사해 상대 경로로 건다
(마크다운을 어디로 옮겨도 그림이 깨지지 않게).
"""
from __future__ import annotations

from .msg import tr

import shutil
import time
from pathlib import Path

from .analysis import Analysis, analyze
from .scan import Run, display_name

HEAD_NAME = {"B": "Box", "P": "Pose", "M": "Mask"}
STATE_EN = {"starting": "Starting", "running": "Training", "stalled": "Stalled",
            "failed": "Failed", "stopped": "Stopped", "done": "Done"}
SHOW_IMAGES = ("results", "box_pr", "box_f1", "pose_pr", "pose_f1", "mask_pr", "pr", "f1",
               "confusion", "val_pred", "val_labels")


FOOTNOTE = ("F1 here is **detection F1** computed from the framework's validation precision and "
            "recall, averaged over classes, at the confidence where the mean F1 is highest. It is "
            "not the average of per-class F1, and not a task-level metric such as a defect "
            "judgment F1 from your own evaluation script. Do not mix the two.")


def fmt(v, d=3):
    return "–" if v is None else f"{v:.{d}f}"


def spark(h: list[float], width: int = 24) -> str:
    if len(h) < 2:
        return ""
    blocks = "▁▂▃▄▅▆▇█"
    step = max(len(h) // width, 1)
    h = h[::step][-width:]
    lo, hi = min(h), max(h)
    span = (hi - lo) or 1.0
    return "".join(blocks[int((v - lo) / span * 7)] for v in h)


def readable(r: Run) -> bool:
    """이 기계에서 그 폴더를 읽을 수 있나. ★source 문자열로 "local"을 찾으면 안 된다:
    LocalSource가 기계 이름(label)을 넣고, SSH로 비춰 온 원격 run도 여기 폴더에 있다.
    그것 때문에 원격·이름 붙은 폴더의 run이 통째로 빈 보고서가 됐다."""
    try:
        return Path(r.path).is_dir()
    except (OSError, TypeError):
        return False


def _review_section(rev: dict) -> list[str]:
    """검수 결과: 요약 수치 한 줄 + 상위 오답 몇 개. 길게 쓰지 않는다."""
    c = rev.get("counts", {})
    thr = []
    if rev.get("conf") is not None:
        thr.append(f"conf {rev['conf']:.2f}")
    if rev.get("iou") is not None:
        thr.append(f"IoU {rev['iou']:.2f}")
    # ★문구는 아직 영어다. 번역 표(msg.py)는 다른 갈래가 쥐고 있어 여기서 키를 더하지 않았다
    out = ["**Human review**", "",
           f"{rev.get('reviewed', 0)} reviewed"
           f" · model wrong {c.get('model_wrong', 0)}"
           f" · label wrong {c.get('label_wrong', 0)}"
           f" · unsure {c.get('unsure', 0)}"
           f" · ok {c.get('ok', 0)}"
           + (f" · labels fixed {rev['fixed']}" if rev.get("fixed") else "")
           + (" · " + " / ".join(thr) if thr else ""), ""]
    if rev.get("worst"):
        out += ["| Image | Score | Extra | Missed | Verdict |", "|---|---|---|---|---|"]
        for w in rev["worst"]:
            out.append(f"| {w['image']} | {fmt(w.get('score'), 3)} | {w.get('extra') if w.get('extra') is not None else '–'} | "
                       f"{w.get('missed') if w.get('missed') is not None else '–'} | {w.get('verdict') or ''} |")
        out.append("")
    return out


def _run_section(r: Run, a: Analysis | None, asset_dir: Path | None, rev: dict | None = None, n: int = 0) -> list[str]:
    out = [f"### {display_name(r)}", "",
           f"{tr(STATE_EN.get(r.state, r.state))} · {tr('epoch')} {r.epoch}/{r.total or '?'} · {r.source}", ""]
    if a is None:
        return out + ["_No results yet._", ""] + (_review_section(rev) if rev else [])
    if a.heads:
        out += [f"| {tr('Head')} | {tr('Best epoch')} | {tr('Precision')} | {tr('Recall')} | **F1** | mAP50 | mAP50-95 |",
                "|---|---|---|---|---|---|---|"]
        for h in a.heads:
            out.append(f"| {tr(HEAD_NAME.get(h.head, h.head))} | {h.best_epoch} | {fmt(h.precision)} | "
                       f"{fmt(h.recall)} | **{fmt(h.f1)}** | {fmt(h.map50)} | {fmt(h.map5095)} |")
        out.append("")
    if a.notes:
        out += ["**" + tr("What stands out") + "**", ""]
        for obs, todo in a.notes:
            out.append(f"* {obs}  \n  _{tr('Try:')}_ {todo}")
        out.append("")
    if asset_dir is not None and a.images:
        out += ["<details><summary>Charts</summary>", ""]
        # 번호를 붙인다. ★이름이 같은 학습(프로젝트마다 'train')끼리 그림 파일이 덮여 다른 학습의 곡선이 보였다
        safe = f"{n:03d}_" + "".join(c if c.isalnum() or c in "-_" else "_" for c in display_name(r))
        for key in SHOW_IMAGES:
            src = a.images.get(key)
            if not src:
                continue
            dst = asset_dir / f"{safe}__{src.name}"
            try:
                shutil.copy2(src, dst)
            except OSError:
                continue
            out.append(f"![{key}]({asset_dir.name}/{dst.name})")
        out += ["", "</details>", ""]
    if rev:
        out += _review_section(rev)
    return out


def build(runs: list[Run], asset_dir: Path | None = None, reviews: dict | None = None) -> str:
    now = time.strftime("%Y-%m-%d %H:%M")
    reviews = reviews or {}
    analyses = {id(r): (analyze(r.path) if readable(r) else None) for r in runs}
    active = [r for r in runs if r.state in ("running", "starting")]
    done = [r for r in runs if r.state == "done"]
    bad = [r for r in runs if r.state in ("stalled", "failed")]

    out = ["# " + tr("Training report · {now}", now=now), "",
           f"**{tr('{n} runs', n=len(runs))}** · {tr('{n} active', n=len(active))} · {tr('{n} done', n=len(done))}"
           + (" · " + tr("⚠ {n} need attention", n=len(bad)) if bad else ""), ""]

    # 비교표: 대표 헤드의 F1 순
    rows = []
    for r in runs:
        a = analyses[id(r)]
        h = a.heads[0] if a and a.heads else None
        # F1이 있으면 F1 순, 없으면 대표 점수 순(낮을수록 좋은 점수는 거꾸로).
        # ★F1만 봐서 Keras·HF 학습은 전부 '–'였고 순위도 뒤죽박죽이었다
        if h and h.f1 is not None:
            k = (0, -h.f1)
        elif r.best is not None:
            k = (1, r.best if getattr(r, "lower", False) else -r.best)
        else:
            k = (2, 0.0)
        rows.append((k, r, h))
    rows.sort(key=lambda t: t[0])
    out += ["## " + tr("Leaderboard"), "",
            f"| # | {tr('Run')} | {tr('State')} | {tr('Epoch')} | {tr('Score')} | **F1** | {tr('Precision')} | {tr('Recall')} | mAP50-95 | {tr('Trend')} |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for i, (_, r, h) in enumerate(rows, 1):
        score = f"{fmt(r.best)} {r.metric_name.split('/')[-1]}{' ↓' if getattr(r, 'lower', False) else ''}" if r.best is not None else "–"
        out.append(f"| {i} | {display_name(r)} | {tr(STATE_EN.get(r.state, r.state))} | {r.epoch}/{r.total or '?'} | {score} | "
                   f"**{fmt(h.f1 if h else None)}** | {fmt(h.precision if h else None)} | "
                   f"{fmt(h.recall if h else None)} | {fmt(h.map5095 if h else None)} | "
                   f"`{spark(r.history)}` |")
    out.append("")

    if bad:
        out += ["## " + tr("Needs attention"), ""]
        for r in bad:
            why = tr("loss became NaN") if r.state == "failed" else tr("no new epoch for a while")
            out.append(f"* **{display_name(r)}** ({r.source}): {why}")
        out.append("")

    out += ["## " + tr("Runs"), ""]
    for n, (_, r, _) in enumerate(rows, 1):
        out += _run_section(r, analyses[id(r)], asset_dir, reviews.get(str(r.path)), n)
    out += ["---",
            "_" + tr(FOOTNOTE) + "_",
            "", "_" + tr("Report generated with [Epokio](https://github.com/8rulerstar/epokio), a menu bar training monitor.") + "_", ""]
    return "\n".join(out)


def save(runs: list[Run], folder: Path | None = None, reviews: dict | None = None) -> Path:
    folder = folder or (Path.home() / "Desktop")
    stamp = time.strftime("%Y%m%d-%H%M")
    path = folder / f"training-report-{stamp}.md"
    assets = folder / f"training-report-{stamp}_files"
    assets.mkdir(parents=True, exist_ok=True)
    path.write_text(build(runs, assets, reviews), encoding="utf-8")
    return path
