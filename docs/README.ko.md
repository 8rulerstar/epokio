<p align="center">
  <img src="images/icon.png" width="128" alt="Epokio 아이콘">
</p>

<h1 align="center">Epokio</h1>

<p align="center">
  내 컴퓨터나 원격 GPU 서버에서 도는 ML 학습을 지켜봅니다. 맥에서는 메뉴바 앱으로, 윈도우·리눅스·폰에서는 웹 화면으로.<br>
  학습 코드를 고칠 필요도, 계정도 없습니다. 학습이 이미 기록을 남기는 폴더만 알려 주면 됩니다.
</p>

<p align="center">
  <img src="images/menubar-characters.gif" width="600" alt="학습 속도에 맞춰 메뉴바에서 뛰는 캐릭터">
</p>

<p align="center">
  <a href="#빠른-시작">빠른 시작</a> ·
  <a href="#읽는-형식">형식</a> ·
  <a href="#알림">알림</a> ·
  <a href="#ssh로-원격-기계-보기">SSH</a> ·
  <a href="#한계">한계</a> ·
  <a href="../README.md">English</a>
</p>

---

## 하는 일

* **이미 있는 기록을 읽습니다.** Ultralytics, Hugging Face Trainer, Lightning, Keras, timm, OpenMMLab, W&B 로컬 파일, TensorBoard 이벤트 파일, MAE·DeiT 계열 `log.txt`, 직접 만든 CSV. [읽는 형식](#읽는-형식) 참고.
* **진행률, 남은 시간, 최고 점수를 메뉴바에** 실시간으로. 학습이 끝나거나, 실패하거나(NaN loss), 멈추거나(비정상 종료·메모리 부족도 이렇게 드러납니다), 마지막 에폭 전에 그치면 알려 줍니다.
* **폰 알림**: ntfy, Slack, Discord, 텔레그램 웹훅으로 학습 기계가 직접 보냅니다. 시험 보내기 버튼으로 도착하는지 확인할 수 있습니다.
* **SSH로 원격 기계 보기**: 서버에 아무것도 설치하지 않습니다. 기록마다 새로 붙은 꼬리만 가져옵니다.
* **클래스별 점수**(클래스마다 정밀도·재현율·mAP, 약한 것부터)와 다음에 무엇을 바꿀지 쉬운 말로 적은 메모.
* **step 단위 학습**(`epoch` 없는 W&B, TensorBoard step 스칼라, 첫 열이 `step`·`iter`·`iteration`인 CSV)은 진행률을 step으로 보여 줍니다.
* **비교, 검수, 학습 시작**은 Studio 창이나 웹 화면에서. 자세한 내용은 [studio.md](studio.md).

## 빠른 시작

| 맥 | 윈도우 | 리눅스, GPU 서버 |
|---|---|---|
| [`.dmg` 받기](https://github.com/8rulerstar/epokio/releases/latest), 응용 프로그램 폴더로 끌어다 놓고 열기 | [`Epokio.exe` 받기](https://github.com/8rulerstar/epokio/releases/latest), 더블클릭 | `pip install epokio` 후 터미널에서 `epokio watch --root runs/`, 웹 화면은 `epokio setup` |

* **맥:** macOS 15 이상. 아직 공증을 받지 않아 처음엔 막힙니다. 한 번 열어 경고를 닫고 **시스템 설정 → 개인정보 보호 및 보안 → 그래도 열기**. macOS 26에서 아이콘이 안 보이면 **시스템 설정 → 메뉴 막대**에서 허용하세요.
* **윈도우:** 서명하지 않은 앱이라 처음 한 번 SmartScreen이 막을 수 있습니다. **추가 정보 → 실행**. 보기만 할 때는 파이썬이 필요 없고, 학습 탭에서 학습을 시작하려면 파이썬 3.10 이상이 필요합니다.
* **리눅스 서버:** Ubuntu 24.04에서는 가상환경을 쓰세요(PEP 668). SSH로 들어온 서버에서는 setup이 브라우저 대신 `ssh -L` 터널 명령을 알려 줍니다.
* **폰에서 웹 화면 보기:** 학습 기계에서 `--lan`을 붙여 setup을 돌리고(`epokio setup --lan`, 윈도우는 `py -m epokio setup --lan`) setup이 출력한 주소로 들어갑니다. 붙이지 않으면 도우미는 그 기계 안에서만 답합니다. SSH 터널로 들어가도 됩니다.

윈도우, 리눅스, 트레이 아이콘, 원격 도우미의 전체 절차: [remote.md](remote.md)(영어).

## 화면

<p align="center">
  <img src="images/popover-light.png" width="330" alt="메뉴바 팝오버, 밝은 화면">
  <img src="images/popover-dark.png" width="330" alt="메뉴바 팝오버, 어두운 화면">
</p>

<p align="center">
  <img src="images/studio-run-detail.png" width="620" alt="학습 하나의 화면: 점수, 곡선, 다음에 해 볼 것">
</p>

<p align="center">
  <img src="images/studio-compare.png" width="620" alt="비교: 여러 학습을 한 그래프에, 점수와 달랐던 설정만">
</p>

**자원 사용.** 맥에서 학습 폴더 50개를 지켜보는 백그라운드 도우미 하나만 재면 메모리(RSS) 약 45MB, CPU는 1분에 0.25초 미만으로 거의 0%입니다.

## 읽는 형식

프레임워크가 이미 쓰는 파일을 읽습니다. 기록 코드를 더할 필요가 없습니다.

| 프레임워크 | 읽는 것 | 보기·결과·비교 | 학습 시작 | 자동 라벨링·검수 |
|---|---|---|---|---|
| Ultralytics YOLO | `results.csv`, `args.yaml` | ✅ | ✅ | ✅ |
| Hugging Face Trainer | `trainer_state.json`(`checkpoint-*` 안도) | ✅ | 스크립트 | |
| PyTorch Lightning | `CSVLogger`의 `metrics.csv`, `hparams.yaml` | ✅ | 스크립트 | |
| Keras | `CSVLogger` 파일(`training.log`, `history.csv`) | ✅ | 스크립트 | |
| TensorBoard 기록 | `events.out.tfevents.*` 스칼라, TensorFlow 없이 읽음. `epoch` 태그가 있으면 에폭, 없으면 step 기준 | ✅ | 스크립트 | |
| 비전 연구 코드(MAE, DeiT, DINO, BEiT, ConvNeXt) | 에폭마다 JSON 한 줄인 `log.txt` | ✅ | 스크립트 | |
| timm `train.py` | `summary.csv`(`eval_top1`이 주 점수), `args.yaml` | ✅ | 스크립트 | |
| OpenMMLab(MMDetection 3.x, MMPretrain, MMSegmentation) | `vis_data/scalars.json`, 저장된 설정의 `max_epochs`(에폭 기반 학습만) | ✅ | 스크립트 | |
| Weights & Biases(로컬 파일) | `wandb/run-*/run-*.wandb`, wandb 설치 없이 읽음. `epoch` 값이 기록돼 있으면 에폭, 없으면 `_step` 기준. SSH로도 | ✅ | 스크립트 | |
| 직접 만든 학습 루프 | 첫 열이 `epoch`·`step`·`iter`·`iteration`이고 loss 열이 있는 CSV | ✅ | 스크립트 | |

진행률과 남은 시간을 내려면 전체 길이를 알아야 합니다. 에폭 수는 프레임워크 자체 파일이나 기록 옆 설정 파일
(`args.yaml`, `args.json`, `config.yaml`, `config.json`, `hparams.yaml`, `opt.yaml`)에서, step 학습은 같은 파일의
`max_steps`, `total_steps`, `max_iters` 같은 전체 step 수에서 읽습니다. 다른 프레임워크를 더하려면 작은 어댑터 클래스
하나면 되고, 목록은 `src/epokio/adapters.py`에 있습니다. 직접 만든 루프에서 `epokio.start`로 기록하는 방법은 [remote.md](remote.md).

## 알림

알림은 학습 기계가 직접 보내므로 맥이 꺼져 있어도 옵니다. 웹훅은 `https`여야 합니다.
[ntfy](https://ntfy.sh) 주소(예: `https://ntfy.sh/비밀-주제`)나 Slack, Discord, 텔레그램 웹훅을 넣으세요.

* **맥 앱:** 설정 → 알림.
* **웹 화면:** **알림**에서 넣고 **시험 보내기**로 도착하는지 확인합니다(도우미의 `POST /webhooks/test`).
* **터미널:** 도우미가 떠 있지 않아도 됩니다(SSH로만 들어가는 서버에서 편합니다).

```bash
# 맥·리눅스
epokio alerts --add https://ntfy.sh/비밀-주제
epokio alerts --list
epokio alerts --test        # 저장된 웹훅마다 시험 메시지 하나
epokio alerts --remove https://ntfy.sh/비밀-주제
```

```powershell
# 윈도우 (--list, --remove도 같은 방식)
py -m epokio alerts --add https://ntfy.sh/비밀-주제
py -m epokio alerts --test
```

## SSH로 원격 기계 보기

맥 앱에서 **설정 → 기계 → SSH로 보기**를 열고 `~/.ssh/config`의 호스트를 고릅니다(`ProxyJump` 포함).
서버에는 아무것도 설치하거나 쓰지 않습니다.

* **조건:** 서버에 `python3` 3.6 이상, 키 로그인(암호나 일회용 코드를 묻지 않아야 합니다). 서버에 인터넷은 필요 없습니다.
* **가져오는 것:** 알려진 기록 이름(`results.csv`, `log.txt`, `summary.csv`, `metrics.csv`, `trainer_state.json`, TensorBoard·W&B 파일 등)과 저장된 설정뿐이고, 이미지나 가중치는 가져오지 않습니다. 15초마다 확인하며, 바뀌지 않은 파일은 건너뛰고 늘어나기만 하는 기록은 새로 붙은 꼬리만 보냅니다.
* **크기 한도:** 글자 기록 4MB, TensorBoard·W&B 파일 20MB(이미 받은 파일은 새로 붙은 부분에 적용). 계속 늘어나는 글자 기록이 한도를 넘으면 첫 줄과 끝 4MB만 받고 이어 붙입니다. 한도를 넘은 TensorBoard·W&B·설정 파일은 건너뜁니다. 몇 개를 건너뛰었거나 잘랐는지는 맥 앱과 웹 화면 SSH 칸이 알려 줍니다.
* 홈 폴더 아래를 찾습니다. `/scratch/you/runs` 같은 경로는 *다른 폴더*에 더하세요.
* 보기 전용입니다. 그 기계에서 학습을 시작하려면 도우미를 설치합니다. 리눅스는 `pip install epokio` 후 `epokio setup --lan --autostart`, 윈도우는 `py -m pip install "epokio[tray]"` 후 `py -m epokio setup --lan --autostart`(파이썬 없이: `Epokio.exe setup --lan --autostart`). 토큰, `--lan`, 네트워크 안전: [remote.md](remote.md).

## 한계

* 에폭 없이 iteration 기반으로 도는 OpenMMLab 학습은 읽지 않습니다.
* SSH로는 알려진 기록 이름만 읽고, 아무 CSV나 읽지는 않습니다. 크기 한도를 넘은 바이너리 기록과 설정은 건너뜁니다.
* 직접 만든 CSV 이름이 `results.csv`, `metrics.csv`, `epokio_log.csv`이면 Ultralytics, Lightning, `epokio.start` 쪽 읽기로 넘어가 직접 만든 CSV로 읽히지 않습니다. 다른 이름을 쓰세요.
* 위 자원 수치는 백그라운드 도우미 하나만, 바뀌지 않는 학습 폴더 50개를 맥에서 잰 값입니다(RSS 약 45MB, CPU 1분에 0.25초 미만).
* 라벨 편집기와 자동 라벨링 시작은 맥 전용입니다. 웹 화면은 보기, 학습, 대기열, 비교, 검수, 스윕, 알림을 다룹니다.
* 맥 앱은 공증, 윈도우 앱은 서명을 받지 않아 둘 다 처음 실행할 때 경고가 뜹니다.
* 도우미는 암호화되지 않은 HTTP로 통신합니다. `--lan`보다 SSH 터널이나 Tailscale을 권합니다.

## 다른 도구와 비교

| | Epokio | TensorBoard | 클라우드 트래커(W&B, Comet) | MLflow, Aim | Ultralytics Platform | Trackio |
|---|---|---|---|---|---|---|
| 학습 스크립트 수정 | **없음** | 프레임워크가 이벤트 파일을 쓰면 없음 | 기록 호출 추가, 또는 내장 연동(HF Trainer, Ultralytics)으로 설정 하나 | 기록 호출 추가(MLflow는 autolog 있음) | Ultralytics는 없음: API 키로 로컬 학습을 전송 | `trackio.init`·`log` 호출 추가, 또는 TensorBoard·CSV 기록 가져오기 |
| 계정·서버 | **없음** | 없음 | 계정 | 로컬은 없음(`mlflow ui`, `aim up`), 또는 직접 운영하는 서버 | 계정 | 없음 |
| 데이터가 가는 곳 | **내 기계에 남음** | 내 기계 | 그쪽 클라우드 | 로컬 폴더(`./mlruns`, `.aim`) 또는 내 서버 | 그쪽 클라우드 | 내 기계(또는 직접 고른 Hugging Face Space·Dataset) |
| 늘 보이는 곳 | **메뉴바, 터미널, 트레이** | `tensorboard --logdir` 뒤 브라우저 탭 | 브라우저 탭, 폰 앱(iOS) | 브라우저 탭 | 브라우저 탭 | 브라우저 탭 |
| 한 화면에서 읽는 형식 | **Ultralytics, HF, Lightning, Keras, timm, OpenMMLab, W&B, TensorBoard, CSV** | 자기 이벤트 파일 | 자기 기록(W&B는 TensorBoard 동기화 가능) | 자기 기록(Aim은 TensorBoard·MLflow·W&B 기록 변환) | Ultralytics | 자기 기록(TensorBoard·CSV 가져오기) |
| 팀 공유, 모델 레지스트리 | 목표가 아님 | 없음 | **있음** | 내 서버에서 공유, 레지스트리는 MLflow만 | **있음** | 일부 |
| step 단위 그래프 | step 기반 학습은 진행률을 step으로 | **있음** | **있음** | **있음** | 에폭 단위 | **있음** |
| 가격 | 무료, MIT | 무료 | 무료 등급과 유료 요금제 | 무료 소프트웨어(호스팅 요금제 있음) | 무료 등급과 유료 요금제 | 무료 |

Epokio는 학습이 끝나거나 실패하거나 멈추면 스스로 알림(맥, 트레이, 폰 웹훅)을 보내고, 곡선을 보고 다음 학습을 제안합니다(예: "아직 좋아지는 중: best.pt에서 2배 더 길게").
클라우드 AI가 아니라 내 기계 안의 간단한 규칙으로 계산합니다.

**트래커를 대신하지 말고 옆에 두고 쓰세요.** 팀이 이미 W&B나 MLflow에 기록한다면 그대로 하세요.
Epokio는 W&B 로컬 파일과 TensorBoard 기록도 읽으므로, 계정이나 기록 호출을 더하지 않고 같은 학습을 메뉴바나 터미널에 보여 줍니다.
내 맥이나 GPU 기계에서 학습이 도는 동안 흘끗 보는 용도입니다.

## 개인정보

직접 켜지 않는 한 아무것도 기계 밖으로 나가지 않습니다. 앱은 내가 띄운 도우미와만 통신합니다.

| 선택 기능 | 보내는 것 | 가는 곳 |
|---|---|---|
| 웹훅(ntfy, Slack, Discord, 텔레그램) | 학습 이름, 에폭, 최고 점수, 사건 | 내가 넣은 주소 |
| 어시스턴트(말로 하는 명령) | 입력한 문장, 최근 학습 최대 12개의 이름 | 내 API 키로 TypeSafe |
| 결과 해설 다듬기 | 상태, 작업 종류, 점수, 설정 숫자, 언어, 초안 문장 | TypeSafe, 어시스턴트를 켰을 때만 |
| 이 맥에서 쓰는 해설(macOS 26 이상) | 없음 | 맥 안에 남음 |
| 업데이트 확인(Sparkle), 업데이트 키로 서명하기 전까지 현재 배포판에서는 꺼짐 | 앱과 macOS 버전 | 프로젝트의 GitHub 릴리스 |
| 맥 앱의 파이썬 준비 | 독립 실행형 파이썬을 내려받음(올리는 것 없음) | github.com/astral-sh/python-build-standalone |
| 문제 보고(맥 앱), 열기를 눌렀을 때만 | `errors.log` 끝부분(홈 폴더는 `~`로 표시)을 채운 GitHub 새 이슈 페이지를 엶. 페이지가 열릴 때 github.com에 닿고, 고치거나 탭을 닫아도 됨 | github.com |
| 학습 탭의 "파이썬 설치" 버튼 | PyTorch, Ultralytics와 의존 패키지를 내려받음(올리는 것 없음) | PyPI, download.pytorch.org |

웹훅은 `https`여야 합니다. TypeSafe 키는 키체인에 있고 두 기능 모두 켜기 전까지 꺼져 있습니다.
오류 기록은 `~/.epokio/logs`에 남고, 문제 보고에서 열기를 눌렀을 때만 밖으로 나갑니다.

## 이상할 때

* `epokio doctor`(`pip install epokio` 필요, `Epokio.exe`에는 `doctor`가 없습니다. 윈도우는 `py -m epokio doctor`)가 Epokio가 보는 것을 출력합니다.
  버전, 도우미가 도는지(어느 버전인지), 지켜보는 폴더, 찾은 파이썬 환경, 로그 마지막 줄. 토큰은 출력하지 않으니 버그 보고에 그대로 붙여도 됩니다(원본 데이터는 `--json`).
* 도우미는 `~/.epokio/agent.log`(1MB, 이전 사본 하나 보관, 윈도우는 `%USERPROFILE%\.epokio\agent.log`)에 오류 원인을 적습니다.
* 업그레이드한 뒤에는 `epokio setup`을 다시 돌리세요. 옛 버전으로 도는 도우미를 다시 띄웁니다.
  이 기계의 도우미는 `epokio agent --stop`(윈도우는 `py -m epokio agent --stop` 또는 `Epokio.exe agent --stop`)으로 끕니다.

## 제거

Epokio를 끝내고 `Epokio.app`을 휴지통으로 옮기고, 직접 띄운 도우미를 끈 뒤(`epokio agent --stop`, 앱이 띄운 것은 앱이 끕니다) `rm -rf ~/.epokio`, pip으로 설치했다면 `pip uninstall epokio`.
설정, 키체인 항목, 윈도우·리눅스 절차: [uninstall.md](uninstall.md).

## 더 보기

아래 문서는 영어입니다.

* [studio.md](studio.md): 메뉴바, 캐릭터, 결과, Studio 창
* [remote.md](remote.md): 원격 도우미, 토큰, 윈도우, 리눅스, 트레이, 터미널 보기, 직접 만든 학습 루프
* [mcp.md](mcp.md): AI 어시스턴트(MCP)와 말로 하는 명령
* [uninstall.md](uninstall.md): 전체 제거
* [DESIGN.md](DESIGN.md): 구성 요소가 맞물리는 방식

## 상태

위 기능은 지금 동작하고 자동 테스트가 있습니다. 버전마다 바뀐 점은 [CHANGELOG.md](../CHANGELOG.md)에 있습니다.
버그 보고와 아이디어는 이슈로 환영합니다. 풀 리퀘스트 전에는 [CONTRIBUTING.md](../CONTRIBUTING.md)를, 구조는 [DESIGN.md](DESIGN.md)를 보세요.

맥 앱은 영어, 한국어, 일본어, 중국어(간체·번체), 스페인어, 프랑스어, 독일어, 포르투갈어(브라질), 베트남어를 지원하고 맥 언어를 따릅니다(설정 → 일반에서 고를 수도 있습니다). 번역 수정은 이슈로 알려 주세요. 웹 화면은 영어와 한국어로, 브라우저 언어를 따르고 위쪽 버튼으로 바꿀 수 있습니다.

라이선스: [MIT](../LICENSE).
