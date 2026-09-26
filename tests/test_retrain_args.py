"""다시 학습 요청 본문: args.yaml 전체를 타입 그대로, 위치 키만 빼고, 모델은 원래 값."""
import os
import time
from pathlib import Path

from epokio import jobs, retrain_args

ARGS = """task: detect
mode: train
model: yolov8s.pt
data: {data}
epochs: 100
batch: -1
imgsz: 640
device: null
project: /somewhere/runs
name: exp3
exist_ok: false
resume: false
save_dir: /somewhere/runs/exp3
freeze: [0, 1, 2]
hsv_h: 0.015
degrees: 5.0
fliplr: 0.5
amp: true
optimizer: auto
cfg: /no/such/custom.yaml
"""


def _run(tmp_path: Path, data: str, rows: int = 3, total: int = 100) -> Path:
    d = tmp_path / "exp3"
    (d / "weights").mkdir(parents=True)
    (d / "args.yaml").write_text(ARGS.format(data=data).replace("epochs: 100", f"epochs: {total}"))
    lines = ["epoch,train/box_loss,metrics/mAP50-95(B)"] + [f"{i},1.0,0.{i}" for i in range(1, rows + 1)]
    (d / "results.csv").write_text("\n".join(lines) + "\n")
    return d


def test_same_keeps_everything_typed(tmp_path):
    data = tmp_path / "data.yaml"
    data.write_text("names: [a]\n")
    got = retrain_args.same(_run(tmp_path, str(data)))
    p = got["params"]
    assert p["model"] == "yolov8s.pt" and got["model_ok"]        # yolo11s로 바뀌지 않는다
    assert p["device"] is None and p["freeze"] == [0, 1, 2]       # "None"·"[0, 1, 2]" 문자열이 아니다
    assert p["batch"] == -1 and p["amp"] is True and p["degrees"] == 5.0 and p["fliplr"] == 0.5
    assert p["data"] == str(data) and p["optimizer"] == "auto"
    for k in ("project", "name", "save_dir", "exist_ok", "resume", "mode"):
        assert k not in p and got["dropped"][k] == "run location"
    assert got["dropped"]["cfg"] == "missing path"
    assert got["kept"] == sorted(p)


def test_missing_model_path_asks_user(tmp_path):
    d = _run(tmp_path, "coco8.yaml")
    (d / "args.yaml").write_text((d / "args.yaml").read_text().replace("model: yolov8s.pt", "model: /gone/best.pt"))
    got = retrain_args.same(d)
    assert not got["model_ok"] and got["model"] == "/gone/best.pt" and "model" not in got["params"]
    assert got["params"]["data"] == "coco8.yaml"                  # 이름만 있는 데이터는 그대로


def test_resume_only_for_stopped_runs_with_last(tmp_path):
    d = _run(tmp_path, "coco8.yaml")
    assert retrain_args.resume_state(d)["resume_why"] == "no last.pt"
    (d / "weights" / "last.pt").write_bytes(b"x")
    old = time.time() - 7 * 86400
    for f in (d / "results.csv", d / "args.yaml"):
        os.utime(f, (old, old))
    got = retrain_args.resume(d)
    assert got["params"] == {"model": str(d / "weights" / "last.pt"), "resume": True}
    done = _run(tmp_path / "b", "coco8.yaml", rows=5, total=5)
    (done / "weights" / "last.pt").write_bytes(b"x")
    assert retrain_args.resume_state(done)["resume_why"] == "already finished"


def test_resume_job_writes_into_original_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "SCRIPTS", tmp_path / "scripts")
    last = tmp_path / "exp3" / "weights" / "last.pt"
    j = jobs.Job(id="r1", kind="train", name="exp3_resume", python="python", params={"model": str(last), "resume": True})
    jobs.build_command(j)
    assert j.output == str(tmp_path / "exp3")
    src = (tmp_path / "scripts" / "r1.py").read_text()
    assert '"project"' not in src and '"resume": true' in src
