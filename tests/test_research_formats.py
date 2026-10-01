"""비전 연구 코드의 기록: MAE·DeiT·DINO 계열 log.txt(에폭마다 JSON 한 줄)와 timm summary.csv.
★둘 다 목록에 아예 안 떴다(log.txt는 형식을 몰랐고, timm은 args.yaml 때문에 울트라리틱스로 오인됐다)"""
import json
import sys
from pathlib import Path

from epokio import adapters, analysis, scan, ssh_source

sys.path.insert(0, __import__("os").path.dirname(__file__))
from test_ssh_source import env  # noqa: E402,F401  (가짜 ssh 로 원격 스크립트를 실제로 돌린다)


def mae(d, rows):
    d.mkdir(parents=True)
    (d / "log.txt").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return d


def deit_rows(n):
    return [{"train_lr": 1e-4, "train_loss": 2.0 - 0.1 * e, "test_loss": 1.5 - 0.05 * e, "test_acc1": 60 + 2 * e,
             "test_acc5": 85 + e, "epoch": e, "n_parameters": 86_000_000} for e in range(n)]


def timm(d, n=12, args="model: vit_base_patch16_224\nepochs: 300\n"):
    d.mkdir(parents=True)
    (d / "summary.csv").write_text("epoch,train_loss,eval_loss,eval_top1,eval_top5,lr\n"
                                   + "".join(f"{e},{2 - 0.1 * e},{1.5 - .05 * e},{60 + 2 * e},{85 + e},0.001\n" for e in range(n)))
    (d / "args.yaml").write_text(args)
    return d


def test_deit_finetune_log_is_read_with_accuracy_as_the_score(tmp_path):
    d = mae(tmp_path / "deit", deit_rows(12))
    got = adapters.load(d)
    assert got.framework == "jsonlog"
    assert got.rows[0] == {"epoch": "1", "train/train_loss": "2.0", "val/test_loss": "1.5",
                           "metrics/test_acc1": "60", "metrics/test_acc5": "85"}    # lr·n_parameters는 점수가 아니다
    assert analysis.analyze(d).score == {"metric": "test_acc1", "value": 82.0, "best_epoch": 12}


def test_mae_pretraining_has_only_a_loss_and_a_half_written_line_is_skipped(tmp_path):
    d = mae(tmp_path / "mae", [{"train_lr": 1e-4, "train_loss": 0.9 - 0.1 * e, "epoch": e} for e in range(3)])
    with (d / "log.txt").open("a") as f:
        f.write('{"train_lr": 0.0001, "train_lo')                           # 쓰는 중
    got = adapters.load(d)
    assert [r["epoch"] for r in got.rows] == ["1", "2", "3"] and "train/train_loss" in got.rows[-1]


def test_an_ordinary_log_txt_is_not_a_run(tmp_path):
    d = tmp_path / "notes"
    d.mkdir()
    (d / "log.txt").write_text("started at 10:00\n{\"epoch\": 1}\n")
    assert adapters.detect(d) is None


def test_timm_is_not_taken_for_ultralytics_and_eval_is_validation(tmp_path):
    d = timm(tmp_path / "20260901-vit_base")
    got = adapters.load(d)
    assert got.framework == "timm"
    assert "val/eval_loss" in got.rows[0] and "metrics/eval_top1" in got.rows[0]
    r = scan.read_run(d)
    assert r.total == 300 and r.metric_name == "metrics/eval_top1"


def test_an_ultralytics_run_before_its_first_epoch_is_still_seen(tmp_path):
    d = tmp_path / "train"
    d.mkdir()
    (d / "args.yaml").write_text("task: detect\nmode: train\nepochs: 50\n")
    assert adapters.detect(d).name == "ultralytics"


def test_ssh_view_brings_both_back(env):  # noqa: F811
    fake, _ = env
    home = env[1].parents[3]
    mae(home / "research" / "output_dir" / "deit", deit_rows(3))
    timm(home / "research" / "output" / "train" / "vit", n=3)
    (home / "notes").mkdir()
    (home / "notes" / "log.txt").write_text("hello\n")
    got = ssh_source.run_remote("gpu-box", {"auto": True}, ssh=fake)
    tails = {Path(r["path"]).parts[-2:] for r in got["runs"]}              # ★경로를 '/'로 비교하면 윈도우에서 깨진다
    assert ("output_dir", "deit") in tails and ("train", "vit") in tails
    assert not any(t[-1] == "notes" for t in tails)
    ssh_source.apply("gpu-box", got)
    names = {r.name for r in scan.scan(ssh_source.mirror_dir("gpu-box"))}
    assert {"deit", "vit"} <= names


def mmdet(d, epochs=3, iter_based=False):
    """MMDetection 3.x: work_dirs/<설정>/<시각>/vis_data/scalars.json (mmengine LocalVisBackend)"""
    (d / "vis_data").mkdir(parents=True)
    lines = []
    for e in range(1, epochs + 1):
        for it in (50, 100):
            r = {"lr": 0.004, "data_time": 0.01, "loss": 2.0 / e + it / 1000, "loss_cls": 1.0 / e, "loss_bbox": 0.5 / e,
                 "time": 0.3, "iter": it, "memory": 3000, "step": (e - 1) * 100 + it}
            if not iter_based:
                r["epoch"] = e
            lines.append(r)
        lines.append({"coco/bbox_mAP": 0.1 * e, "coco/bbox_mAP_50": 0.2 * e, "data_time": 0.01, "time": 0.1, "step": e})
    (d / "vis_data" / "scalars.json").write_text("".join(json.dumps(x) + "\n" for x in lines) + '{"lr": 0.0')
    (d / "vis_data" / "config.py").write_text("train_cfg = dict(type='EpochBasedTrainLoop', max_epochs=12, val_interval=1)\n")
    return d


def test_mmdetection_epochs_with_the_last_training_line_and_coco_map(tmp_path):
    d = mmdet(tmp_path / "work_dirs" / "rtmdet_tiny" / "20260901_120000")
    got = adapters.load(d)
    assert got.framework == "openmmlab" and got.total == 12
    assert got.rows[0] == {"epoch": "1", "train/loss": "2.1", "train/cls_loss": "1.0", "train/bbox_loss": "0.5",
                           "metrics/coco_bbox_mAP": "0.1", "metrics/coco_bbox_mAP_50": "0.2"}   # 에폭의 마지막 학습 줄
    a = analysis.analyze(d)
    assert a.score["metric"] == "coco_bbox_mAP" and a.score["best_epoch"] == 3
    assert scan.read_run(d).total == 12


def test_mmdetection_iteration_based_runs_are_left_alone(tmp_path):
    assert adapters.load(mmdet(tmp_path / "iters", iter_based=True)) is None


def test_ssh_view_brings_mmdetection_back(env):  # noqa: F811
    fake, run = env
    mmdet(run.parents[3] / "mmdet" / "work_dirs" / "cfg" / "20260901_120000")
    got = ssh_source.run_remote("gpu-box", {"auto": True}, ssh=fake)
    ssh_source.apply("gpu-box", got)
    runs = {r.name: r for r in scan.scan(ssh_source.mirror_dir("gpu-box"))}
    assert "20260901_120000" in runs and runs["20260901_120000"].total == 12


def test_wandb_and_openmmlab_runs_get_names_you_can_tell_apart():
    """★목록에 'offline-run-20260930_145135-h32dkwxl'·'20260901_120000'만 보여 어느 학습인지 몰랐다"""
    from types import SimpleNamespace as N
    from epokio.scan_names import display_name
    name = lambda p: display_name(N(name=Path(p).name, path=p))
    assert name("/r/vit/wandb/offline-run-20260930_145135-h32dkwxl") == "vit/h32dkwxl"
    assert name("/w/work_dirs/rtmdet_tiny/20260901_120000") == "rtmdet_tiny/20260901_120000"
    assert name("/x/defect_det/train") == "defect_det/train" and name("/x/myexp") == "myexp"


def test_lineage_and_stage_are_only_for_runs_with_best_pt(tmp_path, monkeypatch):
    """계보·모델 단계는 best.pt 기준이다. 다른 형식에 'Put in use'·'best.pt가 없다'를 띄우지 않는다"""
    from epokio.agent import Agent
    monkeypatch.setattr(Agent, "ROOTS_FILE", tmp_path / "roots.json")
    a = Agent.__new__(Agent)
    a.roots, a.label = [tmp_path], "t"
    d = mae(tmp_path / "deit", deit_rows(3))
    got = a.get("/run", {"path": [str(d)]})
    got = got[1] if isinstance(got, tuple) else got
    assert got["framework"] == "jsonlog" and "lineage" not in got and "stage" not in got


def test_mae_log_finds_the_planned_epochs_in_a_saved_config(tmp_path):
    """★log.txt에는 계획 에폭이 없어 진행률·남은 시간이 늘 비었다. 같은 폴더에 설정을 저장했으면 거기서"""
    d = mae(tmp_path / "mae", [{"train_loss": 0.9, "epoch": e} for e in range(3)])
    assert adapters.load(d).total is None
    (d / "config.yaml").write_text("model: mae_vit_base\nepochs: 800\n")
    assert adapters.load(d).total == 800


def test_a_custom_csv_finds_its_planned_epochs_and_can_finish(tmp_path):
    """★옆에 config.yaml(epochs: 3)을 둬도 3/? 로 남아 끝까지 가도 '끝남(✓)'이 안 됐다"""
    d = tmp_path / "myrun"
    d.mkdir()
    (d / "train_log.csv").write_text("epoch,train_loss,val_acc\n1,1.0,0.5\n2,0.8,0.6\n3,0.7,0.7\n")
    (d / "config.yaml").write_text("epochs: 3\n")
    r = scan.read_run(d)
    assert r.total == 3 and r.epoch == 3 and r.state == "done"
