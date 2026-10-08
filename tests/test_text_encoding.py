"""글자 인코딩. 한국어 윈도우의 기본 인코딩은 cp949라, 인코딩을 안 적은 읽기·쓰기는 그 기계에서만 깨진다"""
import sys

from epokio import repro, ssh_source


def test_ssh_hosts_keep_any_character(tmp_path, monkeypatch):
    """★인코딩 없이 저장해 한국어 윈도우에선 cp949였고, cp949에 없는 글자(✓, ā)가 오면 저장이 실패했다"""
    monkeypatch.setattr(ssh_source, "CONFIG", tmp_path / "hosts.json")
    hosts = [{"host": "gpu-box", "label": "학습 서버 ✓ ā"}]
    ssh_source.save(hosts)
    assert ssh_source.load() == hosts
    assert "학습 서버 ✓ ā" in (tmp_path / "hosts.json").read_text(encoding="utf-8")


def test_ssh_hosts_written_by_an_older_version_still_load(tmp_path, monkeypatch):
    """예전 판이 한국어 윈도우에서 cp949로 쓴 파일도 읽는다(utf-8로 못 풀면 이 기계의 기본 인코딩으로)"""
    import locale
    monkeypatch.setattr(ssh_source, "CONFIG", tmp_path / "hosts.json")
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "cp949")
    (tmp_path / "hosts.json").write_bytes('[{"host": "gpu-box", "label": "학습 서버"}]'.encode("cp949"))
    assert ssh_source.load() == [{"host": "gpu-box", "label": "학습 서버"}]


def test_command_output_is_read_as_utf8():
    """★git diff(utf-8)를 cp949로 풀어 한글 주석이 있는 코드의 재현 기록이 깨지거나 통째로 실패했다"""
    text = "# 학습률을 낮춘다 ✓\n"
    out = repro._run([sys.executable, "-c", f"import sys; sys.stdout.buffer.write({text!r}.encode('utf-8'))"])
    assert out == text


def test_long_server_paths_get_a_short_mirror_folder_on_windows(tmp_path, monkeypatch):
    """★윈도우는 경로 260자 제한이라, 서버 경로를 통째로 옮긴 폴더 이름이 길면 비춤 파일을 못 만들어 그 학습이 안 보였다"""
    import time
    monkeypatch.setattr(ssh_source, "MIRROR", tmp_path / "mirror")
    monkeypatch.setattr(ssh_source.sys, "platform", "win32")
    remote = "/home/alice/" + "/".join(["a_rather_long_project_folder"] * 6) + "/runs/detect/train7"
    d = ssh_source.local_dir("gpu", remote)
    assert len(d.relative_to(tmp_path).parts[2]) < 20                    # 부모 칸이 짧다
    assert ssh_source.remote_path(str(d)) == remote
    assert ssh_source.remote_path(str(d / "weights")) == remote + "/weights"
    short = ssh_source.local_dir("gpu", "/home/a/runs/x")                 # 짧은 경로는 예전 이름 그대로
    assert short.parent.name == "%2Fhome%2Fa%2Fruns"
    # 서버에서 지운 학습을 정리할 때 원래 경로를 적은 파일은 남긴다
    got = {"now": time.time(), "runs": [{"path": remote, "files": {"results.csv": [time.time(), "epoch\n1\n"]}}]}
    ssh_source.apply("gpu", got)
    ssh_source.apply("gpu", got)
    assert (d / "results.csv").exists() and ssh_source.remote_path(str(d)) == remote
