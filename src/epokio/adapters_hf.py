"""Hugging Face transformers Trainer(trainer_state.json) 어댑터."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from . import hf_args
from .adapters_base import Adapter, Loaded, _num


class HuggingFace(Adapter):
    """transformers Trainer의 trainer_state.json (출력 폴더, 또는 가장 최근 checkpoint-N 안).
    log_history에서 eval_* 기록이 나온 지점마다 한 줄(에폭은 평가 시점 그대로, 0.25·0.5…).
    근거(transformers 4.49·5.17 trainer.py): 학습 {loss, grad_norm, learning_rate}(4.x만 loss 반올림), 평가 {eval_loss,
    eval_<지표>, eval_runtime·*_per_second, 4.x는 *_time, eval_mem_*}, 평가 데이터가 여럿이면 같은 step에 eval_<이름>_ 기록이
    여러 개, 끝에 train_runtime·total_flos·train_loss 요약. epoch·step은 log()가 붙인다.
    ★예전엔 같은 에폭 평가를 갈아 끼워 둘째 평가 데이터가 eval_loss를 지웠고 속도값·eval_<이름>_loss가 점수로 들어갔다.

    하이퍼파라미터: trainer_state.json에는 5개뿐이라 비교표가 비어 보였다 → 같은 폴더(또는 체크포인트)의
    training_args.json도 읽는다. 형식·버전 차이(4.49 vs 5.17)·왜 없는 게 정상인지는 hf_args.py 머리말."""
    name = "huggingface"
    SPEED = re.compile(r"(_runtime|_per_second|_time|_flos)$|_mem_")
    # 점수가 아닌 것(시간·처리량·토큰 수). ★eval_model_preparation_time이 '대표 점수'로 뽑혔다
    NOT_SCORE = re.compile(r"(_time|_runtime|_per_second|samples|num_tokens|^lr$|learning_rate)", re.IGNORECASE)
    KNOWN = {"loss", "grad_norm", "learning_rate", "epoch", "step", "num_input_tokens_seen", "train_loss", "total_flos"}

    def _state(self, d: Path) -> Path | None:
        if (d / "trainer_state.json").exists():
            return d / "trainer_state.json"
        cks = sorted(d.glob("checkpoint-*/trainer_state.json"), key=lambda p: int(re.sub(r"\D", "", p.parent.name) or 0))
        return cks[-1] if cks else None

    def detect(self, d, names):
        return "trainer_state.json" in names or any(n.startswith("checkpoint-") for n in names if (d / n).is_dir()) \
            and self._state(d) is not None

    @classmethod
    def _eval_col(cls, k: str) -> str | None:
        rest = k[5:]                                      # eval_ 뒤
        if cls.SPEED.search(k) or rest in ("epoch", "step") or cls.NOT_SCORE.search(rest):
            return None
        if rest == "loss" or rest.endswith("_loss"):
            return f"val/eval_{rest}" if rest != "loss" else "val/eval_loss"
        # 오차류(rmse 등)도 metrics/에 둔다. 방향은 schema.higher_is_better가 정한다(맥: 대표 점수 방향 기능).
        # Keras·Lightning은 dev 규칙(metric_column: 낮을수록 좋은 것은 _loss 열)을 그대로 쓴다
        return f"metrics/{rest}"

    def load(self, d):
        sp = self._state(d)
        if not sp:
            return None
        try:
            st = json.loads(sp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(st, dict):          # ★배열 등 다른 JSON이면 .get에서 죽었다
            return None
        warns = []
        hist = st.get("log_history")
        if not isinstance(hist, list):
            warns.append("unknown format/version: trainer_state.json has no log_history list")
            hist = []
        ta = hf_args.read(d, sp.parent)
        if self._step_mode(st, ta):
            return self._load_steps(st, hist, sp, ta, warns)
        rows, last_train, unknown = [], None, set()
        for h in hist:
            if not isinstance(h, dict):
                continue
            if isinstance(h.get("loss"), (int, float)):
                last_train = h["loss"]
            ev = {k: v for k, v in h.items() if k.startswith("eval_")}
            unknown |= {k for k in h if k not in self.KNOWN and not k.startswith(("eval_", "train_"))}
            if not ev:
                continue
            # 평가 시점의 에폭 그대로. ★올림(ceil)해서 첫 평가(0.1)에 1/1 '끝남'과 알림이 갔고,
            #   한 에폭에 평가가 여러 번이면 마지막 것만 남아 곡선이 한 점이었다
            ep = f"{round(_float(h.get('epoch'), len(rows) + 1), 3):g}"
            if rows and rows[-1]["epoch"] == ep:
                row = rows[-1]                           # 같은 시점: 여러 평가 데이터를 합친다(나중 값이 이긴다)
            else:
                row = {"epoch": ep}
                rows.append(row)
            if last_train is not None:
                row["train/train_loss"] = _num(last_train)
            for k, v in ev.items():
                col = self._eval_col(k)
                if col and isinstance(v, (int, float)) and not isinstance(v, bool):
                    row[col] = _num(v)
        if not rows and last_train is not None:      # 평가 없이 학습만: 손실만 보인다
            rows = [{"epoch": f"{round(_float(st.get('epoch'), 1), 3):g}", "train/train_loss": _num(last_train)}]
        if unknown:
            warns.append("unknown format/version: unrecognized log_history keys " + ", ".join(sorted(unknown)))
        total = int(st["num_train_epochs"]) if st.get("num_train_epochs") else None
        # 끝낸 에폭: 내림(hf_args.done_epochs). 정해진 걸음(max_steps)을 다 갔으면 끝난 것
        done = hf_args.done_epochs(_float(st.get("epoch"), 0) + 1e-6, 0)   # 1e-6: 2.9999999 같은 부동소수 오차
        if total and st.get("max_steps") and (st.get("global_step") or 0) >= st["max_steps"]:
            done = max(done, total)
        args = {k: hf_args._str(st[k]) for k in ("num_train_epochs", "train_batch_size", "max_steps", "best_metric",
                                                 "best_model_checkpoint", "metric_for_best_model", "greater_is_better")
                if st.get(k) is not None}
        # trainer_state 값이 실제로 돈 값이므로 먼저다. training_args.json은 빠진 것만 채운다
        args = {**ta, **args}
        _best_metric_row(st, hist, rows, args)
        _loss_score(rows)
        return Loaded(self.name, rows, sp, total, args, warns, epoch=done)

    @staticmethod
    def _step_mode(st: dict, ta: dict) -> bool:
        """max_steps로 정한 학습인가. training_args의 max_steps가 양수거나, 기록에 계획 에폭이 1 이하인데 max_steps가 있으면.
        ★num_train_epochs는 max_steps 학습에서 대개 1이라 '0/1 에폭'으로 진행률·남은 시간이 없었다"""
        ms = st.get("max_steps")
        if not isinstance(ms, int) or isinstance(ms, bool) or ms <= 0:
            return False
        try:
            if int(float(ta.get("max_steps", -1))) > 0:
                return True
        except (TypeError, ValueError):
            pass
        ne = st.get("num_train_epochs")
        return isinstance(ne, (int, float)) and not isinstance(ne, bool) and ne <= 1

    def _load_steps(self, st: dict, hist: list, sp: Path, ta: dict, warns: list) -> Loaded:
        """step 축(x_axis=step): 기록된 step마다 한 줄(학습 손실 줄도, 평가 줄도). 진행은 global_step / max_steps.
        ★평가 시점마다 한 줄만 두어 10 step마다 적힌 손실 곡선이 평가 횟수만큼의 점으로 줄었다"""
        rows, by, unknown = [], {}, set()
        for h in hist:
            if not isinstance(h, dict):
                continue
            step = h.get("step")
            if not isinstance(step, int) or isinstance(step, bool):
                continue
            unknown |= {k for k in h if k not in self.KNOWN and not k.startswith(("eval_", "train_"))}
            row = by.get(step)
            if row is None:
                row = by[step] = {"epoch": str(step)}
                rows.append(row)
            if isinstance(h.get("loss"), (int, float)) and not isinstance(h.get("loss"), bool):
                row["train/train_loss"] = _num(h["loss"])
            for k, v in h.items():
                col = self._eval_col(k) if k.startswith("eval_") else None
                if col and isinstance(v, (int, float)) and not isinstance(v, bool):
                    row[col] = _num(v)
        rows.sort(key=lambda r: int(r["epoch"]))
        if unknown:
            warns.append("unknown format/version: unrecognized log_history keys " + ", ".join(sorted(unknown)))
        args = {k: hf_args._str(st[k]) for k in ("num_train_epochs", "train_batch_size", "max_steps", "best_metric",
                                                 "best_model_checkpoint", "metric_for_best_model", "greater_is_better")
                if st.get(k) is not None}
        args = {**ta, **args, "x_axis": "step"}
        _best_metric_row(st, hist, rows, args, by_step=True)
        _loss_score(rows)
        gs = st.get("global_step")
        done = gs if isinstance(gs, int) and not isinstance(gs, bool) else (int(rows[-1]["epoch"]) if rows else 0)
        return Loaded(self.name, rows, sp, st["max_steps"], args, warns, epoch=min(done, st["max_steps"]))


def _best_metric_row(st: dict, hist: list, rows: list[dict], args: dict, by_step: bool = False) -> None:
    """기록에 점수가 하나도 없는데 best_metric(+ metric_for_best_model)이 있으면 그 값을 점수 열로 넣는다.
    넣는 줄은 가장 좋은 체크포인트의 평가 시점(best_global_step, 없으면 checkpoint-N의 N), 못 찾으면 마지막 줄.
    방향은 greater_is_better가 있으면 그것(schema.lower_for), 없으면 열 이름으로.
    ★best_metric을 버려 점수 없이 손실만 보였다.
    손실이면(metric_for_best_model이 loss·eval_loss이거나 비어 있음, HF 기본값이 loss) val/eval_loss 칸에 넣는다.
    그 줄에 이미 기록된 eval_loss가 있으면 기록이 이긴다. 점수로 바꾸는 것은 _loss_score"""
    name = str(args.get("metric_for_best_model") or "loss").removeprefix("eval_")
    bm = st.get("best_metric")
    if (not rows or isinstance(bm, bool) or not isinstance(bm, (int, float)) or not math.isfinite(bm)
            or any(k.startswith("metrics/") for r in rows for k in r)):
        return
    loss = name == "loss" or name.endswith("_loss")
    step = st.get("best_global_step")
    if not isinstance(step, int):
        m = re.search(r"checkpoint-(\d+)", str(st.get("best_model_checkpoint") or ""))
        step = int(m.group(1)) if m else None
    if by_step:
        eps = {str(step)}
    else:
        eps = {f"{round(_float(h.get('epoch'), 0), 3):g}" for h in hist if isinstance(h, dict) and h.get("step") == step}
    row = next((r for r in rows if r["epoch"] in eps), rows[-1])
    if not loss:
        row[f"metrics/{name}"] = _num(bm)
        return
    col = "val/eval_loss" if name == "loss" else f"val/eval_{name}"
    row.setdefault(col, _num(bm))


def _loss_score(rows: list[dict]) -> None:
    """다른 점수가 하나도 없으면 eval_loss를 낮을수록 좋은 점수(metrics/eval_loss)로 옮긴다.
    ★손실만 평가하는 HF 학습(언어 모델 미세 조정에 흔하다)은 최고 점수가 늘 '–'였다. 다른 점수가 있으면 손실은 손실로 둔다.
    ★베껴 두었더니 /run에 val/eval_loss와 metrics/eval_loss가 두 번 나왔다. 옮긴다"""
    if any(k.startswith("metrics/") for r in rows for k in r):
        return
    for r in rows:
        if r.get("val/eval_loss") not in (None, ""):
            r["metrics/eval_loss"] = r.pop("val/eval_loss")


def _float(v, fallback: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return float(fallback)
    return x if math.isfinite(x) and x > 0 else float(fallback)
