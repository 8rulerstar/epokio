import SwiftUI

// 첫 실행 안내: 네 장. ①무엇인지(움직이는 메뉴바 미리보기) ②캐릭터 고르기 ③학습 폴더 또는 샘플 ④완료.
// 페이지 내용은 OnboardingPages.swift, 캐릭터 고르기는 OnboardingCharacterPicker.swift.
// 다시 보려면 설정 → 일반 "처음 안내 다시 보기". 건너뛰기(Esc)는 언제든 된다. ←→ 넘기기, Return 다음.
// 스냅샷: `--snapshot-window onboarding out.png -onboardPage 2` 로 원하는 장부터 연다.

struct Onboarding: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduce
    @AppStorage("onboarded") private var onboarded = false
    @State private var page = min(max(UserDefaults.standard.integer(forKey: "onboardPage"), 0), OnboardPage.count - 1)
    @State private var forward = true
    @State private var appeared = false

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                content.id(page).transition(slide)
            }
            .frame(maxWidth: .infinity).frame(height: 400)
            .clipped()
            bar
        }
        .frame(width: 600)
        .background(backdrop)
        .opacity(appeared ? 1 : 0).scaleEffect(appeared ? 1 : 0.97)
        .onAppear { withAnimation(reduce ? nil : Motion.appear) { appeared = true } }
        .background { keys }
    }

    @ViewBuilder private var content: some View {
        switch page {
        case 0: OnboardWelcome()
        case 1: OnboardCharacterPicker()
        case 2: OnboardConnect()
        default: OnboardDone(finish: finish)
        }
    }

    /// 넘기는 방향에 맞춰 밀려 들어오고 나간다. 움직임 끔이면 겹쳐 바뀌기만
    private var slide: AnyTransition {
        if reduce { return .opacity }
        let inEdge: Edge = forward ? .trailing : .leading, outEdge: Edge = forward ? .leading : .trailing
        return .asymmetric(insertion: .move(edge: inEdge).combined(with: .opacity).combined(with: .scale(scale: 0.98)),
                           removal: .move(edge: outEdge).combined(with: .opacity))
    }

    /// 뒤 배경: 브랜드 색이 아주 옅게 번진다(장마다 자리를 옮겨 넘기는 느낌을 준다)
    private var backdrop: some View {
        GeometryReader { g in
            Circle().fill(LinearGradient.brand).opacity(0.10).blur(radius: 110)
                .frame(width: 300, height: 300)
                .offset(x: g.size.width * (0.1 + 0.2 * Double(page)) - 100, y: -210)
                .animation(reduce ? nil : Motion.progress, value: page)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private var bar: some View {
        HStack {
            Button("Skip") { finish() }
                .buttonStyle(OnboardQuiet())
                .keyboardShortcut(.cancelAction)
                .opacity(page == OnboardPage.count - 1 ? 0 : 1)
                .help("Close the guide. Open it again in Settings, General.")
            Spacer()
            dots
            Spacer()
            HStack(spacing: 8) {
                if page > 0 {
                    Button { go(page - 1) } label: { Image(systemName: "chevron.left").frame(width: 14) }
                        .buttonStyle(OnboardQuiet())
                        .help("Back")
                        .accessibilityLabel("Back")
                        .transition(.opacity.combined(with: .scale(scale: 0.8)))
                }
                Button { if page < OnboardPage.count - 1 { go(page + 1) } else { finish() } } label: {
                    if page < OnboardPage.count - 1 { Text("Continue") } else { Text("Done") }
                }
                .primaryButton().controlSize(.large)
                .keyboardShortcut(.defaultAction)
                .hoverLift()
            }
            .animation(Motion.change, value: page)
        }
        .padding(.horizontal, 20).padding(.vertical, 14)
    }

    /// 진행 점: 누르면 그 장으로. 지금 장은 길쭉하게
    private var dots: some View {
        HStack(spacing: 7) {
            ForEach(0..<OnboardPage.count, id: \.self) { i in
                Button { go(i) } label: {
                    Capsule().fill(i == page ? AnyShapeStyle(LinearGradient.brand) : AnyShapeStyle(.quaternary))
                        .frame(width: i == page ? 20 : 7, height: 7)
                        .padding(4).contentShape(.rect)
                }
                .buttonStyle(PressStyle())
                .help(OnboardPage.title(i))
                .accessibilityLabel(Text(verbatim: OnboardPage.title(i)))
                .accessibilityAddTraits(i == page ? .isSelected : [])
            }
        }
        .animation(reduce ? nil : Motion.celebrate, value: page)
    }

    /// ←→ 키. 보이지 않는 버튼에 단축키를 건다(시트 안에서 포커스와 상관없이 먹는다)
    private var keys: some View {
        ZStack {
            Button("") { go(page - 1) }.keyboardShortcut(.leftArrow, modifiers: [])
            Button("") { go(page + 1) }.keyboardShortcut(.rightArrow, modifiers: [])
        }
        .opacity(0).allowsHitTesting(false).accessibilityHidden(true)
    }

    private func go(_ to: Int) {
        let to = min(max(to, 0), OnboardPage.count - 1)
        guard to != page else { return }
        forward = to > page
        withAnimation(reduce ? nil : Motion.change) { page = to }
    }

    private func finish() { onboarded = true; dismiss() }
}

enum OnboardPage {
    static let count = 4
    static func title(_ i: Int) -> String {
        switch i {
        case 0: L("Welcome"); case 1: L("Character"); case 2: L("Your Runs"); default: L("Done")
        }
    }
}

/// 조용한 글자 버튼: 올리면 옅은 바탕, 누르면 살짝 줄어든다
struct OnboardQuiet: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { QuietBody(configuration: configuration) }
    private struct QuietBody: View {
        let configuration: Configuration
        @Environment(\.ink) private var ink
        @State private var hover = false
        var body: some View {
            configuration.label
                .font(.ui(13, weight: .medium))
                .foregroundStyle(hover ? AnyShapeStyle(.primary) : AnyShapeStyle(ink.soft))
                .padding(.horizontal, 10).padding(.vertical, 6)
                .background(.primary.opacity(hover ? 0.07 : 0), in: Capsule())
                .scaleEffect(configuration.isPressed ? 0.95 : 1)
                .animation(Motion.tap, value: configuration.isPressed)
                .onHover { h in withAnimation(Motion.hover) { hover = h } }
                .contentShape(Capsule())
        }
    }
}
