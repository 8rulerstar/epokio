#!/bin/bash
# 스냅샷 격리 점검. 모든 화면을 찍고, 실제 호스트명·사용자명·홈 경로가 남았는지 본다.
# 앱 안 audit(접근성 글자 + OCR)이 발동하면 PNG를 안 쓰고 2/3으로 끝난다. 여기서는 그 결과를 모아 본다.
#   ./snapshot_audit.sh [내놓을 폴더]
set -u
OUT="${1:-$TMPDIR/epokio-snapiso}"
APP="$(cd "$(dirname "$0")" && pwd)/.build/debug/Epokio"
[ -x "$APP" ] || { echo "먼저 swift build"; exit 1; }
mkdir -p "$OUT"; rm -f "$OUT"/*.png "$OUT"/*.log

SECTIONS="home runs runs-table train data review label queue inbox compare detail lineage menubar design onboarding palette shortcuts settings-appearance settings-notify settings-machines settings-customize settings-assistant"
FAIL=0; VACUOUS=0; OK=0; VAC=""

run() {  # run <이름> <인자…>
  local name="$1"; shift
  local log="$OUT/$name.log"
  "$APP" "$@" -AppleLanguages '(en)' >"$log" 2>&1
  local rc=$?
  if [ $rc -eq 143 ]; then "$APP" "$@" -AppleLanguages '(en)' >"$log" 2>&1; rc=$?; fi   # 가끔 밖에서 끊긴다, 한 번 더
  if grep -q "LEAK" "$log"; then
    echo "샘 $name: $(grep LEAK "$log" | head -1)"; rm -f "$OUT/$name.png"; FAIL=$((FAIL+1)); return
  fi
  if [ $rc -ne 0 ]; then
    echo "실패 $name (rc=$rc): $(tail -1 "$log")"; FAIL=$((FAIL+1)); return
  fi
  local line; line=$(grep "isolation audit" "$log" | head -1)
  if [ -z "$line" ]; then echo "점검 안 함 $name, 격리가 발동하지 않았다"; FAIL=$((FAIL+1)); return; fi
  # 글자를 하나도 못 읽었으면 점검이 헛돈 것이다
  local n; n=$(echo "$line" | sed -E 's/.*ok \(([0-9]+) accessibility \+ ([0-9]+) OCR.*/\1+\2/')
  # 글자를 하나도 못 읽은 화면. 아이콘만 있는 화면(menubar)은 정상, 나머지는 사람이 눈으로 볼 것
  if [ "$(( ${n%%+*} + ${n##*+} ))" -eq 0 ]; then VAC="$VAC $name"; VACUOUS=$((VACUOUS+1)); fi
  OK=$((OK+1))
}

# 0) 점검기 자체 시험: 진짜 호스트명을 일부러 넣은 그림을 잡아내나
"$APP" --snapshot-audit-selftest >"$OUT/_selftest.log" 2>&1
if grep -q "selftest ok" "$OUT/_selftest.log"; then echo "점검기 시험 통과"
else echo "점검기 시험 실패, 새는 것을 못 잡는다: $(cat "$OUT/_selftest.log")"; FAIL=$((FAIL+1)); fi

run popover --snapshot "$OUT/popover.png"
for s in $SECTIONS; do run "$s" --snapshot-window "$s" "$OUT/$s.png"; done

echo
[ $VACUOUS -eq 0 ] || echo "글자 없는 화면(눈으로 볼 것):$VAC"
echo "찍힘 $OK · 샘/실패 $FAIL · $OUT"
[ $FAIL -eq 0 ]
