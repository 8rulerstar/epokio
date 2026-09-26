"""상태를 어디서 가져오는가. 지금은 이 기계의 폴더 하나(원격 기계는 앱이 그 agent에 직접 묻는다)."""
from __future__ import annotations

from pathlib import Path

from .scan import Run, scan


class Source:
    label: str

    def fetch(self) -> list[Run]:
        raise NotImplementedError


class LocalSource(Source):
    def __init__(self, root: Path, label: str | None = None):
        self.root = root
        self.label = label or "local"

    def fetch(self) -> list[Run]:
        try:
            runs = scan(self.root)
        except OSError:
            return []
        for r in runs:
            r.source = self.label
        return runs
