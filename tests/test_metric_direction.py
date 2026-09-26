"""지표 방향과 완료 판정.

네 가지 결함을 한 벌로 묶는다.
 1 낮을수록 좋은 지표(rmse·loss)를 "점수"로 다뤄 백분율까지 붙이던 것 → agent가 방향(metric_higher)을 실어 보낸다
 2 홈의 개선 화살표가 방향을 고정하던 것 → 비교 대상도 색도 지표를 따른다
 3 HF가 에폭 중간에 평가하면(19.33) 올림 때문에 "20/20 · 완료"가 되던 것 → 내림
 4 실패·중단인데 100% 완료로 그려지던 것 → 완료는 진행률이 아니라 상태로 본다

스위프트는 이 저장소에 시험 표적이 없다. 화면이 방향을 다시 잃지 않게 소스 자체를 확인한다
(집 규칙 시험과 같은 방식). 응답 모양은 tests/test_contract.py가 따로 지킨다.
"""
import json
from pathlib import Path

from epokio import adapters, scan

ROOT = Path(__file__).resolve().parents[1]
MAC = ROOT / "mac" / "Sources" / "Epokio"


def _run_dir(d: Path, header: str, rows: list[str], epochs: int = 3) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.csv").write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    (d / "args.yaml").write_text(f"epochs: {epochs}\n", encoding="utf-8")
    return d


# ── 1 방향을 JSON에 싣는다 ─────────────────────────────

def test_lower_is_better_run_is_marked(tmp_path):
    """rmse 대표 학습: metric_higher=False이고 최고는 min이다"""
    d = _run_dir(tmp_path / "rmse", "epoch,time,metrics/rmse",
                 ["1,10,0.90", "2,20,0.48", "3,30,0.71"])
    r = scan.read_run(d)
    assert r.metric_name == "metrics/rmse"
    assert r.metric_higher is False
    assert r.best == 0.48 and r.best_epoch == 2          # 낮은 쪽이 최고
    assert r.to_dict()["metric_higher"] is False         # 앱·웹·터미널이 읽는 건 이 JSON이다


def test_higher_is_better_run_is_marked(tmp_path):
    d = _run_dir(tmp_path / "map", "epoch,time,metrics/mAP50-95(B)",
                 ["1,10,0.40", "2,20,0.55", "3,30,0.51"])
    r = scan.read_run(d)
    assert r.metric_higher is True and r.best == 0.55


def test_old_agent_json_without_the_field_still_loads():
    """옛 agent(필드 없음)의 응답: 지금까지 화면이 쓰던 '높을수록 좋다'로 읽힌다"""
    old = {"name": "x", "path": "/tmp/x", "epoch": 1, "total": 3, "elapsed": 1.0, "eta": None,
           "metric": 0.5, "metric_name": "metrics/mAP50-95(B)", "best": 0.5, "best_epoch": 1,
           "state": "running", "idle": 0.0}
    assert scan.Run.from_dict(old).metric_higher is True


def test_table_row_carries_direction(tmp_path, monkeypatch):
    from epokio.agent import Agent
    from epokio.api import table
    root = tmp_path / "runs"
    _run_dir(root / "rmse", "epoch,time,metrics/rmse", ["1,10,0.9", "2,20,0.4"])
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    monkeypatch.setattr("epokio.runmeta.FILE", tmp_path / "meta.json", raising=False)
    a = Agent.__new__(Agent)
    a.roots, a.label = [root], "t"
    rows = table.get(a, "/runs/table", {})["rows"]
    assert rows and rows[0]["metric_higher"] is False


def test_views_format_the_best_score_with_its_direction():
    """Fmt.score는 백분율 설정을 따른다: 낮을수록 좋은 지표에 쓰면 rmse 0.48이 "48.0%"가 된다"""
    for name in ("RunCard.swift", "RunRow.swift", "HomeView.swift"):
        src = (MAC / name).read_text(encoding="utf-8")
        for i, line in enumerate(src.splitlines(), 1):
            if "Fmt.score(" in line and ("best" in line or ".best" in line):
                raise AssertionError(f"{name}:{i} 대표 점수에 방향 없는 Fmt.score를 쓴다: {line.strip()}")
        assert "Fmt.metric(" in src, f"{name}이 방향을 반영하지 않는다"
    assert "metric_higher" in (MAC / "Models.swift").read_text(encoding="utf-8")


# ── 2 개선 화살표 ─────────────────────────────────────

def test_home_delta_follows_the_metric():
    src = (MAC / "HomeView.swift").read_text(encoding="utf-8")
    assert "private func delta(_ d: Double, higher: Bool" in src, "delta가 방향을 안 받는다"
    assert "let better = higher ? d >= 0 : d <= 0" in src, "색이 값의 부호에 묶여 있다"
    assert "$0.metric_name == r.metric_name" in src, "before()가 다른 지표의 학습과 견준다"


def test_runs_table_best_is_per_metric():
    src = (MAC / "RunsTable.swift").read_text(encoding="utf-8")
    assert "$0.metric_name == r.metric_name" in src, "'최고' 강조가 지표를 가리지 않는다"
    assert "higher ? peers.max() : peers.min()" in src
    assert "best.map { higher ? $0 : -$0 }" in src, "정렬이 방향을 무시한다"


# ── 3 HF 에폭 중간 평가 ────────────────────────────────

def _hf(d: Path, epochs: list[float], total: int = 20) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    hist = [{"epoch": e, "loss": 0.5, "eval_loss": 0.4, "eval_accuracy": 0.8} for e in epochs]
    (d / "trainer_state.json").write_text(json.dumps(
        {"epoch": epochs[-1], "num_train_epochs": total, "log_history": hist}), encoding="utf-8")
    return d


def test_hf_midepoch_eval_is_not_done(tmp_path):
    """eval_steps로 19.33에서 평가한 학습은 19에폭까지 끝난 것이다. 20/20 완료가 아니다"""
    d = _hf(tmp_path / "hf", [18.0, 19.0, 19.33])
    assert adapters.load(d).rows[-1]["epoch"] == "19.33"            # 곡선 점은 평가 시점(dev), 끝낸 에폭은 아래 19
    r = scan.read_run(d)
    assert r.epoch == 19 and r.total == 20
    assert r.state != "done"
    assert r.eta is not None                       # done이 되면 eta 계산도 멎었다


def test_hf_finished_run_is_still_done(tmp_path):
    """에폭이 진짜 끝나면 HF는 20.0을 적는다: 정상 종료 판정은 그대로다"""
    d = _hf(tmp_path / "hf2", [18.0, 19.0, 20.0])
    r = scan.read_run(d)
    assert r.epoch == 20 and r.state == "done"


def test_done_epochs_handles_junk():
    from epokio import hf_args
    assert hf_args.done_epochs(None, 7) == 7
    assert hf_args.done_epochs("nope", 7) == 7
    assert hf_args.done_epochs(float("nan"), 7) == 7
    assert hf_args.done_epochs(-0.5, 7) == 0        # 음수 에폭은 없다


# ── 4 실패·중단은 완료가 아니다 ────────────────────────

def test_failed_run_at_last_epoch_is_not_complete(tmp_path):
    """마지막 에폭이 total에 닿아도 손실이 NaN이면 실패다(상태가 진행률보다 우선)"""
    d = _run_dir(tmp_path / "boom", "epoch,time,metrics/mAP50-95(B),val/box_loss",
                 ["1,10,0.4,1.0", "2,20,0.5,0.9", "3,30,0.5,nan"])
    r = scan.read_run(d)
    assert r.state == "failed" and r.progress == 1.0       # 진행률만 보면 "100% 완료"였다


def test_card_completion_uses_state_not_progress():
    models = (MAC / "Models.swift").read_text(encoding="utf-8")
    assert 'var isComplete: Bool { state == "done" }' in models
    card = (MAC / "RunCard.swift").read_text(encoding="utf-8")
    assert "private var complete: Bool { run.isComplete }" in card
    assert "run.progress ?? 0) >= 0.999" not in card, "완료 판정이 아직 진행률에 묶여 있다"
