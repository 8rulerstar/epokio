"""Hugging Face trainer_state.json 형식 자료를 진짜 transformers로 만든다(학습은 하지 않는다).
TrainerState 객체에 Trainer.log()가 넣는 모양 그대로 기록을 쌓고 TrainerState.save_to_json으로 쓴다.
    /opt/anaconda3/envs/omnicrack/bin/python tests/fixtures/frameworks/make_hf.py   # 4.49 -> hf449_trainer
    /opt/anaconda3/envs/yolo5_env/bin/python tests/fixtures/frameworks/make_hf.py   # 5.17 -> hf517_trainer
기록 모양의 근거(trainer.py): _maybe_log_save_evaluate의 logs(loss, grad_norm, learning_rate; 4.x는 loss를 round 4),
evaluate의 metric_key_prefix(eval_ 또는 eval_<이름>_), log()가 붙이는 epoch·step, 학습 끝 speed_metrics("train")+total_flos+train_loss.
training_args.json은 TrainingArguments.to_dict()와 같은 모양으로 쓴다: 설치된 transformers의 dataclasses.fields(init=True)
이름·기본값을 그대로 읽어 몇 개만 바꿔 넣는다(TrainingArguments를 만들면 accelerate·torch를 요구하므로 만들지 않는다).
transformers 자신은 이 파일을 쓰지 않는다(training_args.bin만). TRL·autotrain 등 위층이 남기는 모양을 흉내 낸 것이다.
"""
import dataclasses
import enum
import json
import os
import time
from pathlib import Path

import transformers
from transformers.trainer_callback import TrainerState
from transformers.trainer_utils import speed_metrics, PREFIX_CHECKPOINT_DIR

V4 = transformers.__version__.startswith("4.")
OUT = Path(__file__).parent / ("hf449_trainer" if V4 else "hf517_trainer")
STEPS_PER_EPOCH = 100


def main():
    st = TrainerState(max_steps=3 * STEPS_PER_EPOCH, logging_steps=50, eval_steps=STEPS_PER_EPOCH,
                      save_steps=STEPS_PER_EPOCH, train_batch_size=16, num_train_epochs=3)
    st.log_history = []

    def log(logs, step):
        st.global_step, st.epoch = step, step / STEPS_PER_EPOCH
        logs["epoch"] = st.epoch
        st.log_history.append({**logs, "step": st.global_step})

    losses = [0.93211, 0.71873, 0.60125, 0.55519, 0.50142, 0.47788]
    t0 = time.time() - 42
    for i, step in enumerate(range(50, 301, 50)):
        tr = losses[i]
        log({"loss": round(tr, 4) if V4 else tr, "grad_norm": 3.2 - i * 0.3, "learning_rate": 5e-5 * (1 - step / 300)}, step)
        if step % STEPS_PER_EPOCH == 0:
            ep = step // STEPS_PER_EPOCH
            for name in ("", "_ood_"):          # 평가 데이터가 둘이면 eval_<이름>_ 접두
                p = "eval" + (name[:-1] if name else "")
                m = {f"{p}_loss": 0.8 - ep * 0.1 + (0.1 if name else 0), f"{p}_accuracy": 0.6 + ep * 0.08,
                     f"{p}_f1": 0.55 + ep * 0.09}
                m.update(speed_metrics(p, t0, num_samples=500, num_steps=32))
                if V4:
                    m[f"{p}_model_preparation_time"] = 0.0021
                log(m, step)
            ck = OUT / f"{PREFIX_CHECKPOINT_DIR}-{step}"
            ck.mkdir(parents=True, exist_ok=True)
            st.best_metric, st.best_model_checkpoint = 0.6 + ep * 0.08, f"{OUT.name}/{ck.name}"
            if not V4:
                st.best_global_step = step
            st.save_to_json(str(ck / "trainer_state.json"))
    m = speed_metrics("train", t0, num_samples=4800, num_steps=300)
    m["total_flos"], m["train_loss"] = 1.2e14, sum(losses) / len(losses)
    log(m, 300)
    st.save_to_json(str(OUT / "trainer_state.json"))    # trainer.save_state()가 출력 폴더에 쓰는 것
    _training_args()
    print(OUT, transformers.__version__)


def _training_args():
    """TrainingArguments.to_dict()와 같은 모양(init 필드 전부 + Enum은 .value)"""
    from transformers import TrainingArguments
    over = {"output_dir": str(OUT), "learning_rate": 3e-05, "per_device_train_batch_size": 16,
            "num_train_epochs": 3.0, "weight_decay": 0.01, "lr_scheduler_type": "cosine", "seed": 7,
            "fp16": True, "gradient_accumulation_steps": 2}
    over["warmup_ratio" if V4 else "warmup_steps"] = 0.06      # 4.x에만 warmup_ratio가 있다
    d = {}
    for f in dataclasses.fields(TrainingArguments):
        if not f.init:
            continue
        v = over.get(f.name, f.default)
        if v is dataclasses.MISSING:
            v = None
        if isinstance(v, enum.Enum):
            v = v.value
        if f.name.endswith("_token"):
            v = f"<{f.name.upper()}>"
        try:
            json.dumps(v)
        except TypeError:
            v = str(v)
        d[f.name] = v
    (OUT / "training_args.json").write_text(json.dumps(d, indent=2), encoding="utf-8")


main()
