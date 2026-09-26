# 출시 절차

[문서 지위] 절차 · 2026-09-22 · 아직 한 번도 끝까지 돌려 보지 않음(개발자 계정 없음)

앱스토어가 아니라 **공증한 직접 배포**로 낸다. 앱이 사용자 파이썬을 띄우고 아무 폴더나 지켜보고 LAN 서버를 열어서
샌드박스(앱스토어 필수)와 맞지 않는다.

## 한 번만

1. Apple Developer Program 가입($99/년). 사용자가 직접 한다.
2. Xcode → Settings → Accounts에서 "Developer ID Application" 인증서를 만든다.
   `security find-identity -v -p codesigning`에 보이면 된다.
3. 공증용 키체인 프로필:
   ```bash
   xcrun notarytool store-credentials epokio-notary --apple-id <이메일> --team-id <팀ID>
   ```
   앱 암호는 appleid.apple.com에서 만든다. 암호는 키체인에만 두고 저장소·문서에 적지 않는다.
4. 자동 업데이트(Sparkle) 서명 키:
   ```bash
   mac/.build/artifacts/sparkle/Sparkle/bin/generate_keys
   ```
   비밀키는 이 맥의 키체인에만 남는다. 화면에 나오는 **공개키**를 빌드 때
   `EPOKIO_SPARKLE_PUBKEY`로 넘긴다(Info.plist `SUPublicEDKey`).
   ⚠공개키가 비어 있으면 앱은 업데이트를 아예 확인하지 않는다(`Updater.swift`의 guard).

## 매 출시

```bash
cd mac
EPOKIO_SIGN_ID="Developer ID Application: 이름 (팀ID)" EPOKIO_NOTARY=epokio-notary \
EPOKIO_SPARKLE_PUBKEY="<generate_keys가 낸 공개키>" ./build_app.sh --dmg --no-install
cd .. && ./tools/release_appcast.sh          # appcast.xml (dmg와 같이 릴리스에 올린다)
```

결과: `mac/build.noindex/Epokio-<버전>.dmg`(서명·공증·스테이플 완료)와 `.sha256`,
그리고 `mac/build.noindex/appcast/appcast.xml`. `mac/build`는 `build.noindex`로 가는 바로가기라
아래 명령들은 둘 중 어느 경로로 써도 같다.
버전은 `build_app.sh`의 `CFBundleShortVersionString`에서 올린다.
⚠`pyproject.toml`의 파이썬 패키지 버전은 따로다(지금 0.1.0). 같이 올릴지 정할 것.

확인:
```bash
spctl --assess --type open --context context:primary-signature -v mac/build.noindex/Epokio-*.dmg
```

## 배포 경로

* GitHub Releases에 dmg를 올린다(저장소를 공개로 바꾼 뒤).
* Homebrew cask(자기 tap `8rulerstar/homebrew-tap`에 두는 것부터):

```ruby
cask "epokio" do
  version "0.2.0"
  sha256 "<.sha256 파일 내용>"
  url "https://github.com/8rulerstar/epokio/releases/download/v#{version}/Epokio-#{version}.dmg"
  name "Epokio"
  desc "Menu bar monitor for YOLO and PyTorch training runs"
  homepage "https://github.com/8rulerstar/epokio"
  depends_on macos: ">= :sequoia"
  app "Epokio.app"
  zap trash: ["~/.epokio", "~/Library/Application Support/Epokio"]
end
```

## 상태

* 자동 업데이트(Sparkle 2)는 **붙어 있다**: `mac/Package.swift` 의존성, `Updater.swift`,
  `build_app.sh`의 `SUFeedURL`·`SUPublicEDKey`, `tools/release_appcast.sh`.
  서명된 appcast만 받는다. 아직 릴리스가 없어 실제로 업데이트를 받아 본 적은 없다.
* 단축어(App Shortcuts)는 SwiftPM에서 빌드된다: `mac/Sources/Epokio/Intents/`.
  `build_app.sh`가 `Metadata.appintents`까지 굽는다. 단축어 앱 화면에 실제로 뜨는지는 아직 확인 못 했다.
* 위젯(WidgetKit)은 아직 없다. 막는 것은 빌드 도구가 아니라 **서명 자격**이다
  (App Group + 팀ID + 프로비저닝 프로파일). 선택지는 `docs/SHORTCUTS_WIDGET.md` 참조.
* 서명·공증은 **한 번도 돌려 보지 않았다**(개발자 계정 없음). README와 SECURITY.md도
  그렇게 적혀 있다. 첫 성공 뒤에 이 문서의 머리말을 고칠 것.
