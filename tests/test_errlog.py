from pathlib import Path

from epokio import errlog


def test_record_scrubs_home_and_recent_reads_back(tmp_path):
    home = tmp_path / "alice"
    try:
        open(home / "nope" / "x.txt")
    except OSError as e:
        errlog.record("scan", e, home=home)
    text = errlog.recent(home=home)
    assert "scan" in text and "FileNotFoundError" in text
    # 윈도우는 구분자가 역슬래시고, 예외 메시지(repr)에는 두 겹으로 적힌다. 어느 쪽이든 홈은 사라지고 뒤는 남는다
    assert str(home) not in text and str(home).replace("\\", "\\\\") not in text
    assert "~/nope/x.txt" in text.replace("\\\\", "/").replace("\\", "/")
    assert (home / ".epokio" / "logs" / "errors.log").exists()


def test_rotation_keeps_one_backup(tmp_path):
    for i in range(30):
        errlog.record("loop", message="x" * 100 + str(i), home=tmp_path, max_bytes=500)
    d = errlog.log_dir(tmp_path)
    assert (d / "errors.log.1").exists()
    assert (d / "errors.log").stat().st_size < 500 + 200
    assert not (d / "errors.log.2").exists()
    assert "x29" in errlog.recent(home=tmp_path)


def test_record_never_raises(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    assert errlog.record("x", message="y", home=blocker) is None     # .epokio를 파일 아래에 못 만든다


def test_issue_body_limit_and_env(tmp_path):
    for i in range(200):
        errlog.record("big", message="y" * 200, home=tmp_path)
    body = errlog.issue_body(home=tmp_path, note="app froze", max_chars=2000)
    assert len(body) <= 2000
    assert "app froze" in body and "- python:" in body and "- os:" in body


def test_issue_body_without_logs(tmp_path):
    assert "(no errors recorded)" in errlog.issue_body(home=tmp_path)


def test_scrub_longest_first():
    assert errlog.scrub("/Users/ab/x /Users/a/y", home=Path("/Users/a")) == "/Users/ab/x ~/y"


def test_scrub_windows_home_in_every_spelling():
    """★윈도우 홈(C:\\Users\\이름)이 오류 보고에 그대로 샜다. 이 맥에서도 윈도우 모양 문자열로 시험한다"""
    home = "C:\\Users\\Alice"
    text = ('File "C:\\Users\\Alice\\proj\\a.py", line 3\n'
            "FileNotFoundError: [Errno 2] No such file: 'C:\\\\Users\\\\Alice\\\\nope\\\\x.txt'\n"
            "c:\\users\\alice\\low C:/Users/Alice/fwd C:\\Users\\Alicex\\keep")
    out = errlog.scrub(text, home=home)
    assert "alice\\" not in out.lower() and "alice/" not in out.lower() and "alice'" not in out.lower()
    assert '"~\\proj\\a.py"' in out and "'~\\\\nope\\\\x.txt'" in out
    assert "~\\low" in out and "~/fwd" in out
    assert "C:\\Users\\Alicex\\keep" in out            # 이름이 더 긴 다른 사용자는 건드리지 않는다


def test_scrub_skips_bare_root_and_drive():
    assert errlog.scrub("/a C:\\b", home="/") == "/a C:\\b"
    assert errlog.scrub("/a C:\\b", home="C:\\") == "/a C:\\b"
