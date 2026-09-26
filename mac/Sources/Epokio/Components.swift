import SwiftUI
import AppKit

// 공통 마이크로인터랙션. 규칙은 docs/DESIGN.md "움직임". 새 카드·버튼은 여기 것을 붙인다(직접 애니메이션을 새로 만들지 않는다).
//   누름 PressStyle(Theme.swift) · 올림 hoverLift · 나타남 appearRise · 값 변화 .contentTransition(.numericText()) · 축하 Haptic.success

extension View {
    /// 마우스를 올리면 살짝 떠오른다(카드·타일)
    func hoverLift(_ amount: CGFloat = 1.015) -> some View { modifier(HoverLift(amount: amount)) }
    /// 처음 나타날 때 아래에서 떠오르며 보인다. 목록은 순번을 주면 차례로(12개까지)
    func appearRise(_ index: Int = 0) -> some View { modifier(AppearRise(index: index)) }
}

private struct HoverLift: ViewModifier {
    let amount: CGFloat
    @State private var on = false
    @Environment(\.accessibilityReduceMotion) private var reduce
    func body(content: Content) -> some View {
        content
            .scaleEffect(on && !reduce ? amount : 1)
            .shadow(color: .black.opacity(on ? 0.08 : 0), radius: on ? 8 : 0, y: on ? 3 : 0)
            .onHover { h in withAnimation(Motion.hover) { on = h } }
    }
}

private struct AppearRise: ViewModifier {
    let index: Int
    @State private var shown = false
    @Environment(\.accessibilityReduceMotion) private var reduce
    func body(content: Content) -> some View {
        content
            .opacity(shown || reduce ? 1 : 0)
            .offset(y: shown || reduce ? 0 : 6)
            .onAppear {
                guard !shown else { return }
                withAnimation(Motion.appear.delay(Double(min(index, 12)) * Motion.stagger)) { shown = true }
            }
    }
}

/// 트랙패드 진동. 저장 성공·목표 달성처럼 "됐다"는 순간에만(자주 쓰면 의미가 사라진다)
enum Haptic {
    /// 설정 → 모양 "트랙패드 진동"(haptics, 기본 켬)
    static var on: Bool { UserDefaults.standard.object(forKey: "haptics") as? Bool ?? true }
    static func success() { if on { NSHapticFeedbackManager.defaultPerformer.perform(.levelChange, performanceTime: .now) } }
    static func tick() { if on { NSHapticFeedbackManager.defaultPerformer.perform(.alignment, performanceTime: .now) } }
}

/// 곡선·비교 그래프의 선 색 순서(색 역할에서). 시스템 기본 팔레트 대신 쓴다
let chartPalette: [Color] = [.brand, .brand2, .good, .warn, .mixup, .gold, .info, .bad]

extension View {
    /// 그래프 선 색을 토큰 순서로. 이름(시리즈) 목록을 주면 그 순서대로 색이 붙는다
    func tokenChartColors(_ names: [String]) -> some View {
        chartForegroundStyleScale(domain: names, range: names.indices.map { chartPalette[$0 % chartPalette.count] })
    }
}

/// 링크 버튼. ★시스템 `.link`는 `.tint(.brand)`를 걸어도 시스템 파랑이었다(학습 화면 "샘플로 시작"). 브랜드색 + 올리면 밑줄 + 누르면 흐려짐
struct BrandLink: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { BrandLinkBody(configuration: configuration) }
}

private struct BrandLinkBody: View {
    let configuration: ButtonStyleConfiguration
    @State private var hover = false
    @Environment(\.isEnabled) private var enabled
    var body: some View {
        configuration.label
            .foregroundStyle(enabled ? AnyShapeStyle(.brand) : AnyShapeStyle(.secondary))
            .underline(hover && enabled, color: .brand.opacity(0.6))
            .opacity(configuration.isPressed ? 0.55 : 1)
            .contentShape(.rect)
            .onHover { h in withAnimation(Motion.hover) { hover = h } }
            .animation(Motion.tap, value: configuration.isPressed)
    }
}

/// 글자·아이콘 표시를 조건으로 바꿀 때(좁으면 아이콘만). `.labelStyle(labels ? AnyLabelStyle(.titleAndIcon) : AnyLabelStyle(.iconOnly))`
struct AnyLabelStyle: LabelStyle {
    private let make: (Configuration) -> AnyView
    init<S: LabelStyle>(_ s: S) { make = { AnyView(Label($0).labelStyle(s)) } }
    func makeBody(configuration: Configuration) -> some View { make(configuration) }
}

// ── Liquid Glass ──
// 떠 있는 것(안내 카드·알림 띠·팔레트·떠 있는 버튼)에만 쓴다. 읽는 곳(목록·본문)은 그대로.
// macOS 26 미만은 머티리얼, "투명도 줄이기"를 켜면 불투명 표면. 설정 → 꾸미기 "유리 효과"로 끌 수 있다(glass).
struct GlassSurface<S: Shape>: ViewModifier {
    let shape: S
    var tint: Color? = nil
    var interactive = false
    @Environment(\.accessibilityReduceTransparency) private var solid
    @AppStorage("glass") private var glass = true

    func body(content: Content) -> some View {
        if solid || !glass {
            content.background(Color(nsColor: .windowBackgroundColor), in: shape)
                .overlay(shape.stroke(.primary.opacity(0.12)))
        } else if #available(macOS 26, *) {
            content.glassEffect(interactive ? Glass.regular.tint(tint).interactive() : Glass.regular.tint(tint), in: shape)
        } else {
            content.background(.regularMaterial, in: shape)
        }
    }
}

extension View {
    /// 떠 있는 표면에 유리 효과. `interactive`면 누를 때 유리가 반응한다(버튼·칩)
    func glass<S: Shape>(_ shape: S, tint: Color? = nil, interactive: Bool = false) -> some View {
        modifier(GlassSurface(shape: shape, tint: tint, interactive: interactive))
    }
    /// 둥근 사각 유리(모서리는 디자인 토큰). 툴팁·오버레이용
    func glass(radius: CGFloat = Radius.control, tint: Color? = nil) -> some View {
        glass(RoundedRectangle(cornerRadius: radius, style: .continuous), tint: tint)
    }
}

/// 가까이 붙은 유리끼리 한 덩어리로 섞이게 묶는다(macOS 26). 구형은 그냥 내용
struct GlassGroup<Content: View>: View {
    var spacing: CGFloat = Space.m
    @ViewBuilder var content: Content
    var body: some View {
        if #available(macOS 26, *) { GlassEffectContainer(spacing: spacing) { content } } else { content }
    }
}

// 버튼 체계 세 단계. 새 버튼은 이 중 하나를 고른다.
//   주 버튼 `.primaryButton()`: 화면의 핵심 행동 하나(시작·저장·계속). macOS 26+ 리퀴드 글라스, 구형은 채운 버튼
//   보조 버튼 `.secondaryButton()`: 주 버튼 옆 대안 행동. macOS 26+ 글라스, 구형은 테두리 버튼
//   조용한 버튼 `PressStyle()`: 카드·타일·아이콘처럼 모양은 직접 그리고 누름만 필요한 곳
// 투명도 줄이기·대비 증가를 켜면 글라스 대신 불투명한 시스템 버튼으로 내려간다(글자 대비 보장).
// 누름·올림 효과는 시스템 버튼이 제공한다(글라스는 누르면 튀고 올리면 빛난다).
extension View {
    func primaryButton() -> some View { modifier(PrimaryButtonStyle()) }
    func secondaryButton() -> some View { modifier(SecondaryButtonStyle()) }
}

struct PrimaryButtonStyle: ViewModifier {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    func body(content: Content) -> some View {
        if #available(macOS 26, *), !reduceTransparency, contrast != .increased {
            content.buttonStyle(.glassProminent)
        } else {
            content.buttonStyle(.borderedProminent)
        }
    }
}

struct SecondaryButtonStyle: ViewModifier {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    func body(content: Content) -> some View {
        if #available(macOS 26, *), !reduceTransparency, contrast != .increased {
            content.buttonStyle(.glass)
        } else {
            content.buttonStyle(.bordered)
        }
    }
}
