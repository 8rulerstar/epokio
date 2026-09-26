"""토큰 경계. 이건 '고쳤으니 됐다'가 아니라 다시 열리면 즉시 알아야 하는 줄이다.

2026-09-23 윈도우 실측에서, --host 0.0.0.0 으로 띄운 agent가 토큰 없이
GET /schema?python=<아무 exe> 로 감시 폴더 밖 실행 파일을 띄우는 걸 확인했다.
같은 요청으로 GET /names?path=C:\\Users\\PC 가 홈 폴더 전체를 걸어 실제 경로를 돌려줬다.
README는 그때도 "실행 요청은 토큰이 있어야만 받습니다"라고 적고 있었다.
"""
import sys

import pytest

from epokio import auth


@pytest.mark.parametrize("route", [
    "/schema",                      # 남이 준 경로의 실행 파일을 띄운다
    "/schema?python=/bin/sh",
    "/pythons",
    "/names",                       # 감시 폴더 밖을 걷는다
    "/names?path=/",
    "/health-check",
    "/jobs",                        # 실행 명령·작업 폴더가 그대로 들어 있다
    "/jobs/",
    "/jobs/abc/log",
    "/jobs/abc/logfile",            # 학습 로그 전문
])
def test_executing_and_walking_gets_need_a_token(route):
    assert auth.get_needs_token(route), f"{route} 가 토큰 없이 열려 있다"


@pytest.mark.parametrize("route", [
    "/", "/runs", "/runs/", "/system", "/events", "/events?since=0",
    "/run", "/run?path=/x", "/health", "/config", "/webhooks",
])
def test_view_only_gets_stay_open(route):
    """웹 화면(runs·system·events·run)과 트레이(health·events)가 토큰 없이 돌아야 한다."""
    assert not auth.get_needs_token(route), f"{route} 를 잠그면 웹 화면·트레이가 깨진다"


def test_a_new_route_is_locked_by_default():
    """잠글 것을 적는 방식이라 새 GET이 열린 채로 나갔다. 이제는 열 것만 적는다."""
    for route in ("/something-new", "/export", "/runs.csv", "/jobs2"):
        assert auth.get_needs_token(route)


def test_every_get_route_is_either_open_on_purpose_or_locked():
    """agent.get의 경로를 전부 훑는다. 보기용으로 연 것 외에는 모두 잠겨야 한다."""
    import re
    from pathlib import Path
    src = (Path(auth.__file__).parent / "agent.py").read_text(encoding="utf-8")
    body = src.split("def get(", 1)[1].split("\n    def ", 1)[0]
    routes = set(re.findall(r'route == "(/[\w/-]*)"', body)) | {"/jobs/x" + s for s in re.findall(r'route\.endswith\("(/\w+)"\)', body)}
    assert "/pythons" in routes and "/jobs" in routes          # 훑기가 제대로 됐는지
    for r in routes:
        assert auth.get_needs_token(r) == (r not in auth.OPEN_GET), r


def test_empty_route_is_runs_not_a_protected_one():
    assert not auth.get_needs_token("")
    assert not auth.get_needs_token("/")


def test_check_rejects_everything_but_the_real_token(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token")
    good = auth.token()
    assert len(good) >= 32
    assert auth.check(f"Bearer {good}")
    for bad in [None, "", "Bearer", "Bearer ", "Bearer wrong", good,      # 머리말 없이 값만
                f"bearer {good}", f"Basic {good}", f"Bearer {good}x"]:
        assert not auth.check(bad), f"{bad!r} 를 통과시켰다"


def test_token_is_stable_across_calls(tmp_path, monkeypatch):
    """매번 새로 만들면 맥에 붙여 넣은 토큰이 재시작마다 죽는다."""
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token")
    assert auth.token() == auth.token()


def test_a_too_short_token_file_is_replaced(tmp_path, monkeypatch):
    f = tmp_path / "token"
    monkeypatch.setattr(auth, "TOKEN_FILE", f)
    f.write_text("short")
    assert len(auth.token()) >= 32


def test_a_non_ascii_token_is_refused_not_a_crash(tmp_path, monkeypatch):
    """문자열로 비교하면 한글이 섞인 토큰에서 TypeError가 나서 401 대신 연결이 끊겼다."""
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token")
    assert auth.check("Bearer 토큰토큰") is False
    assert auth.check("Bearer " + auth.token()) is True


def test_a_half_written_token_file_does_not_replace_the_token(tmp_path, monkeypatch):
    """★요청마다 파일을 다시 읽어, 다른 프로세스가 쓰는 중(빈 파일)을 보면 새 토큰으로 덮었다. 붙여 넣은 토큰이 죽었다"""
    f = tmp_path / "token"
    monkeypatch.setattr(auth, "TOKEN_FILE", f)
    good = auth.token()
    f.write_text("")                                  # 누가 쓰는 도중
    assert auth.check("Bearer " + good)
    assert f.read_text() == ""                        # 남의 파일을 덮지 않았다


def test_an_existing_token_is_never_overwritten(tmp_path, monkeypatch):
    f = tmp_path / "token"
    f.write_text("x" * 40)
    monkeypatch.setattr(auth, "TOKEN_FILE", f)
    assert auth.token() == "x" * 40
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX 권한")
def test_a_new_token_file_is_private_from_the_start(tmp_path, monkeypatch):
    f = tmp_path / "ep" / "token"
    monkeypatch.setattr(auth, "TOKEN_FILE", f)
    auth.token()
    assert f.stat().st_mode & 0o777 == 0o600
    assert f.parent.stat().st_mode & 0o077 == 0
