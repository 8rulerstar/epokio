import SwiftUI

// 설정 → 모양 맨 위에 붙는 메뉴바 미리보기 띠. 진짜 메뉴바 라벨(MenuBarLabel)을 가짜 학습 하나로 그린다.
// 타일에 올리면 그 모양을 잠깐 보이고, 떼면 지금 고른 것으로 돌아간다.
// 움직임: 띠가 보일 때만, 메뉴바와 같은 상한(barMaxFPS ≤ 12). Reduce Motion·"애니메이션" 끔이면 멈춘 그림.

private struct StyleHoverKey: EnvironmentKey {
    static let defaultValue: @MainActor (BarStyle, Bool) -> Void = { _, _ in }
}

extension EnvironmentValues {
    /// 모양 타일에 마우스를 올리고 뗄 때(미리보기 띠가 받는다)
    var styleHover: @MainActor (BarStyle, Bool) -> Void {
        get { self[StyleHoverKey.self] }
        set { self[StyleHoverKey.self] = newValue }
    }
}

struct MenuBarPreview: View {
    var hovered: BarStyle?
    @AppStorage("barStyle") private var raw = BarStyle.mark.rawValue
    @AppStorage("animations") private var animations = true
    @Environment(\.accessibilityReduceMotion) private var reduce
    @State private var visible = false
    @State private var itemHover = false

    /// 62%, 에폭당 30초(빠른 편: 캐릭터가 달린다)
    static let sample = Run(name: "coco8", path: "/sample", epoch: 31, total: 50, elapsed: 930, eta: 570,
                            metric: 0.61, metric_name: "", best: 0.642, best_epoch: 29, state: "running", idle: 1)

    private let bg = Color(nsColor: .windowBackgroundColor)
    private let ink = Color(nsColor: .labelColor)
    private var still: Bool { reduce || !animations }
    private var shown: BarStyle { hovered ?? BarStyle.from(raw) }

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "apple.logo").font(.ui(13)).opacity(0.55)
            Spacer(minLength: 8)
            // 진짜 메뉴바처럼 한 색으로(메뉴바는 그림을 템플릿으로 칠한다): 라벨 모양을 가면으로 써서 글자색으로 칠한다
            MenuBarLabel(sample: Self.sample, styleOverride: hovered, frozen: true).hidden()
                .overlay {
                    Rectangle().fill(ink)
                        .mask { MenuBarLabel(sample: Self.sample, styleOverride: hovered, frozen: still || !visible).fixedSize() }
                }
                .id(shown)
                .transition(still ? .opacity : .opacity.combined(with: .scale(scale: 0.85)))
                .padding(.horizontal, 7).frame(height: 22)
                .background(ink.opacity(itemHover || hovered != nil ? 0.12 : 0), in: .rect(cornerRadius: 5))
                .onHover { h in withAnimation(Motion.hover) { itemHover = h } }
            Group {                                                   // 맥락용 가짜 시스템 아이콘(흐리게)
                Image(systemName: "wifi")
                Image(systemName: "battery.75percent")
                Image(systemName: "magnifyingglass")
                Text(verbatim: "9:41")
            }
            .font(.ui(12.5)).opacity(0.4)
            .accessibilityHidden(true)
        }
        .foregroundStyle(ink)                                     // 유리가 글자색을 멋대로 뒤집지 않게 창 글자색으로 고정
        .padding(.horizontal, 14)
        .frame(height: 30)
        .glass(RoundedRectangle(cornerRadius: Radius.control))
        .animation(still ? nil : Motion.change, value: shown)
        .padding(.horizontal, 16).padding(.top, 10).padding(.bottom, 8)
        .background {                                             // 창 바탕 + 아래 페이드: 스크롤한 내용이 띠 밑으로 스며들듯 사라진다
            VStack(spacing: 0) {
                Rectangle().fill(bg)
                LinearGradient(colors: [bg, bg.opacity(0)], startPoint: .top, endPoint: .bottom).frame(height: 14)
            }
            .padding(.bottom, -14)
            .ignoresSafeArea()
        }
        .onAppear { visible = true }
        .onDisappear { visible = false }
        .accessibilityElement(children: .contain)
    }
}
