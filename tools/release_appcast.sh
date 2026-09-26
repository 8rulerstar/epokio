#!/bin/bash
# 공개 배포 때 자동 업데이트 목록(appcast.xml)을 만든다. 공개 저장소 Releases에 dmg와 같이 올린다.
#
# 처음 한 번(사용자가 직접): 서명 키 만들기. 비밀키는 이 맥의 키체인에만 남고, 공개키가 화면에 나온다
#   mac/.build/artifacts/sparkle/Sparkle/bin/generate_keys
#   → 나온 공개키를 빌드 때 EPOKIO_SPARKLE_PUBKEY=... 로 넘긴다(Info.plist SUPublicEDKey). 키가 없으면 앱은 업데이트를 확인하지 않는다
#
# 배포 때: EPOKIO_SPARKLE_PUBKEY=... ./mac/build_app.sh --dmg --no-install → 이 스크립트
set -e
cd "$(dirname "$0")/.."
BIN=mac/.build/artifacts/sparkle/Sparkle/bin
DMG=$(ls -t mac/build.noindex/Epokio-*.dmg | head -1)
[ -n "$DMG" ] || { echo "no dmg: run ./mac/build_app.sh --dmg first"; exit 1; }
OUT=mac/build.noindex/appcast
rm -rf "$OUT" && mkdir -p "$OUT" && cp "$DMG" "$OUT/"
# 내려받을 주소: 공개 저장소의 그 버전 Releases
VER=$(basename "$DMG" .dmg | sed 's/^Epokio-//')
"$BIN/generate_appcast" --download-url-prefix "${EPOKIO_DOWNLOAD_PREFIX:-https://github.com/8rulerstar/epokio/releases/download/v$VER/}" "$OUT"
echo "appcast: $OUT/appcast.xml  (dmg와 같이 v$VER 릴리스에 올린다)"
