"""W&B 로컬 기록(.wandb) 읽기. 파일 모양은 wandb 0.30.0으로 만든 실제 오프라인 기록과 대조해 확인했다(2026-09-30).
실제 파일은 호스트 이름·로컬 경로를 담고 있어 저장소에 넣지 않고, 같은 형식을 여기서 만든다."""
import json
import os
import zlib

from epokio import adapters, analysis, scan
from epokio.adapters_wandb import WandB


def _v(n):
    out = b""
    while True:
        b, n = n & 0x7F, n >> 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def _f(num, payload: bytes) -> bytes:           # 길이 붙은 필드
    return _v(num << 3 | 2) + _v(len(payload)) + payload


def _items(d: dict) -> bytes:
    return b"".join(_f(1, _f(1, k.encode()) + _f(16, json.dumps(v).encode())) for k, v in d.items())


def history(d):
    return _f(2, _items(d) + _f(2, _v(1 << 3) + _v(0)))


def config(d):
    return _f(5, _items({k: {"value": v} for k, v in d.items()}))


def write(path, records, block=32768):
    """LevelDB 로그 틀: 32KiB 블록, 블록에 안 들어가는 레코드는 처음·가운데·끝으로 나눈다"""
    data = bytearray(b":W&B" + (0xBEE1).to_bytes(2, "little") + b"\x00")
    for body in records:
        first = True
        while True:
            left = block - len(data) % block
            if left < 7:
                data += b"\x00" * left
                continue
            chunk, body = body[:left - 7], body[left - 7:]
            kind = (1 if not body else 2) if first else (4 if not body else 3)
            data += zlib.crc32(chunk).to_bytes(4, "little") + len(chunk).to_bytes(2, "little") + bytes([kind]) + chunk
            first = False
            if not body:
                break
    path.write_bytes(bytes(data))


def run(tmp_path, recs, name="offline-run-20260930_145135-h32dkwxl"):
    d = tmp_path / "wandb" / name
    d.mkdir(parents=True)
    write(d / f"run-{name[-8:]}.wandb", recs)
    return d


def test_epochs_take_the_last_value_logged_before_each_epoch_line(tmp_path):
    recs = [config({"lr": 1e-3, "epochs": 5, "model": "vit_b"})]
    for e in range(5):
        recs += [history({"train/loss": 2.0 - 0.1 * e - 0.01 * s, "_step": s}) for s in range(3)]
        recs.append(history({"epoch": e, "val/loss": 1.5 - 0.1 * e, "val/acc1": 60 + 3 * e}))
    got = adapters.load(run(tmp_path, recs))
    assert got.framework == "wandb" and got.total == 5 and got.args["model"] == "vit_b"
    assert got.rows[0] == {"epoch": "1", "train/train_loss": "1.98", "val/val_loss": "1.5", "metrics/val_acc1": "60"}
    assert analysis.analyze(run(tmp_path / "b", recs)).score["metric"] == "val_acc1"


def test_a_record_split_across_blocks_is_joined(tmp_path):
    big = config({"max_epochs": 3, "notes": "x" * 70000})                   # 32KiB 블록 두 개를 넘는다
    recs = [big] + [history({"epoch": e + 1, "train/loss": 1.0 / (e + 1), "val/top1": 50 + e}) for e in range(3)]
    got = adapters.load(run(tmp_path, recs))
    assert got.total == 3 and [r["epoch"] for r in got.rows] == ["1", "2", "3"]
    assert got.rows[-1]["metrics/val_top1"] == "52"


def test_runs_without_an_epoch_and_torn_files_are_skipped(tmp_path):
    assert adapters.load(run(tmp_path, [history({"loss": 0.5})])) is None      # epoch도 _step도 없다: x축이 없다
    d = run(tmp_path / "torn", [history({"epoch": 1, "train/loss": 0.5}), history({"epoch": 2, "train/loss": 0.4})])
    f = next(d.glob("*.wandb"))
    f.write_bytes(f.read_bytes()[:-5])                                       # 쓰는 중
    assert [r["epoch"] for r in WandB().load(d).rows] == ["1"]


def test_latest_run_link_does_not_show_the_run_twice(tmp_path):
    d = run(tmp_path, [history({"epoch": 1, "train/loss": 0.5})])
    try:
        os.symlink(d.name, d.parent / "latest-run", target_is_directory=True)
    except (OSError, NotImplementedError):
        return                                                              # 심링크를 못 만드는 환경(윈도우 개발자 모드 꺼짐)
    assert [r.name for r in scan.scan(tmp_path)] == [d.name]


def test_over_ssh_the_binary_arrives_and_unchanged_files_are_not_sent_again(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from test_ssh_source import FAKE_SSH
    from epokio import ssh_source
    fake = tmp_path / "fakessh.py"
    fake.write_text(FAKE_SSH)
    home = tmp_path / "server_home"
    d = run(home / "vit", [config({"epochs": 3})] + [history({"epoch": e + 1, "train/loss": 1.0 / (e + 1)}) for e in range(3)])
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(ssh_source, "MIRROR", tmp_path / "mirror")
    monkeypatch.setattr(ssh_source, "_HAVE", {})
    ssh = [sys.executable, str(fake)]
    got = ssh_source.run_remote("gpu", {"auto": True}, ssh=ssh, have=ssh_source.have_for("gpu"))
    ssh_source.apply("gpu", got)
    runs = scan.scan(ssh_source.mirror_dir("gpu"))
    assert [r.total for r in runs] == [3] and runs[0].epoch == 3                          # .wandb 가 깨지지 않고 왔다
    again = ssh_source.run_remote("gpu", {"auto": True}, ssh=ssh, have=ssh_source.have_for("gpu"))
    assert all(pair[1] is None for r in again["runs"] for pair in r["files"].values())     # 두 번째는 시각만
    ssh_source.apply("gpu", again)
    assert scan.scan(ssh_source.mirror_dir("gpu"))[0].epoch == 3
    for f in ssh_source.mirror_dir("gpu").rglob("*.wandb"):
        f.unlink()                                                                          # 비춤을 지우면 다시 받는다
    third = ssh_source.run_remote("gpu", {"auto": True}, ssh=ssh, have=ssh_source.have_for("gpu"))
    assert any(pair[1] for r in third["runs"] for pair in r["files"].values())
