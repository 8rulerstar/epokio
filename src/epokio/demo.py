"""예시 학습 만들기: 학습이 하나도 없는 첫 실행에서 모든 화면을 먼저 체험하게(애플 앱들의 예시 콘텐츠처럼).
~/.epokio/demo/ 에 기록 파일만 만든다(이미지·가중치 없음). "예시 지우기"로 폴더째 지운다.
세 개: 잘 끝난 학습 · 과적합한 학습 · 첫 학습에서 이어 한 학습(계보가 보이게)
그리고 진행 중인 학습 하나(sample_live): agent 안의 데몬 스레드가 몇 초마다 에폭 한 줄씩 덧붙여
진행률·ETA·캐릭터 달리기·완료 알림을 실제처럼 보여 준다. 지우기나 agent 종료 때 같이 멈춘다.
"""
from __future__ import annotations

import math
import shutil
import threading
import time
from pathlib import Path

DIR = Path.home() / ".epokio" / "demo"
HEAD = ("epoch,time,train/box_loss,train/cls_loss,train/dfl_loss,metrics/precision(B),metrics/recall(B),"
        "metrics/mAP50(B),metrics/mAP50-95(B),val/box_loss,val/cls_loss,val/dfl_loss")


def _rows(n: int, top: float, overfit: bool) -> str:
    out = [HEAD]
    for e in range(1, n + 1):
        t = e / n
        g = top * (1 - math.exp(-5 * t))                           # 점수는 빨리 오르다 눕는다
        tr = 1.6 * math.exp(-2.2 * t) + 0.35
        va = tr + (1.6 * max(0, t - 0.4) if overfit else 0.05)      # 과적합: 40% 뒤부터 검증 손실이 뚜렷이 오른다
        if overfit and t > 0.55:
            g -= 0.08 * (t - 0.55)
        out.append(f"{e},{e * 38.2:.1f},{tr:.4f},{tr * 1.3:.4f},{tr * 0.9:.4f},{min(g + 0.08, 1):.4f},{g * 0.95:.4f},"
                   f"{min(g * 1.35, 1):.4f},{g:.4f},{va:.4f},{va * 1.3:.4f},{va * 0.9:.4f}")
    return "\n".join(out) + "\n"


LIVE = "sample_live"
LIVE_EPOCHS = 45
LIVE_SEC = 4.0          # 45에폭 x 4초 = 3분. 멈춤 판정(최소 2분)보다 한참 짧은 간격
_live: tuple[threading.Thread, threading.Event] | None = None
_lock = threading.Lock()


def _write_live(d: Path, n: int, sec: float, stop: threading.Event):
    """완성 곡선을 미리 만들어 두고 앞에서부터 한 줄씩 공개한다(원자적 교체라 반쯤 쓴 줄이 안 읽힌다)"""
    lines = _rows(n, 0.58, False).splitlines()
    for i in range(1, len(lines)):                         # time 열을 실제 간격으로(ETA가 맞게)
        c = lines[i].split(",")
        c[1] = f"{i * sec:.1f}"
        lines[i] = ",".join(c)
    for e in range(1, n + 1):
        if stop.wait(sec):
            return
        try:
            tmp = d / "results.csv.tmp"
            tmp.write_text("\n".join(lines[:e + 1]) + "\n", encoding="utf-8")
            tmp.replace(d / "results.csv")
        except OSError:                                    # 폴더가 지워졌다
            return


def start_live(n: int | None = None, sec: float | None = None) -> str:
    global _live
    n, sec = n or LIVE_EPOCHS, sec or LIVE_SEC
    stop_live()
    d = DIR / LIVE
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)               # 이전 실행에서 멈춘 채 남은 것은 처음부터
    (d / "weights").mkdir(parents=True, exist_ok=True)
    (d / "args.yaml").write_text(f"task: detect\nmodel: yolo11n.pt\ndata: demo/helmets.yaml\nepochs: {n}\nimgsz: 640\nbatch: 16\nname: {LIVE}\n",
                                 encoding="utf-8")
    (d / "results.csv").write_text(HEAD + "\n", encoding="utf-8")
    ev = threading.Event()
    t = threading.Thread(target=_write_live, args=(d, n, sec, ev), name="epokio-demo-live", daemon=True)
    with _lock:
        _live = (t, ev)
    t.start()
    return str(d)


def stop_live():
    global _live
    with _lock:
        cur, _live = _live, None
    if cur:
        cur[1].set()
        cur[0].join(timeout=5)


def live_running() -> bool:
    return bool(_live and _live[0].is_alive())


def create() -> list[str]:
    runs = [("helmet_first", 40, 0.52, False, "yolo11n.pt"),
            ("helmet_overfit", 60, 0.47, True, "yolo11n.pt"),
            ("helmet_finetune", 30, 0.61, False, str(DIR / "helmet_first" / "weights" / "best.pt"))]
    made = []
    for name, n, top, over, model in runs:
        d = DIR / name
        (d / "weights").mkdir(parents=True, exist_ok=True)
        (d / "results.csv").write_text(_rows(n, top, over), encoding="utf-8")
        (d / "args.yaml").write_text(f"task: detect\nmodel: {model}\ndata: demo/helmets.yaml\nepochs: {n}\nimgsz: 640\nbatch: 16\nname: {name}\n",
                                     encoding="utf-8")
        (d / "weights" / "best.pt").write_bytes(b"demo")         # 계보용 표시(진짜 가중치 아님)
        made.append(str(d))
    made.append(start_live())
    return made


def remove() -> bool:
    stop_live()
    if DIR.is_dir():
        shutil.rmtree(DIR)
        return True
    return False
