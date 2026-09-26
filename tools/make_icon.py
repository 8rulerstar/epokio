#!/usr/bin/env python3
"""Epokio 앱 아이콘.

원본은 mac/Resources/Epokio.icon (Icon Composer 형식, macOS 26+ 리퀴드 글래스).
  배경: 세로 그라디언트 #2a2f5a → #0b0d1f
  층 2개: spark(끝점, 위) · curve(학습 곡선, 아래). 흰색, 유리 켬, 그림자 neutral
  다크 모드만 곡선 #22d3ee(아래) → #c084fc(위), 점 #c084fc
  ★네온 번짐·하이라이트는 그려 넣지 않는다. 시스템 유리 효과와 겹친다

앱에 들어가는 아이콘은 build_app.sh가 actool로 이 .icon에서 바로 굽는다(옛 macOS용 .icns 포함).
이 스크립트는 README·문서용 PNG만 만든다. 같은 .icon을 Xcode의 ictool로 렌더링한다.

사용: python3 tools/make_icon.py   → docs/images/icon.png
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "mac" / "Resources" / "Epokio.icon"
ICTOOL = Path("/Applications/Xcode.app/Contents/Applications/Icon Composer.app/Contents/Executables/ictool")


def render(out: Path, px: int) -> None:
    subprocess.run([str(ICTOOL), str(ICON), "--export-image", "--output-file", str(out), "--platform", "macOS",
                    "--rendition", "Default", "--width", str(px), "--height", str(px), "--scale", "1"],
                   check=True, capture_output=True)


def main():
    if not ICTOOL.exists():
        raise SystemExit("Xcode 26 이상의 Icon Composer(ictool)가 필요합니다.")
    with tempfile.TemporaryDirectory() as d:
        big = Path(d) / "icon.png"
        render(big, 512)
        shutil.copy(big, ROOT / "docs" / "images" / "icon.png")
    print("icon:", ROOT / "docs" / "images" / "icon.png")


if __name__ == "__main__":
    main()
