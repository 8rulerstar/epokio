"""형식 계약: agent가 보내는 JSON의 모양을 tests/contract에 고정한다.

* 파이썬: 지금 응답의 열쇠·타입이 고정본과 같아야 한다(열쇠가 빠지거나 타입이 바뀌면 깨진다)
* 스위프트: 앱이 빌드돼 있으면 지금 응답을 앱 모델로 실제 읽어 본다(`Epokio --contract`)
고정본을 일부러 바꿀 때: EPOKIO_UPDATE_CONTRACT=1 pytest tests/test_contract.py
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent))

from epokio.agent import Agent

HERE = Path(__file__).parent
GOLD = HERE / "contract"
APP = HERE.parent / "mac" / ".build" / "debug" / "Epokio"


def _responses(tmp_path, monkeypatch) -> dict:
    root = tmp_path / "runs"
    shutil.copytree(HERE / "fixtures" / "formats" / "ultralytics84_pose", root / "pose")
    for f in (root / "pose").iterdir():
        os.utime(f)                     # ★복사본은 옛 시각을 가져가 '멈춘 학습'이 되고 eta가 None으로 바뀐다(날마다 깨짐)
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    monkeypatch.setattr("epokio.runmeta.FILE", tmp_path / "meta.json", raising=False)
    a = Agent.__new__(Agent)
    a.roots, a.label = [root], "t"
    runs = a.get("/runs", {})
    run = a.get("/run", {"path": [str(root / "pose")]})
    body = lambda r: r[1] if isinstance(r, tuple) else r
    return {"runs.json": body(runs), "run.json": body(run)}


def shape(v):
    """값 대신 모양만: dict는 열쇠별 모양, list는 첫 원소 모양, 나머지는 타입 이름"""
    if isinstance(v, dict):
        return {k: shape(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [shape(v[0])] if v else []
    return "num" if isinstance(v, (int, float)) and not isinstance(v, bool) else type(v).__name__


# 열쇠 자체가 데이터인 곳(열 이름·설정 이름): 안쪽 모양만 하나로 본다
DATA_KEYED = {"columns", "column_info", "args"}


# 기계마다 생겼다 빠지는 선택 열쇠(repro.py system_info): 맥에서만 chip·os_version, NVIDIA 기계에서만 gpus·cuda.
# 앱(RunRepro.system)은 전부 옵셔널로 읽으므로 계약에서 뺀다. 안 빼면 우분투·윈도우 CI에서 깨진다
PLATFORM_KEYS = {"system": {"chip", "os_version", "gpus", "cuda"}}


def normalize(v, key=None):
    if isinstance(v, dict):
        if key in PLATFORM_KEYS:
            v = {k: x for k, x in v.items() if k not in PLATFORM_KEYS[key]}
        if key in DATA_KEYED:
            inner = [normalize(x) for x in v.values()]
            return {"*": inner[0] if inner else None}
        return {k: normalize(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [normalize(v[0])] if v else []
    return v


def test_contract(tmp_path, monkeypatch):
    got = _responses(tmp_path, monkeypatch)
    for name, data in got.items():
        s = normalize(shape(data))
        f = GOLD / name
        if os.environ.get("EPOKIO_UPDATE_CONTRACT") or not f.exists():
            GOLD.mkdir(exist_ok=True)
            f.write_text(json.dumps(s, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
        assert s == json.loads(f.read_text()), f"{name}의 모양이 바뀌었다. 앱·웹·터미널도 고친 뒤 고정본을 갱신할 것"


@pytest.mark.skipif(not APP.exists(), reason="맥 앱이 빌드돼 있지 않다(swift build)")
def test_swift_app_decodes_current_responses(tmp_path, monkeypatch):
    got = _responses(tmp_path, monkeypatch)
    out = tmp_path / "c"
    out.mkdir()
    got.update(_deep_responses(tmp_path, monkeypatch))
    for name, data in got.items():
        (out / name).write_text(json.dumps(data, default=str))
    r = subprocess.run([str(APP), "--contract", str(out)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def _deep_responses(tmp_path, monkeypatch) -> dict:
    """스윕 결과·검수 결과 응답 (앱이 실제로 읽는지 보려고)"""
    import test_review
    import test_sweep
    from epokio import review, sweep
    q = test_sweep._queue(tmp_path / "sw", monkeypatch)
    spec = sweep.create(q, "s", "py", {"data": "d", "epochs": 10}, [{"key": "lr0", "values": [0.01, 0.001]}, {"key": "optimizer", "values": ["SGD"]}])
    for t, top in zip(spec["trials"], (0.5, 0.6)):
        j = q.get(t["job"]); j.output, j.state = str(tmp_path / "sw" / j.id), "done"
        test_sweep._run(tmp_path / "sw" / j.id, [top / 2, top])
    return {"sweep.json": sweep.summary(sweep.load(spec["id"]), q), "eval.json": review.rescore(test_review.data(), 0.25)}


@pytest.mark.skipif(not APP.exists(), reason="맥 앱이 빌드돼 있지 않다(swift build)")
def test_swift_app_reads_every_repro_value_kind(tmp_path, monkeypatch):
    """★재현 기록의 seed·system 을 [String: String] 으로 읽어, 값 하나에 학습 상세 전체가 안 열렸다.
    이 앱의 학습 버튼으로 seed 없이 시작한 학습(seed_default: true)과 NVIDIA 기계(gpus 목록)가 전부 그랬다.
    예제 폴더에는 seed 가 없어 위 계약 시험이 잡지 못했다"""
    kinds = {
        "seed_default": {"seed": {"seed_default": True}},
        "seed_number": {"seed": {"seed": 42, "deterministic": True}},
        "nvidia": {"system": {"os": "Linux", "gpus": [{"name": "RTX 4090", "driver": "550.54"}], "cuda": "12.4"}},
        "unknown_shape": {"system": {"os": "Linux", "extra": {"nested": [1, 2]}}, "python": {"packages": {"torch": 2.4}}},
    }
    for tag, patch in kinds.items():
        got = _responses(tmp_path / tag, monkeypatch)
        run = got["run.json"]
        run["repro"] = {**(run.get("repro") or {}), **patch}
        out = tmp_path / tag / "c"
        out.mkdir(parents=True)
        for name, data in got.items():
            (out / name).write_text(json.dumps(data, default=str))
        r = subprocess.run([str(APP), "--contract", str(out)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, (tag, (r.stdout + r.stderr)[-300:])
