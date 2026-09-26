"""학습 하나가 끝났을 때(완료·실패·멈춤) "왜 이 점수인지 + 다음에 뭘 바꿀지"를 2~4문장으로.

1단계는 오프라인 규칙만. 판단은 새로 하지 않고 analysis.analyze()의 해설과 analysis.next_run()의
제안을 골라 이어 붙인다. 판단 규칙을 고치려면 analysis.py를 고칠 것(여기 두 벌 두지 않는다).

2단계(선택, 기본 꺼짐): Jev로 다듬기. Jev는 글을 쓰지 않고 고르기만 한다(System One). 그래서 코드가 만든
후보 문장 중 "초보자에게 꼭 필요한 문장"을 noul로 골라 2~3문장으로 줄인다. 요청 본문은 jev_request()가
만들고(맥 앱이 키체인 키로 보낸다), 보낼 것은 jev_payload()와 후보 문장뿐이다. 경로·이미지·데이터·학습 이름 금지.
"""
from __future__ import annotations

from pathlib import Path

from . import analysis, msg

# 여러 해설이 겹치면 먼저 말할 것. 발산이 있으면 나머지 해설은 의미가 약하다
_PRIORITY = ["diverged", "nan_recovered", "overfit", "still_improving", "early_best", "loss_rise", "misses", "false_alarms"]
STATUSES = ("finished", "failed", "stalled")


def _main_score(a) -> tuple[str, float, int] | None:
    if not a.heads:                   # YOLO 밖(HF·Lightning·Keras): analysis가 고른 대표 점수
        return (a.score["metric"], a.score["value"], a.score["best_epoch"]) if a.score else None
    h = next((x for x in a.heads if x.head in ("M", "P")), a.heads[0])   # 공식 TASK2METRIC: segment=(M), pose=(P)
    if h.map5095 is not None:
        return "mAP50-95", h.map5095, h.best_epoch
    if h.map50 is not None:
        return "mAP50", h.map50, h.best_epoch
    return None


def explain(run_dir: Path, status: str = "finished", args: dict | None = None,
            weights: str | None = None, framework: str | None = None) -> dict:
    """run 폴더 하나 → {"text", "kind", "next", "status"}. text는 2~4문장.
    args·weights·framework를 안 주면 rundetail과 같은 방식으로 폴더에서 읽는다."""
    run_dir = Path(run_dir)
    status = status if status in STATUSES else "finished"
    a = analysis.analyze(run_dir)
    if a is None:
        return {"text": msg.tr("No epochs were recorded, so there is nothing to explain yet."),
                "kind": None, "next": None, "status": status}
    if args is None or framework is None:
        from . import adapters, rundetail
        got = adapters.load(run_dir)
        args = args if args is not None else (rundetail._args(run_dir) or (got.args if got else {}))
        framework = framework or (got.framework if got else "ultralytics")
    if weights is None:
        best = run_dir / "weights" / "best.pt"
        weights = str(best) if best.exists() else None

    parts: list[str] = []
    if status == "failed":
        parts.append(msg.tr("Training failed after {n} epochs.", n=a.epochs))
    elif status == "stalled":
        parts.append(msg.tr("Training seems to have stopped after {n} epochs.", n=a.epochs))
    sc = _main_score(a)
    if sc:
        parts.append(msg.tr("Best {metric} was {v:.3f} at epoch {e} of {n}.", metric=sc[0], v=sc[1], e=sc[2], n=a.epochs))

    order = sorted(range(len(a.notes)),
                   key=lambda i: _PRIORITY.index(a.kinds[i].get("kind")) if a.kinds[i].get("kind") in _PRIORITY else 99)
    kind = nxt = safe_next = None
    if order:
        i = order[0]
        obs, todo = a.notes[i]
        kind = a.kinds[i].get("kind")
        parts.append(obs)
        nxt = analysis.next_run(a.kinds[i], args or {}, weights) if framework == "ultralytics" else None
        if nxt:
            shown = ", ".join(f"{k}={Path(v).name if k == 'weights' else v}" for k, v in nxt.items())
            parts.append(msg.tr("Next run: try {changes}.", changes=shown))
            nums = _numeric(nxt)       # Jev 후보에선 경로(weights)가 빠진 숫자 설정만으로 다시 쓴다
            safe_next = (len(parts) - 1, msg.tr("Next run: try {changes}.", changes=", ".join(f"{k}={v}" for k, v in nums.items()))
                         if nums else todo)
        else:
            parts.append(todo)
    else:
        parts.append(msg.tr("No clear problem showed up in the curves."))
    safe = list(parts[:4])
    if safe_next and safe_next[0] < 4:
        safe[safe_next[0]] = safe_next[1]
    score = {"metric": sc[0], "value": sc[1], "best_epoch": sc[2], "epochs": a.epochs} if sc else None
    return {"text": " ".join(parts[:4]), "kind": kind, "next": nxt, "status": status, "score": score,
            "sentences": safe}


# ---- 2단계 훅: Jev로 다듬기 (기본 꺼짐, 스텁) ----

# 밖으로 나가도 되는 키. 이 목록 밖은 절대 넣지 않는다(경로·이미지·데이터·학습 이름 금지)
# 점수와 설정 값은 보낸다(사용자 결정 2026-09-22). 경로가 되는 값(weights)은 이름도 값도 안 보낸다
JEV_ALLOWED = ("status", "kind", "score", "settings", "lang")
_PATH_KEYS = {"weights", "model", "data", "project", "name", "source"}


def jev_payload(result: dict) -> dict:
    """explain() 결과 → Jev에 보낼 것. 무엇이 나가는지 화면에 그대로 보여 줄 수 있게 평범한 dict로."""
    nxt = result.get("next") or {}
    settings = {k: v for k, v in nxt.items()
                if k not in _PATH_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool)}
    return {
        "status": result.get("status"),
        "kind": result.get("kind"),
        "score": result.get("score"),              # 지표 이름·최고값·최고 에폭·전체 에폭
        "settings": settings,                      # 바꿀 설정의 이름과 숫자 값만
        "lang": msg._lang.get(),
    }


MAX_SENTENCES = 3        # "UI에 글 너무 많지 않게"(사용자 원칙). 다듬어도 3문장 이내
KEEP_P = 0.5


def _numeric(nxt: dict | None) -> dict:
    return {k: v for k, v in (nxt or {}).items()
            if k not in _PATH_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool)}


def jev_request(result: dict) -> dict | None:
    """POST https://api.typesafe.ai/v1/systemone 본문. 후보가 3개 이하로 줄일 게 없으면 None(보낼 필요 없음).
    문장마다 noul 하나: 병렬로 돌고 서로의 답을 못 본다. 문장 순서는 코드가 지킨다."""
    sents = result.get("sentences") or []
    if len(sents) <= 2:
        return None
    q = {f"s{i}": {"type": "noul",
                   "instructions": {"sentence": s,
                                    "question": "A beginner just finished a training run and sees `summary` about it. "
                                                "Is `sentence` needed to understand why the run scored as it did or what to change next?"},
                   "criteria": {"true": "Carries the result, the main cause, or the concrete next step",
                                "false": "Repeats another sentence or adds detail a beginner can skip"}}
         for i, s in enumerate(sents)}
    return {"model": "jev-latest", "state": {"summary": jev_payload(result), "sentences": sents}, "questions": q}


def jev_apply(result: dict, answers: dict | None) -> str:
    """Jev 답 → 2~3문장. 답이 없거나 모자라면 규칙 문장 그대로. 맥 앱(JevExplain.swift)이 같은 규칙을 쓴다."""
    sents = result.get("sentences") or []
    try:
        probs = [float(answers[f"s{i}"]["noul"]) for i in range(len(sents))]
    except (TypeError, KeyError, ValueError):
        return result["text"]
    keep = sorted(sorted(range(len(sents)), key=lambda i: -probs[i])[:MAX_SENTENCES])
    keep = [i for i in keep if probs[i] >= KEEP_P]
    if len(keep) < 2:
        return result["text"]
    return " ".join(sents[i] for i in keep)


def polish_with_jev(result: dict, enabled: bool = False, send=None) -> str:
    """켜져 있고 send(보내는 함수, 키는 그쪽이 가진다)가 있으면 다듬는다. 실패하면 규칙 문장.
    파이썬엔 키가 없다: 실제 호출은 맥 앱이 하고, 이 함수는 시험과 다른 호출부를 위한 같은 흐름이다."""
    if not enabled or send is None:
        return result["text"]
    body = jev_request(result)
    if body is None:
        return result["text"]
    try:
        return jev_apply(result, (send(body) or {}).get("answers"))
    except Exception:
        return result["text"]
