import sys

import pytest

from epokio import envs
from epokio.envs import parse_default_yaml

SAMPLE = """# Ultralytics
task: detect # (str) YOLO task
# Train settings -----------------------------------------------------------------
epochs: 100 # (int) number of epochs
lr0: 0.01 # (float) initial learning rate
cache: False # (bool) cache images
# Predict settings ---------------------------------------------------------------
conf: # (float, optional) confidence threshold
"""


def test_sections_and_types():
    f = {i["key"]: i for i in parse_default_yaml(SAMPLE)}
    assert f["epochs"]["section"] == "train" and f["epochs"]["type"] == "int"
    assert f["lr0"]["type"] == "float" and f["cache"]["type"] == "bool"
    assert f["conf"]["section"] == "predict" and f["conf"]["default"] is None
    assert f["task"]["section"] == "general"
    assert "number of epochs" in f["epochs"]["help"]


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("")


def test_windows_python_locations_are_found(tmp_path, monkeypatch):
    """윈도우 설치 모양(bin 층이 없다, venv는 Scripts)도 찾는다.
    예전엔 맥 모양만 봐서 윈도우에서는 agent 자신의 파이썬 하나만 찾았다(2026-09-25 실측)."""
    monkeypatch.setattr(envs, "HOME", tmp_path)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "PF"))
    want = [tmp_path / "AppData/Local/Programs/Python/Python312/python.exe",   # python.org, 사용자별
            tmp_path / "PF/Python311/python.exe",                                # python.org, 모든 사용자
            tmp_path / "anaconda3/python.exe",                                   # conda 본체
            tmp_path / "miniforge3/envs/yolo/python.exe",                        # conda env
            tmp_path / "Desktop/proj/.venv/Scripts/python.exe"]                  # 프로젝트 venv
    for p in want:
        _touch(p)
    found = envs.candidates()
    for p in want:
        assert str(p) in found


def test_mac_and_linux_locations_are_still_found(tmp_path, monkeypatch):
    monkeypatch.setattr(envs, "HOME", tmp_path)
    want = [tmp_path / "anaconda3/bin/python", tmp_path / "miniconda3/envs/yolo/bin/python",
            tmp_path / "Projects/proj/.venv/bin/python", tmp_path / ".epokio/envs/default/bin/python"]
    for p in want:
        _touch(p)
    found = envs.candidates()
    for p in want:
        assert str(p) in found


@pytest.mark.parametrize("path, name", [
    ("u/anaconda3/envs/yolo/python.exe", "yolo"),            # 윈도우 conda env. 예전엔 'envs'
    ("u/anaconda3/python.exe", "anaconda3"),                  # 윈도우 conda 본체. 예전엔 사용자 폴더 이름
    ("u/Programs/Python/Python312/python.exe", "Python312"),  # python.org. 예전엔 'Python'
    ("u/proj/.venv/Scripts/python.exe", ".venv"),
    ("u/anaconda3/envs/yolo/bin/python", "yolo"),             # 맥·리눅스는 예전과 같다
    ("u/anaconda3/bin/python", "anaconda3"),
    ("u/.pyenv/versions/3.11.4/bin/python", "3.11.4"),
    ("u/proj/.venv/bin/python", ".venv"),
])
def test_env_names(path, name):
    assert envs.env_name(path) == name


def test_a_frozen_exe_is_not_offered_as_a_python(tmp_path, monkeypatch):
    """exe 로 구우면 sys.executable 이 Epokio.exe 다. 파이썬인 줄 알고 -c 로 떠보면
    런처가 인자를 트레이로 넘겨 트레이를 하나 더 띄운다."""
    monkeypatch.setattr(envs, "HOME", tmp_path)
    exe = tmp_path / "dist/Epokio.exe"
    _touch(exe)
    monkeypatch.setattr(envs.sys, "executable", str(exe))
    monkeypatch.setattr(envs.sys, "frozen", True, raising=False)
    assert str(exe) not in envs.candidates()
    monkeypatch.setattr(envs.sys, "frozen", False)
    assert str(exe) in envs.candidates()          # 굽지 않았으면 agent 자신의 파이썬도 후보다


def test_setup_uses_a_real_python_when_frozen(tmp_path, monkeypatch):
    """자동 설치는 venv 를 만들 파이썬이 필요하다. 구운 exe 면 exe 자신이 아니라 이 기계의 파이썬을 쓴다."""
    monkeypatch.setattr(envs, "HOME", tmp_path)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "PF"))
    monkeypatch.setattr(envs.sys, "executable", str(tmp_path / "dist/Epokio.exe"))
    monkeypatch.setattr(envs.sys, "frozen", True, raising=False)
    monkeypatch.setattr(envs, "_on_path", lambda: [])                  # 이 기계 PATH의 파이썬은 빼고 본다
    real = envs.candidates                                             # /opt/anaconda3 같은 이 기계의 절대 경로도 뺀다
    monkeypatch.setattr(envs, "candidates", lambda: [c for c in real() if str(c).startswith(str(tmp_path))])
    assert envs.base_python() is None                                  # 파이썬이 하나도 없다
    py = tmp_path / "AppData/Local/Programs/Python/Python312/python.exe"
    _touch(py)
    assert envs.base_python() == str(py)
    monkeypatch.setattr(envs.sys, "frozen", False)
    assert envs.base_python() == str(tmp_path / "dist/Epokio.exe")     # 굽지 않았으면 agent 자신


@pytest.mark.skipif(sys.platform != "win32", reason="py 런처 목록은 윈도우 경로(C:)만 읽는다")
def test_python_on_path_and_from_the_py_launcher_is_found(tmp_path, monkeypatch):
    """★스토어·'py'로 깐 파이썬을 못 찾아, exe 사용자가 파이썬을 깔고도 '파이썬이 없습니다'에서 막혔다.
    스토어를 여는 가짜 python.exe 는 넣지 않는다(실행하면 스토어 창이 뜬다)"""
    import shutil
    import subprocess
    import sys
    from epokio import envs
    apps = tmp_path / "Microsoft" / "WindowsApps"
    apps.mkdir(parents=True)
    (apps / "python3.12.exe").write_text("")
    real = tmp_path / "Py312" / "python.exe"
    real.parent.mkdir()
    real.write_text("")
    stub = str(apps / "python.exe")
    gone = r"C:\gone\python.exe"                      # 목록에는 있지만 지워진 파이썬
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(shutil, "which", lambda n: {"python": stub, "py": "py.exe"}.get(n))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 0, stdout=f" -V:3.12 *        {real}\n -V:3.9          {gone}\n"))
    got = envs._on_path()
    assert stub not in got
    assert str(apps / "python3.12.exe") in got and str(real) in got
    assert gone not in got
