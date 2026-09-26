# 형식 자료

프레임워크가 실제로 남기는 기록 파일의 **머리줄(열 이름)**을 고정해 둔 것이다. 값은 만든 숫자다.
형식이 바뀌면 `tests/test_formats.py`가 깨진다. 그때 `schema.py`와 `adapters.py`만 고친다.

| 폴더 | 근거 |
|---|---|
| ultralytics84_* | Ultralytics 8.4.150 소스: `utils/metrics.py` keys, `utils/loss.py` loss_names, `engine/trainer.py` save_metrics |
| yolov5_detect | YOLOv5 results.csv 머리줄(앞 공백 포함, 에폭 0부터) |

⚠실제 학습으로 만든 파일이 아니다. 실제 파일이 생기면 교체한다. 다시 만들기: `python tests/fixtures/formats/make.py`
