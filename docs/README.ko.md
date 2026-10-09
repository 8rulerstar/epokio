<p align="center"><img src="images/icon.png" width="96" alt="Epokio 아이콘"></p>
<h1 align="center">Epokio</h1>
<p align="center"><b>학습이 멈추거나, NaN이 나거나, 끝나면 폰으로 알려 줍니다.</b><br>
코드는 그대로 둡니다. YOLO, Hugging Face, Lightning, Keras, TensorBoard가 이미 남기는 기록을 읽습니다. SSH로도 됩니다.</p>
<p align="center"><a href="https://pypi.org/project/epokio/"><img src="https://img.shields.io/pypi/v/epokio" alt="PyPI"></a> <a href="../LICENSE"><img src="https://img.shields.io/pypi/l/epokio" alt="License"></a> · <a href="../README.md">English</a></p>

<p align="center"><img src="images/alert.gif" width="720" alt="Epokio 웹 화면에서 학습이 '학습 중'에서 '멎음'으로 바뀌고, 학습 이름·에폭·최고 점수가 담긴 ntfy 알림이 폰에 옵니다"></p>

## 빠른 시작

파이썬 3.10 이상이면 윈도우, 맥, 리눅스 어디서나 됩니다. 학습을 돌리는 기계에서 터미널을 프로젝트 폴더에 열고:

```bash
pip install epokio
epokio setup
epokio watch --once
```

`epokio setup`은 학습 기록을 찾고, 도우미(기록을 읽고 알림을 보내는 작은 백그라운드 프로그램)를 띄우고, 그 웹 화면을 엽니다. `epokio watch --once`는 같은 목록을 터미널에 찍습니다.
setup은 지금 폴더와 바탕 화면, 문서, 다운로드, Projects, `~/runs`를 찾아봅니다(사용자 폴더 안만). `D:\`나 `/data`처럼 다른 곳에 있으면 폴더를 알려 주세요: `epokio setup --root D:\myproject\runs`.
윈도우에서 `pip`이나 `epokio`를 못 찾는다고 나오면 앞에 `py -m`을 붙이세요: `py -m epokio setup`.
pip이 *externally-managed-environment*로 멈추면(Ubuntu 24.04, Homebrew 파이썬) 가상환경이나 conda 환경에 설치하세요([방법](remote.md#on-windows-linux-or-your-phone), 영어).

## 폰 알림, 세 단계

1. 폰에 [ntfy](https://ntfy.sh) 앱을 깔고, 나만 아는 주제를 구독합니다. 주제 이름에는 영문, 숫자, `-`, `_`만 쓸 수 있습니다.
2. 학습 기계에 저장합니다. `your-secret-topic` 자리에 내 주제를 넣으세요: `epokio alerts --add https://ntfy.sh/your-secret-topic`
3. 시험해 봅니다: `epokio alerts --test`

이제 도우미가 학습이 끝나거나, 실패하거나(NaN, 비정상 종료), 멈추면(평소 에폭 시간보다 한참, 적어도 3분 넘게 새 에폭이 없으면) 알림을 보냅니다. Slack, Discord, 텔레그램 웹훅도 똑같이 넣으면 됩니다(`https`만).
알림은 도우미가 떠 있을 때만 가고, 컴퓨터를 다시 켜면 도우미는 저절로 돌아오지 않습니다. 로그인할 때 띄우려면 `pip install "epokio[tray]"` 뒤 `epokio setup --autostart`(윈도우와 리눅스. 화면 없는 서버에서는 systemd 서비스를 대신 만듭니다).

## 이런 걸 봅니다

<p align="center">
  <img src="images/run-detail.gif" height="400" alt="YOLO 학습의 손실 곡선이 한 에폭씩 늘어납니다. 검증 손실이 가장 낮은 23에폭에 표시가 붙고, 곧 과적합 표시와 함께 점수가 23에폭에서 정점을 찍고 떨어졌다는 메모가 뜹니다">
  <img src="images/phone.gif" height="400" alt="보기 전용 토큰으로 연 폰 화면: 한 학습이 완료로 바뀌고, Hugging Face 학습을 누르면 그 점수가 보이고, 새 체크포인트가 들어오자 점수가 오릅니다">
</p>

* **모든 학습을 한 목록에서 실시간으로.** 진행률, 남은 시간, 최고 점수. 어느 프레임워크가 남긴 기록이든 됩니다.
* **곡선과 쉬운 말 메모.** 검증 손실이 가장 낮은 에폭을 표시하고, 점수가 떨어지기 시작하면 알려 줍니다.
* **폰에서도.** `epokio setup --lan`이 주소와 보기 전용 토큰을 알려 줍니다. 그 토큰으로는 다 보이지만 바꾸는 단추는 전부 숨겨집니다.
* **터미널에서도**(`epokio watch`, SSH에 좋습니다), 윈도우·리눅스 트레이 아이콘, [맥 메뉴바 앱](studio.md)(영어).
* **계정도, 업로드도 없습니다.** 내가 넣은 알림만 기계 밖으로 나갑니다.

## 그냥 ...을 쓰면 안 되나

| | Epokio보다 잘하는 것 | Epokio가 더하는 것 |
|---|---|---|
| **TensorBoard** | step별 그래프, 그림, 히스토그램, 프로파일러. | 브라우저 탭 없이 알림. 여러 프레임워크 기록을 한 목록에(TensorBoard 파일 포함). |
| **W&B** | 팀 대시보드, 스윕, 아티팩트, 모델 레지스트리. | 계정도, 기록 코드도, 업로드도 없습니다. W&B 로컬 파일을 읽으니 같이 써도 됩니다. |
| **nvitop** | GPU, 프로세스, 메모리를 실시간으로. | 학습 자체를 압니다: 에폭, 남은 시간, 최고 점수, 멈춤과 NaN. |

## SSH로 원격 서버 보기

서버에서 빠른 시작을 그대로 합니다(`/data`, `/scratch` 아래 학습은 `--root`로 알려 주세요). SSH 창에서는 setup이 브라우저를 열지 않고,
내 컴퓨터에서 돌릴 터널 명령을 알려 줍니다. 예를 들어 `ssh -N -L 18787:127.0.0.1:8787 <server>`를 돌리면 `http://127.0.0.1:18787/`에서 서버의 학습이 보입니다.
도우미는 `127.0.0.1`에서만 듣기 때문에 네트워크에 열리지 않습니다. 그냥 SSH 창에서는 `epokio watch`로 보면 됩니다.
맥 앱은 서버에 아무것도 깔지 않고 SSH로 기록을 읽을 수도 있습니다([동작 방식](guide.ko.md#맥-앱에서-ssh로-보기)).

## 노트북과 코랩

도우미를 띄울 수 없는 곳에서는 학습 프로세스가 직접 알림을 보냅니다.

```python
!pip install epokio
!epokio alerts --add https://ntfy.sh/your-secret-topic

import epokio
with epokio.start("runs/colab-exp", epochs=20, notify=True) as run:
    for epoch in range(20):
        ...
        run.log(train_loss=tl, val_loss=vl, acc=acc)
```

블록이 끝나면, 또는 오류가 나면(오류 내용과 함께) 알림이 옵니다. 네트워크가 끊겨도 학습은 멈추지 않습니다.

## 기본 보안

* 도우미는 `127.0.0.1`에서만 듣습니다. `setup --lan`을 붙이면 네트워크에 열리고 토큰을 요구합니다.
* 웹 화면에서 학습을 시작할 수도 있습니다. 새로 만든 토큰은 보기 전용이고, 학습까지 시작하는 토큰은 `epokio agent --add-token NAME --scope run`으로 만듭니다.
* `--lan`으로 연 도우미는 `--allow-run`으로 띄우지 않는 한 네트워크로 온 것을 실행하지 않습니다.
* 공용 서버에서는 다른 계정도 `127.0.0.1`의 도우미를 읽을 수 있습니다. `epokio agent --require-token`으로 띄우고 사람마다 그 사람 폴더로 제한한 토큰을 주세요([방법](guide.ko.md#한계)).
* 도우미는 암호화되지 않은 HTTP를 씁니다. `--lan`보다 SSH 터널이나 Tailscale이 낫습니다. 자세히: [remote.md](remote.md)(영어).

## 읽는 형식

Ultralytics YOLO, Hugging Face Trainer, PyTorch Lightning(`CSVLogger`), Keras(`CSVLogger` 또는 `TensorBoard` 콜백),
TensorBoard 이벤트 파일과 W&B 로컬 파일(둘 다 설치할 필요 없음), timm, OpenMMLab, MAE·DeiT 계열 `log.txt`,
직접 짠 루프: `epokio.start`, 또는 첫 열이 `epoch`·`step`·`iter`·`iteration`인 CSV.
각각 어떤 파일을 읽는지, 계획 에폭과 최고 점수 규칙: [guide.ko.md](guide.ko.md#읽는-형식).

## 더 보기

[안내서](guide.ko.md)(알림, 한계, 전체 비교, 개인정보, 문제 해결) ·
[맥 앱](studio.md) · [원격 도우미, 윈도우 앱, 트레이, 폰](remote.md) · [AI 어시스턴트(MCP)](mcp.md) · [제거](uninstall.md)(이상 영어) ·
[CHANGELOG](../CHANGELOG.md) · [CONTRIBUTING](../CONTRIBUTING.md)

문제가 있으면 `epokio doctor` 출력을 이슈에 붙여 주세요(토큰은 출력하지 않습니다). 라이선스: [MIT](../LICENSE).
