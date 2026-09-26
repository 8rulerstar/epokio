"""모든 테스트를 가짜 홈 폴더에서 돌린다.

★예전엔 서버 테스트가 진짜 Agent를 띄우며 진짜 ~/.epokio(대기열·토큰·폴더 목록)를 썼다. 학습 기계에서
pytest를 돌리면 대기 중인 사용자 작업이 시작되거나, 돌고 있는 agent와 같은 대기열 파일을 동시에 쓸 수 있었다.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("home")
    # ★자식 파이썬(학습 스크립트·tui 등)은 설치된 epokio를 부른다. 편집 설치가 다른 작업 공간을 가리키거나
    #   훅이 준 PYTHONPATH=src(상대 경로)가 자식의 cwd에서 안 맞으면, 이 저장소가 아닌 옛 코드를 시험했다
    import os
    from pathlib import Path
    src = str(Path(__file__).resolve().parents[1] / "src")
    rest = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p and p != "src"]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([src, *rest]))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    ep = home / ".epokio"
    from epokio import auth, config, envs, jobs, runmeta
    from epokio.agent import Agent
    monkeypatch.setattr(jobs, "HOME", ep)
    monkeypatch.setattr(jobs, "STATE", ep / "jobs.json")
    monkeypatch.setattr(jobs, "LOGS", ep / "logs")
    monkeypatch.setattr(jobs, "SCRIPTS", ep / "scripts")
    monkeypatch.setattr(jobs, "SETUP_DIR", ep / "envs" / "epokio")
    monkeypatch.setattr(Agent, "ROOTS_FILE", ep / "roots.json")
    monkeypatch.setattr(Agent, "HOOKS_FILE", ep / "webhooks.json")
    monkeypatch.setattr(Agent, "REMOVED_FILE", ep / "removed_roots.json")
    monkeypatch.setattr(runmeta, "FILE", ep / "runmeta.json")
    monkeypatch.setattr(config, "FILE", ep / "config.json")
    monkeypatch.setattr(auth, "TOKEN_FILE", ep / "token")
    envs.forget()
    yield home
