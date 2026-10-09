"""학습별 기계 기록(sysrec.py): 도는 학습 몫으로 15초에 한 번, 화면용 읽기, GPU를 못 쓴 학습의 해설."""
from types import SimpleNamespace

from epokio import sysrec


def snap(gpu=40.0, fan=None):
    return SimpleNamespace(gpus=[SimpleNamespace(util=gpu, mem_used=2.0, mem_total=8.0, temp=70.0)], cpu=30.0,
                           mem_used=8.0, mem_total=16.0, cpu_temp=None, fan=fan)


def test_one_sample_per_run_every_15_seconds(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert sysrec.record([a, b], snap(), now=100) == 2
    assert sysrec.record([a, b], snap(), now=110) == 0
    assert sysrec.record([a], snap(), now=116) == 1
    r = sysrec.read(a)
    assert r["samples"] == 2 and r["minutes"] == [0.0, 0.27] and r["shared"] is True
    assert r["columns"]["gpu"] == [40.0, 40.0] and r["columns"]["gmem"] == [25.0, 25.0] and r["columns"]["mem"] == [50.0, 50.0]
    assert "fan" not in r["columns"] and "temp" not in r["columns"]      # 없는 값은 열도 없다(팬 없는 맥, NVIDIA 없는 기계)
    assert r["avg"]["gtemp"] == 70.0


def test_nothing_to_record_or_read(tmp_path):
    assert sysrec.record([], snap()) == 0
    assert sysrec.record([tmp_path], None) == 0
    assert sysrec.read(tmp_path / "never") is None


def test_the_file_stops_growing(tmp_path, monkeypatch):
    monkeypatch.setattr(sysrec, "MAX_LINES", 3)
    for i in range(6):
        sysrec.record([tmp_path], snap(), now=i * 20)
    assert sysrec.read(tmp_path)["samples"] == 3


def test_a_mostly_idle_gpu_gets_a_note_once_there_is_enough_to_trust(tmp_path):
    for i in range(sysrec.MIN_SAMPLES - 1):
        sysrec.record([tmp_path], snap(gpu=30.0), now=i * 20)
    assert sysrec.note(sysrec.read(tmp_path)) is None                   # 5분이 안 됐다
    sysrec.record([tmp_path], snap(gpu=30.0), now=10_000)
    obs, tip = sysrec.note(sysrec.read(tmp_path))
    assert "30%" in obs and "workers" in tip
    busy = tmp_path / "busy"
    for i in range(sysrec.MIN_SAMPLES):
        sysrec.record([busy], snap(gpu=90.0), now=i * 20)
    assert sysrec.note(sysrec.read(busy)) is None


def test_running_runs_and_running_queue_trainings_are_recorded(tmp_path):
    """★폴더 훑기에 붙여 두어, 배터리 절전(훑기 30~120초)이면 1~2분짜리 학습은 한 번도 안 적혔다"""
    agent = SimpleNamespace(
        _mon=SimpleNamespace(runs=[SimpleNamespace(state="running", path=tmp_path / "a"), SimpleNamespace(state="done", path=tmp_path / "b")]),
        queue=SimpleNamespace(jobs=[SimpleNamespace(state="running", kind="train", output=str(tmp_path / "q")),
                                    SimpleNamespace(state="running", kind="train", output=str(tmp_path / "a")),
                                    SimpleNamespace(state="running", kind="export", output=str(tmp_path / "x")),
                                    SimpleNamespace(state="done", kind="train", output=str(tmp_path / "old"))]))
    assert sysrec.live_paths(agent) == [tmp_path / "a", tmp_path / "q"]
    assert sysrec.live_paths(SimpleNamespace()) == []


def test_the_idle_gpu_tip_uses_the_settings_of_the_runs_framework(tmp_path):
    """★Hugging Face·Keras·Lightning 학습에도 울트라리틱스 인자(workers, cache=ram)를 권했다"""
    for i in range(sysrec.MIN_SAMPLES):
        sysrec.record([tmp_path], snap(gpu=20.0), now=i * 20)
    rec = sysrec.read(tmp_path)
    tip = {fw: sysrec.note(rec, fw)[1] for fw in ("ultralytics", "huggingface", "lightning", "keras", "tensorboard", "wandb")}
    assert "cache=ram" in tip["ultralytics"]
    assert "dataloader_num_workers" in tip["huggingface"] and "per_device_train_batch_size" in tip["huggingface"]
    assert "DataLoader" in tip["lightning"] and "tf.data" in tip["keras"]
    for fw in ("huggingface", "lightning", "keras", "tensorboard", "wandb"):
        assert "cache=ram" not in tip[fw], fw


def test_run_detail_gives_the_tip_for_that_framework(tmp_path):
    """학습 상세(/run)가 프레임워크를 넘긴다: 케라스 학습에 cache=ram이 나오지 않는다"""
    from epokio import rundetail
    d = tmp_path / "keras_run"
    d.mkdir()
    rows = [f"{e},{0.5 + e / 100},{1 - e / 50},{0.5 + e / 120},{1 - e / 60}" for e in range(12)]
    (d / "training.log").write_text("\n".join(["epoch,accuracy,loss,val_accuracy,val_loss"] + rows) + "\n")
    for i in range(sysrec.MIN_SAMPLES):
        sysrec.record([d], snap(gpu=15.0), now=i * 20)
    det = rundetail.detail(d)
    assert det["framework"] == "keras"
    tips = [n["try"] for n in det["notes"] if "GPU" in n["try"]]
    assert tips and "tf.data" in tips[0] and "cache=ram" not in tips[0]
