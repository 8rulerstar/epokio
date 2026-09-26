# 프레임워크 형식 자료 (Hugging Face · Lightning · Keras, 2026-09-22)

`tests/test_framework_formats.py`가 읽는다.

* `hf449_trainer`, `hf517_trainer`: `make_hf.py`를 transformers 4.49(omnicrack env)·5.17(yolo5_env)로 돌려 만든 진짜 `TrainerState.save_to_json` 결과. 학습 없음. 출력 폴더 + checkpoint-100/200/300, 평가 데이터 둘(eval_·eval_ood_), 학습 끝 요약 기록 포함. 다시 만들 때: `<env>/bin/python tests/fixtures/frameworks/make_hf.py`
  `training_args.json`도 같이 쓴다: transformers 자신은 이 파일을 안 쓰지만(`.bin`만) TRL·autotrain 등이 남기는 모양이다.
  설치본의 `dataclasses.fields(TrainingArguments)` 이름·기본값을 그대로 읽어 만든다(TrainingArguments 객체는 accelerate를 요구해서 안 만든다).
  버전 차이: init 필드 131개(4.49) → 112개(5.17), **`warmup_ratio`가 5.x엔 없다**(소수 `warmup_steps`가 비율), `group_by_length`도 없다, `optim` 기본값이 `adamw_torch` → `adamw_torch_fused`.
* `lightning_csvlogger`: 로컬에 Lightning 설치본이 없어 master 소스(fabric/loggers/csv_logs.py, trainer/connectors/logger_connector, result.py forked_name)를 읽고 손으로 쓴 것. 정렬된 열, step·epoch 열, 학습 step 줄·에폭 줄·검증 줄이 따로, `_step`/`_epoch` 갈래 이름, LearningRateMonitor `lr-Adam`.
* `keras3_csvlogger`: 로컬에 Keras 설치본이 없어 master 소스(src/callbacks/csv_logger.py)를 읽고 손으로 쓴 것. epoch + 정렬된 키, `learning_rate`, append 재개로 에폭 1이 두 번.
