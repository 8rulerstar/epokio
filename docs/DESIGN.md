# Epokio 디자인 시스템

[문서 지위] 정본 · 2026-09-22 · 맥 앱과 웹 화면 공통

피그마의 디자인 시스템처럼, 화면은 이 문서의 **토큰**과 **컴포넌트**만으로 만든다.
값은 `design/tokens.json` 한 곳에 있다. 고친 뒤 아래를 실행한다.

```bash
python3 tools/design_tokens.py
```

실행하면 `mac/Sources/Epokio/DesignTokens.swift`와 `src/epokio/web/tokens.css`가 다시 만들어진다. 두 파일은 손으로 고치지 않는다.
테스트(`test_house_rules`)는 생성본이 원본과 같은지, 그리고 스위프트에서 시스템 색을 직접 썼는지를 본다.

한눈에 보기: `docs/images/design-light.png`, `design-dark.png`
(앱을 `swift build` 한 뒤 `.build/debug/Epokio --snapshot-window design <낼 파일.png>`로 다시 찍는다. 다크는 `--dark`)

---

## 1. 원칙 (아이폰 듀오)

* **요약이 먼저, 자세한 건 펼쳐서.** 첫 화면에는 숫자 하나와 할 일 하나만 둔다.
* **버튼은 가장자리 세로 레일로 모은다.** 내용은 넓게 쓴다.
* **아이콘은 세로로, 글자는 가로로.** 아이콘에는 글자 이름을 같이 단다. 아이콘만 두려면 도움말을 붙인다.
* **움직임은 뜻이 있을 때만.** 무엇이 바뀌었는지 보여 주는 데 쓰고, 장식으로 쓰지 않는다.
  시스템의 "동작 줄이기"가 켜져 있으면 나타남·축하 효과는 멈춘다.

## 2. 색 역할

색은 **뜻**으로 고른다. 같은 뜻이면 앱과 웹이 같은 색이다.

| 역할 | 뜻 | 쓰는 곳 |
|---|---|---|
| `brand` | 강조색 (아이콘 보라) | 버튼, 선택, 링크, 진행률, 끝난 학습 |
| `brand2` | 포인트 짝색 (아이콘 청록) | 그라데이션 끝, 메뉴바·트레이 끝점 |
| `good` | 좋음 | 도는 중, 맞춤, 저장 성공, 사용 중 모델 |
| `warn` | 주의 | 멈춤, 놓침, 후보 모델, 경고 알림 |
| `bad` | 나쁨 | 실패, 헛검출, 지우기 |
| `mixup` | 헷갈림 | 클래스 착각, 시작 중 |
| `gold` | 최고 | 1등, 별표, 목표 |
| `info` | 안내 | 링크가 아닌 알림 |

* 스위프트: `.foregroundStyle(.good)`, `Color.bad`, 그라데이션은 `LinearGradient.brand`
* 웹: `var(--good)`, `var(--grad-brand)`
* **하지 말 것**: `.green`, `.red`, `Color.orange`, **`Color.accentColor`** 같은 시스템 색을 직접 쓰기(테스트가 막는다). `accentColor`는 `.tint(.brand)`를 걸어도 시스템 파랑이다. 뜻 없이 색 고르기. 흐린 글자색(`ink.faint`)을 읽는 글씨에 쓰기(장식 기호에만).
* 면·글자 바탕색은 시스템을 따른다(`.primary`, `.quaternary`, `ink.soft`). 라이트·다크 두 벌은 토큰이 맞춘다.

## 3. 글꼴 역할

시스템 서체(SF Pro)를 쓴다. 숫자는 둥근 서체(SF Pro Rounded)에 **폭을 고정**한다. 값이 바뀌어도 글자가 흔들리지 않게 하기 위해서다.

| 역할 | 크기·굵기 | 쓰는 곳 |
|---|---|---|
| `hero` | 44 굵게, 둥근 | 학습 상세의 큰 점수 하나 |
| `display` | 28 굵게, 둥근 | 큰 숫자 칸 |
| `title` | 22 굵게 | 화면 제목 |
| `headline` | 15 반굵게 | 카드·섹션 제목 |
| `body` | 13 | 본문, 목록 이름 |
| `callout` | 12.5 | 보조 설명 |
| `caption` | 11.5 | 가장 작은 읽는 글씨 |
| `badge` | 10 반굵게, 둥근 | 숫자 뱃지 같은 장식만 |

* 스위프트: `.font(.role(.headline))`. 예전 코드의 `.font(.ui(크기))`도 가장 가까운 역할로 자동으로 맞춰진다. 새 코드는 `.role`을 쓴다.
* 설정 → 모양 → 글씨 크기(작게·보통·크게)가 모든 역할에 곱해진다.
* 웹: `var(--t-body)` 등. 숫자는 `.big`, `.stats b`, `.tile b`, `td.num`이 둥근 서체를 쓴다.

## 4. 간격·모서리

* 간격: `xs 4 · s 8 · m 12 · l 16 · xl 24` (스위프트 `Space.m`, 웹 `var(--s-m)`)
* 모서리: `chip 6 · control 10 · card 14 · sheet 20` (스위프트 `Radius.card`, 웹 `var(--r-card)`)

## 5. 움직임 (마이크로인터랙션)

**새 기능과 화면마다 필수다.** 여섯 가지만 쓴다. 속도를 직접 쓰면 테스트(`test_no_raw_animation_speeds_in_swift`)가 막는다.

| 역할 | 값 | 언제 |
|---|---|---|
| `tap` | snappy 0.12 | 누름: 살짝 줄고 흐려진다(`PressStyle`) |
| `hover` | snappy 0.15 | 올림: 카드가 떠오른다(`.hoverLift()`), 배경이 옅게 찬다 |
| `change` | smooth 0.30 | 값·배치 변화, 펼침·접기, 선택 이동(사이드 레일 선택 표시가 미끄러진다) |
| `progress` | smooth 0.60 | 진행률 고리·막대가 새 값으로 차오를 때 |
| `appear` | spring 0.40, 차례로 25ms | 나타남: 목록과 격자가 아래에서 차례로 떠오른다(`.appearRise(순번)`, 12개까지) |
| `celebrate` | bouncy 0.45 + 진동 | 됐다: 저장 성공, "사용 중"으로 올림, 목표 달성(`Haptic.success()`) |

* 숫자가 바뀌면 굴러간다: `.contentTransition(.numericText())`
* 아이콘은 뜻이 바뀔 때 튄다: `.symbolEffect(.bounce, value:)`. 모양이 바뀌면 `.contentTransition(.symbolEffect(.replace))`
* 진동은 "됐다"는 순간에만 쓴다. 판정 한 번, 레일 이동은 `Haptic.tick()`(아주 약하게). 자주 울리면 뜻이 사라진다.
* 웹: `transition: … var(--m-hover)`, `animation: rise var(--m-appear)`. `prefers-reduced-motion`이면 전부 멈춘다.
* **조작 관례(애플 앱과 같게)**: 스페이스 = 훑어보기, ⌘Z = 되돌리기, ⌘·⇧ 클릭 = 여러 개 고르기, ⌘A = 전부, Esc = 닫기·풀기, 끌어서 순서 바꾸기(대기열). 새 화면도 이 관례를 따른다.
* **성능**: 메뉴바는 보이는 칸이 바뀔 때만, 초당 12번까지 다시 그린다(빠르면 2·3칸씩 고르게 건너뛴다). 계속 도는 효과는 창 전체 배치를 다시 재게 만들 수 있다: 상세 화면에는 빛줄기를 두지 않는다. 학습이 끝나는 순간 메뉴바 아이콘이 체크로 5초 튄다
* 웹: 키보드(Tab)로 옮기면 `brand` 테두리(`:focus-visible`), 목록 줄은 Enter·스페이스로 연다. 웹의 시간도 `var(--m-…)` 토큰만(테스트)
* **하지 말 것**: `.snappy(duration: 0.18)`처럼 새 속도를 만들기(필요하면 `design/tokens.json`에 역할을 더한다). 예외는 끝없이 도는 장식 반복(`repeatForever`, 숨쉬기·빛줄기)뿐. 반복 애니메이션을 멈출 수 없게 두기(도는 학습만 움직이고 멎으면 멈춘다).

## 6. 컴포넌트

새로 만들기 전에 여기 있는 것을 쓴다. 새로 만들면 이 표와 디자인 갤러리(`DesignGallery.swift`)에 한 칸 더한다.

| 컴포넌트 | 파일 | 상태별 규칙 |
|---|---|---|
| 버튼 | Components.swift `.primaryButton()`·`.secondaryButton()`·`PressStyle()` | 세 단계. 화면의 핵심 행동 하나만 primary, 그 옆 대안은 secondary, 모양을 직접 그리는 카드·타일·아이콘은 PressStyle. 지우기는 `role: .destructive`. macOS 26+는 글라스(`.glassProminent`·`.glass`), 구형·투명도 줄이기·대비 증가는 `.borderedProminent`·`.bordered`로 내려간다 |
| 유리 표면 | Components.swift `GlassSurface`·`.glass(모양)` | 떠 있는 표면(레일·툴바·툴팁·오버레이)은 전부 이것. macOS 26+ `glassEffect`, 구형은 `.regularMaterial`, 투명도 줄이기·설정 끄기면 불투명. 손 그림자를 따로 달지 않는다 |
| 링크 | Components.swift `BrandLink()` | `brand` 글자, 올리면 밑줄, 누르면 55%. 시스템 `.link`는 파래서 금지(테스트) |
| 아이콘 얼굴 | Theme.swift `IconFace` | 26pt, 올리면 8% 바탕 + 1.06배. 메뉴·설정처럼 Button이 아닌 곳의 라벨 |
| `IconButton` | Theme.swift | 아이콘만 쓰면 도움말(`help`) 필수. 누름 `tap` |
| `FilterChip` | ReviewParts.swift | 꺼짐: 옅은 색 바탕 + 아이콘 + 개수. 켜짐: 색이 차고 이름이 나타남. 개수는 굴러간다 |
| `StageBadge`·알약 | VersionViews.swift | 색 역할의 14% 바탕 + 같은 색 글자. 나타날 때 커지며 보인다 |
| 학습 카드(팝오버) | RunCard.swift | 누르면 눌림(`PressStyle`), 올리면 테두리가 상태색으로. 도는 학습의 최고 점수가 오르면 `gold` 테두리가 1.2초 빛난다 |
| `MetricTile` | ResultParts.swift | 숫자는 둥근 서체·폭 고정. 강조 칸은 `brand` 글자. 올리면 떠오른다 |
| `SectionTitle` | ResultParts.swift | 제목(headline) + 한 줄 설명(caption, `ink.soft`) |
| `CapsuleBar` | Theme.swift | 진행률. 도는 동안 빛이 지나간다(학습 속도로), 멎으면 멈춘다 |
| `RailItem`·`StatusRing` | IconRail.swift | 선택 표시가 미끄러져 옮겨 간다(`matchedGeometryEffect`). 올리면 옅게 찬다 |
| 토스트 | ResultParts.swift `ToastView` | 성공은 `good`, 문제는 `warn`. 위에서 내려오고, 누르면 닫힌다 |
| 카드 | `.background(.quaternary.opacity(0.25), in: .rect(cornerRadius: Radius.card))` | 격자의 카드는 `hoverLift` + `appearRise` |
| 되돌리기 알림 | `store.say(…, actionTitle: L("Undo")) { … }` | 바꾼 것을 되돌릴 수 있으면 알림에 "되돌리기"(⌘Z도 같은 동작). 6초 동안 보인다 |
| 선택 막대 | ReviewActions.swift `selectionBar` · 웹 `.selbar` | 여러 개를 고르면(⌘·⇧ 클릭, ⌘A) 아래에서 떠오른다. 1~4로 한 번에, Esc로 풀기 |
| 확대·이동 | ReviewDetail.swift `ZoomPan` · 웹 `zoomable()` | 두 손가락·휠로 확대, 끌어서 이동, 두 번 눌러 원래대로/2.5배. 배율을 오른쪽 아래에 보인다. 다음 장으로 가면 원래 크기 |
| 메뉴바 우클릭 메뉴 | MenuBarRightClick.swift | 맨 위는 지금 상태(누를 수 없음), 그 아래 자주 하는 일. 항목마다 SF Symbol |
| 메뉴바 캐릭터 | BarRunners.swift `Runner` | 16프레임 단색(template) 그림을 코드로 그린다. 한 바퀴 속도 = 학습 속도, 멎으면 멈춘 자세. 24×16pt 안에서 머리·귀가 위 끝에 닿지 않게. 새 캐릭터는 case 하나 + draw 함수 하나 |
| 캐릭터 고르기 | SettingsAppearance.swift `CharacterStrip`·`CharacterTile` | 5칸 격자, 아이콘 아래 이름. 고른 것·올린 것만 제자리에서 움직인다. 고른 칸은 `gradient.brand` 바탕 + 흰 글자 |
| 평행 좌표 | ParallelCoords.swift · 웹 `parallelHTML()` | 설정 축 → 맨 오른쪽 점수. 좋을수록 진하고 굵게. 올리면 그 선만 도드라지고 값이 뜬다, 누르면 그 학습. 자릿수가 넓으면 로그 눈금. 폰에선 최소 폭 520px로 옆으로 민다 |
| 홈(대시보드) | HomeView.swift `LiveTile` | Studio 첫 화면. 지금(도는 학습·대기열 다음·기계) → 챙길 것(멈춤·실패·토큰 기다리는 스윕·검수할 평가·다음 학습 제안) → 최근 결과(같은 데이터의 이전 최고 대비 ±) → 데이터셋별 최고 → 빠른 작업. 칸 머리 아이콘은 그 칸의 색, 카드는 눌림·떠오름·차례로 나타남. ⌘0 |
| 학습 기록 묶기 | RunGrouping.swift `RunTree` | 최근·날짜(연›월›일)·디스크 폴더(공통 앞부분 떼고, 가지 하나뿐이면 a/b/c로 이어 붙임)·내 모음·작업·데이터셋·모델·프레임워크·기계·태그. 윗단은 머리 줄을 눌러 접고, 아랫단은 폴더처럼 펼친다(개수·최고 점수). 우클릭 "모음에 넣기" |
| 시작 카드 줄 | TrainStart.swift `StartCard`·`NudgeChip` | 새 학습 맨 위: 프리셋 3 · 최근 4 · 데이터셋별 최고 3. 누르면 양식만 채운다(시작은 사람이). 채운 뒤 "X 기준 · N개 바꿈 · 되돌리기", 살짝 비틀기 알약(누르면 아이콘이 튄다), 데이터가 다르면 경고 |
| 검수 도장 | ReviewDetail.swift `stamp` · 웹 `.stamp` | 판정을 누르면 그 색 알약이 그림 가운데에 튀어 찍히고(celebrate) 0.33초 뒤 다음 장. ★바로 넘기면 눌렸는지 몰랐다 |
| 학습 기록 표 | RunsTable.swift · 웹 `table.js` | 학습 하나 = 한 줄, 칸 머리로 정렬(숫자는 숫자로, 빈 칸은 늘 아래), 위 칸에 `lr0<0.01 batch>=16 tag:x 글자`로 거르기(모두 만족), 2~8개 골라 비교, 두 번 누르면 연다. 최고 점수는 `brand` |
| 다음 학습 제안 | RunDetailSections.swift `NextRunButton` · 웹 `.nextrun` | 해설 아래 "해 보기: epochs 30 → 60 · best.pt에서 시작". `brand` 12% 알약, 올리면 그라데이션으로 차고 흰 글자. 누르면 양식만 채운다(바로 돌지 않음). 웹은 확인 창에서 파이썬을 고른 뒤 대기열에 |
| 가장 좋은 절충 | ParetoChart.swift · 웹 `paretoHTML()` | 가로 = 두 번째 목표, 세로 = 점수. 앞줄은 `brand` 큰 점 + 계단 선, 나머지는 옅게. 점에 올리면 설정이 뜬다 |
| 지금까지 최고 | SweepView.swift `BestSoFar` · 웹 `bestSoFarHTML()` | 계단 선, 최고점을 찾은 시도는 `gold` 큰 점. 똑똑한 스윕이면 "여기부터 결과를 보고 고름" 점선 |
| 못 읽은 폴더 안내 | PopoverCards.swift `SlowRootsNote` | `warn` 9% 바탕 + 자물쇠 아이콘 + 이유 한 줄 + 설정 여는 링크. 폴더를 다시 읽으면 저절로 사라진다 |
| 꺼진 버튼의 이유 | TrainView `blocked` · AutoLabelView | 꺼진 버튼은 도움말이 안 뜬다. 옆에 `info.circle` + "먼저 …을 고르세요" 한 줄(`caption`, `ink.soft`) |

### 상태 표기 (모든 컴포넌트 공통)

* **올림**: 옅은 바탕(`.primary.opacity(0.06~0.07)`) 또는 `hoverLift`
* **누름**: `PressStyle` (0.9배, 70% 투명)
* **선택**: `brand` 18% 바탕 + `brand` 글자·아이콘(채운 모양)
* **끔**: 시스템 `disabled`(흐려짐). 왜 꺼졌는지 **버튼 옆에 글로** 쓴다(꺼진 버튼엔 도움말이 안 뜬다)
* **실패·경고**: 문구 앞에 아이콘(`exclamationmark.triangle.fill`), 색만으로 알리지 않는다(색각 이상 대비)

## 7. 웹 화면

같은 토큰을 쓴다(`tokens.css` → `style.css`가 `--accent: var(--brand)` 식으로 잇는다).
외부 글꼴·CDN은 쓰지 않는다(오프라인 LAN). 폰 폭(375px)에서 격자는 두 줄, 탭 줄은 옆으로 스크롤한다.
