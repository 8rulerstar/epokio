import SwiftUI

/// 설정 → 메뉴바: 캐릭터가 무엇을 따라 달릴지 고른다(`barPaceSource`, RunnerPace.swift).
/// 알약 버튼 줄. 올리면 살짝 뜨고, 누르면 줄어든다(Motion.hover · PressStyle).
struct PaceSourceRow: View {
    @AppStorage(PaceSource.key) private var raw = PaceSource.train.rawValue
    @Environment(Store.self) private var store
    @State private var hovered: PaceSource?

    /// 아직 고른 적이 없으면 저절로 정해지는 값이 켜진 것으로 보인다
    private var current: PaceSource {
        PaceSource.effective(stored: UserDefaults.standard.string(forKey: PaceSource.key),
                             resting: store.gotRuns && RestMode.isResting(runs: store.runs))
    }

    private func symbol(_ s: PaceSource) -> String {
        switch s {
        case .train: return "chart.line.uptrend.xyaxis"
        case .idleCPU, .cpu: return "cpu"
        case .idleGPU: return "memorychip"
        case .aiUse: return "sparkles"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Character speed").font(.ui(13))
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 6, alignment: .leading)],
                      alignment: .leading, spacing: 6) {
                ForEach(PaceSource.allCases) { s in
                    let on = current == s
                    Button { withAnimation(Motion.change) { raw = s.rawValue } } label: {
                        Label(s.title, systemImage: symbol(s))
                            .font(.ui(11.5, weight: on ? .semibold : .regular))
                            .padding(.horizontal, 8).padding(.vertical, 4)
                            .foregroundStyle(on ? AnyShapeStyle(.white) : AnyShapeStyle(.primary))
                            .background(on ? AnyShapeStyle(.tint) : AnyShapeStyle(.quaternary.opacity(0.6)), in: Capsule())
                            .scaleEffect(hovered == s && !on ? 1.04 : 1)
                    }
                    .buttonStyle(PressStyle())
                    .onHover { h in withAnimation(Motion.hover) { hovered = h ? s : (hovered == s ? nil : hovered) } }
                }
            }
            if current == .aiUse {
                Text("Epokio watches how busy AI tools on this Mac are. It never reads what you typed or what they answered. AI tools can also report their own activity.")
                    .font(.ui(11.5)).foregroundStyle(.secondary)
                    .transition(.opacity)
            }
        }
        .animation(Motion.change, value: current)
    }
}
