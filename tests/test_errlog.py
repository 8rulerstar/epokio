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
    assert str(home) not in text and "~/nope/x.txt" in text
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
