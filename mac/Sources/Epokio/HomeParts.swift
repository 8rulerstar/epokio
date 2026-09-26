import SwiftUI

// 홈에서 쓰는 조용한 부품. 스크롤 처리(.epokioScroll)와 행 올림(.rowHover)은 다른 화면에도 그대로 붙일 수 있다.

extension View {
    /// 스크롤 화면 공통 처리: 스크롤 막대 숨김 · 위아래 가장자리 페이드(macOS 26은 시스템 soft 가장자리) ·
    /// 스크롤하면 제목이 유리 캡슐로 위에 붙는다(title을 주면). 움직임 줄이기·애니메이션 끔이면 페이드만 남는다
    func epokioScroll(title: LocalizedStringKey? = nil) -> some View { modifier(EpokioScroll(title: title)) }
    /// 스크롤 안의 칸: 화면 가장자리로 갈수록 옅어지고 살짝 작아진다
    func scrollRise() -> some View { modifier(ScrollRise()) }
    /// 목록 한 줄: 올리면 옅은 바탕이 생긴다(카드 없이 구분)
    func rowHover() -> some View { modifier(RowHover()) }
}

private struct EpokioScroll: ViewModifier {
    let title: LocalizedStringKey?
    @State private var offset: CGFloat = 0
    @Environment(\.accessibilityReduceMotion) private var reduce
    @AppStorage("animations") private var animations = true
    private var still: Bool { reduce || !animations }
    private var pinned: Bool { title != nil && offset > 110 }

    func body(content: Content) -> some View {
        edge(content.scrollIndicators(.never))
            .onScrollGeometryChange(for: CGFloat.self, of: { $0.contentOffset.y + $0.contentInsets.top }) { _, y in offset = y }
            .overlay(alignment: .top) {
                if pinned, let title {
                    Text(title).font(.role(.headline)).foregroundStyle(.primary)
                        .padding(.horizontal, 16).padding(.vertical, 7)
                        .glass(Capsule())
                        .padding(.top, 10)
                        .transition(still ? .opacity : .opacity.combined(with: .move(edge: .top)))
                }
            }
            .animation(still ? nil : Motion.change, value: pinned)
    }

    @ViewBuilder private func edge(_ v: some View) -> some View {
        if #available(macOS 26, *) {
            v.scrollEdgeEffectStyle(.soft, for: .vertical)
        } else {
            v.mask {
                VStack(spacing: 0) {
                    LinearGradient(colors: [.clear, .black], startPoint: .top, endPoint: .bottom).frame(height: min(max(offset, 0), 24))
                    Color.black
                    LinearGradient(colors: [.black, .clear], startPoint: .top, endPoint: .bottom).frame(height: 24)
                }
            }
        }
    }
}

private struct ScrollRise: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduce
    @AppStorage("animations") private var animations = true
    func body(content: Content) -> some View {
        let move = !(reduce || !animations)
        content.scrollTransition(.interactive, axis: .vertical) { e, phase in
            e.opacity(phase.isIdentity ? 1 : 0.35)
                .scaleEffect(phase.isIdentity || !move ? 1 : 0.97)
                .offset(y: move ? phase.value * 6 : 0)
        }
    }
}

private struct RowHover: ViewModifier {
    @State private var on = false
    func body(content: Content) -> some View {
        content
            .background(.quaternary.opacity(on ? 0.35 : 0), in: .rect(cornerRadius: Radius.control))
            .contentShape(.rect)
            .onHover { h in withAnimation(Motion.hover) { on = h } }
    }
}

/// 빠른 작업 막대: 아이콘만, 캡슐 하나. 이름은 올림 툴팁·우클릭 메뉴로
struct QuickBar: View {
    struct Item: Identifiable { let title: LocalizedStringKey; let symbol: String; let go: () -> Void; var id: String { symbol } }
    let items: [Item]
    var body: some View {
        HStack(spacing: 2) {
            ForEach(items) { QuickIcon(item: $0) }
        }
        .padding(4)
        .background(.quaternary.opacity(0.35), in: Capsule())          // 유리는 떠 있는 것에만(Components 규칙). 글자 위 막대라 조용한 표면으로
    }
}

private struct QuickIcon: View {
    let item: QuickBar.Item
    @State private var hover = false
    @State private var taps = 0
    var body: some View {
        Button { taps += 1; item.go() } label: {
            Image(systemName: item.symbol).font(.role(.headline)).symbolRenderingMode(.monochrome)
                .foregroundStyle(hover ? AnyShapeStyle(.brand) : AnyShapeStyle(.secondary))
                .symbolEffect(.bounce, value: taps)
                .frame(width: 40, height: 32)
                .background(.quaternary.opacity(hover ? 0.5 : 0), in: Capsule())
                .contentShape(Capsule())
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(Text(item.title))
        .accessibilityLabel(Text(item.title))
        .contextMenu { Button(action: item.go) { Label(item.title, systemImage: item.symbol) } }
    }
}

extension View {
    /// 목록 줄 사이 가는 선(카드 대신)
    func divided() -> some View { overlay(alignment: .bottom) { Divider().opacity(0.5).padding(.horizontal, 8) } }
}

/// 홈 요약의 큰 곡선 하나(점수 기록). 축·눈금 없이 선과 옅은 면만. 처음 나타날 때 왼쪽에서 그려진다
struct HeroCurve: View {
    let values: [Double]
    @State private var drawn: CGFloat = 0
    @Environment(\.accessibilityReduceMotion) private var reduce
    @AppStorage("animations") private var animations = true

    var body: some View {
        GeometryReader { g in
            let pts = points(in: g.size)
            ZStack {
                area(pts, g.size).fill(LinearGradient(colors: [Color.brand.opacity(0.22), Color.brand.opacity(0)], startPoint: .top, endPoint: .bottom))
                    .opacity(Double(drawn))
                line(pts).trim(from: 0, to: drawn).stroke(Color.brand, style: StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
            }
        }
        .onAppear { if reduce || !animations { drawn = 1 } else { withAnimation(Motion.progress) { drawn = 1 } } }
        .animation(Motion.change, value: values)
        .accessibilityHidden(true)
    }

    private func points(in s: CGSize) -> [CGPoint] {
        guard values.count > 1, let lo = values.min(), let hi = values.max() else { return [] }
        let span = max(hi - lo, 1e-9)
        return values.enumerated().map { i, v in
            CGPoint(x: s.width * CGFloat(i) / CGFloat(values.count - 1), y: s.height * (1 - CGFloat((v - lo) / span) * 0.9) - 2)
        }
    }
    private func line(_ p: [CGPoint]) -> Path { Path { path in guard let f = p.first else { return }; path.move(to: f); p.dropFirst().forEach { path.addLine(to: $0) } } }
    private func area(_ p: [CGPoint], _ s: CGSize) -> Path {
        var path = line(p)
        guard let l = p.last, let f = p.first else { return path }
        path.addLine(to: CGPoint(x: l.x, y: s.height)); path.addLine(to: CGPoint(x: f.x, y: s.height)); path.closeSubpath()
        return path
    }
}
