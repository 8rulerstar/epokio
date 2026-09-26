"""재현성 스냅샷(repro·repro_runs). git은 tmp_path 안 임시 저장소에서만, GIT_*는 지운 env로."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from epokio import repro, repro_runs


@pytest.fixture(autouse=True)
def _no_git_leak(monkeypatch):
    # pre-commit 훅이 GIT_DIR·GIT_INDEX_FILE을 내보낸다. 안 지우면 실제 저장소를 건드린다.
    for k in list(os.environ):
        if k.startswith("GIT_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _git(repo: Path, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", HOME=str(repo.parent))
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "train.py").write_text("print('hi')\n")
    _git(repo, "add", "train.py")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _dataset(tmp_path: Path, n=3) -> Path:
    root = tmp_path / "ds"
    (root / "images" / "train").mkdir(parents=True)
    (root / "images" / "val").mkdir(parents=True)
    for i in range(n):
        (root / "images" / "train" / f"{i}.jpg").write_bytes(b"x" * (10 + i))
    (root / "images" / "val" / "v.png").write_bytes(b"y" * 5)
    (root / "images" / "train" / "note.txt").write_text("not an image")
    y = root / "data.yaml"
    y.write_text(f"path: {root}\ntrain: images/train\nval: images/val\nnames:\n  0: a\n")
    return y


def test_git_clean_then_dirty(tmp_path):
    repo = _repo(tmp_path)
    g = repro.git_info(repo / "train.py")
    assert g["repo"] and g["branch"] == "main" and len(g["commit"]) == 40 and g["dirty"] is False
    (repo / "train.py").write_text("print('changed')\n")
    d1 = repro.git_info(repo)
    assert d1["dirty"] and d1["changed_files"] == 1 and len(d1["diff_sha256"]) == 64
    (repo / "train.py").write_text("print('changed again')\n")
    assert repro.git_info(repo)["diff_sha256"] != d1["diff_sha256"]


def test_git_outside_repo_and_missing(tmp_path):
    (tmp_path / "plain").mkdir()
    assert repro.git_info(tmp_path / "plain") == {"repo": False}
    assert repro.git_info(tmp_path / "nope") == {"repo": False}


def test_git_ignores_leaked_git_dir(tmp_path, monkeypatch):
    """GIT_DIR이 다른 저장소를 가리켜도 대상 폴더의 저장소를 읽는다."""
    repo = _repo(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    assert repro.git_info(repo)["repo"] is True


def test_python_info_reports_only_installed():
    info = repro.python_info(sys.executable, packages=("pytest", "surely-not-a-package-xyz"))
    assert info["version"].count(".") == 2 and "pytest" in info["packages"]
    assert "surely-not-a-package-xyz" not in info["packages"]


def test_python_info_bad_interpreter(tmp_path):
    assert "error" in repro.python_info(str(tmp_path / "nopython"))


def test_data_fingerprint(tmp_path):
    y = _dataset(tmp_path)
    d = repro.data_info(y)
    assert d["images"] == 4 and d["bytes"] == 10 + 11 + 12 + 5 and len(d["yaml_sha256"]) == 64
    assert "content_sha256" not in d
    (y.parent / "images" / "train" / "new.jpg").write_bytes(b"z")
    d2 = repro.data_info(y, full_hash=True)
    assert d2["images"] == 5 and d2["listing_sha256"] != d["listing_sha256"] and "content_sha256" in d2


def test_data_missing_and_none(tmp_path):
    assert repro.data_info(None) == {}
    assert repro.data_info(tmp_path / "x.yaml")["missing"] is True


def test_seed_from_params_and_args_yaml(tmp_path):
    a = tmp_path / "args.yaml"
    a.write_text("seed: 7\ndeterministic: true\nepochs: 3\n")
    assert repro.seed_info(None, a) == {"seed": "7", "deterministic": "true"}
    assert repro.seed_info({"seed": 1}, a)["seed"] == 1
    assert repro.seed_info({"epochs": 3})["seed_default"] is True


def test_home_is_hidden():
    home = str(Path.home())
    assert repro.tilde({"p": [home + "/x"]}) == {"p": ["~/x"]}


def test_snapshot_survives_a_broken_step(monkeypatch):
    monkeypatch.setattr(repro, "system_info", lambda: 1 / 0)
    s = repro.snapshot(python=sys.executable)
    assert s["system"] == {"error": "ZeroDivisionError"} and "version" in s["python"]


def test_write_read_with_lock(tmp_path):
    p = repro.write(tmp_path / "r", {"schema": 1}, freeze=f"pkg==1\n# {Path.home()}/x\n")
    s = repro.read(tmp_path / "r")
    assert p.name == repro.FILE and s["lock_file"] == repro.LOCK_FILE
    assert str(Path.home()) not in (tmp_path / "r" / repro.LOCK_FILE).read_text()
    assert repro.read(tmp_path / "none") is None


def test_job_snapshot_then_adopt(tmp_path):
    repo = _repo(tmp_path)
    y = _dataset(tmp_path)
    job = SimpleNamespace(id="j1", kind="train", name="exp", python=sys.executable, cwd=str(repo),
                          params={"data": str(y), "seed": 3, "epochs": 2})
    pend = tmp_path / "pending"
    p = repro_runs.for_job(job, root=pend)
    s = json.loads(p.read_text())
    assert s["code"]["repo"] and s["seed"]["seed"] == 3 and s["data"]["images"] == 4 and s["job"]["id"] == "j1"
    assert not (tmp_path / "runs").exists()                  # run 폴더를 미리 만들지 않는다
    run = tmp_path / "runs" / "exp"
    run.mkdir(parents=True)
    assert repro_runs.adopt("j1", run, root=pend) == run / repro.FILE
    assert not (pend / "j1").exists() and repro.read(run)["job"]["name"] == "exp"
    assert repro_runs.adopt("j1", run, root=pend) is None


def test_script_job_uses_script_repo(tmp_path):
    repo = _repo(tmp_path)
    job = SimpleNamespace(id="j2", kind="script", name="s", python=sys.executable, cwd=str(tmp_path),
                          params={"args": [str(repo / "train.py"), "--x"]})
    s = json.loads(repro_runs.for_job(job, root=tmp_path / "p").read_text())
    assert s["code"]["repo"] is True


def test_posthoc_partial_and_never_overwrites(tmp_path):
    y = _dataset(tmp_path)
    run = tmp_path / "old"
    run.mkdir()
    (run / "args.yaml").write_text(f"data: {y}\nseed: 0\ndeterministic: true\n")
    s = repro_runs.posthoc(run)
    assert s["partial"] and s["data"]["images"] == 4 and s["seed"]["seed"] == "0" and s["python"] == {}
    repro.write(run, {"schema": 1, "real": True})
    repro_runs.posthoc(run)
    assert repro.read(run)["real"] is True


def test_compare(tmp_path):
    a = {"code": {"commit": "a1", "dirty": False}, "seed": {"seed": 0},
         "python": {"version": "3.12.1", "packages": {"torch": "2.4", "numpy": "2.0"}},
         "data": {"images": 10, "listing_sha256": "L1"}, "system": {"gpus": [{"name": "4090"}]}}
    b = json.loads(json.dumps(a))
    assert repro_runs.compare(a, b)["same"] is True
    b["code"]["commit"] = "b2"
    b["python"]["packages"]["torch"] = "2.5"
    b["python"]["packages"]["timm"] = "1.0"
    b["data"]["images"] = 11
    b["seed"] = {}
    r = repro_runs.compare(a, b)
    fields = {d["field"] for d in r["diffs"]}
    assert fields == {"code.commit", "package.torch", "package.timm", "data.images"}
    assert "seed.seed" in r["unknown"] and r["same"] is False


def test_compare_runs_missing_files(tmp_path):
    r = repro_runs.compare_runs(tmp_path / "a", tmp_path / "b")
    assert r["same"] is False and r["have"] == [False, False] and r["diffs"] == [] and r["unknown"] == []


def test_tilde_hides_windows_home_and_respects_name_boundary(monkeypatch):
    """★재현 기록은 단순 치환이라 윈도우 홈(역슬래시·대소문자)에서 사용자 이름이 남았다"""
    from pathlib import Path
    from epokio import repro
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path(r"C:\Users\Alice")))
    out = repro.tilde({"cwd": r"c:\users\alice\runs", "cfg": ["C:/Users/Alice/d.yaml"], "other": r"C:\Users\AliceX\x"})
    assert "alice" not in out["cwd"].lower() and out["cwd"].startswith("~"), out
    assert out["cfg"] == ["~/d.yaml"], out
    assert out["other"] == r"C:\Users\AliceX\x", out          # 이름이 더 긴 다른 사용자는 그대로
