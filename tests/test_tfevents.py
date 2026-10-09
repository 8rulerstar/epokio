"""TensorBoard tfevents 읽기와 어댑터. 설치본(tensorboard·protobuf)이 없어 스펙대로 직접 인코딩한 파일로 시험한다.
인코더는 파서와 따로, protobuf wire 형식(varint·태그·길이)을 처음부터 쓴다.
_w_ 로 시작하는 인코더는 read() 쪽 시험용(다른 모양의 인자를 받는다)."""
import struct
import time
from pathlib import Path

from epokio import adapters, tfevents
from epokio.scan import read_run, scan
from epokio.tfevents import column, crc32c, masked_crc


def _vi(x):
    x &= (1 << 64) - 1
    out = bytearray()
    while True:
        b = x & 0x7F
        x >>= 7
        out.append(b | (0x80 if x else 0))
        if not x:
            return bytes(out)


def _f(no, wt, payload):
    key = _vi(no << 3 | wt)
    return key + (_vi(len(payload)) + payload if wt == 2 else payload)


def _value(tag, simple=None, tensor=None, image=False):
    b = _f(1, 2, tag.encode())
    if simple is not None:
        b += _f(2, 5, struct.pack("<f", simple))
    if tensor is not None:
        b += _f(8, 2, tensor)
    if image:
        b += _f(4, 2, _f(1, 0, _vi(2)) + _f(4, 2, b"\x89PNG"))
    return b


def _tensor_floatval(x):                     # torch SummaryWriter(new_style) 모양: dtype FLOAT, shape 빈 것, float_val packed
    return _f(1, 0, _vi(1)) + _f(2, 2, b"") + _f(5, 2, struct.pack("<f", x))


def _tensor_content(x):                      # TF2 tf.summary.scalar 모양: dtype FLOAT, tensor_content 4바이트
    return _f(1, 0, _vi(1)) + _f(2, 2, b"") + _f(4, 2, struct.pack("<f", x))


def _event(wall, step, values=(), version=None):
    b = _f(1, 1, struct.pack("<d", wall)) + _f(2, 0, _vi(step))
    if version:
        b += _f(3, 2, version.encode())
    if values:
        b += _f(5, 2, b"".join(_f(1, 2, v) for v in values))
    return b


def _record(data):
    head = struct.pack("<Q", len(data))
    return head + struct.pack("<I", masked_crc(head)) + data + struct.pack("<I", masked_crc(data))


def _write(p, events):
    p.write_bytes(b"".join(_record(e) for e in events))


def test_crc32c_known_vector():
    assert crc32c(b"123456789") == 0xE3069283           # RFC 3720 검사값
    assert crc32c(b"") == 0


def test_step_mode_simple_and_tensor(tmp_path):
    f = tmp_path / "events.out.tfevents.1700000000.host.1.0"
    _write(f, [
        _event(1000.0, 0, version="brain.Event:2"),
        _event(1000.0, 10, [_value("train/loss", 0.9), _value("lr", 0.01), _value("img", image=True)]),
        _event(1005.5, 20, [_value("train/loss", tensor=_tensor_floatval(0.7))]),
        _event(1006.0, 20, [_value("eval/accuracy", tensor=_tensor_content(0.8)), _value("eval/loss", 0.6)]),
    ])
    got = adapters.load(tmp_path)
    assert got.framework == "tensorboard" and got.warnings == [] and got.args["x_axis"] == "step"
    assert [r["epoch"] for r in got.rows] == ["10", "20"]
    r = got.rows[1]
    assert abs(float(r["train/loss"]) - 0.7) < 1e-6 and abs(float(r["metrics/accuracy"]) - 0.8) < 1e-6
    assert abs(float(r["val/loss"]) - 0.6) < 1e-6 and r["time"] == "6"
    assert not any("lr" in k or "img" in k for k in got.rows[0])


def test_epoch_tag_groups_steps(tmp_path):
    f = tmp_path / "events.out.tfevents.1.h"
    evs = []
    for s in range(1, 7):
        evs.append(_event(float(s), s * 100, [_value("train/loss", 1.0 / s), _value("train/epoch", s / 2)]))
    evs.append(_event(7.0, 600, [_value("eval/loss", 0.3), _value("eval/f1", 0.9)]))
    _write(f, evs)
    got = adapters.load(tmp_path)
    assert got.args == {"x_axis": "epoch", "epoch_tag": "train/epoch"}
    assert [r["epoch"] for r in got.rows] == ["1", "2", "3"]      # epoch 0.5,1.0 -> 1 / 1.5,2.0 -> 2 / ...
    assert got.rows[-1]["val/loss"] == "0.3"
    assert "metrics/f1" in got.rows[-1] and "metrics/train_epoch" not in got.rows[-1]


def test_keras_train_validation_dirs(tmp_path):
    for sub, vals in (("train", (0.5, 0.3)), ("validation", (0.6, 0.4))):
        (tmp_path / sub).mkdir()
        _write(tmp_path / sub / "events.out.tfevents.9.h.v2",
               [_event(1.0 + e, e, [_value("epoch_loss", tensor=_tensor_content(v)),
                                    _value("epoch_accuracy", tensor=_tensor_content(0.7 + e / 10))])
                for e, v in enumerate(vals)])
    got = adapters.load(tmp_path)
    assert got.framework == "tensorboard" and [r["epoch"] for r in got.rows] == ["1", "2"]
    r = got.rows[0]
    assert set(r) == {"epoch", "time", "train/loss", "val/loss", "metrics/accuracy", "metrics/train_accuracy"}


def test_incremental_read_and_partial_record(tmp_path):
    f = tmp_path / "events.out.tfevents.2.h"
    first = _record(_event(1.0, 1, [_value("loss", 0.5)]))
    second = _record(_event(2.0, 2, [_value("loss", 0.4)]))
    f.write_bytes(first + second[:10])                   # 둘째 레코드를 쓰는 중
    ev, bad = tfevents.read_scalars(f)
    assert [e[1] for e in ev] == [1] and bad == 0
    st = tfevents._CACHE[f]
    assert st.offset == len(first)
    with f.open("ab") as h:
        h.write(second[10:])
    ev, bad = tfevents.read_scalars(f)
    assert [e[1] for e in ev] == [1, 2] and st.offset == len(first) + len(second)


def test_corrupt_record_warns(tmp_path):
    f = tmp_path / "events.out.tfevents.3.h"
    good = _record(_event(1.0, 1, [_value("loss", 0.5)]))
    bad = bytearray(_record(_event(2.0, 2, [_value("loss", 0.4)])))
    bad[-6] ^= 0xFF                                      # 데이터 한 바이트를 깨뜨린다
    f.write_bytes(good + bytes(bad))
    got = adapters.load(tmp_path)
    assert got.rows == [{"epoch": "1", "train/loss": "0.5", "time": "0"}] and got.warnings


def test_ultralytics_folder_prefers_results_csv(tmp_path):
    (tmp_path / "results.csv").write_text("epoch,train/box_loss,metrics/mAP50-95(B)\n1,0.5,0.3\n")
    _write(tmp_path / "events.out.tfevents.4.h", [_event(1.0, 1, [_value("loss", 0.5)])])
    assert adapters.detect(tmp_path).name == "ultralytics"


def test_tag_mapping():
    cases = {
        ("loss", None): "train/loss", ("val_loss", None): "val/val_loss", ("train/loss", None): "train/loss",
        ("eval/accuracy", None): "metrics/accuracy", ("eval_accuracy", None): "metrics/accuracy",
        ("eval_loss", None): "val/eval_loss", ("val_accuracy", None): "metrics/val_accuracy",
        ("Loss/train", None): "train/Loss", ("Accuracy/test", None): "metrics/Accuracy",
        ("epoch_loss", "val"): "val/loss", ("epoch_accuracy", "train"): "metrics/train_accuracy",
        ("metrics/mAP50(B)", None): "metrics/mAP50(B)", ("val/box_loss", None): "val/box_loss",
        ("lr", None): None, ("train/learning_rate", None): None, ("train/grad_norm", None): None, ("epoch", None): None,
    }
    for (tag, side), want in cases.items():
        assert column(tag, side) == want, tag


def test_big_file_incremental_is_fast(tmp_path):
    import time
    f = tmp_path / "events.out.tfevents.5.h"
    _write(f, [_event(float(s), s, [_value("loss", 1.0 / (s + 1)), _value("val_loss", 0.5)]) for s in range(20000)])
    t = time.perf_counter()
    tfevents.read_scalars(f)
    full = time.perf_counter() - t
    with f.open("ab") as h:
        h.write(_record(_event(1.0, 20000, [_value("loss", 0.01)])))
    t = time.perf_counter()
    ev, _ = tfevents.read_scalars(f)
    inc = time.perf_counter() - t
    assert len(ev) == 40001 and inc < full / 10


# ---- read(): 가벼운 읽기와 Lightning·HF·Keras 폴더 ----


def _varint(n: int) -> bytes:
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out += bytes([b | 0x80])
        else:
            return out + bytes([b])


def _field(num: int, wt: int, payload: bytes) -> bytes:
    key = _varint(num << 3 | wt)
    return key + (_varint(len(payload)) + payload if wt == 2 else payload)


def _w_value(tag: str, v: float, tf2: bool = False) -> bytes:
    body = _field(1, 2, tag.encode())
    if tf2:                                   # TF2: tensor(dtype=float, float_val=[v])
        tensor = _field(1, 0, _varint(1)) + _field(5, 5, struct.pack("<f", v))
        body += _field(8, 2, tensor)
    else:                                     # PyTorch SummaryWriter: simple_value
        body += _field(2, 5, struct.pack("<f", v))
    return body


def _w_event(step: int, wall: float, values: dict, tf2: bool = False) -> bytes:
    summary = b"".join(_field(1, 2, _w_value(t, v, tf2)) for t, v in values.items())
    return _field(1, 1, struct.pack("<d", wall)) + _field(2, 0, _varint(step)) + _field(5, 2, summary)


def _w_record(data: bytes) -> bytes:
    """진짜 파일처럼 CRC를 넣는다(read_scalars·어댑터는 CRC를 본다. read()는 보지 않는다)"""
    head = struct.pack("<Q", len(data))
    return head + struct.pack("<I", masked_crc(head)) + data + struct.pack("<I", masked_crc(data))


def _w_write(path: Path, events, mode="wb"):
    with path.open(mode) as f:
        for e in events:
            f.write(_w_record(_w_event(*e)))


def test_lightning_default_logger_runs_are_seen(tmp_path):
    """★Lightning의 기본 기록기(TensorBoard)만 쓴 학습은 목록에 아예 안 보였다"""
    d = tmp_path / "lightning_logs" / "version_0"
    d.mkdir(parents=True)
    (d / "hparams.yaml").write_text("max_epochs: 3\n", encoding="utf-8")
    t = time.time() - 100
    f = d / "events.out.tfevents.1700000000.pc.1.0"
    _w_write(f, [
        (10, t, {"train_loss_step": 1.2, "epoch": 0, "lr-Adam": 0.1}),
        (49, t + 10, {"val_loss": 1.0, "val_acc": 0.5, "epoch": 0, "train_loss_epoch": 1.1}),
        (99, t + 20, {"val_loss": 0.8, "val_acc": 0.7, "epoch": 1, "train_loss_epoch": 0.9}, True),   # TF2 모양도
    ])
    runs = scan(tmp_path)
    assert len(runs) == 1
    r = runs[0]
    assert r.framework == "tensorboard" and r.epoch == 2 and r.total == 3
    assert r.metric_name == "metrics/val_acc" and abs(r.best - 0.7) < 1e-6        # 학습률은 점수가 아니다
    rows = adapters.load(d).rows
    assert rows[-1]["train/train_loss"] and rows[-1]["val/val_loss"]
    # 학습이 이어지면 새로 붙은 부분만 읽는다
    _w_write(f, [(149, t + 30, {"val_loss": 0.7, "val_acc": 0.8, "epoch": 2})], mode="ab")
    r = read_run(d)
    assert r.epoch == 3 and r.state == "done"


def test_huggingface_runs_without_trainer_state_are_seen_once(tmp_path):
    """trainer_state.json 없이 TensorBoard만 남긴 HF 학습도 보인다. 있으면 HF 쪽이 읽고 두 번 보이지 않는다"""
    out = tmp_path / "out"
    d = out / "runs" / "Sep25_10-00-00_pc"
    d.mkdir(parents=True)
    t = time.time() - 50
    _w_write(d / "events.out.tfevents.1.pc", [
        (100, t, {"train/loss": 2.0, "train/epoch": 0.5, "train/learning_rate": 1e-4}),
        (200, t + 5, {"eval/loss": 1.5, "eval/accuracy": 0.6, "train/epoch": 1.0, "eval/runtime": 3.0}),
    ])
    runs = scan(tmp_path)
    assert [r.framework for r in runs] == ["tensorboard"]
    assert runs[0].metric_name == "metrics/accuracy" and runs[0].epoch == 1     # HF 어댑터와 같은 이름(eval_accuracy → metrics/accuracy)
    (out / "trainer_state.json").write_text('{"log_history": [{"eval_loss": 1.5, "epoch": 1.0}], "epoch": 1.0}')
    assert [r.framework for r in scan(tmp_path)] == ["huggingface"]


def test_a_half_written_record_is_read_later(tmp_path):
    f = tmp_path / "events.out.tfevents.x"
    whole = _w_record(_w_event(1, 1.0, {"val_loss": 0.5}))
    f.write_bytes(whole[:-6])                        # 쓰는 중
    assert tfevents.read(f)[0] == {}
    f.write_bytes(whole)
    assert tfevents.read(f)[0] == {1: {"val_loss": 0.5}}


def test_a_tensor_with_a_shape_is_not_a_score(tmp_path):
    """★모양을 안 봐서 PR 곡선(6×127 텐서)의 첫 값(참양성 수)이 '대표 점수'로 뽑혔다. float16 숫자 하나는 읽는다"""
    def tensor_value(tag, tensor):
        return _field(1, 2, tag.encode()) + _field(8, 2, tensor)
    dim = _field(2, 2, _field(1, 0, _varint(6)))                       # shape { dim { size: 6 } }
    pr = _field(1, 0, _varint(1)) + _field(2, 2, dim) + _field(5, 2, struct.pack("<3f", 16.0, 3.0, 1.0))
    half = _field(1, 0, _varint(19)) + _field(4, 2, struct.pack("<e", 0.5))
    summary = _field(1, 2, tensor_value("val_pr", pr)) + _field(1, 2, tensor_value("val_half", half))
    f = tmp_path / "events.out.tfevents.y"
    f.write_bytes(_w_record(_field(1, 1, struct.pack("<d", 1.0)) + _field(2, 0, _varint(3)) + _field(5, 2, summary)))
    assert tfevents.read(f)[0] == {3: {"val_half": 0.5}}


def test_keras_train_and_validation_folders_are_one_run(tmp_path):
    """★Keras TensorBoard 콜백의 train/·validation/ 이 학습 두 개로 보였고, 검증 손실이 train 쪽으로 들어갔다"""
    log = tmp_path / "logs" / "fit"
    (log / "train").mkdir(parents=True)
    (log / "validation").mkdir()
    t = time.time() - 30
    _w_write(log / "train" / "events.out.tfevents.1.pc.v2", [
        (0, t, {"epoch_loss": 1.0, "epoch_accuracy": 0.5, "epoch_learning_rate": 0.01}, True),
        (1, t + 5, {"epoch_loss": 0.8, "epoch_accuracy": 0.6}, True)])
    _w_write(log / "validation" / "events.out.tfevents.2.pc.v2", [
        (0, t + 1, {"epoch_loss": 1.1, "epoch_accuracy": 0.45, "evaluation_loss_vs_iterations": 1.1}, True),
        (1, t + 6, {"epoch_loss": 0.9, "epoch_accuracy": 0.55}, True)])
    runs = scan(tmp_path)
    assert len(runs) == 1 and runs[0].path == log
    r = runs[0]
    assert r.epoch == 2 and r.metric_name == "metrics/accuracy" and abs(r.best - 0.55) < 1e-6
    row = adapters.load(log).rows[-1]
    assert row["val/loss"] and row["train/loss"] and "metrics/train_accuracy" in row      # 폴더가 쪽을 정한다(column 규칙)


def test_a_hostile_file_does_not_hang_the_reader(tmp_path):
    """★길이 제한 없는 varint가 0xFF로 채운 기록에서 큰 정수를 계속 키워, 640KB에 27초가 걸렸다(감시 스레드가 멈춤)"""
    f = tmp_path / "events.out.tfevents.bad"
    f.write_bytes(_w_record(b"\xff" * 700_000) + _w_record(_w_event(5, 1.0, {"val_loss": 0.25})))
    t0 = time.time()
    got = tfevents.read(f)[0]
    assert time.time() - t0 < 2 and got == {5: {"val_loss": 0.25}}


def test_memory_stays_small_on_a_long_run(tmp_path):
    """★모든 걸음×태그를 들고 있어 30만 걸음 파일 하나에 268MB였다. 검증 걸음과 줄인 학습 걸음만 남긴다"""
    f = tmp_path / "events.out.tfevents.long"
    evs = [(s, float(s), {"train_loss": 1.0 / (s + 1), "epoch": s // 1000}) for s in range(20000)]
    evs += [(s, float(s), {"val_loss": 0.5, "val_acc": s / 20000}) for s in range(999, 20000, 1000)]
    _w_write(f, sorted(evs, key=lambda e: e[0]))
    sc, walls = tfevents.read(f)
    assert len(sc) <= tfevents.KEEP_TRAIN + 20 and len(walls) <= tfevents.KEEP_TRAIN + 20
    assert sc[19999]["val_acc"] > 0.99 and "train_loss" in sc[19999]                 # 검증 걸음엔 그때의 학습 값도


def test_tensorboard_runs_come_over_ssh_and_find_their_epochs_in_args(tmp_path, monkeypatch):
    """★SSH 원격 보기가 tfevents를 안 가져와 서버의 TensorBoard 학습이 안 보였다. 계획 에폭은 같은 폴더 args.json에서"""
    import json
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from test_ssh_source import FAKE_SSH
    from epokio import ssh_source
    fake = tmp_path / "fakessh.py"
    fake.write_text(FAKE_SSH)
    home = tmp_path / "server_home"
    d = home / "exp" / "vit_run"
    d.mkdir(parents=True)
    (d / "args.json").write_text(json.dumps({"lr": 1e-3, "epochs": 30}))
    t = time.time() - 100
    _w_write(d / "events.out.tfevents.1700000000.gpu.1.0", [
        (49, t, {"val_loss": 1.0, "val_acc": 0.5, "epoch": 0, "train_loss_epoch": 1.1}),
        (99, t + 20, {"val_loss": 0.8, "val_acc": 0.7, "epoch": 1, "train_loss_epoch": 0.9}),
    ])
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(ssh_source, "MIRROR", tmp_path / "mirror")
    monkeypatch.setattr(ssh_source, "_HAVE", {})
    got = ssh_source.run_remote("gpu", {"auto": True}, ssh=[sys.executable, str(fake)])
    ssh_source.apply("gpu", got)
    runs = scan(ssh_source.mirror_dir("gpu"))
    assert [(r.framework, r.epoch, r.total) for r in runs] == [("tensorboard", 2, 30)]


def test_an_epoch_scalar_that_starts_at_one_is_not_shifted(tmp_path):
    """★직접 1부터 적은 epoch 값에 Lightning처럼 +1을 해서 '20에폭 중 21에폭'이 됐다"""
    d = tmp_path / "vit"
    d.mkdir()
    (d / "config.yaml").write_text("epochs: 20\n")
    t = time.time() - 100
    _w_write(d / "events.out.tfevents.1700000000.pc.1.0",
             [(10 * e, t + e, {"epoch": e, "val/acc1": 50 + e}) for e in range(1, 21)])
    r = read_run(d)
    assert r.epoch == 20 and r.total == 20


def test_two_evaluations_in_one_hf_epoch_keep_the_best_score(tmp_path):
    """★HF식 TensorBoard(한 에폭에 평가 두 번)에서 1.5에폭의 최고 점수가 같은 에폭 2.0의 평가에 덮였다.
    점수는 그 에폭의 가장 좋은 값(낮을수록 좋은 것은 가장 낮은 값), 손실은 예전처럼 나중 값"""
    d = tmp_path / "out" / "runs" / "Oct01_10-00-00_pc"
    d.mkdir(parents=True)
    t = time.time() - 50
    _w_write(d / "events.out.tfevents.1.pc", [
        (50, t, {"eval/loss": 1.2, "eval/accuracy": 0.5, "eval/rmse": 0.9, "train/epoch": 0.5}),
        (100, t + 1, {"eval/loss": 1.0, "eval/accuracy": 0.6, "eval/rmse": 0.8, "train/epoch": 1.0}),
        (150, t + 2, {"eval/loss": 0.8, "eval/accuracy": 0.9, "eval/rmse": 0.3, "train/epoch": 1.5}),
        (200, t + 3, {"eval/loss": 0.85, "eval/accuracy": 0.7, "eval/rmse": 0.5, "train/epoch": 2.0}),
    ])
    r = read_run(d)
    assert r.metric_name == "metrics/accuracy" and abs(r.best - 0.9) < 1e-6 and r.best_epoch == 2
    rows = adapters.load(d).rows
    assert rows[1]["metrics/rmse"] == "0.3" and rows[1]["val/loss"] == "0.85" and rows[0]["metrics/accuracy"] == "0.6"


def test_settings_table_shows_hparams_not_internal_keys(tmp_path):
    """★TensorBoard·Lightning 학습의 '사용한 설정'이 hparams.yaml(lr·batch_size)은 빼고 x_axis·epoch_tag만 보였다"""
    from epokio import rundetail
    now = time.time()
    tb = tmp_path / "lightning_logs" / "version_0"
    tb.mkdir(parents=True)
    (tb / "hparams.yaml").write_text("lr: 0.001\nbatch_size: 32\nmax_epochs: 10\nmodel:\n  depth: 4\n", encoding="utf-8")
    ev = [_event(now - 300, 0, version="brain.Event:2")]
    for e in range(4):
        ev.append(_event(now - 300 + e * 60, (e + 1) * 30, [_value("val_loss", 0.9 / (e + 1)), _value("val_acc", 0.5 + 0.04 * e),
                                                            _value("epoch", float(e))]))
    _write(tb / f"events.out.tfevents.{int(now)}.host.1.0", ev)
    args = rundetail.detail(tb)["args"]
    assert args.get("lr") == "0.001" and args.get("batch_size") == "32" and args.get("max_epochs") == "10"
    assert "x_axis" not in args and "epoch_tag" not in args and "model" not in args   # 여러 줄 값은 뺀다
    csv = tmp_path / "csv_logs" / "version_0"
    csv.mkdir(parents=True)
    (csv / "hparams.yaml").write_text("lr: 0.01\n", encoding="utf-8")
    (csv / "metrics.csv").write_text("epoch,step,val_loss,val_acc\n0,10,0.9,0.5\n1,20,0.8,0.6\n", encoding="utf-8")
    assert rundetail.detail(csv)["args"] == {"lr": "0.01"}               # CSVLogger 학습은 설정 표가 아예 없었다
