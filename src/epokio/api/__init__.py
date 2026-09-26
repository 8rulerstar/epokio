"""기능별 HTTP 요청 처리. agent.py는 여기로 나눠 줄 뿐이다.

모듈마다 get(agent, route, q) · post(agent, route, body)를 둔다. 자기 요청이 아니면 NOT_MINE을 돌려준다.
돌려주는 값은 agent.get/post와 같다: 사전(200) 또는 (코드, 사전).
★새 기능의 요청은 agent.py에 늘어놓지 말고 여기에 모듈을 하나 더 만든다.
"""
from __future__ import annotations

from pathlib import Path

NOT_MINE = object()


def result_file(j, kind: str) -> Path | None:
    """작업 결과 파일. 예전 이름(TrainBar) 시절 파일도 읽는다."""
    if not j or not j.output:
        return None
    for name in (f"epokio_{kind}.json", f"trainbar_{kind}.json"):
        if (Path(j.output) / name).exists():
            return Path(j.output) / name
    return None


from . import aiuse, hooks, jobs_post, models, predict, report, retrain, review, roots_api, ssh, sweep_table, sweeps, table  # noqa: E402  (NOT_MINE을 먼저 정의해야 한다)

API = (review, sweeps, sweep_table, models, table, ssh, retrain, report, aiuse, hooks, roots_api, predict, jobs_post)
