# Epokio 안내서

[README로](README.ko.md) · [English](guide.md)

README에서 뺀 자세한 내용입니다. 형식, 알림, SSH, 한계, 비교, 개인정보, 문제 해결.

## 앱 설치

| 맥 | 윈도우 | 리눅스, GPU 서버 |
|---|---|---|
| [`.dmg` 받기](https://github.com/8rulerstar/epokio/releases/latest), 응용 프로그램 폴더로 끌어다 놓고 열기 | [`Epokio.exe` 받기](https://github.com/8rulerstar/epokio/releases/latest), 더블클릭 | `pip install epokio` 후 `epokio setup` |

* **맥:** macOS 15 이상. 아직 공증을 받지 않아 처음엔 막힙니다. 한 번 열어 경고를 닫고 **시스템 설정 → 개인정보 보호 및 보안 → 그래도 열기**. macOS 26에서 아이콘이 안 보이면 **시스템 설정 → 메뉴 막대**에서 허용하세요.
* **윈도우:** 서명하지 않은 앱이라 처음 한 번 SmartScreen이 막을 수 있습니다. **추가 정보 → 실행**. 보기만 할 때는 파이썬이 필요 없고, 학습 탭에서 학습을 시작하려면 파이썬 3.10 이상이 필요합니다.
* **리눅스 서버:** Ubuntu 24.04에서는 가상환경을 쓰세요(PEP 668). SSH로 들어온 서버에서는 setup이 브라우저 대신 `ssh -L` 터널 명령을 알려 줍니다.
* **폰에서 웹 화면 보기:** 도우미는 그 기계 안에서만 답합니다. 폰에서 보려면 `ssh -L` 터널이나 Tailscale을 쓰거나, `--lan`을 붙여 setup을 돌리고(`epokio setup --lan`, 윈도우는 `py -m epokio setup --lan`) 출력된 주소와 토큰으로 들어갑니다.

윈도우, 리눅스, 트레이 아이콘, 원격 도우미의 전체 절차: [remote.md](remote.md)(영어).

## 하는 일

<p align="center">
  <img src="images/runs-live.gif" width="720" alt="Epokio 웹 화면이 학습 목록을 불러오고, 한 학습이 마지막 에폭에 닿아 잠깐 반짝이며 완료로 바뀌고, 다른 학습의 진행 막대와 남은 시간은 계속 움직입니다">
</p>

* **이미 있는 기록을 읽습니다.** Ultralytics, Hugging Face Trainer, Lightning, Keras, timm, OpenMMLab, W&B 로컬 파일, TensorBoard 이벤트 파일, MAE·DeiT 계열 `log.txt`, 직접 만든 CSV.
* **진행률, 남은 시간, 최고 점수**를 메뉴바, 트레이, 터미널, 웹 화면에 실시간으로. 학습이 끝나거나, 실패하거나(NaN loss), 멈추거나(비정상 종료·메모리 부족도 이렇게 드러납니다), 마지막 에폭 전에 그치면 알려 줍니다.
* **폰 알림**: ntfy, Slack, Discord, 텔레그램 웹훅으로 학습 기계가 직접 보냅니다.
* **SSH로 원격 기계 보기**: 서버에 아무것도 설치하지 않습니다. 기록마다 새로 붙은 꼬리만 가져옵니다.
* **클래스별 점수**(클래스마다 정밀도·재현율·mAP, 약한 것부터. Epokio로 시작한 Ultralytics 학습 또는 클래스별 점수 계산을 한 번 돌린 뒤)와 다음에 무엇을 바꿀지 쉬운 말로 적은 메모.
* **step 단위 학습**(`epoch` 없는 W&B, TensorBoard step 스칼라, 첫 열이 `step`·`iter`·`iteration`인 CSV)은 진행률을 step으로 보여 줍니다.
* **더 있는 것:** 맥 메뉴바 앱, Studio 창, 비교, 학습 시작·대기열, 라벨 검수, 스윕, 데이터셋 보기. [studio.md](studio.md)(영어) 참고.

## 읽는 형식

프레임워크가 이미 쓰는 파일을 읽으니 기록 코드를 더할 필요가 없습니다. Keras는 `CSVLogger`나 `TensorBoard` 콜백이 있어야 하고, 직접 짠 루프는 `epokio.start`를 씁니다.

| 프레임워크 | 읽는 것 |
|---|---|
| Ultralytics YOLO | `results.csv`, `args.yaml` |
| Hugging Face Trainer | `trainer_state.json`(`checkpoint-*` 안도) |
| PyTorch Lightning | `CSVLogger`의 `metrics.csv`, `hparams.yaml` |
| Keras | `CSVLogger` 파일(`training.log`, `history.csv`) |
| TensorBoard 기록 | `events.out.tfevents.*` 스칼라, TensorFlow 없이 읽음. `epoch` 태그가 있으면 에폭, 없으면 step 기준 |
| 비전 연구 코드(MAE, DeiT, DINO, BEiT, ConvNeXt) | 에폭마다 JSON 한 줄인 `log.txt` |
| timm `train.py` | `summary.csv`(`eval_top1`이 주 점수), `args.yaml` |
| OpenMMLab(MMDetection 3.x, MMPretrain, MMSegmentation) | `vis_data/scalars.json`, 저장된 설정의 `max_epochs`(에폭 기반 학습만) |
| Weights & Biases(로컬 파일) | `wandb/run-*/run-*.wandb`, wandb 설치 없이 읽음. `epoch` 값이 기록돼 있으면 에폭, 없으면 `_step` 기준. SSH로도 |
| 직접 만든 학습 루프 | 첫 열이 `epoch`·`step`·`iter`·`iteration`이고 loss 열이 있는 CSV |

**최고 점수**는 검증 지표(또는 Hugging Face의 `best_metric`)를 기록한 학습에만 나오고, 손실만 기록한 학습에는 없습니다. 예외로 `eval_loss`만 평가한 Hugging Face 학습은 가장 낮은 `eval_loss`가 최고 점수입니다.
Hugging Face 학습은 체크포인트를 저장할 때 갱신됩니다. 그때 `trainer_state.json`이 쓰이기 때문입니다.
주 점수를 직접 고르려면 `epokio score <학습 또는 폴더> <열> [--lower]`, `--auto`, `--list`.

**진행률과 남은 시간**을 내려면 전체 길이를 알아야 합니다. 에폭 수는 프레임워크 자체 파일이나 기록 옆 설정 파일
(`args.yaml`, `args.json`, `config.yaml`, `config.json`, `hparams.yaml`, `opt.yaml`)에서, step 학습은 같은 파일의
`max_steps`, `total_steps`, `max_iters` 같은 전체 step 수에서 읽습니다. Keras의 `CSVLogger`는 계획을 남기지 않아 기록 옆 설정 파일의 `epochs`를 읽고, Lightning은 `hparams.yaml`의 `max_epochs`(또는 `epochs`, 하이퍼파라미터로 저장했을 때만 있음)를 읽습니다. 없으면 에폭은 보이지만 진행률·남은 시간은 비어 있습니다.

다른 프레임워크를 더하려면 작은 어댑터 클래스 하나면 되고, 목록은 `src/epokio/adapters.py`에 있습니다. 직접 만든 루프에서 `epokio.start`로 기록하는 방법은 [remote.md](remote.md)(영어).

## 알림

알림은 학습 기계의 도우미가 직접 보내므로 노트북이 꺼져 있어도 옵니다. 다만 그 도우미가 떠 있을 때만 갑니다. 웹훅은 `https`여야 합니다.
[ntfy](https://ntfy.sh) 주소(예: `https://ntfy.sh/your-secret-topic`)나 Slack, Discord, 텔레그램 웹훅을 넣으세요.

* **맥 앱:** 설정 → 알림.
* **웹 화면:** **알림**에서 넣고 **시험 보내기**로 도착하는지 확인합니다(도우미의 `POST /webhooks/test`).
* **터미널:** 같은 설정 파일에 쓰므로 저장할 때 도우미가 떠 있지 않아도 됩니다(SSH로만 들어가는 서버에서 편합니다).

```bash
epokio alerts --add https://ntfy.sh/your-secret-topic
epokio alerts --list        # 주소의 경로는 가려서 보여 줍니다
epokio alerts --test        # 저장된 웹훅마다 시험 메시지 하나
epokio alerts --remove https://ntfy.sh/your-secret-topic
epokio alerts --lang ko     # 알림 문구 언어
```

윈도우에서 `epokio`를 못 찾으면 `py -m epokio alerts ...`로 쓰면 됩니다.

계획 에폭이 없는 학습이 조용해지면 급한 '멈춤' 알림 대신 차분한 *기록이 멈췄습니다* 안내가 뜨고, 따로 고르지 않는 한 폰 웹훅으로는 가지 않습니다.

* **보내기:** 네트워크 오류, 429, 5xx로 실패하면 두 번 더 보냅니다(5초, 30초 뒤). 4xx(틀린 주소, 지운 웹훅)는 다시 보내지 않고, 이유는 `epokio doctor`와 `agent.log`에 남습니다.
* **도우미를 다시 켰을 때:** 도우미가 꺼진 사이(업데이트, 재부팅) 학습이 끝나거나 실패하거나 멈췄으면, 다시 켤 때 알림을 보냅니다(이틀 안의 변화만).
* **종류:** 맥 앱에서 종류를 전부 끄면 전부 꺼진 채로 남습니다. 목표 점수 알림은 직접 건 것이라 늘 갑니다.
* **목표:** 목표는 그 학습의 최고 점수, 곧 저장된 가장 좋은 모델(`best.pt`)의 점수와 비교합니다. YOLO 분할·포즈·분류는 `best.pt`를 마스크(포즈) mAP와 박스 mAP를 더한 값으로 고르므로, 그 마스크 점수가 열의 가장 높은 값보다 조금 낮을 수 있습니다. 그래서 열의 최고값 바로 아래로 건 목표는 울리지 않을 수 있습니다. 일부러 이렇게 했습니다. 알림이 오면 실제로 쓸 모델이 목표에 닿았다는 뜻입니다.
* **조용한 시간**(맥 앱: 설정 → 알림): 그 시간에는 폰으로 보내지 않습니다. 앱과 웹 **알림** 탭에는 그대로 뜨지만, 그 폰 알림을 나중에 몰아 보내지는 않습니다.

`epokio.start(..., notify=True)`를 쓰면 학습 프로세스가 `with` 블록이 끝날 때(완료) 또는 오류로 끝날 때(실패, 오류 종류와 문구) 직접 알림을 보냅니다. 표준 라이브러리만 쓰고, 네트워크가 안 돼도 학습은 멈추지 않습니다. 같은 폴더를 도우미도 지켜보고 있으면 같은 알림을 다시 보내지 않습니다.

## 맥 앱에서 SSH로 보기

맥 앱에서 **설정 → 기계 → SSH로 보기**를 열고 `~/.ssh/config`의 호스트를 고릅니다(`ProxyJump` 포함).
서버에는 아무것도 설치하거나 쓰지 않습니다.

* **조건:** 서버에 `python3` 3.6 이상, 키 로그인(암호나 일회용 코드를 묻지 않아야 합니다). 서버에 인터넷은 필요 없습니다.
* **가져오는 것:** 알려진 기록 이름(`results.csv`, `log.txt`, `summary.csv`, `metrics.csv`, `trainer_state.json`, TensorBoard·W&B 파일 등)과 저장된 설정뿐이고, 이미지나 가중치는 가져오지 않습니다. 15초마다 확인하며, 바뀌지 않은 파일은 건너뛰고 늘어나기만 하는 기록은 새로 붙은 꼬리만 보냅니다.
* **크기 한도:** 글자 기록 4MB, TensorBoard·W&B 파일 20MB(이미 받은 파일은 새로 붙은 부분에 적용). 계속 늘어나는 글자 기록이 한도를 넘으면 첫 줄과 끝 4MB만 받고 이어 붙입니다. 한도를 넘은 TensorBoard·W&B·설정 파일은 건너뜁니다. 몇 개를 건너뛰었거나 잘랐는지는 맥 앱과 웹 화면 SSH 칸이 알려 줍니다.
* 홈 폴더 아래를 찾습니다. `/scratch/you/runs` 같은 경로는 *다른 폴더*에 더하세요.
* SSH로 가져온 학습의 알림에는 서버 이름(`ssh:<호스트>`)이 붙습니다.
* 보기 전용입니다. 다른 기계에서 그 서버의 학습을 시작하려면 서버에 도우미를 `--lan --allow-run`으로 설치합니다. 리눅스는 `pip install epokio` 후 `epokio setup --lan --allow-run --autostart`, 윈도우는 `py -m pip install "epokio[tray]"` 후 `py -m epokio setup --lan --allow-run --autostart`(파이썬 없이: `Epokio.exe setup ...`). 그리고 맥에 실행 토큰을 줍니다(`epokio agent --add-token mac --scope run`). 토큰, `--lan`, 네트워크 안전: [remote.md](remote.md)(영어).

### 서버에서 실제로 도는 것

15초마다 `ssh -o BatchMode=yes -o ConnectTimeout=8 <호스트> python3 - '<설정>'`을 실행합니다(맥·리눅스에서는 `ControlMaster=auto`, `ControlPersist=120`, `~/.epokio/ssh-control` 아래 제어 소켓을 더해 한 번 로그인한 연결을 다시 씁니다). 표준 입력으로 스크립트 하나, [`src/epokio/ssh_remote.py`](../src/epokio/ssh_remote.py)(표준 라이브러리만, 파이썬 3.6 이상)를 보냅니다. 이 스크립트는 홈 폴더와 더한 폴더 아래에서 알려진 기록 이름을 찾아 내용을, 또는 지난번 뒤로 붙은 부분만 JSON으로 출력합니다. 서버에 아무것도 쓰지 않고, 프로세스를 띄우지 않고, 설치하지 않고, 이미지나 가중치는 읽지 않습니다. BatchMode라 암호나 호스트 키 질문에 답하지 않습니다.

## 한계

* 에폭 없이 iteration 기반으로 도는 OpenMMLab 학습은 읽지 않습니다.
* SSH로는 알려진 기록 이름만 읽고, 아무 CSV나 읽지는 않습니다. 크기 한도를 넘은 바이너리 기록과 설정은 건너뜁니다.
* 직접 만든 CSV 이름이 `results.csv`, `metrics.csv`, `epokio_log.csv`이면 Ultralytics, Lightning, `epokio.start` 쪽 읽기로 넘어가 직접 만든 CSV로 읽히지 않습니다. 다른 이름을 쓰세요.
* **공용 서버:** 기본값으로는 그 기계에 로그인할 수 있는 사람 누구나 `127.0.0.1`의 도우미를 읽을 수 있습니다(학습, 설정, 로그). `epokio agent --require-token`으로 띄워 보는 것에도 토큰이 필요하게 하고(`epokio setup`이 띄운 도우미는 먼저 `epokio agent --stop`으로 끕니다. 이 명령은 앞에서 계속 돌므로 tmux나 서비스로 띄우세요), 사람마다 그 사람 폴더로 제한한 토큰을 주세요: `epokio agent --add-token alice --scope read --root /data/alice/runs`(`--root`는 여러 번, 무늬도 됩니다). 그 토큰은 학습 목록, 학습 화면, 그림, 사건, 표에서 그 폴더 안 학습만 보고, 그 밖(대기열, 스윕, 설정, 바꾸기)은 못 합니다. `--root` 없이 만든 토큰은 지켜보는 학습을 전부 봅니다.
* 맥 앱은 공증, 윈도우 앱은 서명을 받지 않아 둘 다 처음 실행할 때 경고가 뜹니다.
* 도우미는 암호화되지 않은 HTTP로 통신합니다. `--lan`보다 SSH 터널이나 Tailscale을 권합니다. `--lan`으로 연 도우미는 `--allow-run` 없이는 보기만 되고, 새 토큰은 `--scope run`으로 만들지 않으면 보기 전용입니다.

**자원 사용.** 백그라운드 도우미 하나만 재면 메모리(RSS)는 맥에서 학습 폴더 50개일 때 약 45MB입니다. CPU는 학습 폴더 330개에 도는 학습이 없을 때 1분에 약 0.67초, 학습 하나가 돌 때 1분에 약 1.7초입니다(코어 하나의 1% 미만).

## 다른 도구와 비교

| | Epokio | TensorBoard | 클라우드 트래커(W&B, Comet) | MLflow, Aim | Ultralytics Platform | Trackio |
|---|---|---|---|---|---|---|
| 학습 스크립트 수정 | 지원하는 파일을 쓰는 프레임워크면 **없음**(Keras는 `CSVLogger`나 `TensorBoard` 콜백) | 프레임워크가 이벤트 파일을 쓰면 없음 | 기록 호출 추가, 또는 내장 연동(HF Trainer, Ultralytics)으로 설정 하나 | 기록 호출 추가, 또는 MLflow 내장 연동으로 설정 하나(HF Trainer `report_to="mlflow"`, Lightning `MLFlowLogger`, Ultralytics `mlflow` 설정). MLflow는 autolog도 있음 | Ultralytics는 없음: API 키로 로컬 학습을 전송 | `trackio.init`·`log` 호출 추가, 또는 HF Trainer 설정 하나(`report_to="trackio"`). TensorBoard·CSV 기록 가져오기 |
| 계정·서버 | **없음** | 없음 | 계정 | 로컬은 없음(`mlflow ui`, `aim up`), 또는 직접 운영하는 서버 | 계정 | 없음 |
| 데이터가 가는 곳 | **내 기계에 남음** | 내 기계 | 기본은 그쪽 클라우드, 직접 호스팅·오프라인도 가능 | 로컬 폴더(`./mlruns`, `.aim`) 또는 내 서버 | 그쪽 클라우드 | 내 기계(또는 직접 고른 Hugging Face Space·Dataset) |
| 늘 보이는 곳 | **메뉴바, 터미널, 트레이** | `tensorboard --logdir` 뒤 브라우저 탭 | 브라우저 탭, 폰 앱(iOS) | 브라우저 탭 | 브라우저 탭 | 브라우저 탭 |
| 한 화면에서 읽는 형식 | **Ultralytics, HF, Lightning, Keras, timm, OpenMMLab, W&B, TensorBoard, CSV** | 자기 이벤트 파일 | 자기 기록(W&B는 TensorBoard 동기화 가능) | 자기 기록(Aim은 TensorBoard·MLflow·W&B 기록 변환) | Ultralytics | 자기 기록(TensorBoard·CSV 가져오기) |
| 팀 공유, 모델 레지스트리 | 목표가 아님 | 없음 | **있음** | 내 서버에서 공유, 레지스트리는 MLflow만 | **있음** | 일부 |
| step 단위 그래프 | step 기반 학습은 진행률을 step으로 | **있음** | **있음** | **있음** | 에폭 단위 | **있음** |
| 가격(2026-10 기준) | 무료, MIT | 무료 | 무료 등급과 유료 요금제 | 무료 소프트웨어(호스팅 요금제 있음) | 무료 등급과 유료 요금제 | 무료 |

Epokio는 곡선을 보고 다음 학습도 제안합니다(예: "아직 좋아지는 중: best.pt에서 2배 더 길게"). 클라우드 AI가 아니라 내 기계 안의 간단한 규칙으로 계산합니다.

**트래커를 대신하지 말고 옆에 두고 쓰세요.** 팀이 이미 W&B나 MLflow에 기록한다면 그대로 하세요.
Epokio는 W&B 로컬 파일과 TensorBoard 기록도 읽으므로, 계정이나 기록 호출을 더하지 않고 같은 학습을 메뉴바나 터미널에 보여 줍니다.

## 개인정보

직접 켜지 않는 한 아무것도 기계 밖으로 나가지 않습니다. 앱은 내가 띄운 도우미와만 통신합니다.

| 선택 기능 | 보내는 것 | 가는 곳 |
|---|---|---|
| 웹훅(ntfy, Slack, Discord, 텔레그램) | 학습 이름, 에폭, 최고 점수와 지표 이름, 사건, 기계 이름. `epokio.start` 학습이 실패하면 오류 종류와 문구 | 내가 넣은 주소 |
| 어시스턴트(말로 하는 명령) | 입력한 문장, 최근 학습 최대 12개의 이름 | 내 API 키로 TypeSafe |
| 결과 해설 다듬기 | 상태, 작업 종류, 점수, 설정 숫자, 언어, 초안 문장 | TypeSafe, 어시스턴트를 켰을 때만 |
| 이 맥에서 쓰는 해설(macOS 26 이상) | 없음 | 맥 안에 남음 |
| 업데이트 확인(Sparkle), 업데이트 키로 서명하기 전까지 현재 배포판에서는 꺼짐 | 앱과 macOS 버전 | 프로젝트의 GitHub 릴리스 |
| 맥 앱의 파이썬 준비 | 독립 실행형 파이썬을 내려받음(올리는 것 없음) | github.com/astral-sh/python-build-standalone |
| 문제 보고(맥 앱), 열기를 눌렀을 때만 | `errors.log` 끝부분(홈 폴더는 `~`로 표시)을 채운 GitHub 새 이슈 페이지를 엶. 페이지가 열릴 때 github.com에 닿고, 고치거나 탭을 닫아도 됨 | github.com |
| 학습 탭의 "파이썬 설치" 버튼 | PyTorch, Ultralytics와 의존 패키지를 내려받음(올리는 것 없음) | PyPI, download.pytorch.org |

웹훅은 `https`여야 하고, 웹훅 주소는 로그에 남지 않습니다. TypeSafe 키는 키체인에 있고 두 기능 모두 켜기 전까지 꺼져 있습니다.
오류 기록은 `~/.epokio/logs`에 남고, 문제 보고에서 열기를 눌렀을 때만 밖으로 나갑니다.
도우미의 `/ai`는 그 기계에서 어떤 AI 도구가 얼마나 바쁜지(프로세스 이름과 CPU만, 프롬프트는 절대 아님)를 메뉴바 캐릭터용으로 알려 줍니다. 학습 목록처럼 도우미를 볼 수 있는 사람은 누구나 읽을 수 있습니다.

## 이상할 때

* `epokio doctor`(`pip install epokio` 필요, `Epokio.exe`에는 `doctor`가 없습니다. 윈도우는 `py -m epokio doctor`)가 Epokio가 보는 것을 출력합니다.
  버전, 도우미가 도는지(어느 버전인지), 지켜보는 폴더, 찾은 파이썬 환경, 로그 마지막 줄. 토큰은 출력하지 않으니 버그 보고에 그대로 붙여도 됩니다(원본 데이터는 `--json`).
* 도우미는 `~/.epokio/agent.log`(1MB, 이전 사본 하나 보관, 윈도우는 `%USERPROFILE%\.epokio\agent.log`)에 오류 원인을 적습니다.
* 업그레이드한 뒤에는 `epokio setup`을 다시 돌리세요. 옛 버전으로 도는 도우미를 다시 띄웁니다.
  이 기계의 도우미는 `epokio agent --stop`(윈도우는 `py -m epokio agent --stop` 또는 `Epokio.exe agent --stop`)으로 끕니다.

## 제거

Epokio를 끝내고 `Epokio.app`을 휴지통으로 옮기고, 직접 띄운 도우미를 끈 뒤(`epokio agent --stop`, 앱이 띄운 것은 앱이 끕니다) `rm -rf ~/.epokio`, pip으로 설치했다면 `pip uninstall epokio`.
설정, 키체인 항목, 윈도우·리눅스 절차: [uninstall.md](uninstall.md)(영어).

## 상태와 언어

위 기능은 지금 동작하고 자동 테스트가 있습니다. 버전마다 바뀐 점은 [CHANGELOG.md](../CHANGELOG.md)에 있습니다.
버그 보고와 아이디어는 이슈로 환영합니다. 풀 리퀘스트 전에는 [CONTRIBUTING.md](../CONTRIBUTING.md)를 보세요.

**Epokio를 쓰고 있다면** 무엇을 학습하는지 [Discussions](https://github.com/8rulerstar/epokio/discussions/categories/show-and-tell)에 한 줄 남겨 주세요. 문제가 없어도 큰 도움이 됩니다.

맥 앱은 영어, 한국어, 일본어, 중국어(간체·번체), 스페인어, 프랑스어, 독일어, 포르투갈어(브라질), 베트남어를 지원하고 맥 언어를 따릅니다(설정 → 일반에서 고를 수도 있습니다). 번역 수정은 이슈로 알려 주세요. 웹 화면은 영어와 한국어로, 브라우저 언어를 따르고 위쪽 버튼으로 바꿀 수 있습니다.

화면 사진은 앱이 만들어 주는 예시 학습으로 찍었습니다.
