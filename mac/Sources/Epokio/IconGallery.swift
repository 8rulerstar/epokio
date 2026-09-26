import SwiftUI

// 설정 → 모양 → 메뉴바 아이콘: 목록 대신 전부 펼친 갤러리. 칸마다 실제로 움직이는 미리보기(메뉴바와 같은 그림 함수).
// 일부 예쁜 아이콘은 업적으로 연다(업적을 켠 사람에게만. 업적을 끄면 모두 열려 있다).

extension BarStyle {
    /// 이 아이콘을 여는 업적(없으면 처음부터 열림)
    var unlockedBy: String? {
        switch self {
        case .rocket: "ship"             // 모델을 사용 중으로
        case .planet: "runs10"           // 학습 10개
        case .dino: "sweep"              // 첫 스윕
        case .neuron: "smart"            // 똑똑한 스윕
        case .fish: "review100"          // 검수 100장
        case .coffee: "night"            // 숨은 업적: 새벽 학습
        default: nil
        }
    }
    @MainActor var locked: Bool {
        guard UserDefaults.standard.bool(forKey: "achievements"), let a = unlockedBy else { return false }
        // 쓰고 있던 모양은 절대 뺏지 않는다. 업적을 끈 채로 고른 아이콘이 있는데 나중에 업적을 켜면
        // 그 칸이 자물쇠로 바뀌어(고른 칸인데도) 다시 못 고르는 상태가 됐다. 업적을 켜는 것이 손해가 되면 안 된다
        if UserDefaults.standard.string(forKey: "barStyle") == rawValue { return false }
        return Trophies.shared.unlocked[a] == nil
    }
}

struct IconGallery: View {
    @Binding var selected: BarStyle
    @Environment(Store.self) private var store
    @Environment(\.accessibilityReduceMotion) private var reduce

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            group("Progress", BarStyle.still)
            group("Characters", BarStyle.characters)
            group("Mine", BarStyle.mine)
        }
    }

    private func group(_ title: LocalizedStringKey, _ styles: [BarStyle]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.role(.caption, weight: .semibold)).foregroundStyle(.secondary)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 5), spacing: 6) {
                ForEach(styles) { s in
                    StyleTile(style: s, on: selected == s, locked: s.locked) {
                        if s.locked, let id = s.unlockedBy, let a = Trophies.all.first(where: { $0.id == id }) {
                            Haptic.tick()
                            store.say(a.hidden ? L("Unlock: hidden achievement") : L("Unlock: %@", a.detail),
                                      actionTitle: L("See")) { store.section = .trophies }
                        } else {
                            withAnimation(Motion.celebrate) { selected = s }
                        }
                    }
                }
            }
        }
    }
}

/// 갤러리 한 칸: 그 아이콘이 메뉴바에서처럼 움직인다
struct StyleTile: View {
    let style: BarStyle
    let on: Bool
    let locked: Bool
    let pick: () -> Void
    @State private var hover = false
    @Environment(\.accessibilityReduceMotion) private var reduce
    @AppStorage("animations") private var animations = true
    @Environment(\.styleHover) private var styleHover

    var body: some View {
        Button(action: pick) {
            VStack(spacing: 3) {
                ZStack {
                    // ★움직이는 칸만 다시 그린다(올린 칸·고른 칸). 예전엔 탭이 보이는 내내 모든 칸을 초당 20번
                    TimelineView(.animation(minimumInterval: 1 / 12, paused: reduce || !animations || locked || !(hover || on))) { tl in
                        preview(tl.date.timeIntervalSinceReferenceDate)
                    }
                    .opacity(locked ? 0.25 : 1).blur(radius: locked ? 1.2 : 0)
                    if locked { Image(systemName: "lock.fill").font(.ui(12, weight: .bold)) }
                }
                .frame(width: 44, height: 24)
                Text(style.title).font(.role(.badge, weight: on ? .semibold : .regular)).lineLimit(1).minimumScaleFactor(0.75)
            }
            .foregroundStyle(on ? AnyShapeStyle(.white) : AnyShapeStyle(.primary))
            .frame(maxWidth: .infinity).padding(.vertical, 6)
            .background(on ? AnyShapeStyle(LinearGradient.brand) : AnyShapeStyle(.quaternary.opacity(hover ? 0.9 : 0.5)),
                        in: .rect(cornerRadius: Radius.control))
            .scaleEffect(hover && !on ? 1.04 : 1)
            .contentShape(.rect)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h }; if !locked { styleHover(style, h) } }
        .help(locked ? L("Locked") : style.name)
        .accessibilityLabel(Text(verbatim: style.name + (locked ? ", " + L("Locked") : "")))
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    /// 움직임: 올리거나 골랐을 때만(가만히 있을 땐 첫 모습. 열 개가 한꺼번에 뛰면 산만하다)
    @ViewBuilder private func preview(_ phase: Double) -> some View {
        let t = hover || on ? phase : 0
        let p = 0.62, f = Int(t * 8)
        switch style {
        case .mark: Image(nsImage: markImage(p, pulse: t)).renderingMode(.template)
        case .bar: Image(nsImage: barImage(p, sheen: t, w: 40)).renderingMode(.template)
        case .gauge: Image(nsImage: gaugeImage(p, wobble: t)).renderingMode(.template)
        case .dots: Text(String(BarStyle.spin[f % BarStyle.spin.count])).font(.system(size: 15, design: .monospaced))
        case .orbit: Text(String(BarStyle.orbitF[f % BarStyle.orbitF.count])).font(.system(size: 15, design: .monospaced))
        case .wave: Text(String((0..<3).map { BarStyle.waveF[(f + $0 * 3) % BarStyle.waveF.count] })).font(.system(size: 13, design: .monospaced))
        case .percent: Text(verbatim: "62%").font(.system(size: 12.5, weight: .semibold, design: .monospaced))
        case .custom:
            if let img = CustomMark.image() { Image(nsImage: img) } else { Image(systemName: "photo.badge.plus") }
        case .customAnim:
            if let img = CustomAnim.image(t * 1.2) { Image(nsImage: img) } else { Image(systemName: "film.stack") }
        default:
            if let r = style.runner {
                Image(nsImage: r.image(t * 1.1)).renderingMode(.template).resizable().interpolation(.high).frame(width: 36, height: 24)
            }
        }
    }
}
