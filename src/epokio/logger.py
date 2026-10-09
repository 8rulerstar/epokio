"""학습 코드에서 Epokio에 값을 남기는 작은 기록기(선택). 표준 라이브러리만 쓴다. 두 가지 쓰는 법이 있다.

1) 모듈 함수(한 줄 기록). 이 파일 하나를 학습 폴더에 복사해도 된다.

    import epokio                      # 또는: from epokio_log import log, image, params (이 파일을 복사했을 때)
    epokio.params(epochs=50, lr0=0.01) # 설정: 학습 기록 표·비교에 칸으로 나온다 (args.yaml)
    for epoch in range(1, 51):
        ...
        epokio.log(epoch, loss=l, val_loss=vl, val_acc=a)     # 곡선
        epokio.image("predictions", "pred.png", epoch)          # 상세 화면 그림 모음에

   쓰는 곳: epokio.init(폴더)로 정하거나, 환경 변수 EPOKIO_RUN_DIR, 없으면 ./runs/epokio/<시각>.
   Ultralytics 폴더(results.csv가 있는 곳)를 주면 그 에폭에 값이 더해진다(epokio_log.csv).

2) 기록기 객체(직접 짠 학습 전체를 ultralytics 모양 results.csv + args.yaml로).

    with epokio.start("runs/detr-small", epochs=50, lr=1e-4, batch=16) as run:   # 폴더와 args.yaml을 만든다
        for epoch in range(1, 51):                                              # 에폭은 1부터
            ...
            run.log(train_loss=tl, val_loss=vl, mAP50=m)                         # 에폭마다 한 줄. torch 텐서도 된다

   ultralytics·Hugging Face·Lightning·Keras가 아닌 학습(DETR, 손으로 짠 PyTorch 루프)도 목록·비교·알림·CSV에
   그대로 나온다. 어댑터를 새로 만들 필요가 없다.

서버·계정·네트워크는 쓰지 않는다. 파일만 쓴다.
★원칙: 이 기록기 때문에 사용자의 학습이 죽으면 안 된다. Logger.log()는 어떤 경우에도 예외를 던지지 않는다.
"""
from __future__ import annotations

import atexit
import csv
import os
import shutil
import sys
import time
from pathlib import Path

try:
    from .adapters import metric_column
except ImportError:                    # 이 파일만 복사해 쓸 때(패키지 밖). 열 이름을 간단한 규칙으로 만든다
    def metric_column(name: str, val: bool) -> str:
        return f"{'val' if val else 'metrics'}/{name}"

LOG_FILE = "epokio_log.csv"
MEDIA_DIR = "epokio_media"
_state = {"dir": None, "rows": {}, "keys": []}


def init(run_dir: str | os.PathLike | None = None) -> Path:
    """기록할 폴더를 정한다(없으면 만든다). 이미 기록이 있으면 이어서 쓴다"""
    d = Path(run_dir or os.environ.get("EPOKIO_RUN_DIR") or Path("runs") / "epokio" / time.strftime("%Y%m%d-%H%M%S"))
    d.mkdir(parents=True, exist_ok=True)
    _state.update(dir=d, rows={}, keys=[])
    f = d / LOG_FILE
    if f.exists():
        with f.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("epoch"):
                    _state["rows"][int(float(r["epoch"]))] = {k: v for k, v in r.items() if k != "epoch" and v != ""}
                    for k in r:
                        if k != "epoch" and k not in _state["keys"]:
                            _state["keys"].append(k)
    return d


def _dir() -> Path:
    return _state["dir"] or init()


def log(epoch: int, **values) -> None:
    """이 에폭의 값들. 같은 에폭을 다시 부르면 값이 더해진다(덮어씀). 숫자가 아닌 값은 건너뛴다"""
    row = _state["rows"].setdefault(int(epoch), {})
    for k, v in values.items():
        try:
            x = float(v.item() if hasattr(v, "item") else v)       # 텐서·numpy 값도
        except (TypeError, ValueError):
            continue
        row[k] = repr(x) if x == x else "nan"
        if k not in _state["keys"]:
            _state["keys"].append(k)
    _write()


def _write() -> None:
    d = _dir()
    tmp = d / (LOG_FILE + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["epoch", *_state["keys"]])
        for e in sorted(_state["rows"]):
            r = _state["rows"][e]
            w.writerow([e, *[r.get(k, "") for k in _state["keys"]]])
    tmp.replace(d / LOG_FILE)                                      # ★반쯤 쓴 파일을 읽지 않게 통째로 바꿔 넣는다


def image(name: str, path_or_image, epoch: int | None = None) -> Path:
    """그림 하나를 기록한다: 파일 경로, 또는 .save(path)가 있는 것(PIL 이미지·matplotlib 그림). 상세 화면 그림 모음에 나온다"""
    media = _dir() / MEDIA_DIR
    media.mkdir(exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:60] or "image"
    out = media / (f"{safe}_e{int(epoch):04d}.png" if epoch is not None else f"{safe}.png")
    if hasattr(path_or_image, "savefig"):
        path_or_image.savefig(out)
    elif hasattr(path_or_image, "save"):
        path_or_image.save(out)
    else:
        shutil.copyfile(path_or_image, out)
    return out


def params(**settings) -> None:
    """설정(한 줄짜리 값만). args.yaml로 남긴다: 학습 기록 표의 칸, 비교의 "서로 다른 설정", 계획 에폭(epochs)"""
    d = _dir()
    f = d / "args.yaml"
    old = {}
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if ":" in line and not line.startswith((" ", "-")):
                k, v = line.split(":", 1)
                old[k.strip()] = v.strip()
    old.update({k: str(v) for k, v in settings.items()})
    f.write_text("".join(f"{k}: {v}\n" for k, v in old.items()), encoding="utf-8")


# ---- 기록기 객체: epokio.start() ----

DONE_MARK = "epokio_done"              # 끝났다는 표시. 총 에폭을 모르는 학습도 '멎음' 경고가 나지 않게(scan.py가 본다)
FAIL_MARK = "epokio_failed"            # 예외로 죽었다는 표시. 내용은 "RuntimeError: CUDA out of memory"(scan_names.crash_reason이 읽는다)

# 검출 점수 이름을 ultralytics 모양으로(분석이 P·R·F1·mAP 표와 해설을 만든다). ★안 바꾸면 성적·해설이 비었다
_HEAD = {"precision": "precision", "recall": "recall", "map50": "mAP50", "map50-95": "mAP50-95", "map50_95": "mAP50-95",
         "map": "mAP50-95"}


def _num(v):
    """torch 텐서·numpy 값도 숫자로. ★텐서가 "tensor(0.6, device='cuda:0')" 글자로 들어가 곡선이 비었다"""
    if isinstance(v, (int, float)) or v is None:
        return v
    try:
        return float(v.item() if hasattr(v, "item") else v)
    except (TypeError, ValueError):
        return v


# 폴더 → 지금 그 폴더에 쓰는 기록기. ★노트북에서 셀을 다시 돌리면 옛 기록기가 끝날 때(atexit) 새 학습의 CSV를 덮었다
_ACTIVE: dict[str, "Logger"] = {}


def _mark_crashed(exc=None):
    """지금 쓰고 있는 기록기들에만 '예외로 죽었음'을 적는다.
    ★모듈 전체 깃발로 두었더니 대화형 파이썬에서 오류 한 번 뒤 그 뒤의 모든 학습이 '완료'를 못 받았다"""
    for lg in list(_ACTIVE.values()):
        lg._crashed = True
        lg._fail(exc)


def _watch_crashes():
    """★atexit은 예외·Ctrl+C로 죽어도 불린다. 그대로 두면 죽은 학습이 '완료'로 표시되고 '끝남' 알림이 갔다.
    주 스레드(sys.excepthook)와 다른 스레드(threading.excepthook)의 잡히지 않은 예외를 둘 다 본다"""
    import threading
    prev = sys.excepthook
    if not getattr(prev, "_epokio", False):
        def hook(t, v, tb):
            _mark_crashed(v)
            prev(t, v, tb)
        hook._epokio = True
        sys.excepthook = hook
    tprev = threading.excepthook
    if not getattr(tprev, "_epokio", False):
        def thook(args):
            _mark_crashed(args.exc_value)
            tprev(args)
        thook._epokio = True
        threading.excepthook = thook


def _in_notebook() -> bool:
    """주피터·IPython. 셀 오류는 sys.excepthook을 거치지 않아 죽은 학습도 커널을 끌 때 '완료'가 됐다.
    그래서 노트북에서는 끝날 때 자동으로 적지 않는다(`with`나 run.finish()로만)"""
    ip = sys.modules.get("IPython")
    try:
        return bool(ip and ip.get_ipython())
    except Exception:
        return False


class Logger:
    def __init__(self, folder: str | Path, epochs: int | None = None, notify: bool = False, **params):
        self.dir = Path(folder)
        self._notify = bool(notify)                 # 도우미 없이 이 프로세스가 폰 알림을 보낸다(selfnotify.py)
        if self._notify:
            from . import notify as _n, selfnotify
            if not [u for u in selfnotify._hooks().get("urls", []) if isinstance(u, str) and _n.valid(u)]:
                # 웹후크 없이 notify=True면 아무 말 없이 알림이 안 왔다
                print("epokio: notify=True but no webhook is saved, so no phone alert will be sent. "
                      "Add one with `epokio alerts --add <url>`.", file=sys.stderr)
        self.rows: list[dict] = []
        self.t0 = time.time()
        self._warned = False
        key = os.path.abspath(self.dir)
        old = _ACTIVE.get(key)
        if old is not None:                         # 같은 폴더의 옛 기록기는 이제 아무것도 쓰지 않는다
            old._retired = True
            atexit.unregister(old._at_exit)
        _ACTIVE[key] = self
        self._retired = False
        self._crashed = False
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / DONE_MARK).unlink(missing_ok=True)
            (self.dir / FAIL_MARK).unlink(missing_ok=True)
            (self.dir / "epokio_notified").unlink(missing_ok=True)
        except OSError as e:
            self._warn(e)
        # 같은 폴더로 다시 시작하면 옛 기록은 옆으로 치운다(지우지 않는다).
        # ★남겨 두면 첫 에폭이 끝날 때까지 옛 학습의 '완료·점수'가 그대로 보였다. 잠겨 있어도 아래 args.yaml은 쓴다
        # ★results.prev.csv 하나에 덮어써서 세 번째 실행이 첫 실행의 기록을 지웠다. 비어 있는 이름을 찾는다.
        #   ultralytics 학습 폴더를 가리켰다면 그 args.yaml도 치운다(덮어쓰면 그 학습의 설정이 사라졌다)
        def keep_aside(name: str, suffix: str):
            src = self.dir / name
            if not src.exists():
                return
            n, dst = 1, self.dir / f"{Path(name).stem}.prev{suffix}"
            while dst.exists():
                n += 1
                dst = self.dir / f"{Path(name).stem}.prev-{n}{suffix}"
            src.replace(dst)
        # 치우지 못하면(엑셀·백신이 잡고 있으면) 이 폴더에는 아무것도 쓰지 않는다.
        # ★경고만 하고 계속 써서, 진짜 ultralytics 학습의 args.yaml·results.csv를 백업 없이 덮었다
        self._blocked = False
        for name, suffix in (("results.csv", ".csv"), ("args.yaml", ".yaml")):
            try:
                f = self.dir / name
                if name == "args.yaml" and (not f.exists() or f.read_text(encoding="utf-8", errors="ignore").startswith("task: custom")):
                    continue                      # 우리가 쓴 것이면 그냥 새로 쓴다
                keep_aside(name, suffix)
            except OSError as e:
                self._blocked = True
                self._warn(OSError(f"{name} is in use, so nothing will be written here ({e})"))
                break                             # 하나라도 못 치웠으면 나머지도 건드리지 않는다
        if self._blocked:
            self.log = lambda *a, **k: None       # type: ignore[method-assign]  학습은 계속, 기록만 안 한다
            self.finish = lambda: None            # type: ignore[method-assign]
            self._auto = False                    # __exit__이 찾는다
            return
        try:
            lines = ["task: custom"] + ([f"epochs: {int(epochs)}"] if epochs else [])
            # data는 적지 않는다(웹·맥이 ultralytics 학습으로 보고 "다시 학습"을 내밀었다)
            lines += [f"{k}: {v}" for k, v in params.items() if k != "data" and "\n" not in str(v)]
            (self.dir / "args.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as e:
            self._warn(e)
        _watch_crashes()
        self._auto = not _in_notebook()
        if self._auto:
            atexit.register(self._at_exit)          # 스크립트가 끝나면 끝남 표시(예외로 죽었으면 안 남긴다)

    def _warn(self, e):
        if not self._warned:
            self._warned = True
            print(f"epokio: could not write to {self.dir} ({e}). Training continues; Epokio may not show this run.",
                  file=sys.stderr, flush=True)

    @staticmethod
    def _column(name: str) -> str:
        """이름을 Epokio 규칙의 열로: 손실은 train/·val/…_loss, 나머지는 metrics/(mae 같은 오차 지표는 낮을수록 좋은 점수)"""
        if "/" in name:                                      # 이미 규칙대로 쓴 이름(train/box_loss, metrics/mAP50(B))
            return name
        low = name.lower()
        if low in ("lr", "learning_rate"):                   # ★metrics/lr 이 '대표 점수'로 뽑혔다. ultralytics 이름으로
            return "lr/pg0"
        prefixes = ("train_", "val_", "valid_", "eval_", "test_")
        pre = next((p for p in prefixes if low.startswith(p)), "")
        bare = name[len(pre):]                               # val_loss → loss, valid_mae → mae
        head = _HEAD.get(bare.lower()) if pre != "train_" else None      # ★train_precision이 val 점수 칸을 덮었다
        if head:
            return f"metrics/{head}(B)"
        val = pre in ("val_", "valid_", "eval_", "test_") or low.startswith(("val", "valid", "eval", "test"))
        if "loss" in low:
            base = "total_loss" if bare.lower() == "loss" else bare if bare.endswith("_loss") else bare + "_loss"
            return f"{'val' if val else 'train'}/{base}"       # val_loss·valid_loss → val/total_loss (★예전엔 val/val_loss, val/valid_loss)
        col = metric_column(bare, val)
        return col if col.endswith("_loss") else metric_column(name, val)   # 손실류만 접두어를 뗀다(val_mae → metrics/val_mae)

    def log(self, epoch: int | None = None, **metrics) -> None:
        """한 에폭의 값. epoch를 안 주면 1, 2, 3… 차례로 센다(1부터). 실패해도 예외를 던지지 않는다."""
        if self._retired:                                     # 같은 폴더에 새 기록기가 생겼다
            return
        try:
            row = {"epoch": epoch if epoch is not None else len(self.rows) + 1,
                   "time": round(time.time() - self.t0, 3)}
            row.update({self._column(k): _num(v) for k, v in metrics.items()})
            self.rows.append(row)
            self._write()
        except Exception as e:                                # 기록 때문에 학습이 죽지 않게
            self._warn(e)

    def _write(self):
        cols = ["epoch", "time"] + sorted({k for r in self.rows for k in r} - {"epoch", "time"})
        tmp = self.dir / "results.csv.tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f:    # 열이 늘 수 있어 통째로 다시 쓴다(에폭 수만큼이라 작다)
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(self.rows)
        # ★윈도우는 다른 프로그램(agent, 엑셀)이 읽는 중인 파일을 바꿔치기하지 못한다(WinError 5).
        #   잠깐씩 다시 해 보고, 끝내 안 되면 이번 줄은 건너뛴다(다음 log에서 다시 쓴다)
        for i in range(20):
            try:
                tmp.replace(self.dir / "results.csv")
                return
            except PermissionError:
                time.sleep(0.05)
        raise PermissionError(f"{self.dir / 'results.csv'} is locked by another program")

    def finish(self) -> None:
        """끝났다고 적는다. 총 에폭을 모르거나 일찍 멈춘 학습이 '멎음' 경고를 받지 않게.
        노트북처럼 스크립트가 안 끝나는 곳에서는 루프 뒤에 직접 부르거나 `with`를 쓴다."""
        if self._retired or not self.rows:
            return
        try:
            self._write()
        except Exception as e:                                # CSV가 잠겨 있어도 끝남 표시는 따로 남긴다
            self._warn(e)
        from . import selfnotify
        if self._notify:
            selfnotify.claim(self.dir, "finished")         # 끝남 표시보다 먼저(도우미가 겹쳐 보내지 않게)
        try:
            (self.dir / FAIL_MARK).unlink(missing_ok=True)
            (self.dir / DONE_MARK).write_text(str(time.time()), encoding="utf-8")
        except Exception as e:
            self._warn(e)
        if self._notify:
            selfnotify.send(self.dir, "finished")

    def _fail(self, exc) -> None:
        """예외로 죽었다고 바로 적는다(종류: 첫 줄, 200자). ★3분 뒤 '멎음'으로만 보여 OOM인지 무엇인지 몰랐다.
        Ctrl+C(KeyboardInterrupt)는 실패가 아니라 사람이 멈춘 것이라 적지 않는다"""
        if self._retired or not isinstance(exc, Exception):
            return
        lines = str(exc).strip().splitlines()
        text = f"{type(exc).__name__}: {lines[0] if lines else ''}".rstrip(": ")[:200]
        from . import selfnotify
        if self._notify:
            selfnotify.claim(self.dir, "failed")
        try:
            (self.dir / FAIL_MARK).write_text(text, encoding="utf-8")
        except OSError as e:
            self._warn(e)
        if self._notify:
            selfnotify.send(self.dir, "failed")

    def _at_exit(self):
        """스크립트가 끝날 때. 예외로 죽었으면 '완료'가 아니다(실패·멎음이 맞다).
        sys.exit(1)처럼 오류 코드로 끝난 것은 여기서 가려낼 방법이 없다. 그런 스크립트는 with나 finish()를 쓴다"""
        if not self._crashed:
            self.finish()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc=None, *_):
        if exc_type is None:                                  # 예외로 끝났으면 끝남 표시를 남기지 않는다(실패가 맞다)
            self.finish()
        else:
            self._crashed = True
            self._fail(exc)
        if self._auto:
            atexit.unregister(self._at_exit)
        return False


class _Quiet:
    """분산 학습의 0번이 아닌 프로세스용. 아무것도 안 쓴다(★여러 프로세스가 같은 파일을 덮어써 값이 사라졌다)"""
    def __init__(self, folder):
        self.dir, self.rows = Path(folder), []           # run.dir을 읽는 코드가 0번 아닌 프로세스에서 죽지 않게
    def log(self, *a, **k): pass
    def finish(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False


def start(folder: str | Path, epochs: int | None = None, notify: bool = False, **params):
    """학습 하나를 시작한다. folder가 Epokio가 지켜보는 폴더(runs 등) 안에 있어야 목록에 보인다.
    분산 학습(torchrun)이면 RANK 0 프로세스만 기록한다.
    notify=True: 도우미 없이도 끝날 때·예외로 죽을 때 설정된 웹후크로 폰 알림(epokio alerts --add로 넣은 주소)"""
    rank = os.environ.get("RANK") or os.environ.get("LOCAL_RANK") or "0"
    if rank not in ("", "0"):
        return _Quiet(folder)
    return Logger(folder, epochs, notify=notify, **params)
