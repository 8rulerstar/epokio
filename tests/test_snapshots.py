"""에폭별 예측 사진: 학습 틀의 콜백(jobs_templates.add_snapshots)과 상세 화면용 읽기(rundetail.snapshots)."""
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

from epokio import rundetail
from epokio.jobs_templates import ENV_HELPERS, TRAIN_TEMPLATE


def _fakes(monkeypatch, calls):
    """ultralytics·cv2 없이: 예측한 이미지와 저장한 파일 이름만 기록한다"""
    u = types.ModuleType("ultralytics")
    uu = types.ModuleType("ultralytics.utils")
    uu.RANK = -1

    class YOLO:
        def __init__(self, w):
            self.w = w

        def predict(self, ims, **kw):
            calls.append(("predict", self.w, list(ims), kw["device"]))
            return [SimpleNamespace(plot=lambda: SimpleNamespace(shape=(960, 640, 3))) for _ in ims]
    u.YOLO, u.utils = YOLO, uu
    cv2 = types.ModuleType("cv2")
    cv2.IMWRITE_JPEG_QUALITY = 1
    cv2.resize = lambda im, size: SimpleNamespace(shape=(size[1], size[0], 3))
    cv2.imwrite = lambda path, im, *a: calls.append(("write", Path(path).name, im.shape[:2]))   # ★윈도우 경로는 \\
    for name, m in (("ultralytics", u), ("ultralytics.utils", uu), ("cv2", cv2)):
        monkeypatch.setitem(sys.modules, name, m)


def test_every_n_epochs_and_the_last_on_the_cpu_same_images(tmp_path, monkeypatch):
    calls, cbs = [], []
    _fakes(monkeypatch, calls)
    g = {}
    exec(ENV_HELPERS, g)
    g["add_snapshots"](SimpleNamespace(add_callback=lambda n, f: cbs.append((n, f))), 5)
    ims = [f"/v/{i}.jpg" for i in range(10)]
    tr = SimpleNamespace(epochs=12, last="/w/last.pt", save_dir=str(tmp_path), args=SimpleNamespace(imgsz=320),
                         validator=SimpleNamespace(dataloader=SimpleNamespace(dataset=SimpleNamespace(im_files=ims))))
    assert cbs[0][0] == "on_fit_epoch_end"
    for e in range(13):                               # 12는 학습 끝의 마지막 검증(epoch+1): 건너뛴다
        tr.epoch = e
        cbs[0][1](tr)
    preds = [c for c in calls if c[0] == "predict"]
    assert len(preds) == 3                            # 5, 10, 마지막 12
    assert all(p[2] == ["/v/0.jpg", "/v/2.jpg", "/v/5.jpg", "/v/7.jpg"] and p[3] == "cpu" and p[1] == "/w/last.pt" for p in preds)
    writes = [c for c in calls if c[0] == "write"]
    assert writes[0] == ("write", "e0005_0.jpg", (480, 320)) and writes[-1][1] == "e0012_3.jpg"


def test_a_failure_never_stops_training(tmp_path, monkeypatch, capsys):
    calls, cbs = [], []
    _fakes(monkeypatch, calls)
    g = {}
    exec(ENV_HELPERS, g)
    g["add_snapshots"](SimpleNamespace(add_callback=lambda n, f: cbs.append((n, f))), 1)
    cbs[0][1](SimpleNamespace(epoch=0, epochs=3, validator=None))
    assert "prediction snapshot skipped" in capsys.readouterr().out


def test_the_option_is_taken_out_before_ultralytics_sees_it(tmp_path, monkeypatch):
    seen = {}
    u = types.ModuleType("ultralytics")

    class YOLO:
        trainer = None

        def __init__(self, m):
            pass

        def add_callback(self, name, f):
            seen.setdefault("callbacks", []).append(name)

        def train(self, **p):
            seen["train"] = p
    u.YOLO = YOLO
    monkeypatch.setitem(sys.modules, "ultralytics", u)
    for snaps, n in ((5, 2), (0, 1)):
        seen.clear()
        p = {"model": "m.pt", "data": "d.yaml", "epokio_snapshots": snaps}
        exec(compile(ENV_HELPERS + TRAIN_TEMPLATE.format(params=json.dumps(p), git=False), "t", "exec"), {"__name__": "__main__"})
        assert "epokio_snapshots" not in seen["train"] and len(seen["callbacks"]) == n


def test_the_run_page_lists_them_by_epoch(tmp_path):
    assert rundetail.snapshots(tmp_path) is None
    d = tmp_path / "epokio_snapshots"
    d.mkdir()
    for n in ("e0010_1.jpg", "e0005_0.jpg", "e0010_0.jpg", "notes.txt", "eX_0.jpg"):
        (d / n).write_bytes(b"x")
    assert rundetail.snapshots(tmp_path) == {"epochs": [5, 10], "files": {"5": ["e0005_0.jpg"], "10": ["e0010_0.jpg", "e0010_1.jpg"]}}
