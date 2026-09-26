"""실패한 작업 로그에서 원인과 고칠 방법을 찾는다. 문장은 ultralytics·PyTorch가 실제로 찍는 것."""
import pytest

from epokio.diagnose import diagnose


@pytest.mark.parametrize("log, title", [
    ("torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB", "The GPU ran out of memory"),
    ("OSError: [WinError 1455] The paging file is too small for this operation to complete", "Windows ran out of virtual memory"),
    ("RuntimeError: DataLoader worker (pid 1234) exited unexpectedly", "The data loading workers crashed"),
    ("ValueError: Invalid CUDA 'device=0' requested. Use 'device=cpu'", "A GPU was asked for, but this PyTorch cannot use it"),
    ("FileNotFoundError: Dataset 'd.yaml' images not found, missing path 'C:/x/images/val'", "The dataset images were not found"),
    ("ValueError: train: No labels found in C:/x/labels/train.cache.", "No label files were found"),
    ("Label class 7 exceeds dataset class count 3. Possible class labels are 0-2", "A label uses a class number the data.yaml does not list"),
    ("OSError: [Errno 28] No space left on device", "The disk is full"),
    ("urllib.error.URLError: <urlopen error [Errno 11001] getaddrinfo failed>", "A download failed"),
    ("AssertionError: runs/detect/train/weights/last.pt training to 100 epochs is finished, nothing to resume.", "This run cannot be resumed"),
])
def test_known_failures_get_a_plain_reason(log, title):
    hints = diagnose("Traceback (most recent call last):\n  ...\n" + log)
    assert [h["title"] for h in hints] == [title]
    assert hints[0]["fix"]


def test_missing_module_names_the_package():
    [h] = diagnose("ModuleNotFoundError: No module named 'ultralytics'")
    assert h["fix"].endswith("pip install ultralytics")


def test_a_clean_log_has_no_hints():
    assert diagnose("      1/10  2.1G  1.2  3.4  0.9  12  640: 100%\nResults saved to runs/detect/train") == []


def test_the_same_reason_is_said_once():
    assert len(diagnose("CUDA out of memory\nCUDA out of memory\nOutOfMemoryError")) == 1


def test_the_error_that_actually_stopped_the_run_comes_first():
    """앞쪽의 다운로드 재시도 경고보다 마지막 트레이스백의 원인이 먼저다."""
    # 규칙 순서로는 메모리 부족이 먼저지만, 실제로 멈춘 건 마지막의 디스크 부족이다
    log = ("WARNING CUDA out of memory, retrying with a smaller batch\nepoch 1/10 ...\n"
           "Traceback (most recent call last):\nOSError: [Errno 28] No space left on device")
    assert [h["title"] for h in diagnose(log)] == ["The disk is full", "The GPU ran out of memory"]
