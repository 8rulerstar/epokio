"""CONTRIBUTING의 개발 환경 안내. ★윈도우에서 그대로 따라 하면 python3(스토어 바로 가기)·.venv/bin이 없어 첫 줄에서 멈췄다"""
from pathlib import Path

DOC = (Path(__file__).resolve().parents[1] / "CONTRIBUTING.md").read_text(encoding="utf-8")


def test_windows_setup_does_not_need_python3_or_bin():
    assert "py -m venv .venv" in DOC
    # 날 문자열(r""): ★"\S"가 잘못된 이스케이프라 시험을 돌릴 때마다 SyntaxWarning이 떴다
    assert r".venv\Scripts\python -m pip install -e" in DOC and r".venv\Scripts\python -m pytest" in DOC
