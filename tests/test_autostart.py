

def test_cli_hint_matches_how_epokio_runs(monkeypatch):
    """★윈도우 안내가 `epokio autostart --off`였는데 Scripts가 PATH에 없어 안 먹고, exe엔 그 명령이 없었다"""
    import sys
    from epokio import autostart
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "base_prefix", sys.prefix)          # venv가 아닌 설치(아래 시험이 venv를 따로 본다)
    # ★PATH 찾기는 못 박는다. 이 기계의 PATH를 따르면 CI(리눅스는 epokio가 python 옆에 깔린다)마다 답이 달랐다.
    #   PATH에 있을 때의 짧은 명령은 test_setup_hints_use_the_short_command_when_it_is_on_path가 본다
    monkeypatch.setattr(autostart, "_on_path", lambda: False)
    monkeypatch.setattr(sys, "platform", "linux")
    assert autostart.cli("autostart --off") == "epokio autostart --off"
    monkeypatch.setattr(sys, "platform", "win32")
    assert autostart.cli("autostart --off") == "py -m epokio autostart --off"
    assert autostart.pip_cmd('"epokio[tray]"') == 'py -m pip install "epokio[tray]"'
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Epokio\Epokio.exe")
    assert autostart.cli("autostart --off") == ".\\Epokio.exe autostart --off"


def test_cli_hint_uses_the_venv_python_when_installed_in_a_venv(monkeypatch):
    """★venv에 깐 사용자에게 `py -m epokio`(전역 파이썬)를 안내해 'No module named epokio'가 났다"""
    import sys
    from epokio import autostart
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "prefix", r"C:\proj\.venv")
    monkeypatch.setattr(sys, "base_prefix", r"C:\Python312")
    monkeypatch.setattr(autostart, "_on_path", lambda: False)      # venv를 켜지 않은 터미널(PATH에 이 epokio가 없다)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", r"C:\proj\.venv\Scripts\pythonw.exe")   # 자동 시작은 창 없는 pythonw로 돈다
    assert autostart.cli("agent --stop") == r"C:\proj\.venv\Scripts\python.exe -m epokio agent --stop"
    assert autostart.pip_cmd('"epokio[tray]"') == r'C:\proj\.venv\Scripts\python.exe -m pip install "epokio[tray]"'
    monkeypatch.setattr(sys, "executable", r"C:\my proj\.venv\Scripts\python.exe")
    assert autostart.cli("setup") == r'& "C:\my proj\.venv\Scripts\python.exe" -m epokio setup'   # PowerShell은 &가 있어야 실행
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "executable", "/home/a/proj/.venv/bin/python")
    assert autostart.cli("watch") == "/home/a/proj/.venv/bin/python -m epokio watch"


def test_the_on_path_check_never_raises(monkeypatch):
    """★sys.platform만 win32로 바꾼 맥·리눅스(파이썬 3.12+)에서 shutil.which가 윈도우 분기로 들어가 _winapi(None)를
    불렀다. 안내 문구 하나 고르다 AttributeError로 죽었다(0.8.0 CI). 못 찾으면 PATH에 없는 것으로 본다"""
    import shutil
    import sys
    from epokio import autostart
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "base_prefix", sys.prefix)
    monkeypatch.setattr(sys, "platform", "win32")

    def broken(name, *a, **k):
        raise AttributeError("'NoneType' object has no attribute 'NeedCurrentDirectoryForExePath'")
    monkeypatch.setattr(shutil, "which", broken)
    assert autostart._on_path() is False
    assert autostart.cli("autostart --off") == "py -m epokio autostart --off"
    # 맥·리눅스의 진짜 shutil 모양(_winapi가 None)으로 진짜 which를 불러도 죽지 않는다
    monkeypatch.undo()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(shutil, "_winapi", None, raising=False)
    assert autostart._on_path() in (True, False)


def test_short_home_replaces_only_a_whole_home_folder():
    """★홈 글자가 들어 있기만 하면 바꿨다. 홈이 /home/al이면 /home/alice가 ~ice(bash에선 ice 사용자의 홈)로,
    /mnt/home/al/x가 /mnt~/x로, 작은따옴표 안(~도 $HOME도 안 풀림)도 ~로 바뀌어 틀린 명령이 됐다"""
    import os
    from epokio.autostart import short_home
    home, sep = os.path.expanduser("~").rstrip("\\/"), os.sep
    for same in (home + "x" + sep + "venv", "/mnt" + home + sep + "v", "'" + home + sep + "v' -m epokio"):
        assert short_home(same) == same
    assert short_home(home + sep + "v -m epokio --root " + home + sep + "runs") == f"~{sep}v -m epokio --root ~{sep}runs"
    assert short_home('"' + home + sep + 'my v" -m epokio') == f'"$HOME{sep}my v" -m epokio'
    assert short_home(home) == "~"
