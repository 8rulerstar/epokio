import SwiftUI

// 💡 해설 켜고 끄기. 키 하나(showTips, 기본 켬)로 앱 곳곳의 전구 설명을 숨긴다(자리까지 사라진다).

enum Tips {
    static let key = "showTips"
    static var on: Bool { UserDefaults.standard.object(forKey: key) as? Bool ?? true }
}

/// 전구 설명을 감싼다. 끄면 뷰가 빠지고, 켜고 끌 때 페이드 + 살짝 이동(Reduce Motion이면 페이드 없이 바로)
struct TipGate: ViewModifier {
    @AppStorage(Tips.key) private var show = true
    @Environment(\.accessibilityReduceMotion) private var reduce
    func body(content: Content) -> some View {
        Group {
            if show { content.transition(.opacity.combined(with: .move(edge: .top))) }
        }
        .animation(reduce ? nil : Motion.change, value: show)
    }
}

extension View {
    func tip() -> some View { modifier(TipGate()) }
}

/// 설정 → 꾸미기의 한 줄. 옆에 작은 미리보기 전구가 켜지고 꺼진다
struct TipsSettingsRow: View {
    @AppStorage(Tips.key) private var show = true
    @Environment(\.accessibilityReduceMotion) private var reduce
    @State private var hover = false

    var body: some View {
        Toggle(isOn: $show.animation(reduce ? nil : Motion.change)) {
            HStack(spacing: 8) {
                Image(systemName: show ? "lightbulb.fill" : "lightbulb.slash")
                    .foregroundStyle(show ? AnyShapeStyle(.gold) : AnyShapeStyle(.secondary))
                    .contentTransition(.symbolEffect(.replace))
                    .symbolEffect(.bounce, value: show)
                    .frame(width: 22, height: 22)
                    .background(Circle().fill(.gold.opacity(show ? (hover ? 0.22 : 0.14) : 0)))
                    .accessibilityHidden(true)
                Text("Tips")
            }
        }
        .help("Show 💡 hints across the app")
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
    }
}
