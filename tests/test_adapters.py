"""프레임워크 어댑터: Hugging Face·Lightning·Keras 기록을 읽어 같은 모양(에폭별 행)으로 바꾸는지.
파일 모양은 각 프레임워크가 실제로 남기는 형식을 따랐다."""
import json
import time
from pathlib import Path

from epokio import adapters, analysis, rundetail
from epokio.scan import scan


def hf_run(root: Path) -> Path:
    d = root / "bert-finetune"
    (d / "checkpoint-500").mkdir(parents=True)
    (d / "checkpoint-1000").mkdir()
    hist = [{"loss": 0.9, "epoch": 0.5, "step": 250}, {"eval_loss": 0.70, "eval_accuracy": 0.71, "eval_f1": 0.69, "eval_runtime": 3.1, "epoch": 1.0, "step": 500},
            {"loss": 0.5, "epoch": 1.5, "step": 750}, {"eval_loss": 0.55, "eval_accuracy": 0.80, "eval_f1": 0.78, "eval_runtime": 3.0, "epoch": 2.0, "step": 1000}]
    state = {"epoch": 2.0, "num_train_epochs": 3, "train_batch_size": 16, "log_history": hist}
    (d / "checkpoint-500" / "trainer_state.json").write_text(json.dumps({**state, "log_history": hist[:2]}))
    (d / "checkpoint-1000" / "trainer_state.json").write_text(json.dumps(state))
    return d


def lightning_run(root: Path) -> Path:
    d = root / "lightning_logs" / "version_0"
    d.mkdir(parents=True)
    (d / "hparams.yaml").write_text("lr: 0.001\nmax_epochs: 4\n")
    (d / "metrics.csv").write_text(
        "epoch,step,train_loss,val_loss,val_acc\n"
        "0,99,0.80,,\n0,99,,0.75,0.60\n"
        "1,199,0.60,,\n1,199,,0.62,0.72\n")
    return d


def keras_run(root: Path) -> Path:
    d = root / "keras_mnist"
    d.mkdir(parents=True)
    (d / "training.log").write_text("epoch,accuracy,loss,val_accuracy,val_loss\n0,0.90,0.35,0.93,0.25\n1,0.95,0.17,0.96,0.14\n")
    return d


def test_huggingface(tmp_path):
    d = hf_run(tmp_path)
    got = adapters.load(d)
    assert got.framework == "huggingface" and got.total == 3
    assert got.source.parent.name == "checkpoint-1000"            # 가장 최근 체크포인트
    assert [r["epoch"] for r in got.rows] == ["1", "2"]
    assert got.rows[-1]["metrics/f1"] == "0.78" and got.rows[-1]["val/eval_loss"] == "0.55"
    assert "metrics/runtime" not in got.rows[-1]                  # 속도 같은 건 점수가 아니다


def test_lightning(tmp_path):
    got = adapters.load(lightning_run(tmp_path))
    assert got.framework == "lightning" and got.total == 4
    assert got.rows == [{"epoch": "1", "train/train_loss": "0.80", "val/val_loss": "0.75", "metrics/val_acc": "0.60"},
                        {"epoch": "2", "train/train_loss": "0.60", "val/val_loss": "0.62", "metrics/val_acc": "0.72"}]


def test_keras(tmp_path):
    got = adapters.load(keras_run(tmp_path))
    assert got.framework == "keras"
    assert got.rows[0]["epoch"] == "1"                             # Keras는 0부터 센다
    assert got.rows[1]["metrics/val_accuracy"] == "0.96" and got.rows[1]["val/val_loss"] == "0.14"


def test_scan_finds_all_frameworks(tmp_path):
    hf_run(tmp_path); lightning_run(tmp_path); keras_run(tmp_path)
    runs = {r.framework: r for r in scan(tmp_path, now=time.time())}
    assert set(runs) == {"huggingface", "lightning", "keras"}
    assert runs["huggingface"].epoch == 2 and runs["huggingface"].total == 3
    assert runs["huggingface"].metric_name in ("metrics/f1", "metrics/accuracy")
    assert runs["keras"].metric_name == "metrics/val_accuracy"     # 검증 점수를 먼저
    assert runs["lightning"].best == 0.72


def test_detail_and_notes_work_for_other_frameworks(tmp_path):
    d = rundetail.detail(keras_run(tmp_path))
    assert d["framework"] == "keras"
    assert "metrics/val_accuracy" in d["columns"] and "val/val_loss" in d["columns"]
    assert analysis.analyze(tmp_path / "keras_mnist") is not None


def test_unchanged_runs_are_not_read_again(tmp_path, monkeypatch):
    """폴링마다 모든 학습의 기록 파일을 통째로 다시 읽었다. 그대로면 시각·크기만 본다."""
    from epokio import scan as scan_mod
    d = tmp_path / "runs" / "exp"
    d.mkdir(parents=True)
    (d / "args.yaml").write_text("epochs: 5\n")
    (d / "results.csv").write_text("epoch,time,metrics/mAP50-95(B)\n1,1,0.1\n2,2,0.2\n")
    reads = []                                   # _parse가 어댑터를 골라 파일을 읽은 횟수
    real_detect = adapters.detect

    def detect(p, *names):
        if not names:                            # 폴더 걷기(names를 준다)가 아니라 _parse에서 부른 것
            reads.append(p)
        return real_detect(p, *names)
    monkeypatch.setattr(scan_mod.adapters, "detect", detect)
    scan_mod._cache.clear()
    first = scan(tmp_path / "runs")
    n = len(reads)
    again = scan(tmp_path / "runs")
    assert len(reads) == n and again[0].best == first[0].best == 0.2
    with (d / "results.csv").open("a") as f:
        f.write("3,3,0.3\n")
    assert scan(tmp_path / "runs")[0].best == 0.3          # 바뀌면 다시 읽는다


def test_lower_is_better_metrics_are_not_scores(tmp_path):
    """Keras 회귀의 val_mae를 점수로 두면 가장 나쁜 에폭이 best가 됐다."""
    d = tmp_path / "runs" / "reg"
    d.mkdir(parents=True)
    (d / "training.log").write_text("epoch,loss,mae,val_loss,val_mae\n0,9,3,8,2.5\n1,5,2,4,1.5\n2,3,1,2,0.9\n")
    got = adapters.load(d)
    assert "val/val_mae_loss" in got.rows[0] and not any(k.startswith("metrics/") for k in got.rows[0])


def test_the_scan_cache_does_not_keep_every_row(tmp_path):
    """캐시가 어댑터가 읽은 모든 행을 들고 있어서 학습 2,000개에서 agent가 583MB였다(497MB가 CSV 행)."""
    from epokio import scan as scan_mod
    d = tmp_path / "runs" / "exp"
    d.mkdir(parents=True)
    (d / "args.yaml").write_text("epochs: 5\n")
    (d / "results.csv").write_text("epoch,time,metrics/mAP50-95(B)\n" + "".join(f"{i},{i},0.{i}\n" for i in range(1, 6)))
    scan_mod._cache.clear()
    [r] = scan(tmp_path / "runs")
    entry = scan_mod._cache[d]
    assert isinstance(entry[3], scan_mod._Meta) and not hasattr(entry[3], "rows")
    assert r.total == 5 and r.framework == "ultralytics"


def test_a_new_huggingface_checkpoint_is_seen(tmp_path):
    """★캐시가 마지막으로 읽은 checkpoint-N 파일만 봐서, 새 체크포인트(새 폴더)가 생겨도 첫 에폭에 멈춘 것처럼 보이다
    3분 뒤 '멎음' 알림을 보냈다."""
    import os
    from epokio import scan as scan_mod
    d = tmp_path / "runs" / "bert"
    (d / "checkpoint-100").mkdir(parents=True)
    st = lambda ep: {"epoch": ep, "num_train_epochs": 3, "log_history": [{"eval_loss": 1.0 / ep, "eval_accuracy": 0.5 + ep / 10, "epoch": float(ep)}]}
    (d / "checkpoint-100" / "trainer_state.json").write_text(json.dumps(st(1)))
    scan_mod._cache.clear()
    assert scan(tmp_path / "runs")[0].epoch == 1
    (d / "checkpoint-200").mkdir()
    (d / "checkpoint-200" / "trainer_state.json").write_text(json.dumps(st(2)))
    os.utime(d, (time.time() + 5, time.time() + 5))            # 파일 시스템 시각 해상도가 거친 곳에서도 확실히
    assert scan(tmp_path / "runs")[0].epoch == 2


def _hf_state(d: Path, **st):
    d.mkdir(parents=True)
    (d / "trainer_state.json").write_text(json.dumps(st), encoding="utf-8")
    return d


def test_a_huggingface_run_is_not_done_after_its_first_mid_epoch_eval(tmp_path):
    """★평가 시점(0.1 에폭)을 올림해 1/1 '끝남'과 '끝났어요' 알림이 10%에서 갔다. 곡선도 에폭당 한 점이었다"""
    from epokio.scan import read_run
    d = _hf_state(tmp_path / "hf", num_train_epochs=1, max_steps=1000, global_step=100, epoch=0.1, log_history=[
        {"loss": 2.0, "epoch": 0.05, "step": 50},
        {"eval_loss": 1.9, "eval_accuracy": 0.4, "eval_model_preparation_time": 0.004, "epoch": 0.1, "step": 100}])
    r = read_run(d)
    assert r.state != "done" and r.epoch == 0
    assert r.metric_name == "metrics/val_accuracy" or "accuracy" in r.metric_name   # 준비 시간은 점수가 아니다
    st = json.loads((d / "trainer_state.json").read_text())
    st.update(global_step=1000, epoch=1.0)
    st["log_history"].append({"eval_loss": 1.5, "eval_accuracy": 0.6, "epoch": 0.5, "step": 500})
    st["log_history"].append({"eval_loss": 1.2, "eval_accuracy": 0.7, "epoch": 1.0, "step": 1000})
    (d / "trainer_state.json").write_text(json.dumps(st))
    r = read_run(d)
    assert r.state == "done" and r.epoch == 1
    got = adapters.load(d)
    assert [row["epoch"] for row in got.rows] == ["0.1", "0.5", "1"]            # 평가마다 한 점


def test_loss_like_scores_and_learning_rates_are_not_the_best_score(tmp_path):
    """★Keras의 crossentropy 지표에서 가장 나쁜 에폭을, Lightning에서는 최고 학습률을 'best'로 골랐다"""
    from epokio.scan import read_run
    k = tmp_path / "k"
    k.mkdir()
    (k / "training.log").write_text("epoch,loss,sparse_categorical_crossentropy,val_loss,val_sparse_categorical_crossentropy\n"
                                    "0,2.0,2.0,2.1,2.1\n1,1.0,1.0,1.1,1.1\n", encoding="utf-8")
    r = read_run(k)
    assert not (r.metric_name or "").startswith("metrics/")
    lt = tmp_path / "lightning_logs" / "version_0"
    lt.mkdir(parents=True)
    (lt / "hparams.yaml").write_text("max_epochs: 5\n", encoding="utf-8")
    (lt / "metrics.csv").write_text("epoch,step,lr-Adam,val_acc,train_loss\n0,10,0.1,0.5,1.0\n1,20,0.01,0.6,0.8\n", encoding="utf-8")
    r = read_run(lt)
    assert "lr" not in r.metric_name and r.best == 0.6


def test_a_slow_epoch_is_not_called_stalled(tmp_path, monkeypatch):
    """★고정 3분이라 에폭이 10분 걸리는 학습은 매 에폭 '멎음'(급한 소리·폰 알림)과 '다시 돎'을 오갔다"""
    import os
    from epokio import scan
    d = tmp_path / "slow"
    d.mkdir()
    (d / "args.yaml").write_text("epochs: 10\n", encoding="utf-8")
    (d / "results.csv").write_text("epoch,time,train/box_loss,metrics/mAP50-95(B)\n1,600,1.0,0.1\n2,1200,0.9,0.2\n", encoding="utf-8")
    t = time.time() - 8 * 60                                  # 마지막 에폭 뒤 8분: 한 에폭(10분)보다 짧다
    os.utime(d / "results.csv", (t, t))
    assert scan.read_run(d).state == "running"
    t = time.time() - 20 * 60                                 # 두 에폭 넘게 조용하면 멎음
    os.utime(d / "results.csv", (t, t))
    assert scan.read_run(d).state == "stalled"


def test_a_chosen_main_score_and_direction_are_used(tmp_path):
    """★대표 점수를 고를 수 없어, 손실·오류율이 기준인 학습은 엉뚱한 열(또는 없음)로 순위·목표 알림이 갔다"""
    from epokio import runmeta
    from epokio.scan import read_run
    d = tmp_path / "k"
    d.mkdir()
    (d / "training.log").write_text("epoch,loss,val_loss,val_acc\n0,2.0,1.0,0.9\n1,1.0,0.4,0.5\n2,0.8,0.6,0.6\n", encoding="utf-8")
    assert read_run(d).metric_name == "metrics/val_acc"
    runmeta.update(str(d), {"metric": "val/val_loss", "lower": True, "goal": 0.5})
    r = read_run(d)
    assert r.metric_name == "val/val_loss" and r.best == 0.4 and r.best_epoch == 2
    assert [x.path for x in runmeta.goals_reached([r])] == [d]            # 낮을수록 좋으면 목표 아래로 내려가야 넘은 것
    runmeta.update(str(d), {"metric": None})                               # 자동으로 되돌린다
    assert read_run(d).metric_name == "metrics/val_acc"


def test_the_chosen_score_survives_a_train_only_row_and_goals_use_the_real_direction(tmp_path):
    """★새 에폭의 첫 줄(학습 값만)에서 고른 점수가 사라졌고, 고른 열이 없어 자동 점수로 돌아가도
    저장된 '낮을수록'으로 목표를 판정해 거짓 알림이 갔다. 저장만 다시 눌러도 알림이 또 갔다"""
    from epokio import runmeta
    from epokio.scan import read_run
    lt = tmp_path / "lightning_logs" / "version_0"
    lt.mkdir(parents=True)
    (lt / "metrics.csv").write_text("epoch,step,train_loss,val_loss,val_acc\n0,9,1.0,0.9,0.5\n1,19,0.8,0.6,0.6\n2,20,0.7,,\n",
                                    encoding="utf-8")
    runmeta.update(str(lt), {"metric": "val/val_loss", "lower": True, "goal": 0.7})
    r = read_run(lt)
    assert r.metric_name == "val/val_loss" and r.best == 0.6 and r.lower and r.metric == 0.6
    assert runmeta.goals_reached([r]) == [r]
    runmeta.update(str(lt), {"metric": "val/val_loss", "lower": True})          # 그대로 저장
    assert runmeta.goals_reached([r]) == []                                     # 다시 알리지 않는다
    runmeta.update(str(lt), {"metric": "val/seg_loss"})                          # 없는 열: 자동 점수(높을수록)
    r = read_run(lt)
    assert r.metric_name == "metrics/val_acc" and not r.lower
    runmeta.update(str(lt), {"goal": 0.9})
    assert runmeta.goals_reached([r]) == []                                     # 0.6 ≥ 0.9 가 아니다
    runmeta.update(str(lt), {"metric": None, "lower": True})
    assert "lower" not in runmeta.get(str(lt))                                  # 고른 점수 없이 방향만 남지 않는다


def test_the_report_ranks_by_the_chosen_score_when_there_is_no_f1(tmp_path):
    from epokio import report, runmeta
    from epokio.scan import read_run
    runs = []
    for name, maes in (("a", "0.9,0.8"), ("b", "0.5,0.2")):
        d = tmp_path / name
        d.mkdir()
        vals = maes.split(",")
        (d / "training.log").write_text("epoch,loss,val_loss,val_mae\n" + "".join(
            f"{i},1.0,1.0,{v}\n" for i, v in enumerate(vals)), encoding="utf-8")
        runmeta.update(str(d), {"metric": "val/val_mae_loss", "lower": True})
        runs.append(read_run(d))
    md = report.build(runs)
    board = md.split("## Leaderboard")[1].split("## ")[0]
    assert board.index("| b |") < board.index("| a |")
    assert "0.200 val_mae_loss ↓" in md


def test_a_deleted_run_leaves_the_scan_cache(tmp_path):
    """★지운 학습의 요약이 캐시에 영원히 남았다(일주일 켜 두면 계속 늘었다)"""
    import shutil
    from epokio import scan as scan_mod
    d = tmp_path / "exp"
    d.mkdir()
    (d / "results.csv").write_text("epoch,metrics/mAP50-95(B)\n1,0.1\n", encoding="utf-8")
    scan(tmp_path)
    assert d in scan_mod._cache
    shutil.rmtree(d)
    scan(tmp_path)
    assert d not in scan_mod._cache


def test_nested_watched_folders_show_each_run_once_and_names_are_shared(tmp_path, monkeypatch):
    """★직접 더한 폴더 안의 폴더를 찾기가 또 더해 학습이 두 번 나왔고, 보고서에서는 같은 이름('train')끼리
    그림이 덮여 다른 학습의 곡선이 보였다. 폰 알림·트레이·맥은 'train'만 보였다"""
    from epokio import report
    from epokio.agent import Agent
    for proj in ("defect_det", "scratch_det"):
        d = tmp_path / proj / "runs" / "detect" / "train"
        d.mkdir(parents=True)
        (d / "results.csv").write_text("epoch,metrics/mAP50-95(B)\n1,0.1\n", encoding="utf-8")
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label = [tmp_path, tmp_path / "defect_det" / "runs"], "t"
    runs = a.get("/runs", {})["runs"]
    assert sorted(r["display"] for r in runs) == ["defect_det/train", "scratch_det/train"]
    rs = [read_run_path for read_run_path in scan(tmp_path)]
    assets = tmp_path / "assets"
    assets.mkdir()
    md = report.build(rs, assets)
    assert "### defect_det/train" in md and "### scratch_det/train" in md


def test_durations_keep_the_hours_and_follow_the_language():
    """★터미널·트레이는 47시간 남은 학습을 '1d'로 보였고, 한국어 윈도우에서도 영어 단위였다"""
    from epokio import i18n
    from epokio.scan import fmt_dur
    assert fmt_dur(172000) == "1d 23h" and fmt_dur(3700) == "1h 1m" and fmt_dur(None) == "-"
    try:
        i18n.use("ko")
        assert fmt_dur(172000) == "1일 23시간"
    finally:
        i18n.use("en")


def test_keras_bom_header(tmp_path):
    """★윈도우·엑셀·pandas(utf-8-sig)가 붙인 BOM 때문에 이름이 맞는 Keras 기록도 못 알아봤다"""
    d = tmp_path / "keras_bom"
    d.mkdir()
    (d / "history.csv").write_text("﻿epoch,loss,val_loss\n0,0.5,0.6\n1,0.4,0.5\n", encoding="utf-8")
    got = adapters.load(d)
    assert got.framework == "keras" and [r["epoch"] for r in got.rows] == ["1", "2"]


def test_custom_epoch_csv_any_name(tmp_path):
    """직접 짠 루프의 train_log.csv(BOM · 1부터 · 에폭당 초 · best 표시 '*')가 이름 무관하게 잡히는지"""
    d = tmp_path / "normal100"
    d.mkdir()
    (d / "train_log.csv").write_text(
        "﻿epoch,train_loss,train_acc,val_loss,val_acc,lr,best,sec\n"
        "1,0.05,0.98,0.03,0.98,3e-04,*,63.1\n2,0.01,0.99,0.02,1.0,2.9e-04,,53.2\n", encoding="utf-8")
    got = adapters.load(d)
    assert got.framework == "custom"
    assert [r["epoch"] for r in got.rows] == ["1", "2"]                  # 1부터 쓴 건 그대로
    assert got.rows[0]["train/train_loss"] == "0.05" and got.rows[0]["val/val_loss"] == "0.03"
    assert not any(k.endswith(("sec", "lr", "best")) for k in got.rows[0])   # 시간·학습률·표시는 점수 아님


def test_custom_epoch_csv_zero_based_and_not_hijacking(tmp_path):
    d = tmp_path / "zero"
    d.mkdir()
    (d / "log.csv").write_text("epoch,loss\n0,0.9\n1,0.8\n")
    assert [r["epoch"] for r in adapters.load(d).rows] == ["1", "2"]
    other = tmp_path / "plain"
    other.mkdir()
    (other / "data.csv").write_text("id,label\n1,cat\n")               # 학습 기록 아닌 CSV는 무시
    (other / "loss_epoch.csv").write_text("step,epoch,loss\n1,0,0.9\n")  # 첫 열이 epoch가 아니면 무시
    assert adapters.detect(other) is None
    assert adapters.detect(lightning_run(tmp_path)).name == "lightning"  # Lightning 폴더를 가로채지 않는다


def test_lightning_runs_are_named_by_their_project(tmp_path):
    """★Lightning 학습이 전부 version_0으로 떠 여러 개를 구분할 수 없었다"""
    from epokio.scan import display_name
    from types import SimpleNamespace
    r = SimpleNamespace(name="version_0", path=tmp_path / "cls_exp" / "lightning_logs" / "version_0")
    assert display_name(r) == "cls_exp/version_0"


def test_run_json_has_no_float_noise(tmp_path):
    from epokio.scan import read_run
    d = tmp_path / "noise"
    d.mkdir()
    (d / "log.csv").write_text("epoch,loss,acc\n1,0.5,0.8200000000000001\n")
    got = read_run(d).to_dict()
    assert got["best"] == 0.82 and got["metric"] == 0.82
