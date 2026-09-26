#!/bin/bash
# Epokio.app 만들기. swift build 결과를 앱 번들로 감싼다.
set -e
cd "$(dirname "$0")"
swift build -c release
# ★결과물은 build.noindex/ 에 둔다(build 는 그리로 가는 바로가기). 이름이 .noindex 로 끝나는 폴더는 Spotlight가
#   훑지 않아 Launchpad에 Epokio가 두 개 뜨지 않는다(2026-09-22 사용자 지적, 설치본 + 빌드본)
if [ -d build ] && [ ! -L build ]; then rm -rf build.noindex; mv build build.noindex; fi
mkdir -p build.noindex; [ -L build ] || ln -s build.noindex build
APP=build/Epokio.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" build
cp .build/release/Epokio "$APP/Contents/MacOS/Epokio"
# Sparkle(자동 업데이트) 틀. ditto로 바로가기(symlink)를 살려 복사한다
mkdir -p "$APP/Contents/Frameworks"
SPARKLE=$(find .build -path "*Release*/Sparkle.framework" -maxdepth 5 -type d | head -1)
[ -n "$SPARKLE" ] && ditto "$SPARKLE" "$APP/Contents/Frameworks/Sparkle.framework"
# 제3자 라이선스 고지(NOTICE 참조). 번들에 들어가는 것은 라이선스 원문도 같이 넣는다.
# 파이썬 원문은 tar가 Resources/python/lib/python3.12/LICENSE.txt 로 이미 풀어 놓는다
TPL="$APP/Contents/Resources/ThirdPartyLicenses"
mkdir -p "$TPL/Sparkle"
if [ -f ../NOTICE ]; then cp ../NOTICE "$TPL/NOTICE"; fi
SPARKLE_SRC=$(find .build/checkouts -maxdepth 2 -name LICENSE -path "*Sparkle*" | head -1)
if [ -n "$SPARKLE_SRC" ]; then cp "$SPARKLE_SRC" "$TPL/Sparkle/LICENSE"; fi
for v in bsdiff ed25519-sparkle; do
  f=$(find ".build/checkouts/Sparkle/Vendor/$v" -maxdepth 1 -iname "licen[sc]e*" 2>/dev/null | head -1)
  if [ -n "$f" ]; then cp "$f" "$TPL/Sparkle/$v-LICENSE.txt"; fi
done
# 아이콘: Icon Composer 원본(.icon)을 굽는다. macOS 26+는 Assets.car(리퀴드 글래스·다크·틴트),
# 그 전 macOS는 actool이 같이 만드는 Epokio.icns를 쓴다
xcrun actool Resources/Epokio.icon --compile "$APP/Contents/Resources" --platform macosx \
  --minimum-deployment-target 15.0 --app-icon Epokio --output-partial-info-plist build/icon-partial.plist >/dev/null
cp -R Resources/*.lproj "$APP/Contents/Resources/"     # 화면 번역. 키는 영어 원문
# App Intents(Siri·단축어·Spotlight): 시스템은 코드를 훑지 않고 Contents/Resources/Metadata.appintents 만 읽는다.
# Xcode가 빌드 단계로 돌리는 appintentsmetadataprocessor를 여기서 직접 돌린다(SwiftPM은 안 돌린다).
# 이게 없으면 Intents/ 가 컴파일돼도 단축어 앱에 동작이 하나도 안 뜬다.
TC=$(xcode-select -p)/Toolchains/XcodeDefault.xctoolchain
if [ -x "$TC/usr/bin/appintentsmetadataprocessor" ]; then
  find Sources/Epokio -name "*.swift" > build/appintents-sources.txt
  # 릴리스는 모듈 통째 최적화라 .swiftconstvalues 가 한 개다. 없으면 만들지 않는다(잘못된 빈 묶음보다 낫다)
  find .build -path "*Release*" -name "*.swiftconstvalues" > build/appintents-constvals.txt
  if [ -s build/appintents-constvals.txt ]; then
    rm -rf "$APP/Contents/Resources/Metadata.appintents"
    "$TC/usr/bin/appintentsmetadataprocessor" --output "$APP/Contents/Resources" \
      --toolchain-dir "$TC" --module-name Epokio --sdk-root "$(xcrun --sdk macosx --show-sdk-path)" \
      --xcode-version "$(xcodebuild -version | tail -1 | awk '{print $3}')" \
      --platform-family macOS --deployment-target 15.0 \
      --target-triple "$(uname -m)-apple-macos15.0" \
      --source-file-list build/appintents-sources.txt \
      --swift-const-vals-list build/appintents-constvals.txt --quiet-warnings >build/appintents.log 2>&1 || true
  fi
fi
if [ ! -f "$APP/Contents/Resources/Metadata.appintents/extract.actionsdata" ]; then
  echo "warning: App Intents metadata not built. Siri/Shortcuts will show no Epokio actions. See build/appintents.log" >&2
fi
# agent를 앱 안에 넣는다: pip 설치 없이 앱 하나로 끝나게. 표준 라이브러리만 쓰므로 파이썬만 있으면 된다
mkdir -p "$APP/Contents/Resources/agent"
rsync -a --exclude __pycache__ --exclude mcp_server.py ../src/epokio "$APP/Contents/Resources/agent/"
# 파이썬도 앱 안에(2026-09-22 사용자 결정): 파이썬이 없는 맥에서도 메뉴바가 뜬다. agent 전용(표준 라이브러리만). 학습용 torch 환경은 넣지 않는다.
# Astral python-build-standalone, 판·SHA-256 고정(PythonInstaller.swift와 같은 값). 받은 파일은 .cache에 두고 다시 쓴다
PY_REL=20260901; PY_VER=3.12.14
case "$(uname -m)" in arm64) PY_ARCH=aarch64; PY_SHA=3ee3ee547cedfeb7c2b16b2b7156039f7b470bb8f857e226fd3d2eb11db83c76 ;;
                      *) PY_ARCH=x86_64; PY_SHA=2e31b23f3f1319f707d0e620b48847a0046577541d357276821f9f1b5492e0ba ;; esac
PY_TAR=".cache/cpython-$PY_VER+$PY_REL-$PY_ARCH-apple-darwin-install_only.tar.gz"
if [ "${EPOKIO_NO_PYTHON:-}" != "1" ]; then
  mkdir -p .cache
  [ -f "$PY_TAR" ] || curl -fsSL -o "$PY_TAR" "https://github.com/astral-sh/python-build-standalone/releases/download/$PY_REL/cpython-$PY_VER%2B$PY_REL-$PY_ARCH-apple-darwin-install_only.tar.gz"
  echo "$PY_SHA  $PY_TAR" | shasum -a 256 -c - >/dev/null || { echo "python download checksum mismatch"; rm -f "$PY_TAR"; exit 1; }
  tar -xzf "$PY_TAR" -C "$APP/Contents/Resources"                     # → Resources/python
  PYLIB="$APP/Contents/Resources/python/lib/python3.12"
  # agent에 필요 없는 것 덜어 내기(시험 모음·Tk 화면·IDLE·설치기)
  rm -rf "$PYLIB/test" "$PYLIB/idlelib" "$PYLIB/tkinter" "$PYLIB/turtledemo" "$PYLIB/ensurepip" "$PYLIB/lib2to3" \
         "$PYLIB/site-packages/pip"* "$PYLIB/lib-dynload/_tkinter"* "$APP/Contents/Resources/python/lib/"{tcl,tk,itcl,thread}* \
         "$APP/Contents/Resources/python/lib/libtcl"* "$APP/Contents/Resources/python/lib/libtk"* "$APP/Contents/Resources/python/share" \
         "$APP/Contents/Resources/python/include"
  find "$APP/Contents/Resources/python" -name __pycache__ -type d -prune -exec rm -rf {} +
fi
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Epokio</string>
  <key>CFBundleDisplayName</key><string>Epokio</string>
  <key>CFBundleIdentifier</key><string>io.github.8rulerstar.epokio</string>
  <key>CFBundleExecutable</key><string>Epokio</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleDevelopmentRegion</key><string>en</string>
  <key>CFBundleLocalizations</key><array><string>en</string><string>ko</string><string>ja</string><string>zh-Hans</string><string>zh-Hant</string><string>es</string><string>fr</string><string>de</string><string>pt-BR</string><string>vi</string></array>
  <key>CFBundleIconFile</key><string>Epokio</string>
  <key>CFBundleIconName</key><string>Epokio</string>
  <key>CFBundleShortVersionString</key><string>0.4.3</string>
  <key>CFBundleVersion</key><string>7</string>
  <key>LSMinimumSystemVersion</key><string>15.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
  <key>SUFeedURL</key><string>${EPOKIO_APPCAST:-https://github.com/8rulerstar/epokio/releases/latest/download/appcast.xml}</string>
  <key>SUPublicEDKey</key><string>${EPOKIO_SPARKLE_PUBKEY:-}</string>
  <key>SUEnableInstallerLauncherService</key><false/>
</dict></plist>
PLIST
# 서명: EPOKIO_SIGN_ID("Developer ID Application: 이름 (팀ID)")가 있으면 배포용, 없으면 로컬 실행용 임시 서명.
# ★임시 서명은 빌드마다 달라져 macOS가 폴더 권한을 다시 묻고, 앱이 띄운 agent가 바탕화면 폴더를 못 읽었다
if [ -n "${EPOKIO_SIGN_ID:-}" ]; then
  # ★--deep은 Resources 안의 파이썬 .dylib·.so를 서명하지 않는다: 안쪽부터 하나씩 서명하고 앱을 마지막에
  find "$APP/Contents/Resources/python" -type f \( -name "*.dylib" -o -name "*.so" -o -perm -u+x \) -exec \
    codesign --force --options runtime --timestamp --sign "$EPOKIO_SIGN_ID" {} \; 2>/dev/null || true
  # Sparkle: 안쪽 도우미(Autoupdate·Updater.app·XPC)부터
  SP="$APP/Contents/Frameworks/Sparkle.framework"
  for x in "$SP/Versions/B/XPCServices/"*.xpc "$SP/Versions/B/Autoupdate" "$SP/Versions/B/Updater.app" "$SP"; do
    [ -e "$x" ] && codesign --force --options runtime --timestamp --sign "$EPOKIO_SIGN_ID" "$x"
  done
  codesign --force --options runtime --timestamp --entitlements entitlements.plist --sign "$EPOKIO_SIGN_ID" "$APP"
  codesign --verify --strict "$APP" && echo "signed: $EPOKIO_SIGN_ID"
else
  codesign --force --sign - "$APP" >/dev/null 2>&1 || true
fi
echo "built: $APP"

# ── .dmg (GitHub 배포용). 끌어다 놓기 창: 앱 + Applications 바로가기 ──
if [ "$1" = "--dmg" ]; then
  VER=$(/usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" "$APP/Contents/Info.plist")
  STAGE=build/dmg
  rm -rf "$STAGE" && mkdir -p "$STAGE"
  cp -R "$APP" "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  DMG="build/Epokio-$VER.dmg"
  rm -f "$DMG"
  hdiutil create -volname "Epokio" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
  rm -rf "$STAGE"     # 남겨 두면 Launchpad·Spotlight에 Epokio가 두 개로 보인다
  if [ -n "${EPOKIO_SIGN_ID:-}" ]; then codesign --force --timestamp --sign "$EPOKIO_SIGN_ID" "$DMG"; fi
  # 공증: EPOKIO_NOTARY = `xcrun notarytool store-credentials`로 만든 키체인 프로필 이름
  if [ -n "${EPOKIO_NOTARY:-}" ]; then
    xcrun notarytool submit "$DMG" --keychain-profile "$EPOKIO_NOTARY" --wait && xcrun stapler staple "$DMG"
  fi
  shasum -a 256 "$DMG" | cut -d' ' -f1 > "$DMG.sha256"      # Homebrew cask에 넣을 값
  echo "dmg: $DMG ($(du -h "$DMG" | cut -f1)) sha256 $(cat "$DMG.sha256")"
fi

# ★빌드 폴더에 앱이 남아 있으면 LaunchServices가 다시 등록해 Launchpad에 Epokio가 두 개 뜬다(2026-09-22, Spotlight 제외로도 안 됨).
#   /Applications에 설치하고 빌드 사본은 지운다. 설치하지 않으려면 --no-install
LSREG=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
if [[ " $* " != *" --no-install "* ]]; then
  pkill -f /Applications/Epokio.app/Contents/MacOS/Epokio 2>/dev/null || true
  pkill -f "epokio.agent.*--label local" 2>/dev/null || true   # ★앱이 띄운 agent가 살아남아 옛 코드로 계속 답했다
  rm -rf /Applications/Epokio.app && ditto "$APP" /Applications/Epokio.app
  "$LSREG" -u "$(pwd)/build.noindex/Epokio.app" 2>/dev/null || true
  rm -rf "$APP"
  echo "installed: /Applications/Epokio.app"
fi
