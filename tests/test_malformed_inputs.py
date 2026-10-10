"""깨진·이상한 입력: 미래 시각 파일, 바로 가기로 두 번 닿는 학습, 쓸 수 없는 ~/.epokio, 잘못된 웹후크, TensorBoard 흔한 폴더 이름."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from epokio import alerts_cli, cli, notify
from epokio.scan import display_name, read_run, scan, unique

HDR = "epoch,train/box_loss,metrics/mAP50-95(B),val/box_loss\n"


def _yolo(d: Path, rows: int = 1, epochs: int = 10) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "args.yaml").write_text(f"epochs: {epochs}\n")
    (d / "results.csv").write_text(HDR + "".join(f"{i},1.0,0.5,1.0\n" for i in range(1, rows + 1)))
    return d


def test_file_from_the_future_does_not_give_a_years_long_eta(tmp_path):
    """★시계가 뒤로 간 기계(또는 미래 시각으로 복사된 파일)에서 '3285d 0h left'가 나왔다"""
    d = _yolo(tmp_path / "future")
    later = time.time() + 365 * 86400
    os.utime(d / "results.csv", (later, later))
    r = read_run(d)
    assert r.eta is None or r.eta < 86400, r.eta
    assert r.elapsed < 86400, r.elapsed


@pytest.mark.parametrize("folder", ["logs", "tb", "tensorboard", "summaries"])
def test_tensorboard_log_folders_get_the_parent_name(tmp_path, folder):
    """★seed1/logs와 seed2/logs가 둘 다 'logs'로 떠 구별이 안 됐다"""
    class R:
        name = folder
        path = tmp_path / "proj" / "seed1" / folder
    assert display_name(R()) == f"seed1/{folder}"


def _link(link: Path, target: Path) -> bool:
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if sys.platform == "win32":                          # 개발자 모드가 아니어도 정션은 만들 수 있다
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        return r.returncode == 0
    return False


def test_a_run_reached_through_a_link_is_listed_once(tmp_path):
    """★윈도우 정션·심볼릭 링크로 같은 학습에 두 길로 닿으면(링크가 위 폴더를 가리키면 더 여러 번) 목록에 겹쳐 나왔다"""
    root = tmp_path / "runs"
    real = _yolo(root / "a" / "train")
    if not (_link(root / "shortcut", real) and _link(root / "a" / "loop", root)):
        pytest.skip("cannot make links here")
    runs = unique(scan(root))
    assert len(runs) == 1, [str(r.path) for r in runs]
    assert Path(runs[0].path) == real                    # 바로 가기가 아닌 쪽을 남긴다


@pytest.mark.parametrize("url,ok", [
    ("https://ntfy.sh/abc_DEF-123", True),
    ("https://hooks.slack.com/services/T0/B0/xyz", True),
    ("https://api.telegram.org/bot123:ABC/sendMessage?chat_id=1", True),
    ("https://[::1]:8443/hook", True),
    ("notaurl", False),
    ("http://ntfy.sh/abc", False),
    ("https://", False),
    ("https:// spaces .com/x", False),
    ("https://ntfy.sh/비밀-주제", False),
    ("https://ntfy.sh/", False),
    ("https://exa mple.com/x", False),
    ("https://host:99999/x", False),
    (None, False),
])
def test_webhook_address_check(url, ok):
    assert notify.valid(url) is ok
    assert (notify.problem(url) is None) is ok


def test_alerts_add_says_what_is_wrong_and_saves_nothing(capsys):
    """★'notaurl'에 'Not saved: ... (/*** (95ea))'만 나왔고, 'https://'만 준 주소는 저장됐다"""
    for bad in ("notaurl", "https://", "https://ntfy.sh/비밀-주제"):
        assert alerts_cli.main(["--add", bad]) == 2
        out = capsys.readouterr().out
        assert "Not saved" in out and "https://ntfy.sh/<a-long-random-topic>" in out, out
        assert "95ea" not in out
    assert not alerts_cli.hooks_file().exists()


def test_doctor_shows_how_many_webhooks_are_saved(monkeypatch, tmp_path, capsys):
    from epokio import doctor, envs, onboard
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(onboard, "agent_health", lambda *a, **k: None)
    monkeypatch.setattr(envs, "list_envs", lambda: [])
    secret = "https://ntfy.sh/very_secret_topic_42"
    f = alerts_cli.hooks_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"urls": [secret, "https://"]}))
    assert doctor.doctor([]) == 0
    out = capsys.readouterr().out
    assert "phone alerts: 2 webhooks saved (1 not usable)" in out and "very_secret" not in out
    assert doctor.doctor(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["webhooks"] == {"saved": 2, "usable": 1}


def test_unwritable_settings_folder_is_one_line_not_a_traceback(monkeypatch, capsys):
    """★~/.epokio가 파일이거나 읽기 전용이거나 디스크가 차면 OSError 트레이스백이 그대로 나왔다"""
    ep = alerts_cli.hooks_file().parent
    ep.parent.mkdir(parents=True, exist_ok=True)
    ep.write_text("not a folder")
    monkeypatch.setattr(sys, "argv", ["epokio", "alerts", "--add", "https://ntfy.sh/abc_123"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert err.startswith("epokio: could not use") and "Traceback" not in err and "disk is not full" in err


def test_setup_hints_use_the_short_command_when_it_is_on_path(monkeypatch, tmp_path):
    """★venv를 켠 학생에게도 150자짜리 python.exe 경로로 안내했다"""
    import shutil
    from epokio import autostart
    exe = tmp_path / "Scripts" / "python.exe"
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(shutil, "which", lambda name: str(tmp_path / "Scripts" / "epokio.exe"))
    assert autostart.cli("watch") == "epokio watch"
    monkeypatch.setattr(shutil, "which", lambda name: str(tmp_path / "other" / "epokio.exe"))
    assert autostart._on_path() is False


def test_watch_without_a_helper_lists_a_linked_run_once(tmp_path):
    """★도우미 없이 폴더를 읽는 watch는 겹침 정리를 안 거쳐, 정션으로 두 번 닿은 학습이 두 줄로 나왔다"""
    from epokio import tui
    root = tmp_path / "runs"
    _yolo(root / "a" / "train")
    if not _link(root / "shortcut", root / "a" / "train"):
        pytest.skip("cannot make links here")
    assert len(tui.Feed(None, [root]).runs()) == 1
