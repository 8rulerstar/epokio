

def test_cli_hint_matches_how_epokio_runs(monkeypatch):
    """★윈도우 안내가 `epokio autostart --off`였는데 Scripts가 PATH에 없어 안 먹고, exe엔 그 명령이 없었다"""
    import sys
    from epokio import autostart
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    assert autostart.cli("autostart --off") == "epokio autostart --off"
    monkeypatch.setattr(sys, "platform", "win32")
    assert autostart.cli("autostart --off") == "py -m epokio autostart --off"
    assert autostart.pip_cmd('"epokio[tray]"') == 'py -m pip install "epokio[tray]"'
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Epokio\Epokio.exe")
    assert autostart.cli("autostart --off") == ".\\Epokio.exe autostart --off"
