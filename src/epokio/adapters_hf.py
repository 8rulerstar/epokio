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
        warns = []
        hist = st.get("log_history")
        if not isinstance(hist, list):
            warns.append("unknown format/version: trainer_state.json has no log_history list")
            hist = []
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
        args = {k: str(st[k]) for k in ("num_train_epochs", "train_batch_size", "max_steps", "best_metric",
                                        "best_model_checkpoint") if st.get(k) is not None}
        # trainer_state 값이 실제로 돈 값이므로 먼저다. training_args.json은 빠진 것만 채운다
        args = {**hf_args.read(d, sp.parent), **args}
        return Loaded(self.name, rows, sp, total, args, warns, epoch=done)


def _float(v, fallback: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return float(fallback)
    return x if math.isfinite(x) and x > 0 else float(fallback)
