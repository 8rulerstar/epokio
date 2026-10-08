"use strict";
// 화면 언어(영어·한국어)와 브라우저 저장소. 다른 스크립트보다 먼저 불러온다(index.html 순서).
// 사이트 데이터를 막은 브라우저에서는 localStorage를 읽기만 해도 예외가 나서 페이지가 통째로 비었다.
// 그럴 땐 이 탭에서만 기억하는 빈 객체로 대신한다
const LS = (() => { try { const s = window.localStorage; s.getItem("x"); return s; } catch { return {}; } })();

// ── 언어 ──
// 영어 원문이 코드에 있고, 한국어는 아래 KO 표에서 찾는다(msg.py와 같은 방식: 키 = 영어 문장 그대로).
// ★화면과 agent 문장(검진·해설·진단)은 항상 같은 언어여야 한다. api()가 LANG을 Accept-Language로 싣는다
const LANG = (() => {
  let s = "";
  try { s = LS.epokioLang || ""; } catch { }
  return (s || navigator.language || "en").toLowerCase().startsWith("ko") ? "ko" : "en";
})();
const KO = {
  // SSH 서버(ssh.js)
  "SSH servers": "SSH 서버", "Read now": "지금 읽기", "Connected": "연결됨", "Could not connect": "연결하지 못함", "Not read yet": "아직 읽지 않음",
  "read {d} ago": "{d} 전에 읽음", "{n} log files over the size limit were skipped": "크기 제한을 넘은 로그 파일 {n}개를 건너뛰었습니다",
  "{n} large log files: only the last part was loaded": "큰 로그 파일 {n}개는 끝부분만 받았습니다",
  "and {n} more": "외 {n}개", "Too many folders to read": "읽을 폴더가 너무 많습니다",
  // 탭·상태
  "Runs": "학습 기록", "Train": "학습", "Queue": "대기열", "Compare": "비교", "Alerts": "알림",
  "Training": "학습 중", "Starting": "시작하는 중", "Stalled": "진행 없음", "Failed": "실패", "Stopped": "중단됨", "Ended": "종료", "Done": "완료",
  "Waiting": "대기 중", "Running": "실행 중", "Cancelled": "취소됨",
  "kind|Training": "학습", "section|Training": "학습",
  "Evaluation": "평가", "Auto-labelling": "자동 라벨링", "Export": "내보내기", "Script": "스크립트", "Python setup": "파이썬 설치",
  "Change the language of this page": "이 화면의 언어를 바꿉니다",
  // 시간·공통
  "{n}s": "{n}초", "{n}m": "{n}분", "{h}h {m}m": "{h}시간 {m}분", "{n}d": "{n}일",
  "{n}h": "{n}시간", "{d}d {h}h": "{d}일 {h}시간",
  "{d} left": "{d} 남음", "{d} ago": "{d} 전", "epoch {e}/{n}": "에폭 {e}/{n}", "epoch {n}": "에폭 {n}", "step {e}/{n}": "스텝 {e}/{n}", "step {n}": "스텝 {n}", "steps": "스텝", "took {d}": "걸린 시간 {d}",
  "{n} active": "{n}개 진행 중", "Can't reach Epokio": "Epokio에 연결되지 않음", "last update {time}": "마지막 갱신 {time}",
  "MEM": "메모리", "request failed ({status})": "요청 실패 ({status})", "this machine": "이 기계",
  "Box": "박스", "Pose": "포즈", "Mask": "마스크", "precision": "정밀도", "recall": "재현율",
  "The token did not work.": "토큰이 맞지 않습니다.", "The token stopped working.": "토큰이 더 이상 맞지 않습니다.",
  // 학습 기록
  "Can't reach Epokio on this machine.": "이 기계의 Epokio에 연결되지 않습니다.",
  "Is the helper running? On Windows, look for the Epokio icon under ^ at the right end of the taskbar, or run Epokio.exe again.": "도우미가 켜져 있는지 확인하세요. 윈도우에서는 작업 표시줄 오른쪽 ^ 안의 Epokio 아이콘을 확인하거나, Epokio.exe를 다시 실행하세요.",
  "No training runs found yet.": "아직 찾은 학습이 없습니다.", "This folder does not exist:": "없는 폴더입니다:", "Check the path given with --root.": "--root로 준 경로를 확인하세요.",
  "Some run folders have paths longer than Windows allows (260 characters), so they cannot be read:": "경로가 윈도우 한도(260자)보다 길어 읽지 못한 학습 폴더가 있습니다:",
  "Move them to a shorter path, or turn on long paths in Windows.": "더 짧은 경로로 옮기거나 윈도우에서 긴 경로를 켜세요.",
  "Add the folder where your runs are saved (the one that holds <code>runs</code>, or <code>runs</code> itself).": "학습 결과가 저장되는 폴더를 추가하세요(<code>runs</code>가 들어 있는 폴더나 <code>runs</code> 폴더 자체).",
  "Add folder": "폴더 추가",
  "Adding a folder needs this machine's token": "폴더를 추가하려면 이 기계의 토큰이 필요합니다", "This needs this machine's token": "이 기계의 토큰이 필요합니다",
  "The settings table needs this machine's token": "설정 표를 보려면 이 기계의 토큰이 필요합니다", "Changing alerts needs this machine's token": "알림을 바꾸려면 이 기계의 토큰이 필요합니다",
  "No runs match {q}.": "{q}에 맞는 학습이 없습니다.", "Clear": "지우기",
  "The starting model file. A .pt file continues from trained weights; a .yaml file starts from scratch.": "시작할 모델 파일입니다. .pt는 학습된 가중치에서 출발하고, .yaml은 처음부터 학습합니다.", "How many times to go over all the training images.": "학습 이미지 전체를 몇 번 볼지입니다.", "Stop after this many hours, even if epochs remain. Overrides epochs.": "에폭이 남아도 이 시간(시간 단위)이 지나면 멈춥니다. 에폭보다 우선합니다.", "Stop early if the score has not improved for this many epochs.": "이 에폭 수만큼 점수가 나아지지 않으면 일찍 멈춥니다.", "Images per step. -1 picks the largest that fits in GPU memory.": "한 번에 넣는 이미지 수입니다. -1이면 GPU 메모리에 맞게 가장 크게 고릅니다.", "Images are resized to this many pixels on the long side. Bigger finds small objects but is slower.": "이미지 긴 변을 이 픽셀로 맞춥니다. 크면 작은 물체를 잘 찾지만 느립니다.", "Also save a checkpoint every this many epochs. -1 saves only the best and last.": "이 에폭마다 체크포인트를 따로 저장합니다. -1이면 최고·마지막만 저장합니다.", "Keep images in memory (ram) or on disk to load them faster.": "이미지를 메모리(ram)나 디스크에 미리 두어 빨리 읽습니다.", "Which GPU to use: 0 is the first, 0,1 uses two, cpu uses no GPU.": "쓸 GPU입니다. 0은 첫 번째, 0,1은 두 개, cpu는 GPU를 쓰지 않습니다.", "Processes that load images. Lower it if the machine runs out of memory.": "이미지를 읽는 프로세스 수입니다. 메모리가 모자라면 줄이세요.", "Folder that holds the run folders.": "학습 폴더들을 담을 폴더입니다.", "Name of this run's folder.": "이 학습의 폴더 이름입니다.", "Write into the run folder even if it already exists.": "같은 이름의 학습 폴더가 있어도 거기에 씁니다.", "Start from weights trained on a large dataset. Usually better than starting from nothing.": "큰 데이터로 미리 학습한 가중치에서 시작합니다. 대개 처음부터보다 낫습니다.", "How the weights are updated. auto picks one for you.": "가중치를 고치는 방법입니다. auto면 알아서 고릅니다.", "Random seed. The same seed gives more repeatable results.": "난수 시드입니다. 같으면 결과가 더 비슷하게 나옵니다.", "Make results repeatable, at some cost in speed.": "결과를 똑같이 재현되게 합니다. 조금 느려집니다.", "Treat every class as one class.": "모든 클래스를 한 클래스로 봅니다.", "Keep each batch's image shape instead of squares. Less padding, less augmentation.": "이미지를 정사각형으로 채우지 않고 비율을 지킵니다. 여백은 줄고 증강은 약해집니다.", "Lower the learning rate along a cosine curve.": "학습률을 코사인 곡선을 따라 줄입니다.", "Turn off mosaic augmentation for the last this many epochs.": "마지막 이 에폭 동안 모자이크 증강을 끕니다.", "Continue from the last checkpoint of this run.": "이 학습의 마지막 체크포인트부터 이어 합니다.", "Mixed precision. Faster and uses less GPU memory.": "혼합 정밀도입니다. 빠르고 GPU 메모리를 덜 씁니다.", "Train on only this share of the images (1.0 = all).": "이미지 중 이 비율만 학습합니다(1.0 = 전부).", "Keep the first this many layers fixed.": "앞쪽 이 개수의 층은 고정합니다.", "Check the score on the validation images during training.": "학습하는 동안 검증 이미지로 점수를 봅니다.", "Save charts and example images in the run folder.": "학습 폴더에 그래프와 예시 이미지를 저장합니다.", "Randomly drop connections to fight overfitting (classify only).": "과적합을 막으려고 연결을 무작위로 끊습니다(분류만).", "Starting learning rate.": "처음 학습률입니다.", "Final learning rate as a share of the starting one.": "마지막 학습률(처음 학습률에 곱하는 비율)입니다.", "How much each update keeps from the previous one.": "업데이트가 이전 방향을 얼마나 이어 가는지입니다.", "Keeps weights small to fight overfitting.": "가중치를 작게 유지해 과적합을 막습니다.", "Epochs spent slowly raising the learning rate at the start.": "처음에 학습률을 천천히 올리는 에폭 수입니다.", "Random change of hue.": "색조를 무작위로 바꾸는 정도입니다.", "Random change of saturation.": "채도를 무작위로 바꾸는 정도입니다.", "Random change of brightness.": "밝기를 무작위로 바꾸는 정도입니다.", "Random rotation, in degrees.": "무작위 회전 각도입니다.", "Random shift, as a share of the image size.": "무작위 이동(이미지 크기에 대한 비율)입니다.", "Random zoom in or out.": "무작위 확대·축소 정도입니다.", "Chance of flipping an image left to right.": "좌우로 뒤집을 확률입니다.", "Chance of flipping an image upside down.": "위아래로 뒤집을 확률입니다.", "Chance of stitching four images into one.": "이미지 네 장을 한 장으로 붙일 확률입니다.", "Chance of blending two images together.": "두 이미지를 겹칠 확률입니다.", "Print more in the log.": "로그에 더 자세히 적습니다.",
  "Added.": "추가했습니다.", "Looking for runs…": "학습을 찾는 중입니다…", "Not added.": "추가하지 못했습니다.",
  "Score": "점수", "Scores": "점수", "No details for this run.": "이 학습의 상세 정보가 없습니다.",
  "Open Train with the settings this run used": "이 학습의 설정으로 학습 화면을 엽니다", "Resumed from {name}": "{name}에서 이어 함", "More": "더 보기", "Fewer": "접기", "the official score for this task": "이 작업의 공식 점수",
  "the usual main score for this kind of model": "이런 모델의 흔한 대표 점수", "the first validation mAP, F1, accuracy, IoU or Dice": "검증 mAP·F1·정확도·IoU·Dice 중 첫째",
  "no other score was logged, so the validation loss": "다른 점수가 없어 검증 손실", "the first score column": "점수 열 중 첫째",
  "chosen for this run": "이 학습에 고른 것", "chosen for the folder this run is in": "이 학습이 든 폴더에 고른 것", "Train again with these settings": "이 설정으로 다시 학습", "Resume": "이어 하기", "Main score": "대표 점수", "Cancel": "취소", "Cancel {name}? It will not run, and you would have to add it again.": "{name}을(를) 취소할까요? 실행되지 않고, 다시 하려면 새로 넣어야 합니다.", "queue: {r} running, {q} waiting": "대기열 {r}개 실행 중, {q}개 대기", "Lost connection to {machine}": "{machine}과(와) 연결이 끊겼습니다", "showing the state at {time}": "{time} 기준 화면", "Watch another folder of runs": "학습이 있는 다른 폴더 보기", "Folder": "폴더", "Folder with runs on {machine}": "{machine}에서 학습이 있는 폴더 경로", "Settings table for all shown runs": "보이는 학습 전부의 설정 표", "Each score is ranked on its own.": "점수마다 따로 순위를 매깁니다.", "Showing {r} of {n} runs and {c} of {k} settings. Filter the list to narrow it down; the CSV has everything.": "학습 {n}개 중 {r}개, 설정 {k}개 중 {c}개를 보입니다. 목록을 거르면 좁혀지고, CSV에는 전부 있습니다.", "Settings table": "설정 표", "Hide": "숨기기", "Runs use different scores:": "학습마다 대표 점수가 다릅니다:", "These runs used the same settings.": "이 학습들은 설정이 모두 같습니다.", "Newest": "최근 순", "Best score": "점수 순", "Tags, separated by commas": "태그(쉼표로 구분)", "Report": "보고서", "A Markdown report of the picked runs (or all shown), saved on the training machine": "고른 학습(없으면 보이는 전부)의 마크다운 보고서를 학습 기계에 저장합니다", "Report saved on {machine}: {path}": "{machine}에 보고서를 저장했습니다: {path}", "Up to 4 runs. Untick one first.": "4개까지입니다. 하나를 먼저 빼세요.", "On this machine, open this page from the Epokio tray icon or <code>epokio setup</code> (it unlocks by itself), or find the token in <code>~/.epokio/token</code> (Windows: <code>%USERPROFILE%\\.epokio\\token</code>).": "이 기계에서는 Epokio 트레이 아이콘이나 <code>epokio setup</code>으로 이 페이지를 열면 저절로 풀립니다. 또는 <code>~/.epokio/token</code>(윈도우: <code>%USERPROFILE%\\.epokio\\token</code>)에서 토큰을 찾으세요.", "Target": "목표", "Automatic": "자동", "Direction": "방향", "Higher is better": "높을수록 좋음", "Lower is better": "낮을수록 좋음", "lower is better": "낮을수록 좋음", "none": "없음", "Show {n} more": "{n}개 더 보기", "Folder with runs": "학습이 있는 폴더", "Webhook address": "웹후크 주소", "Tick \"Add python.exe to PATH\" while installing, then press the button again.": "설치할 때 \"Add python.exe to PATH\"를 체크한 뒤 버튼을 다시 누르세요.", "Continue from the last saved epoch (weights/last.pt)": "마지막으로 저장한 에폭부터 이어 합니다(weights/last.pt)",
  "At the best epoch. Higher is better.": "최고 에폭 기준입니다. 높을수록 좋습니다.",
  "Precision": "정밀도", "Recall": "재현율", "Best epoch": "최고 에폭",
  "Of what it found, how much was right": "찾은 것 중 맞은 비율", "Of what was there, how much it found": "있던 것 중 찾아낸 비율",
  "Balance of precision and recall": "정밀도와 재현율의 균형",
  "Curves": "곡선", "Loss": "손실", "Smoothing": "스무딩",
  "Loss should go down. If validation goes up while training goes down, it is overfitting.": "손실은 내려가야 합니다. 학습 손실은 내려가는데 검증 손실이 오르면 과적합입니다.",
  "Scores should go up and level off.": "점수는 오르다가 평평해져야 합니다.",
  "Your notes": "내 메모", "Goal:": "목표:", "reached": "달성", "What stands out": "눈에 띄는 점",
  "Result images": "결과 이미지", "Saved by the framework. Click to enlarge.": "프레임워크가 저장한 그림입니다. 누르면 크게 봅니다.",
  "Settings used": "사용한 설정", "No data yet.": "아직 데이터가 없습니다.",
  "Environment": "실행 환경", "Recorded when Epokio started this run.": "Epokio가 이 학습을 시작할 때 기록했습니다.",
  // 비교
  "Tick two to eight runs in the list.": "목록에서 학습을 2~8개 고르세요.", "Compare runs": "학습 비교",
  "Run": "학습", "Epochs": "에폭", "Steps": "스텝", "Epochs / steps": "에폭 / 스텝", "Model": "모델",
  "These runs used different data.": "이 학습들은 데이터가 다릅니다.", "Their scores are not directly comparable.": "점수를 그대로 비교할 수 없습니다.",
  "Filter by name or #tag": "이름이나 #태그로 찾기", "All runs as a spreadsheet": "모든 학습을 표 파일로 받습니다",
  "Pick up to 4 runs": "최대 4개까지 고르세요", "No run matches.": "맞는 학습이 없습니다.",
  "Same settings in all of them.": "모두 같은 설정입니다.", "Settings that differ": "다른 설정", "Setting": "설정",
  // 알림
  "Training finished": "학습 완료", "Training failed": "학습 실패", "Training may have stopped": "학습이 멈춘 것 같음", "Training stopped logging": "학습 기록이 멈춤",
  "Stopped before the last epoch": "마지막 에폭 전에 끝남", "Training started": "학습 시작", "Job finished": "작업 완료", "Job failed": "작업 실패",
  "Goal reached": "목표 점수 달성", "Disk almost full": "디스크 공간 부족", "GPU is very hot": "GPU가 매우 뜨거움", "Fans at full speed": "팬이 최고 속도로 돎", "Per class": "클래스별", "not in validation set": "검증셋에 없음", "Filter": "거르기", "Tags": "태그", "Updated": "갱신", "Select {name}": "{name} 고르기", "Python": "파이썬", "Epoch": "에폭", "Machine while training": "학습하는 동안의 기계", "Predictions by epoch": "에폭별 예측", "data version": "데이터 버전", "What changed in the data": "데이터에서 바뀐 것", "The data changed after this run trained": "이 학습 뒤에 데이터가 바뀌었음", "Data v{n} of {of}": "데이터 v{n} / {of}", "Data {fp}": "데이터 {fp}", "Save predictions every 5 epochs": "5에폭마다 예측 사진 저장", "Predicts 4 validation images on the CPU every 5 epochs, so you can watch the model learn. Costs a second or two each time.": "5에폭마다 검증 이미지 4장을 CPU로 예측해 모델이 배우는 과정을 볼 수 있게 합니다. 한 번에 1~2초 걸립니다.", "The same validation images, predicted as training went on. Drag to compare.": "같은 검증 이미지를 학습이 진행되며 예측한 것입니다. 끌어서 비교하세요.", "GPU memory": "GPU 메모리", "{n} min": "{n}분",
  "Recorded every 15 seconds while this run trained. Averages below.": "학습하는 동안 15초마다 기록했습니다. 아래는 평균입니다.",
  "Other runs trained at the same time, so these are shared numbers.": "같은 시간에 다른 학습도 돌아서, 함께 쓴 값입니다.", "GPU temperature": "GPU 온도", "SoC temperature": "SoC 온도", "Class": "클래스", "Examples": "사례", "few": "적음",
  "Which classes pull the score down. Runs Epokio starts save this at the end; for this one it takes one validation pass with best.pt.": "어느 클래스가 점수를 끌어내리는지 봅니다. Epokio로 시작한 학습은 끝날 때 저장하고, 이 학습은 best.pt로 검증을 한 번 돌리면 됩니다.",
  "Work out per-class scores": "클래스별 점수 계산", "Start it on the machine that has this run.": "이 학습이 있는 기계에서 시작하세요.",
  "From a validation pass with best.pt.": "best.pt로 검증한 결과입니다.", "From the last validation of this run.": "이 학습의 마지막 검증 결과입니다.",
  "Weakest first. Highlighted: well below the class average.": "약한 순서. 강조: 클래스 평균보다 크게 낮음.", "Few examples: the score is shaky": "사례가 적어 점수가 흔들립니다",
  "Class average": "클래스 평균", "Added to the queue. The table appears here when it finishes.": "대기열에 넣었습니다. 끝나면 여기에 표가 나옵니다.", "Fan": "팬", "Fan speed": "팬 속도", "GPU fan": "GPU 팬", "GPU fan speed": "GPU 팬 속도",
  "GPU memory is full": "GPU 메모리가 가득 참", "Training resumed": "학습이 다시 진행 중",
  "On: sends to {hosts}.": "켜짐 · 받는 곳: {hosts}", "Off.": "꺼짐.", "Phone alerts": "폰 알림",
  "Easiest: install the free <b>ntfy</b> app on your phone, subscribe to a topic with a long random name, and paste <code>https://ntfy.sh/your-topic</code> here. Slack, Discord and Telegram webhook addresses work too. Anyone who knows the topic can read it, so make it hard to guess.":
    "가장 쉬운 방법: 폰에 무료 앱 <b>ntfy</b>를 설치하고, 길고 무작위인 이름의 토픽을 구독한 뒤 <code>https://ntfy.sh/your-topic</code>을 여기에 붙여 넣으세요. Slack·Discord·Telegram 웹후크 주소도 됩니다. 토픽 이름을 아는 사람은 누구나 볼 수 있으니 짐작하기 어렵게 지으세요.",
  "Save": "저장", "Turn off": "끄기", "Send a test": "시험 보내기", "Test sent.": "시험 알림을 보냈습니다.", "Some alerts did not go through.": "일부 알림이 가지 않았습니다.", "Delivered": "전달됨",
  "Not saved.": "저장하지 못했습니다.", "best {v}": "최고 {v}",
  "No notifications yet. When a run finishes, fails or stalls, it shows up here.": "아직 알림이 없습니다. 학습이 끝나거나, 실패하거나, 멈추면 여기에 나타납니다.",
  // 잠금
  "Starting a run needs this machine's token": "학습을 시작하려면 이 기계의 토큰이 필요합니다",
  "The queue needs this machine's token": "대기열을 보려면 이 기계의 토큰이 필요합니다",
  "Starting and cancelling runs is locked, so nobody else on your network can run commands here.": "같은 네트워크의 다른 사람이 여기서 명령을 실행하지 못하도록 학습 시작과 취소는 잠겨 있습니다.",
  "From a terminal on this machine: {cmd}. On a Mac: Settings, Machines.": "이 기계의 터미널에서는 {cmd}. 맥에서는 설정의 기계 항목에 있습니다.",
  "From a terminal on that machine, run Epokio with <code>agent --show-token</code>, for example <code>.\\Epokio.exe agent --show-token</code>, <code>py -m epokio agent --show-token</code> or <code>epokio agent --show-token</code>. On a Mac: Settings, Machines.":
    "그 기계의 터미널에서 Epokio를 <code>agent --show-token</code>으로 실행하세요. 예: <code>.\\Epokio.exe agent --show-token</code>, <code>py -m epokio agent --show-token</code>, <code>epokio agent --show-token</code>. 맥에서는 설정의 기계 항목에 있습니다.",
  "That token did not work.": "그 토큰은 맞지 않습니다.", "It may have changed on this machine.": "이 기계에서 토큰이 바뀌었을 수 있습니다.",
  "Paste the token": "토큰 붙여 넣기", "Unlock": "잠금 풀기",
  "Remove the token from this browser": "이 브라우저에서 토큰을 지웁니다", "Lock this page": "이 화면 잠그기",
  // 파이썬 설치
  "Installing. This downloads 1 to 3 GB and takes 5 to 15 minutes. You can watch it in Queue.": "설치하는 중입니다. 1~3GB를 받고 5~15분 걸립니다. 대기열에서 볼 수 있습니다.",
  "Setup did not finish. Open Queue to see the log.": "설치가 끝나지 않았습니다. 대기열에서 로그를 보세요.",
  "Try again": "다시 시도", "Set up automatically": "자동으로 설치",
  "Or let Epokio set up a Python for training.": "또는 Epokio가 학습용 파이썬을 설치하게 할 수 있습니다.", "Set up Python for training.": "학습용 파이썬을 설치하세요.",
  "Epokio makes a separate Python environment just for training (<code>~/.epokio/envs/epokio</code>) and installs Ultralytics and PyTorch in it, with CUDA if this PC has an NVIDIA GPU. Your other Python setups are not touched. Delete that folder to remove it.":
    "Epokio가 학습 전용 파이썬 환경(<code>~/.epokio/envs/epokio</code>)을 따로 만들고 Ultralytics와 PyTorch를 설치합니다. 이 기계에 NVIDIA GPU가 있으면 CUDA 판으로 설치합니다. 다른 파이썬 환경은 건드리지 않습니다. 지우려면 그 폴더를 지우면 됩니다.",
  // 학습 시작
  "General": "일반", "Validation": "검증", "Other": "기타",
  "Epochs (passes over the data)": "에폭 (데이터를 몇 번 돌지)", "Image size (px)": "이미지 크기 (px)",
  "Batch size (-1 = automatic)": "배치 크기 (-1 = 자동)", "Device (0 = first GPU, cpu)": "장치 (0 = 첫 GPU, cpu)",
  "Detect": "검출", "Segment": "분할", "Classify": "분류",
  "Nano": "초소형", "Small": "소형", "Medium": "중형", "Large": "대형", "X-Large": "초대형",
  "not set": "설정 안 함", "Data": "데이터", "Check data": "데이터 점검", "Tiny sample": "작은 샘플",
  "8 public images, downloaded by Ultralytics": "공개 이미지 8장, Ultralytics가 받습니다",
  "Path to a data.yaml on {machine}.": "{machine}에 있는 data.yaml 경로입니다.",
  "Looking for Python environments on {machine}. The first time can take a few seconds.": "{machine}에서 파이썬 환경을 찾는 중입니다. 처음에는 몇 초 걸릴 수 있습니다.",
  "needs {pkg}": "{pkg} 필요",
  "Runs one at a time on {machine}. If something is already training, this waits in the queue.": "{machine}에서 한 번에 하나씩 돌립니다. 이미 도는 학습이 있으면 대기열에서 기다립니다.",
  "Name": "이름", "Taken from the data folder if empty": "비워 두면 데이터 폴더 이름을 씁니다", "Shown in the queue.": "대기열에 보이는 이름입니다.",
  "This environment cannot train yet.": "이 환경으로는 아직 학습할 수 없습니다.", "It needs {pkg}.": "{pkg} 패키지가 필요합니다.",
  "Pick another one, run {cmd}, or let Epokio set one up.": "다른 환경을 고르거나, {cmd}를 실행하거나, Epokio가 설치하게 하세요.",
  "Could not read the settings.": "설정을 읽지 못했습니다.",
  "What should the model learn?": "모델이 무엇을 배울까요?", "Model size": "모델 크기",
  "Bigger is more accurate but slower. Nano is enough to try things out.": "클수록 정확하지만 느립니다. 시험 삼아 해 보기에는 초소형으로 충분합니다.",
  "Hide the other settings": "나머지 설정 숨기기", "Show all {n} settings": "설정 {n}개 모두 보기", "Start training": "학습 시작",
  "Ultralytics {version} runs it. Only the values you changed are sent.": "Ultralytics {version}이(가) 실행합니다. 바꾼 값만 보냅니다.",
  "Filled in from {name}.": "{name}의 설정으로 채웠습니다.",
  "Change anything, then start. It trains as a new run and leaves the old one as it is.": "원하는 값을 바꾼 뒤 시작하세요. 새 학습으로 돌고 예전 학습은 그대로 둡니다.",
  "Type the path to a data.yaml first.": "먼저 data.yaml 경로를 적으세요.",
  "Sample data.": "샘플 데이터입니다.", "Ultralytics downloads it on the first run.": "첫 학습 때 Ultralytics가 받습니다.",
  "Checking…": "점검하는 중…", "Could not read it.": "읽지 못했습니다.",
  "Looks good.": "좋아 보입니다.", "Worth a look.": "살펴볼 것이 있습니다.", "Has problems.": "문제가 있습니다.", "Checked.": "점검했습니다.",
  "train": "학습", "val": "검증", "test": "테스트",
  "{n} {split}": "{split} {n}장", "{counts} images": "이미지 {counts}", "1 class": "클래스 1개", "{n} classes": "클래스 {n}개",
  "Choose the data first.": "먼저 데이터를 고르세요.", "Type a data.yaml path, or use the tiny sample.": "data.yaml 경로를 적거나 작은 샘플을 쓰세요.",
  "Checking the data first…": "먼저 데이터를 점검하는 중…", "The data.yaml could not be read.": "data.yaml을 읽지 못했습니다.",
  "Not started. The data has a problem.": "시작하지 않았습니다. 데이터에 문제가 하나 있습니다.",
  "Not started. The data has {n} problems.": "시작하지 않았습니다. 데이터에 문제가 {n}개 있습니다.",
  "Start anyway": "그래도 시작", "Added to the queue.": "대기열에 넣었습니다.", "Not started.": "시작하지 않았습니다.",
  "The token stopped working. Unlock again.": "토큰이 더 이상 맞지 않습니다. 잠금을 다시 푸세요.",
  // 대기열
  "about {d} left, done around {time}": "약 {d} 남음, {time}쯤 끝남",
  "for {d}": "{d}째", "added {d} ago": "{d} 전에 추가", "ended {d} ago": "{d} 전에 끝남", "exit {code}": "종료 코드 {code}",
  "Move up": "위로", "Move down": "아래로", "Hide log": "로그 숨기기", "Log": "로그", "Stop": "중지",
  "Loading…": "불러오는 중…", "No output yet.": "아직 출력이 없습니다.",
  "One at a time on {machine}": "{machine}에서 한 번에 하나씩", "New run": "새 학습",
  "Nothing here yet. Start a run from Train, or from the Mac app.": "아직 아무것도 없습니다. 학습 탭이나 맥 앱에서 학습을 시작하세요.",
  "Stop this run? The epochs it has finished stay on disk, but it will not continue.": "이 학습을 멈출까요? 끝난 에폭은 디스크에 남지만 이어서 돌지는 않습니다.",
  // 맥 작업(검수·스윕·계보·곡선 툴팁 등)에서 온 화면 문장
  "Sweep stopped a run that fell behind": "스윕이 뒤처진 학습을 멈췄습니다", "Training report": "학습 보고서",
  "A token is needed to view this machine.": "이 기계를 보려면 토큰이 필요합니다.", "A token is needed for this action.": "이 작업에는 토큰이 필요합니다.",
  "Table": "표", "Review": "검수", "Sweeps": "스윕",
  "Epoch {n}": "에폭 {n}", "No value": "값 없음",
  "Curve chart. Use left and right arrow keys to read values by epoch.": "곡선 그래프입니다. 왼쪽·오른쪽 화살표로 에폭별 값을 읽습니다.",
  "Lowest val loss · epoch {x} · overfitting after": "검증 손실 최저 · 에폭 {x} · 이후 과적합", "Lowest val loss · epoch {x}": "검증 손실 최저 · 에폭 {x}",
  "Validation loss rose after epoch {x}: likely overfitting. best.pt keeps the best epoch.": "에폭 {x} 뒤로 검증 손실이 올랐습니다. 과적합일 가능성이 큽니다. best.pt에는 가장 좋은 에폭이 남아 있습니다.",
  "Validation loss was lowest here.": "검증 손실이 여기서 가장 낮았습니다.",
  "Time per epoch": "에폭당 시간", "{d}/epoch": "{d}/에폭", "Time per step": "스텝당 시간", "{d}/step": "{d}/스텝",
  "Lowest val loss · step {x} · overfitting after": "검증 손실 최저 · 스텝 {x} · 이후 과적합", "Lowest val loss · step {x}": "검증 손실 최저 · 스텝 {x}",
  "Validation loss rose after step {x}: likely overfitting.": "스텝 {x} 뒤로 검증 손실이 올랐습니다. 과적합일 가능성이 큽니다.", "Time left": "남은 시간", "Estimated finish": "끝날 예상 시각",
  "Train again with a change": "바꿔서 다시 학습", "Same settings as {name}, with {change}.": "{name}과(와) 같은 설정에 {change}을(를) 바꿉니다.",
  "Looking for Python…": "파이썬을 찾는 중…", "Queue training": "대기열에 넣기", "Added to the queue": "대기열에 넣었습니다",
  "Try: {change}": "해 볼 것: {change}", "from {file}": "{file}에서 시작", "No Python with ultralytics found": "ultralytics가 있는 파이썬이 없습니다", "no ultralytics": "ultralytics 없음",
  "Up to 8 runs. Untick one first.": "8개까지입니다. 하나를 먼저 빼세요.", "Pick up to 8 runs": "최대 8개까지 고르세요",
  // 계보·단계(versions.js)
  "No stage": "단계 없음", "Candidate": "후보", "In use": "사용 중", "Archived": "보관", "Where it came from": "어디서 왔나",
  "Which weights this run started from, and which runs started from this one.": "이 학습이 어떤 가중치에서 시작했고, 어떤 학습이 이 학습에서 시작했는지입니다.",
  "Data changed since {name}": "{name} 뒤로 데이터가 바뀜", "Same data as {name}": "{name}과(와) 같은 데이터",
  "1 run started from this one": "이 학습에서 시작한 학습 1개", "{n} runs started from this one": "이 학습에서 시작한 학습 {n}개",
  "Stage": "단계", "Copy best.pt to the model registry as a new version": "best.pt를 모델 등록부에 새 버전으로 복사합니다",
  "Put in use": "사용하기", "This run has no weights/best.pt yet.": "이 학습에는 아직 weights/best.pt가 없습니다.",
  "Change it on the machine that has this run.": "이 학습이 있는 기계에서 바꾸세요.", "Stage saved": "단계를 저장했습니다",
  "Copied to the model registry as {name} v{version}": "모델 등록부에 복사했습니다: {name} v{version}",
  "Can't compare": "비교할 수 없습니다", "Images added": "더해진 이미지", "Images removed": "빠진 이미지", "Labels changed": "바뀐 라벨",
  "class {c}": "클래스 {c}", "Added": "더해진 것", "Removed": "빠진 것", "Changed": "바뀐 것", "None": "없음",
  "The list was recorded when Epokio first saw each data version.": "목록은 Epokio가 각 데이터 버전을 처음 봤을 때 기록한 것입니다.",
};
/// 화면 문장. {이름} 자리는 vars에서 채운다. 표에 없으면 영어 그대로
function t(s, vars) {
  const out = LANG === "ko" && KO[s] != null ? KO[s] : s;
  const filled = vars ? out.replace(/\{(\w+)\}/g, (m, k) => k in vars ? String(vars[k]) : m) : out;
  return LANG === "ko" ? josa(filled) : filled;
}
/// 한국어 조사: 번역문의 '이(가)·은(는)·을(를)·과(와)·(으)로'를 앞 글자 받침으로 고른다(agent의 msg.josa와 같은 규칙).
/// ★'{name}과(와)'·'{change}을(를)'이 괄호째 화면에 나왔다
function josa(s) {
  const DIGIT = { 0: 1, 1: 2, 2: 0, 3: 1, 4: 0, 5: 0, 6: 1, 7: 2, 8: 2, 9: 0 }, LATIN = { l: 2, r: 2, m: 1, n: 1 };
  const bat = (c) => {
    const k = c.charCodeAt(0) - 0xac00;
    if (k >= 0 && k < 11172) { const j = k % 28; return j === 0 ? 0 : j === 8 ? 2 : 1; }
    if (c >= "0" && c <= "9") return DIGIT[c];
    return LATIN[c.toLowerCase()] || 0;
  };
  const PAIR = { "이(가)": ["이", "가"], "은(는)": ["은", "는"], "을(를)": ["을", "를"], "과(와)": ["과", "와"] };
  return s.replace(/(\S*?[^\s(])(이\(가\)|은\(는\)|을\(를\)|과\(와\)|\(으\)로)/g, (m, before, p) => {
    const last = [...before].reverse().find((c) => /[0-9A-Za-z가-힣]/.test(c)) || "";
    const b = last ? bat(last) : 0;
    return before + (p === "(으)로" ? (b === 0 || b === 2 ? "로" : "으로") : PAIR[p][b ? 0 : 1]);
  });
}
/// 영어는 같은데 한국어가 자리에 따라 다른 말(예: 상태 "Training"=학습 중, 작업 종류 "Training"=학습). 키는 "자리|영어"
const tc = (ctx, s, vars) => t(LANG === "ko" && KO[ctx + "|" + s] != null ? ctx + "|" + s : s, vars);
const LOCALE = LANG === "ko" ? "ko-KR" : "en-GB";   // ★시각은 화면 언어로. 브라우저 언어면 영어 화면에 '오후 11:15'가 섞였다
const HM = { hour: "2-digit", minute: "2-digit", hour12: false };
document.documentElement.lang = LANG;
