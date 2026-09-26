"""Hugging Face 쪽 자잘한 규칙: training_args.json에서 비교표에 쓸 값 고르기 + 에폭 세는 법.

형식은 `TrainingArguments.to_json_string()` = `to_dict()`를 json.dumps 한 것이다
(dataclass의 init=True 필드 전부, Enum은 .value, *_token은 가려서 "<HUB_TOKEN>" 같은 문자열).

⚠transformers 자신은 이 파일을 쓰지 않는다. Trainer가 남기는 것은 `training_args.bin`(torch pickle)이고,
json은 TRL·autotrain 같은 위층이나 사용자 코드가 따로 남긴다. 그러니 **없는 것이 정상**이고 없다고 경고하지 않는다.
.bin은 읽지 않는다(코드를 고치지 않는다는 원칙과 별개로, 남의 pickle을 푸는 일은 하지 않는다).

버전 차이(설치본 4.49.0 · 5.17.0을 dataclasses.fields로 실측):
  * init 필드 131개(4.49) → 112개(5.17)
  * **warmup_ratio가 5.x에는 없다.** 5.x의 warmup_steps는 float이고 0<v<1이면 비율로 쓴다
    → 비교표가 버전을 넘어 줄 맞도록, 그럴 때 warmup_ratio도 같이 낸다
  * group_by_length가 5.x에 없다. optim 기본값 adamw_torch → adamw_torch_fused
"""
from __future__ import annotations

import json
import math
from pathlib import Path

# 비교표에 낼 값만 추린다(131개를 다 내면 표가 못 쓰게 된다). 순서 = 표에 나오는 순서
ARG_KEYS = ("learning_rate", "lr_scheduler_type", "warmup_ratio", "warmup_steps", "optim", "weight_decay",
            "adam_beta1", "adam_beta2", "adam_epsilon", "max_grad_norm",
            "per_device_train_batch_size", "per_device_eval_batch_size", "gradient_accumulation_steps",
            "num_train_epochs", "max_steps", "seed", "data_seed",
            "fp16", "bf16", "tf32", "gradient_checkpointing", "group_by_length", "label_smoothing_factor")


def _str(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"          # args.yaml(ultralytics) 표기와 맞춘다
    return str(v)


def read(*dirs: Path) -> dict:
    """앞에 준 폴더부터 training_args.json을 찾아 추린 값만. 없거나 깨졌으면 빈 dict"""
    for d in dirs:
        p = d / "training_args.json"
        if not p.exists():
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        out = {k: _str(raw[k]) for k in ARG_KEYS
               if raw.get(k) is not None and not isinstance(raw.get(k), (dict, list))}
        w = raw.get("warmup_steps")
        if "warmup_ratio" not in out and isinstance(w, float) and 0 < w < 1:
            out["warmup_ratio"] = _str(w)                 # 5.x: 소수 warmup_steps = 비율
        return out
    return {}


def done_epochs(v, fallback: int) -> int:
    """trainer_state의 epoch을 '끝난 에폭 수'로. ★올림이 아니라 내림이다: eval_steps로 에폭 중간에
    평가하면 epoch=19.33이 오는데, 올림은 이를 20으로 만들어 scan이 아직 도는 학습을 "20/20 · 완료"로
    보고 ETA까지 멈췄다. 에폭이 실제로 끝나면 HF가 정확히 20.0을 적으므로 정상 종료 판정은 그대로다."""
    try:
        return max(math.floor(float(v)), 0)
    except (TypeError, ValueError, OverflowError):
        return fallback
