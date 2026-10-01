"""소스를 모아 갱신하고, 상태가 바뀐 순간을 사건(Event)으로 뽑는다.

알림은 '지금 상태'가 아니라 '바뀐 순간'에 울려야 한다.
  예) 도는 중 → 멎음 : 예기치 않게 멈췄을 수 있다
     도는 중 → 완료 : 끝났다
  그래서 이전 상태를 run마다 기억한다.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .scan import Run, sort_runs, unique
from .sources import Source

LIVE = ("running", "starting")


@dataclass
class Event:
    kind: str        # finished | failed | stalled | stopped_early | recovered | started
    run: Run
    before: str      # 바뀌기 전 상태


def classify(before: str | None, run: Run) -> str | None:
    """상태 변화 하나를 사건 종류로. 알릴 게 아니면 None."""
    now = run.state
    if before is None or before == now:
        return None
    if before in LIVE and now == "done":
        return "finished"
    if now == "failed":
        return "failed"                      # 손실이 NaN으로 발산
    if before in LIVE and now == "stalled":
        return "stalled"                     # 3분째 기록이 없다. 죽었을 수 있다
    if before in LIVE + ("stalled",) and now == "stopped":
        if run.total and run.epoch < run.total:
            return "stopped_early"           # 계획보다 일찍 끝남: 조기종료거나 비정상 종료
        if not run.total:
            # ★계획 에폭을 모르면 끝난 건지 죽은 건지 알 수 없다. 그런데 '학습이 끝났습니다'를 보내, 크래시한 학습도 끝났다고 했다.
            #   멎음 알림은 이미 갔다(stalled). 곧장 멈춤으로 왔으면(주기가 길 때) 멎음으로만 알린다
            return None if before == "stalled" else "stalled"
        return "finished"
    if before == "stalled" and now in LIVE:
        return "recovered"                   # 멎은 줄 알았는데 다시 돈다
    if before is not None and before not in LIVE and now in LIVE:
        return "started"
    return None


class Monitor:
    def __init__(self, sources: list[Source]):
        self.sources = sources
        self.runs: list[Run] = []
        self._last: dict[str, str] = {}      # run 키 → 마지막으로 본 상태
        self._primed = False                 # 첫 갱신은 기준만 잡고 알리지 않는다
        self._fired: deque[str] = deque(maxlen=400)

    def add(self, source: Source):
        """소스를 나중에 더한다. 거기 있던 학습은 조용히 기억만 한다.
        ★그냥 붙이면 옛 학습이 전부 '방금 새로 끝남'으로 알림이 떴다 (폴더 자동 탐색 때)."""
        self.sources.append(source)
        for r in source.fetch():
            self._last[self.key(r)] = r.state

    @staticmethod
    def key(r: Run) -> str:
        return f"{r.source}|{r.path}"

    def refresh(self) -> list[Event]:
        runs: list[Run] = []
        for s in self.sources:
            runs.extend(s.fetch())
        self.runs = sort_runs(unique(runs))

        events: list[Event] = []
        for r in self.runs:
            k = self.key(r)
            before = self._last.get(k)
            self._last[k] = r.state
            if not self._primed:
                continue                     # 앱을 켰을 때 옛날 일로 알림이 쏟아지지 않게
            if before is None:
                if r.state in LIVE:          # 켜 둔 사이 새로 시작된 학습
                    events.append(Event("started", r, "none"))
                elif r.state in ("done", "failed"):
                    # ★감시 주기보다 짧게 끝난 작업은 '도는 중'을 한 번도 못 본다. 그래도 알린다
                    events.append(Event("finished" if r.state == "done" else "failed", r, "none"))
                continue
            kind = classify(before, r)
            if kind:
                tag = f"{k}|{kind}|{r.epoch}"
                if tag not in self._fired:
                    self._fired.append(tag)
                    events.append(Event(kind, r, before))
        self._primed = True
        return events
