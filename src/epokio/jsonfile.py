"""작은 설정 파일(json)을 안전하게 읽고 쓴다. roots·removed_roots·webhooks·config가 쓴다.

★예전엔 그냥 write_text로 덮어써서, 쓰다 끊기면 반쯤 쓰인 파일이 남았고, 다음에 읽을 때 '빈 것'으로 보고
  그 위에 다시 써서 내용이 통째로 사라졌다(설정이 기본값으로, 웹후크가 전부 지워짐).
  - 쓰기: 임시 파일에 쓰고 바꿔치기(원자적). 윈도우에서 누가 읽는 중이면 잠깐 뒤 다시
  - 읽기: 없으면 기본값. 깨졌으면 지우지 않고 옆에 .broken-시각.json 으로 옮긴 뒤 알린다(BrokenFile)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


class BrokenFile(ValueError):
    """파일이 깨져 있어 옆으로 옮겼다. .saved_as 에 옮긴 곳"""
    def __init__(self, path: Path, saved_as: Path):
        super().__init__(f"{path.name} was damaged; kept as {saved_as.name}")
        self.saved_as = saved_as


def read(path: Path, default, *, move_broken: bool = True):
    if not path.exists():
        return default
    for i in range(6):
        try:
            text = path.read_text(encoding="utf-8")
            break
        except PermissionError:
            if i == 5:
                raise
            time.sleep(0.05 * (i + 1))
    try:
        return json.loads(text)
    except ValueError:
        if not move_broken:
            raise
        aside = path.with_name(f"{path.stem}.broken-{int(time.time())}{path.suffix}")
        path.replace(aside)
        raise BrokenFile(path, aside) from None


def private_dir(d: Path) -> None:
    """~/.epokio 같은 폴더를 나만 보게(POSIX). ★없을 때만 0700으로 만들어, 먼저 생긴 폴더(setup --label 등)는
    0755로 남았고 그 안의 webhooks.json(슬랙·텔레그램 비밀 주소)을 같은 서버의 다른 사용자가 읽을 수 있었다"""
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass


def write(path: Path, obj) -> None:
    private_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)      # 처음부터 나만 읽게
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=1))
    for i in range(6):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if i == 5:
                raise
            time.sleep(0.05 * (i + 1))
