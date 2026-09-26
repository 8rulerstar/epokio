"""HF·Lightning·Keras 형식 자료(tests/fixtures/frameworks)를 어댑터가 제대로 읽는지. 근거는 fixtures/formats/README.md."""
import json
from pathlib import Path

import pytest

from epokio import adapters

FIX = Path(__file__).parent / "fixtures" / "frameworks"


@pytest.mark.parametrize("name,last_loss", [("hf449_trainer", "0.4779"), ("hf517_trainer", "0.47788")])
def test_hf_real_trainer_state(name, last_loss):
    got = adapters.load(FIX / name)
    assert got.framework == "huggingface" and got.total == 3 and got.warnings == []
    assert [r["epoch"] for r in got.rows] == ["1", "2", "3"]
    last = got.rows[-1]
    assert last["val/eval_loss"] == "0.5" and last["train/train_loss"] == last_loss   # 4.x는 반올림, 5.x는 안 함
    assert last["metrics/accuracy"] == "0.84" and last["val/eval_ood_loss"] == "0.6"  # 둘째 평가 데이터가 첫째를 지우지 않는다
    assert not [k for k in last if k.startswith("metrics/") and ("time" in k or "second" in k or "runtime" in k or k.endswith("loss"))]
    assert got.args["best_metric"] == "0.84"


def test_hf_checkpoint_only(tmp_path):
    import shutil
    d = tmp_path / "run"
    shutil.copytree(FIX / "hf517_trainer", d)
    (d / "trainer_state.json").unlink()                 # save_state()를 안 부르면 체크포인트 안에만 있다
    got = adapters.load(d)
    assert got.source.parent.name == "checkpoint-300" and got.rows[-1]["epoch"] == "3"


def test_hf_unknown_shape_warns(tmp_path):
    (tmp_path / "trainer_state.json").write_text('{"epoch": 1, "history": []}')
    assert adapters.load(tmp_path).warnings


def test_lightning_csvlogger():
    got = adapters.load(FIX / "lightning_csvlogger" / "lightning_logs" / "version_0")
    assert got.framework == "lightning" and got.warnings == [] and got.total is None
    assert got.rows == [
        {"epoch": "1", "train/train_loss": "0.853", "metrics/val_acc": "0.61", "val/val_loss": "0.74"},
        {"epoch": "2", "train/train_loss": "0.627", "metrics/val_acc": "0.72", "val/val_loss": "0.63"},
    ]


def test_keras3_csvlogger():
    got = adapters.load(FIX / "keras3_csvlogger")
    assert got.framework == "keras" and got.warnings == []
    assert [r["epoch"] for r in got.rows] == ["1", "2", "3"]        # append 재개로 겹친 에폭은 하나로
    assert got.rows[1]["val/val_loss"] == "0.1380" and "metrics/learning_rate" not in got.rows[1]


def test_keras_semicolon_warns(tmp_path):
    (tmp_path / "training.log").write_text("epoch;loss;val_loss\n0;0.3;0.2\n")
    assert adapters.load(tmp_path).warnings


def test_hf_training_args_json(tmp_path):
    """training_args.json(= TrainingArguments.to_dict())의 주요 값이 args로 나온다. 근거·버전 차이는 hf_args.py"""
    a4 = adapters.load(FIX / "hf449_trainer").args
    a5 = adapters.load(FIX / "hf517_trainer").args
    for a in (a4, a5):
        assert a["learning_rate"] == "3e-05" and a["lr_scheduler_type"] == "cosine"
        assert a["per_device_train_batch_size"] == "16" and a["gradient_accumulation_steps"] == "2"
        assert a["weight_decay"] == "0.01" and a["seed"] == "7"
        assert a["fp16"] == "true" and a["bf16"] == "false"          # bool은 args.yaml 표기와 같게
        assert a["warmup_ratio"] == "0.06"                            # 4.x는 그대로, 5.x는 소수 warmup_steps에서
        assert a["num_train_epochs"] == "3"                           # trainer_state 값(실제로 돈 것)이 이긴다
        assert "output_dir" not in a and "hub_token" not in a         # 추린 목록 밖은 안 낸다
    assert "warmup_ratio" not in json.loads((FIX / "hf517_trainer" / "training_args.json").read_text())
    assert a4["optim"] == "adamw_torch" and a5["optim"] == "adamw_torch_fused"


def test_hf_without_training_args_json_is_normal(tmp_path):
    """transformers 자신은 training_args.bin만 쓴다: json이 없어도 경고하지 않고 예전 값은 그대로"""
    import shutil
    d = tmp_path / "run"
    shutil.copytree(FIX / "hf517_trainer", d)
    (d / "training_args.json").unlink()
    (d / "training_args.bin").write_bytes(b"\x80\x05not-json")        # .bin은 풀지 않는다
    got = adapters.load(d)
    assert got.warnings == [] and "learning_rate" not in got.args
    assert got.args["num_train_epochs"] == "3" and got.args["best_metric"] == "0.84"


def test_hf_broken_training_args_json_is_ignored(tmp_path):
    import shutil
    d = tmp_path / "run"
    shutil.copytree(FIX / "hf517_trainer", d)
    (d / "training_args.json").write_text("{not json")
    got = adapters.load(d)
    assert got.warnings == [] and "learning_rate" not in got.args and got.rows[-1]["epoch"] == "3"


def test_hf_training_args_json_inside_checkpoint(tmp_path):
    """출력 폴더엔 없고 체크포인트 안에만 있을 때"""
    import shutil
    d = tmp_path / "run"
    shutil.copytree(FIX / "hf517_trainer", d)
    shutil.move(d / "training_args.json", d / "checkpoint-300" / "training_args.json")
    (d / "trainer_state.json").unlink()
    assert adapters.load(d).args["learning_rate"] == "3e-05"
