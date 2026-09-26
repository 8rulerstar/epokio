"""실패한 작업의 로그에서 흔한 원인을 찾아 쉬운 말과 고칠 방법으로 돌려준다.

레퍼런스 아이디어: Ultralytics Platform 콘솔의 치명적 오류 감지. 초보자는 트레이스백 50줄에서
마지막 한 줄을 못 찾는다. 여기서는 그 한 줄을 알아보고 "무엇을 바꾸면 되는지"까지 말한다.
문장은 ultralytics·PyTorch가 실제로 찍는 것에 맞췄다(2026-09-25, ultralytics 8.4 소스에서 확인).
"""
from __future__ import annotations

import re

from .msg import tr

# (찾을 글, 제목, 고칠 방법). 위에서부터 보고, 같은 제목은 한 번만.
# 제목·고칠 방법은 영어 원문이고, 돌려줄 때 msg.tr로 요청 언어(Accept-Language)에 맞춘다. 번역은 msg.KO
RULES: list[tuple[str, str, str]] = [
    (r"CUDA out of memory|OutOfMemoryError|CUBLAS_STATUS_ALLOC_FAILED",
     "The GPU ran out of memory",
     "Lower batch (half of it, or -1 to let Ultralytics pick), or lower imgsz."),
    (r"WinError 1455|paging file is too small",
     "Windows ran out of virtual memory",
     "Set workers to 0 or 2 and lower batch. Making the Windows page file bigger also helps."),
    (r"DataLoader worker \(pid|An attempt has been made to start a new process|BrokenPipeError",
     "The data loading workers crashed",
     "Set workers to 0. On Windows this is the usual fix."),
    (r"Invalid CUDA 'device=|Torch not compiled with CUDA enabled",
     "A GPU was asked for, but this PyTorch cannot use it",
     "This Python has the CPU-only PyTorch. Use Set up automatically on the Train tab, "
     "or install PyTorch with CUDA. To train on the CPU now, set device to cpu."),
    (r"images not found",
     "The dataset images were not found",
     "A path in the data.yaml is wrong. Use Check data on the Train tab to see which one."),
    (r"No labels found",
     "No label files were found",
     "Each image needs a .txt with the same name in a labels folder next to images. Use Check data."),
    (r"exceeds dataset class count",
     "A label uses a class number the data.yaml does not list",
     "Add the missing class names to names: in the data.yaml, or fix the label files."),
    (r"No space left on device|Errno 28",
     "The disk is full",
     "Free some space, or move the project folder to a bigger disk."),
    (r"No module named '([\w.]+)'",
     "A Python package is missing",
     "Install it in the Python this job used: python -m pip install {0}"),
    # 이어 하기: 일찍 멈춘(patience) 학습이나 끝난 학습은 ultralytics가 거절한다. 파일만 봐서는 미리 알 수 없다
    (r"nothing to resume|Start a new training without resuming|start_epoch",
     "This run cannot be resumed",
     "It already finished or stopped early on its own (patience). Use Train again with these settings instead."),
    (r"urlopen error|HTTPError|ConnectionError|Download failure|Temporary failure in name resolution",
     "A download failed",
     "The model weights or the sample data are downloaded on first use. Check the internet connection and try again."),
]


def diagnose(log: str) -> list[dict]:
    """로그 뒤쪽(진짜로 멈춘 자리)에 가까운 원인부터. ★예전엔 규칙 순서라 앞쪽의 재시도 경고
    (HTTPError·BrokenPipe)가 마지막 트레이스백의 진짜 원인보다 먼저 나왔다."""
    hits = {}
    for pat, title, fix in RULES:
        m = None
        for m in re.finditer(pat, log, re.IGNORECASE):
            pass                                            # 그 원인이 마지막으로 나온 자리
        if m and title not in hits:
            text = tr(fix)
            hits[title] = (m.start(), text.format(*(g for g in m.groups() if g)) if m.groups() else text)
    return [{"title": tr(t), "fix": f} for t, (_, f) in sorted(hits.items(), key=lambda kv: -kv[1][0])]
