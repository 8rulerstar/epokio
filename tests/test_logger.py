"""epokio 기록기 두 갈래.
epokio.log()/params()/image(): 학습 코드 한 줄 기록 → 파일 → agent가 곡선·설정·그림으로 읽는다.
epokio.start(): 직접 짠 학습 코드의 기록기. 쓴 파일을 Epokio가 그대로 읽는지, 어떤 경우에도 학습을 죽이지 않는지."""
import importlib

import epokio
from epokio import adapters, analysis, logger, rundetail, scan as scan_mod
from epokio.scan import scan


def _fresh():
    import epokio.logger as lg
    return importlib.reload(lg)


def test_log_params_and_image_become_a_run(tmp_path):
    lg = _fresh()
    d = lg.init(tmp_path / "exp")
    lg.params(epochs=3, lr0=0.01, model="resnet18")
    for e in (1, 2, 3):
        lg.log(e, loss=1.0 / e, val_loss=1.2 / e, val_acc=0.5 + e / 10)
    png = tmp_path / "p.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    lg.image("predictions", png, 3)
    r = scan_mod.read_run(d)
    assert r.epoch == 3 and r.total == 3 and r.metric_name == "val_acc" and abs(r.best - 0.8) < 1e-9
    det = rundetail.detail(d)
    assert det["framework"] == "epokio" and det["args"]["lr0"] == "0.01"
    assert {"train/loss", "val/val_loss", "val_acc"} <= set(det["columns"])
    assert det["column_info"]["train/loss"]["kind"] == "loss" and det["column_info"]["val_acc"]["kind"] == "score"
    assert "epokio_media/predictions_e0003.png" in det["images"]


def test_log_adds_to_an_ultralytics_run(tmp_path):
    """results.csv가 있는 폴더에 쓰면 같은 에폭에 값이 붙는다"""
    d = tmp_path / "yolo"
    d.mkdir()
    (d / "results.csv").write_text("epoch,metrics/mAP50-95(B)\n1,0.3\n2,0.4\n")
    lg = _fresh()
    lg.init(d)
    lg.log(1, gpu_mem=3.2)
    lg.log(2, gpu_mem=3.4, my_f1=0.61)
    det = rundetail.detail(d)
    assert det["framework"] == "ultralytics" and det["columns"]["gpu_mem"] == [3.2, 3.4] and det["columns"]["my_f1"][1] == 0.61


def test_log_resumes_and_skips_non_numbers(tmp_path):
    lg = _fresh()
    lg.init(tmp_path / "r")
    lg.log(1, loss=0.9, note="hello")
    lg = _fresh()
    lg.init(tmp_path / "r")                             # 다시 켜도 이어 쓴다
    lg.log(2, loss=0.5)
    text = (tmp_path / "r" / "epokio_log.csv").read_text()
    assert text.splitlines() == ["epoch,loss", "1,0.9", "2,0.5"]



class FakeTensor:                                   # torch 텐서처럼 .item()만 있다
    def __init__(self, v): self.v = v
    def item(self): return self.v
    def __repr__(self): return f"tensor({self.v}, device='cuda:0')"


def test_a_custom_loop_shows_up_with_scores_and_notes(tmp_path):
    """★점수를 metrics/mAP50 으로 적어서 P·R·F1·mAP 표와 해설이 비었다. ultralytics 모양 (B)로 적는다."""
    with epokio.start(tmp_path / "runs" / "detr-small", epochs=3, lr=1e-4, data="d.yaml") as run:
        for tl, vl, m in [(1.2, 1.3, 0.2), (0.9, 1.0, 0.35), (0.7, 0.9, 0.41)]:
            run.log(train_loss=FakeTensor(tl), val_loss=vl, precision=0.6, recall=0.5, mAP50=m, val_mae=1.0 - m)
    [r] = scan(tmp_path / "runs")
    assert r.name == "detr-small" and r.epoch == 3 and r.total == 3 and r.state == "done"
    assert r.framework == "custom"                                          # ★ultralytics로 보였다
    head = (tmp_path / "runs" / "detr-small" / "results.csv").read_text(encoding="utf-8")
    assert "train/total_loss" in head and "val/total_loss" in head and "metrics/val_mae" in head   # 오차 지표는 낮을수록 좋은 점수(val/val_mae_loss 였다)
    assert "tensor(" not in head                                           # ★텐서가 글자로 들어가 곡선이 비었다
    a = analysis.analyze(tmp_path / "runs" / "detr-small")
    assert a.heads and a.heads[0].precision == 0.6
    args = (tmp_path / "runs" / "detr-small" / "args.yaml").read_text(encoding="utf-8")
    assert "lr: 0.0001" in args and "data:" not in args                     # data를 적으면 YOLO '다시 학습'이 붙었다


def test_a_run_without_total_epochs_is_done_not_stalled(tmp_path, monkeypatch):
    """총 에폭을 모르는 학습이 끝나고 3분 뒤 '멎음' 알림(폰까지)을 받았다. 끝남 표시로 '완료'."""
    with epokio.start(tmp_path / "runs" / "loop") as run:
        run.log(val_loss=1.0); run.log(val_loss=0.8)
    import time
    [r] = scan(tmp_path / "runs", now=time.time() + 3600)
    assert r.state == "done"


def test_logging_never_kills_training_when_the_file_is_locked(tmp_path, monkeypatch, capsys):
    """윈도우에서 agent·엑셀이 results.csv를 읽는 중이면 바꿔치기가 PermissionError로 실패해 학습 루프가 죽었다."""
    run = logger.Logger(tmp_path / "runs" / "x", epochs=2)
    real = type(tmp_path).replace
    calls = {"n": 0}

    def flaky(self, target):
        calls["n"] += 1
        if calls["n"] <= 3:                        # 처음 몇 번은 잠겨 있다가 풀린다
            raise PermissionError(5, "Access is denied")
        return real(self, target)
    monkeypatch.setattr(type(tmp_path), "replace", flaky)
    monkeypatch.setattr(logger.time, "sleep", lambda s: None)
    run.log(val_loss=1.0)                                      # 다시 시도해서 성공
    assert (tmp_path / "runs" / "x" / "results.csv").exists()
    monkeypatch.setattr(type(tmp_path), "replace", lambda self, t: (_ for _ in ()).throw(PermissionError(5, "locked")))
    run.log(val_loss=0.9)                                      # 끝내 잠겨 있어도 예외를 던지지 않는다
    assert "could not write" in capsys.readouterr().err


def test_only_rank_zero_writes_in_distributed_training(tmp_path, monkeypatch):
    """여러 프로세스가 같은 파일을 덮어써 한쪽 값이 사라졌다."""
    monkeypatch.setenv("RANK", "1")
    run = epokio.start(tmp_path / "runs" / "ddp", epochs=2)
    run.log(val_loss=1.0)
    assert not (tmp_path / "runs" / "ddp").exists()


def _run_script(tmp_path, body):
    import subprocess, sys, textwrap
    script = tmp_path / "train.py"
    script.write_text("import epokio\n" + textwrap.dedent(body), encoding="utf-8")
    return subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=60, cwd=tmp_path)


def test_a_crashed_script_is_not_marked_done(tmp_path):
    """atexit은 예외로 죽어도 불린다. ★with 없이 쓰다 죽은 학습이 '완료'로 표시되고 '끝남' 알림이 갔다."""
    r = _run_script(tmp_path, """
        run = epokio.start("runs/crash", epochs=10)
        run.log(val_loss=1.0); run.log(val_loss=0.9)
        raise RuntimeError("CUDA out of memory")
    """)
    assert r.returncode != 0
    assert (tmp_path / "runs" / "crash" / "results.csv").exists()
    assert not (tmp_path / "runs" / "crash" / logger.DONE_MARK).exists()


def test_a_script_that_ends_normally_is_marked_done(tmp_path):
    r = _run_script(tmp_path, """
        run = epokio.start("runs/ok")
        run.log(val_loss=1.0)
    """)
    assert r.returncode == 0 and (tmp_path / "runs" / "ok" / logger.DONE_MARK).exists()


def test_rerunning_a_notebook_cell_does_not_let_the_old_logger_overwrite(tmp_path):
    """노트북에서 셀을 다시 돌리면 옛 기록기가 끝날 때 새 학습의 CSV를 덮었다."""
    old = epokio.start(tmp_path / "runs" / "nb")
    old.log(val_loss=9.0); old.log(val_loss=9.0); old.log(val_loss=9.0)
    new = epokio.start(tmp_path / "runs" / "nb")
    new.log(val_loss=1.0)
    old.log(val_loss=9.0)                        # 옛 기록기가 또 써도 무시
    old.finish()
    rows = (tmp_path / "runs" / "nb" / "results.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2 and rows[1].split(",")[-1] == "1.0"
    assert (tmp_path / "runs" / "nb" / "results.prev.csv").exists()    # 옛 기록은 지우지 않고 옆으로


def test_learning_rate_and_prefixed_names(tmp_path):
    """lr이 '대표 점수'로 뽑혔고, valid_loss·val_mae는 접두어가 겹쳤다."""
    c = logger.Logger._column
    assert c("lr") == "lr/pg0" and c("learning_rate") == "lr/pg0"
    assert c("valid_loss") == "val/total_loss" and c("eval_loss") == "val/total_loss" and c("train_loss") == "train/total_loss"
    assert c("val_mae") == "metrics/val_mae" and c("val_acc") == "metrics/val_acc"
    with epokio.start(tmp_path / "runs" / "lr", epochs=2) as run:
        run.log(lr=0.01, val_acc=0.5); run.log(lr=0.001, val_acc=0.7)
    [r] = scan(tmp_path / "runs")
    assert r.metric_name == "metrics/val_acc" and r.best == 0.7


def test_one_error_at_the_prompt_does_not_block_later_runs(tmp_path):
    """모듈 전체 깃발이라, 대화형 파이썬에서 오류 한 번 뒤 그 뒤의 모든 학습이 '완료'를 못 받았다."""
    import sys
    a = epokio.start(tmp_path / "runs" / "a")
    a.log(val_loss=1.0)
    try:
        raise RuntimeError("typo at the prompt")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())          # 대화형 파이썬이 잡히지 않은 오류를 알리는 길
    with epokio.start(tmp_path / "runs" / "b") as b:
        b.log(val_loss=1.0)
    assert (tmp_path / "runs" / "b" / logger.DONE_MARK).exists()
    a._at_exit()
    assert not (tmp_path / "runs" / "a" / logger.DONE_MARK).exists()   # 오류 때 쓰던 것은 '완료'가 아니다


def test_a_crash_in_another_thread_is_not_marked_done(tmp_path):
    r = _run_script(tmp_path, """
        import threading
        run = epokio.start("runs/thread", epochs=10)
        run.log(val_loss=1.0)
        def work():
            raise RuntimeError("dataloader died")
        t = threading.Thread(target=work); t.start(); t.join()
    """)
    assert not (tmp_path / "runs" / "thread" / logger.DONE_MARK).exists()


def test_restarting_three_times_keeps_every_earlier_history(tmp_path):
    """results.prev.csv 하나에 덮어써서 세 번째 실행이 첫 실행의 기록을 지웠다."""
    for loss in (3.0, 2.0, 1.0):
        with epokio.start(tmp_path / "runs" / "same") as run:
            run.log(val_loss=loss)
    names = sorted(p.name for p in (tmp_path / "runs" / "same").glob("results*.csv"))
    assert names == ["results.csv", "results.prev-2.csv", "results.prev.csv"]


def test_a_locked_ultralytics_folder_is_left_alone(tmp_path, monkeypatch):
    """results.csv가 잠겨 있으면 치우지 못했는데도 계속 써서, 진짜 ultralytics 학습의 args.yaml·results.csv를 덮었다."""
    d = tmp_path / "runs" / "yolo"
    d.mkdir(parents=True)
    (d / "args.yaml").write_text("epochs: 50\nmodel: yolo11n.pt\n")
    (d / "results.csv").write_text("epoch,time\n1,1\n")
    real = type(d).replace
    monkeypatch.setattr(type(d), "replace", lambda self, t: (_ for _ in ()).throw(PermissionError(5, "locked"))
                        if self.name == "results.csv" else real(self, t))
    run = logger.Logger(d)
    run.log(val_loss=1.0); run.finish()
    assert (d / "args.yaml").read_text() == "epochs: 50\nmodel: yolo11n.pt\n"
    assert (d / "results.csv").read_text() == "epoch,time\n1,1\n"


def test_a_crash_inside_with_is_failed_at_once_with_the_reason(tmp_path):
    """★with epokio.start() 안에서 죽으면 3분 뒤 '멎음'으로만 보였고 왜 죽었는지 몰랐다"""
    from epokio import notify
    from epokio.monitor import Event
    from epokio.scan import read_run
    d = tmp_path / "runs" / "oom"
    try:
        with epokio.start(d, epochs=10) as run:
            run.log(val_loss=1.0)
            run.log(val_loss=0.9)
            raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB\nmore detail")
    except RuntimeError:
        pass
    r = read_run(d)
    assert r.state == "failed" and r.error == "RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB"
    assert "CUDA out of memory" in notify.body_of(Event("failed", r, "running"))
    with epokio.start(d, epochs=10) as run:              # 같은 폴더로 다시 돌려 잘 끝나면 실패 표시는 사라진다
        run.log(val_loss=0.5)
    assert read_run(d).state == "done" and not (d / logger.FAIL_MARK).exists()


def test_ctrl_c_is_not_a_failure(tmp_path):
    d = tmp_path / "runs" / "stop"
    try:
        with epokio.start(d, epochs=10) as run:
            run.log(val_loss=1.0)
            raise KeyboardInterrupt
    except KeyboardInterrupt:
        pass
    assert not (d / logger.FAIL_MARK).exists()


def test_an_uncaught_crash_in_a_script_leaves_the_reason(tmp_path):
    r = _run_script(tmp_path, """
        run = epokio.start("runs/crash2", epochs=10)
        run.log(val_loss=1.0); run.log(val_loss=0.9)
        raise ValueError("bad batch")
    """)
    assert r.returncode != 0
    assert (tmp_path / "runs" / "crash2" / logger.FAIL_MARK).read_text(encoding="utf-8") == "ValueError: bad batch"
