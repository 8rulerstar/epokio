

def test_cli_hint_matches_how_epokio_runs(monkeypatch):
    """★윈도우 안내가 `epokio autostart --off`였는데 Scripts가 PATH에 없어 안 먹고, exe엔 그 명령이 없었다"""
    import sys
    from epokio import autostart
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "base_prefix", sys.prefix)          # venv가 아닌 설치(아래 시험이 venv를 따로 본다)
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
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", r"C:\proj\.venv\Scripts\pythonw.exe")   # 자동 시작은 창 없는 pythonw로 돈다
    assert autostart.cli("agent --stop") == r"C:\proj\.venv\Scripts\python.exe -m epokio agent --stop"
    assert autostart.pip_cmd('"epokio[tray]"') == r'C:\proj\.venv\Scripts\python.exe -m pip install "epokio[tray]"'
    monkeypatch.setattr(sys, "executable", r"C:\my proj\.venv\Scripts\python.exe")
    assert autostart.cli("setup") == r'& "C:\my proj\.venv\Scripts\python.exe" -m epokio setup'   # PowerShell은 &가 있어야 실행
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "executable", "/home/a/proj/.venv/bin/python")
    assert autostart.cli("watch") == "/home/a/proj/.venv/bin/python -m epokio watch"
