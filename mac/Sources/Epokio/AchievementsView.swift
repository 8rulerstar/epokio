import SwiftUI

// 업적 화면: 배지 격자. 딴 것은 등급 색, 못 딴 것은 흐리게, 여러 번 해야 하는 것은 진행 막대(37/50).
// 숨은 업적은 따기 전까지 "?"로만 보인다.

struct AchievementsView: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @AppStorage("achievementAlerts") private var alerts = true
    private var book: Trophies { .shared }

    var body: some View {
        let done = Trophies.all.filter { book.unlocked[$0.id] != nil }.count
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Achievements").font(.role(.title))
                        Text(verbatim: L("%d of %d unlocked", done, Trophies.all.count)).font(.role(.callout)).foregroundStyle(ink.soft)
                            .contentTransition(.numericText()).animation(Motion.change, value: done)
                    }
                    Spacer()
                    Toggle("Show when unlocked", isOn: $alerts).toggleStyle(.switch).controlSize(.small)
                        .help("Show a banner when you unlock an achievement")
                }
                CapsuleBar(value: Double(done) / Double(max(Trophies.all.count, 1)), tint: .gold, height: 6)
                    .animation(Motion.progress, value: done)
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 200), spacing: 12)], spacing: 12) {
                    ForEach(Array(Trophies.all.enumerated()), id: \.element.id) { i, a in
                        Badge(a: a, at: book.unlocked[a.id], progress: book.progress[a.id] ?? 0).appearRise(i)
                    }
                }
            }
            .padding(24)
            .frame(maxWidth: 980, alignment: .leading)
        }
        .onAppear { book.evaluate(store) }
    }
}

/// 배지 한 칸
struct Badge: View {
    let a: Achievement
    let at: Date?
    let progress: Int
    @Environment(\.ink) private var ink
    @State private var hover = false
    private var on: Bool { at != nil }
    private var secret: Bool { a.hidden && !on }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                ZStack {
                    Circle().fill(on ? AnyShapeStyle(a.tier.color.gradient) : AnyShapeStyle(ink.faint.opacity(0.25)))
                    Circle().strokeBorder(on ? AnyShapeStyle(a.tier.color.opacity(0.6)) : AnyShapeStyle(ink.faint.opacity(0.4)), lineWidth: 1.5).padding(-3)
                    Image(systemName: secret ? "questionmark" : a.symbol)
                        .font(.ui(17, weight: .bold))
                        .foregroundStyle(on ? AnyShapeStyle(.white) : ink.faint)
                        .symbolEffect(.bounce, value: hover && on)
                }
                .frame(width: 42, height: 42)
                .rotation3DEffect(.degrees(hover && on ? 14 : 0), axis: (x: 0, y: 1, z: 0))
                VStack(alignment: .leading, spacing: 2) {
                    Text(verbatim: secret ? L("Hidden achievement") : a.title).font(.ui(13, weight: .semibold)).lineLimit(1)
                    Text(verbatim: on ? a.tier.title : (secret ? L("Keep training to find it") : a.detail))
                        .font(.ui(11)).foregroundStyle(on ? AnyShapeStyle(a.tier.color) : AnyShapeStyle(ink.soft)).lineLimit(2)
                }
            }
            if on, let at {
                Text(verbatim: a.detail + "  ·  " + at.formatted(date: .abbreviated, time: .omitted)).font(.ui(10.5)).foregroundStyle(ink.faint).lineLimit(1)
            } else if a.goal > 1 {
                HStack(spacing: 6) {
                    CapsuleBar(value: Double(progress) / Double(a.goal), tint: a.tier.color, height: 4)
                    Text(verbatim: "\(progress)/\(a.goal)").font(.ui(10.5, design: .monospaced)).foregroundStyle(ink.soft)
                        .contentTransition(.numericText())
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 92, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: Radius.card).fill(on ? AnyShapeStyle(a.tier.color.opacity(0.08)) : AnyShapeStyle(ink.faint.opacity(0.06))))
        .overlay(RoundedRectangle(cornerRadius: Radius.card).strokeBorder(on ? AnyShapeStyle(a.tier.color.opacity(hover ? 0.5 : 0.25)) : AnyShapeStyle(ink.faint.opacity(0.2))))
        .opacity(on ? 1 : 0.75)
        .hoverLift()
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(secret ? L("Hidden achievement") : a.detail)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text(verbatim: (secret ? L("Hidden achievement") : a.title) + ", " + (on ? L("Unlocked") : L("Locked"))))
    }
}

/// 홈의 "다음 업적" 칸
struct NextTrophy: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    var body: some View {
        if let a = Trophies.shared.next {
            let p = Trophies.shared.progress[a.id] ?? 0
            Button { withAnimation(Motion.change) { store.section = .trophies } } label: {
                HStack(spacing: 10) {
                    Image(systemName: a.symbol).font(.ui(14, weight: .semibold)).foregroundStyle(a.tier.color).frame(width: 22)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(verbatim: L("Next: %@", a.title)).font(.ui(12.5, weight: .medium))
                        Text(verbatim: a.detail).font(.ui(11)).foregroundStyle(ink.soft)
                    }
                    Spacer()
                    if a.goal > 1 {
                        CapsuleBar(value: Double(p) / Double(a.goal), tint: a.tier.color, height: 4).frame(width: 80)
                        Text(verbatim: "\(p)/\(a.goal)").font(.ui(11, design: .monospaced)).foregroundStyle(ink.soft)
                    }
                    Image(systemName: "chevron.right").font(.ui(10, weight: .semibold)).foregroundStyle(ink.faint)
                }
                .padding(10)
                .background(RoundedRectangle(cornerRadius: Radius.control).fill(a.tier.color.opacity(0.07)))
                .contentShape(Rectangle())
            }
            .buttonStyle(PressStyle())
            .hoverLift()
        }
    }
}
