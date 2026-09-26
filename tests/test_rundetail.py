"""학습 상세 API: 곡선·그림 목록을 제대로 주는지, 지켜보는 폴더 밖 파일은 절대 안 주는지."""
from pathlib import Path

from epokio import rundetail

CSV = """epoch,train/box_loss,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B),val/box_loss
1,1.5,0.4,0.3,0.35,0.20,1.6
2,1.2,0.6,0.5,0.55,0.30,1.3
3,1.0,0.7,0.6,0.65,0.40,1.1
"""


def _run(tmp: Path) -> Path:
    d = tmp / "runs" / "exp"
    (d / "weights").mkdir(parents=True)
    (d / "results.csv").write_text(CSV)
    (d / "args.yaml").write_text("task: detect\nmodel: yolo11n.pt\nepochs: 3\nimgsz: 640\n")
    for n in ("labels.jpg", "results.png", "zz.png", "notes.txt"):
        (d / n).write_bytes(b"x")
    (d / "weights" / "best.pt").write_bytes(b"x")
    return d


def test_detail(tmp_path):
    d = rundetail.detail(_run(tmp_path))
    assert d["columns"]["epoch"] == [1, 2, 3]
    assert d["columns"]["metrics/mAP50-95(B)"][-1] == 0.40
    assert d["heads"][0]["head"] == "B" and d["heads"][0]["best_epoch"] == 3
    assert d["images"] == ["results.png", "labels.jpg", "zz.png"]     # 정해 둔 순서 먼저, 그림만
    assert d["args"]["model"] == "yolo11n.pt" and d["args"]["epochs"] == "3"
    assert d["weights"].endswith("best.pt")


def test_inside_blocks_escape(tmp_path):
    run = _run(tmp_path)
    roots = [tmp_path / "runs"]
    assert rundetail.inside(run / "results.png", roots)
    assert not rundetail.inside(run / ".." / ".." / "secret.png", roots)
    assert not rundetail.inside(Path("/etc/hosts"), roots)


def test_inside_hangul_nfd_nfc(tmp_path):
    import unicodedata
    root = tmp_path / unicodedata.normalize("NFD", "교통표지판")
    (root / "train").mkdir(parents=True)
    nfc_root = Path(unicodedata.normalize("NFC", str(root)))
    assert rundetail.inside(root / "train", [nfc_root])
    assert rundetail.inside(Path(unicodedata.normalize("NFC", str(root / "train"))), [root])


def test_zero_val_loss_epochs_are_not_overfitting(tmp_path):
    """YOLO는 검증을 건너뛴 초반 에폭의 검증 손실을 0으로 적는다. 그걸 최저점으로 보면 안 된다."""
    from epokio import analysis
    d = tmp_path / "r"
    d.mkdir()
    rows = ["epoch,val/box_loss,metrics/mAP50-95(B)"] + [f"{i},0,0" for i in range(1, 6)] + \
           [f"{i},{2.0 - i * 0.05:.2f},{i / 100:.2f}" for i in range(6, 16)]
    (d / "results.csv").write_text("\n".join(rows) + "\n")
    notes = [o for o, _ in analysis.analyze(d).notes]
    assert not any("overfit" in n.lower() for n in notes)


def test_data_fingerprint_changes_when_a_label_changes(tmp_path):
    import os, time
    from epokio import versions
    ds = tmp_path / "ds"
    for sub in ("images/train", "labels/train", "images/val", "labels/val"):
        (ds / sub).mkdir(parents=True)
    (ds / "images/train/a.jpg").write_bytes(b"x")
    (ds / "labels/train/a.txt").write_text("0 0.5 0.5 0.1 0.1\n")
    y = ds / "data.yaml"
    y.write_text(f"path: {ds}\ntrain: images/train\nval: images/val\nnames:\n  0: a\n")
    a = versions.data_fingerprint(y)
    assert a == versions.data_fingerprint(y)                     # 그대로면 같다
    time.sleep(0.01)
    (ds / "labels/train/a.txt").write_text("0 0.5 0.5 0.2 0.2\n")   # 라벨 하나 고침
    os.utime(ds / "labels/train", None)
    assert versions.data_fingerprint(y) != a
