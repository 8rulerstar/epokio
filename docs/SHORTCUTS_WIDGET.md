# 단축어(App Intents)와 위젯

기준: 2026-09-23, macOS 27.0 / Xcode 27 툴체인 / Swift 6.4, SwiftPM 빌드(`mac/build_app.sh`).

## 단축어 - 된다. 지금 빌드에 들어간다

`mac/Sources/Epokio/Intents/` 의 네 파일은 `path: "Sources/Epokio"` 아래라 `swift build` 가 이미
컴파일하고 있었다. 빠져 있던 것은 **메타데이터 묶음**이다.

시스템(단축어 앱, Siri, Spotlight)은 앱 실행 파일의 코드를 훑지 않는다.
`Contents/Resources/Metadata.appintents/extract.actionsdata` 만 읽는다. 이 묶음은 Xcode가
빌드 단계에서 `appintentsmetadataprocessor` 로 만드는데, SwiftPM은 그 단계를 돌리지 않는다.
그래서 코드가 멀쩡히 컴파일돼도 단축어 앱에 동작이 **하나도** 뜨지 않았다.

`build_app.sh` 가 이제 그 처리기를 직접 돌린다. 입력은 둘이다.

* 소스 목록: `Sources/Epokio` 아래 모든 `.swift`
* `.swiftconstvalues`: 스위프트 컴파일러가 내는 상수 메타데이터.
  이 저장소의 SwiftPM은 Xcode 빌드 시스템을 써서 이 파일을 이미 낸다
  (`.build/out/Intermediates.noindex/Epokio.build/Release/.../Epokio-primary.swiftconstvalues`).
  릴리스는 모듈 통째 최적화라 파일이 한 개다.

결과물은 `/Applications/Goodnotes.app` 등 Xcode로 만든 앱이 담고 있는 것과 같은 모양이다
(`extract.actionsdata` + `version.json`, 같은 위치).

빌드 뒤 확인:

```
ls build/Epokio.app/Contents/Resources/Metadata.appintents
python3 -c "import json;d=json.load(open('build/Epokio.app/Contents/Resources/Metadata.appintents/extract.actionsdata'));print(list(d['actions']),len(d['autoShortcuts']))"
```

지금 값: `['OpenRunIntent','RetrainIntent','TrainingStatusIntent','WaitForRunIntent']`, 자동 단축어 3개,
개체 `RunEntity` 1개.

처리기가 없거나 실패하면 빌드는 계속되고 경고 한 줄을 낸다(`build/appintents.log` 에 까닭).
Xcode 커맨드라인 도구만 깔린 기계에는 `appintentsmetadataprocessor` 가 없을 수 있다.

### 확인 못 한 것

단축어 앱 화면에 Epokio 동작 네 개가 실제로 뜨는지는 **확인하지 못했다.** 그러려면
`/Applications` 에 설치하고 앱을 한 번 띄워야 하는데, 그게 돌고 있는 agent를 죽인다.
확인하려면 `cd mac && ./build_app.sh` (기본값이 설치까지 한다) 뒤 앱을 띄우고 단축어 앱을 열면 된다.

## 위젯 - 지금 빌드 구조로는 안 된다. 억지로 넣지 않았다

SwiftPM은 `.appex` 를 못 만든다. 그건 알려진 제약이고, 돌아갈 길은 두 가지다.
둘 다 **지금 빌드로는 막힌다.** 막는 것은 빌드 도구가 아니라 **서명 자격(entitlement)** 이다.

이 맥에 깔린 서드파티 위젯의 자격을 실제로 읽어 확인했다
(`codesign -d --entitlements :- /Applications/Goodnotes.app/Contents/PlugIns/WidgetExtension.appex`):

```
application-identifier        C88F57F4TJ.com.goodnotesapp.x.WidgetExtension
com.apple.developer.team-identifier  C88F57F4TJ
com.apple.security.app-sandbox       true
com.apple.security.application-groups  [group.com.goodnotesapp.goodnotes]
```

여기서 나오는 요구가 셋이다.

1. **위젯은 샌드박스 안에서 돈다.** 그러니 위젯이 `~/.epokio` 같은 임의 경로를 읽을 수 없다.
   앱이 공유 파일에 최신 상태를 적어 두는 방식 자체는 맞지만, 그 파일이
   **App Group 컨테이너 안**(`~/Library/Group Containers/<팀ID>.group.…`)에 있어야 한다.
2. **App Group 은 팀 ID 접두사를 요구한다.** 즉 Developer ID 계정과, `application-identifier` 를
   담은 프로비저닝 프로파일이 필요하다. 지금 `build_app.sh` 는 `EPOKIO_SIGN_ID` 가 없으면
   임시(ad-hoc) 서명이고, 있어도 프로파일을 넣지 않는다.
3. 본체 앱도 같은 그룹 자격을 받아야 한다. 지금 `entitlements.plist` 에는 앱 안 파이썬을 위한
   `disable-library-validation` 하나뿐이다.

그래서 판단은 이렇다. **위젯은 계정·프로파일 문제이지 코드 문제가 아니다.**
지금 위젯 코드를 써 두면 아무 기계에서도 빌드·실행되지 않는 죽은 코드가 된다.

### 나중에 하려면 (선택지와 각각이 요구하는 것)

| 길 | 요구하는 것 | 지금 빌드에 주는 충격 |
|---|---|---|
| A. Xcode 프로젝트로 이사(`.xcodeproj`, 앱 타깃 + 위젯 타깃) | Developer ID·프로파일. SwiftPM 패키지는 앱 타깃의 의존성으로 남길 수 있다 | 크다. `build_app.sh` 의 아이콘·파이썬 동봉·Sparkle·서명 차례를 전부 Xcode 빌드 단계로 옮겨야 한다 |
| B. `build_app.sh` 에서 `.appex` 수동 조립(swiftc로 별도 모듈 컴파일 + `NSExtensionPointIdentifier=com.apple.widgetkit-extension` Info.plist + 안쪽부터 서명) | 위와 같은 Developer ID·프로파일. 더해 WidgetKit 링크·`@main WidgetBundle` 을 손으로 맞춰야 한다 | 중간. 지금 구조는 유지되나 스크립트가 60줄쯤 늘고 검증하기 어렵다 |

어느 쪽이든 앞에 App Group 설정이 먼저다. 그게 정해지기 전에는 A도 B도 의미가 없다.

### 데이터 전달은 이미 답이 나와 있다

위젯이 로컬 agent에 HTTP를 때리는 건 하지 말 것. 포트가 뜨는 시점이 다르고 토큰이 앱 쪽에만 있다.
앱이 상태를 파일 한 장으로 적고 위젯이 그것만 읽는 구조가 맞다. 내용은 이 정도면 된다.

* 도는 학습 하나: 이름, 진행률, `epoch n/m`, ETA
* 최근 끝난 학습 한 줄: 이름과 최고 점수

`Intents/RunEntity.swift` 의 `IntentText.line` · `IntentText.eta` 가 이미 그 문장을 만든다.
위젯을 켤 때 그대로 쓰면 된다. 쓸 자리는 App Group 컨테이너다(위 1번).
