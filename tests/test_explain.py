"""학습 해설 문단: 과적합·정체·NaN·좋음이 제대로 갈리는지, Jev로 나갈 것에 경로가 없고 점수는 있는지."""
import shutil
from pathlib import Path

from epokio import analysis, explain, msg

FIX = Path(__file__).parent / "fixtures" / "formats" / "ultralytics84_detect"


def _run(tmp: Path, rows=None) -> Path:
    """기존 fixture를 복사하고, rows를 주면 같은 열 모양으로 results.csv를 갈아 끼운다."""
    d = tmp / "exp"
    shutil.copytree(FIX, d)
    if rows is not None:
        head = (FIX / "results.csv").read_text().splitlines()[0]
        body = [",".join(str(x) for x in (e, 30 * e, *r)) for e, r in enumerate(rows, 1)]
        (d / "results.csv").write_text("\n".join([head, *body]) + "\n")
    return d


def _row(tl, m, vl, lr=0.001):
    return [tl] * 3 + [m] * 4 + [vl] * 3 + [lr] * 3


def test_good_run_still_improving(tmp_path):
    r = explain.explain(_run(tmp_path))
    assert r["kind"] == "still_improving"
    assert "0.700" in r["text"] and "epoch 6 of 6" in r["text"]


def test_overfit(tmp_path):
    """과적합은 대표 점수(mAP50-95) 하락으로 판정한다. 검증 손실 상승은 참고 문장"""
    m = [0.2, 0.3, 0.4, 0.5, 0.55, 0.5, 0.45, 0.4, 0.38, 0.35]
    rows = [_row(1.5 - 0.1 * i, m[i], [1.5, 1.3, 1.1, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6][i]) for i in range(10)]
    r = explain.explain(_run(tmp_path, rows))
    assert r["kind"] == "overfit" and "peaked at epoch 5" in r["text"] and "Validation loss also rose" in r["text"]
    assert r["next"] == {"epochs": 10} and "epochs=10" in r["text"]


def test_loss_rise_while_score_climbs_is_not_overfit(tmp_path):
    """YOLO는 mAP가 오르는 중에도 검증 손실이 오를 수 있다. 이때 에폭 줄이기를 권하면 안 된다"""
    rows = [_row(1.5 - 0.1 * i, 0.2 + 0.03 * i if i < 9 else 0.4, [1.5, 1.3, 1.1, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6][i])
            for i in range(10)]
    d = _run(tmp_path, rows)
    r = explain.explain(d)
    assert r["kind"] == "still_improving"                     # 점수가 오르는 중이 먼저, 에폭 줄이기 제안 없음
    kinds = [k["kind"] for k in analysis.analyze(d).kinds]
    assert "overfit" not in kinds and "loss_rise" in kinds


def test_plateau_score_with_loss_rise_is_not_overfit(tmp_path):
    rows = [_row(1.5 - 0.1 * i, min(0.2 + 0.05 * i, 0.5), [1.5, 1.3, 1.1, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6][i]) for i in range(10)]
    r = explain.explain(_run(tmp_path, rows))
    assert r["kind"] == "loss_rise" and r["next"] is None


def test_plateau_early_best(tmp_path):
    rows = [_row(1.0, 0.6 if i == 1 else 0.4, 1.0) for i in range(12)]
    r = explain.explain(_run(tmp_path, rows))
    assert r["kind"] == "early_best" and "lr0=" in r["text"]


def test_nan_diverged_wins_and_failed_status(tmp_path):
    rows = [_row(1.0 - 0.1 * i, 0.3 + 0.05 * i, 1.0) for i in range(5)] + [_row("nan", 0.1, "nan")]
    r = explain.explain(_run(tmp_path, rows), status="failed")
    assert r["kind"] == "diverged"
    assert r["text"].startswith("Training failed after 6 epochs.")
    assert "first became NaN at epoch 6" in r["text"]
    assert r["text"].endswith("Next run: try lr0=0.001.")


def test_nan_mid_run_then_recovered(tmp_path):
    """마지막 행만 보면 놓치던 중간 발산"""
    rows = [_row(1.0 - 0.05 * i, 0.3 + 0.02 * i, 1.0) for i in range(3)] + [_row("nan", 0.1, "nan")] + \
        [_row(0.8 - 0.05 * i, 0.3 + 0.02 * i, 1.0) for i in range(3)]
    r = explain.explain(_run(tmp_path, rows))
    assert r["kind"] == "nan_recovered" and "NaN at epoch 4 but recovered" in r["text"]


def test_korean(tmp_path):
    tok = msg._lang.set("ko")
    try:
        r = explain.explain(_run(tmp_path), status="stalled")
        assert r["text"].startswith("학습이 6에폭에서 멈춘 것 같습니다.")
    finally:
        msg._lang.reset(tok)


def test_empty_run(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    assert explain.explain(d)["kind"] is None


def test_jev_payload_sends_scores_but_no_paths(tmp_path):
    d = _run(tmp_path)
    (d / "weights").mkdir(exist_ok=True)
    (d / "weights" / "best.pt").write_bytes(b"x")
    r = explain.explain(d)
    p = explain.jev_payload(r)
    assert set(p) <= set(explain.JEV_ALLOWED)
    assert str(tmp_path) not in repr(p) and "best.pt" not in repr(p)
    assert p["score"] and p["score"]["value"] == r["score"]["value"]
    assert explain.polish_with_jev(r) == r["text"]       # 기본 꺼짐


def test_jev_request_has_no_paths_and_numeric_next(tmp_path):
    rows = [_row(1.0 - 0.1 * i, 0.3 + 0.05 * i, 1.0) for i in range(5)] + [_row("nan", 0.1, "nan")]
    r = explain.explain(_run(tmp_path, rows), status="failed")
    body = explain.jev_request(r)
    assert body["model"] == "jev-latest" and len(body["questions"]) == len(r["sentences"]) == 4
    flat = str(body)
    assert "best.pt" not in flat and str(tmp_path) not in flat and "weights" not in flat
    assert all(q["type"] == "noul" for q in body["questions"].values())


def test_jev_apply_keeps_order_and_limit(tmp_path):
    r = {"text": "rule", "sentences": ["a.", "b.", "c.", "d."]}
    ans = {"s0": {"noul": 0.9}, "s1": {"noul": 0.2}, "s2": {"noul": 0.8}, "s3": {"noul": 0.7}}
    assert explain.jev_apply(r, ans) == "a. c. d."
    ans["s3"]["noul"] = 0.95; ans["s1"]["noul"] = 0.96
    assert explain.jev_apply(r, ans).count(".") == 3


def test_jev_falls_back_to_rules(tmp_path):
    r = {"text": "rule", "sentences": ["a.", "b.", "c."]}
    assert explain.jev_apply(r, None) == "rule"
    assert explain.jev_apply(r, {"s0": {"noul": 0.9}, "s1": {"noul": 0.1}, "s2": {"noul": 0.1}}) == "rule"
    assert explain.polish_with_jev(r, enabled=False, send=lambda b: 1 / 0) == "rule"

    def boom(body):
        raise OSError("offline")
    assert explain.polish_with_jev(r, enabled=True, send=boom) == "rule"
    seen = []
    ok = explain.polish_with_jev(r, enabled=True, send=lambda b: seen.append(b) or
                                 {"answers": {"s0": {"noul": 0.9}, "s1": {"noul": 0.2}, "s2": {"noul": 0.8}}})
    assert ok == "a. c." and seen and set(seen[0]["state"]) == {"summary", "sentences"}
    assert explain.jev_request({"text": "x", "sentences": ["a.", "b."]}) is None


def _tail_run(tmp, scores, args):
    d = _run(tmp, [_row(1.0, m, 1.0) for m in scores])
    (d / "args.yaml").write_text(args)
    return [k["kind"] for k in analysis.analyze(d).kinds]


FLAT_THEN_TAIL = [0.5] * 10 + [0.5 + 0.01 * i for i in range(1, 11)]      # 모자이크 끈 뒤에만 오름
RISING = [0.3 + 0.015 * i for i in range(20)]                              # 처음부터 끝까지 오름


def test_close_mosaic_tail_alone_is_not_still_improving(tmp_path):
    """Ultralytics는 마지막 close_mosaic 에폭에 모자이크를 끄고 학습률도 lrf까지 줄여 끝이 최고가 되기 쉽다.
    그 구간 효과만으로 끝이 최고면 '더 학습하라'고 하지 않는다"""
    assert "still_improving" not in _tail_run(tmp_path, FLAT_THEN_TAIL, "task: detect\nepochs: 20\nclose_mosaic: 10\n")


def test_close_mosaic_default_is_used_when_missing(tmp_path):
    assert "still_improving" not in _tail_run(tmp_path, FLAT_THEN_TAIL, "task: detect\nepochs: 20\n")


def test_rising_before_close_mosaic_is_still_improving(tmp_path):
    d = _run(tmp_path, [_row(1.0, m, 1.0) for m in RISING])
    (d / "args.yaml").write_text("task: detect\nepochs: 20\nclose_mosaic: 10\n")
    a = analysis.analyze(d)
    i = [k["kind"] for k in a.kinds].index("still_improving")
    assert "final 10 epochs" in a.notes[i][0]


def test_lr_decay_tail_without_mosaic(tmp_path):
    """close_mosaic=0이어도 학습률이 lrf까지 줄어드는 끝난 학습이면 마지막 10%의 상승만으로는 제안하지 않는다"""
    scores = [0.5] * 18 + [0.52, 0.55]
    assert "still_improving" not in _tail_run(tmp_path / "a", scores, "task: detect\nepochs: 20\nclose_mosaic: 0\nlrf: 0.01\n")
    assert "still_improving" in _tail_run(tmp_path / "b", scores, "task: detect\nepochs: 20\nclose_mosaic: 0\nlrf: 1.0\n")


def test_pr_gap_advice_names_f1_threshold(tmp_path):
    """results.csv의 P/R은 사용자가 고른 문턱이 아니라 F1 최대 지점 값이다. 문구가 그걸 밝힌다"""
    d = _run(tmp_path)
    head = (d / "results.csv").read_text().splitlines()[0].split(",")
    rows = [dict(zip(head, ln.split(","))) for ln in (d / "results.csv").read_text().splitlines()[1:]]
    for r in rows:
        r["metrics/precision(B)"], r["metrics/recall(B)"] = "0.9", "0.5"
    (d / "results.csv").write_text("\n".join([",".join(head)] + [",".join(r[h] for h in head) for r in rows]) + "\n")
    a = analysis.analyze(d)
    tip = a.notes[[k["kind"] for k in a.kinds].index("misses")][1]
    assert "best F1" in tip and "review screen" in tip
