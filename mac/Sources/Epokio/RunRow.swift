import SwiftUI

// 학습 목록 한 줄과 목록 위 작은 필터 칩(RunsView에서 나눔, 파일 400줄 규칙)

/// 목록 한 줄. 카드보다 작게, 상태 색·이름·점수만.
struct RunRow: View {
    let run: Run
    let checked: Bool?                       // 비교 모드일 때만 체크 표시
    @Environment(\.ink) private var ink
    @Environment(Store.self) private var store
    @AppStorage(ViewPrefs.densityKey) private var density = "regular"
    @Environment(\.accessibilityDifferentiateWithoutColor) private var noColor

    var body: some View {
        HStack(spacing: 9) {
            Capsule().fill(run.tint).frame(width: 3, height: 26).opacity(run.isLive ? 1 : 0.55)
            if let checked {
                Image(systemName: checked ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(checked ? AnyShapeStyle(.tint) : ink.faint)
                    .contentTransition(.symbolEffect(.replace))
            } else {
                Image(systemName: run.symbol).foregroundStyle(run.tint).font(.ui(12, weight: .semibold))
                    .help(run.stateText).accessibilityLabel(run.stateText)          // 뜻을 색·도움말에만 두지 않는다
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(run.displayName).font(.ui(12.5, weight: .medium)).lineLimit(1).truncationMode(.tail)
                    .help(run.displayName)
                Text(verbatim: "\(run.epoch)/\(run.total.map(String.init) ?? "?")" + (run.ssh.map { "  ·  " + $0.host } ?? (run.source == "local" ? "" : "  ·  \(run.source)"))          // 좁은 목록: "에폭" 글자를 빼고 숫자만
                     + ((run.meta?.tags ?? []).isEmpty ? "" : "  ·  #" + (run.meta?.tags ?? []).joined(separator: " #")))
                    .font(.ui(11)).foregroundStyle(ink.soft).lineLimit(1)
                if noColor && checked == nil {                                   // 색 없이 구분: 상태 이름을 글자로
                    Text(verbatim: run.stateText).font(.ui(10, weight: .semibold)).foregroundStyle(ink.soft)
                        .accessibilityHidden(true)
                }
            }
            Spacer(minLength: 4)
            if let st = run.meta?.stage.flatMap(Stage.init(rawValue:)), st != .none {
                Image(systemName: st.symbol).font(.ui(10)).foregroundStyle(st.color).transition(.scale).help(st.title)
            }
            if let w = run.format_warnings, !w.isEmpty {                       // 못 알아본 열·버전: 조용히 틀리지 않게
                Image(systemName: "exclamationmark.triangle").font(.ui(10)).foregroundStyle(.warn)
                    .help(w.joined(separator: "\n")).accessibilityLabel(Text("Unknown format"))
            }
            if run.isPractice {
                Text("Practice").font(.ui(9.5, weight: .semibold)).foregroundStyle(.info)
                    .padding(.horizontal, 5).padding(.vertical, 1).background(Color.info.opacity(0.12), in: Capsule())
                    .help("A practice run: a made-up curve, no GPU used")
            }
            if run.meta?.star == true {
                Image(systemName: "star.fill").font(.ui(10)).foregroundStyle(.gold)
                    .symbolEffect(.bounce, value: store.flashRun == run.id)
                    .transition(.scale.combined(with: .opacity))
            }
            VStack(alignment: .trailing, spacing: 2) {
                if let b = run.best {
                    Text(Fmt.metric(b, higher: run.metricHigher)).font(.ui(11.5, design: .monospaced)).foregroundStyle(ink.soft)
                        .contentTransition(.numericText())
                }
                if run.history.count >= 3 { Sparkline(values: run.history, tint: run.tint).frame(width: 44, height: 11) }
            }
        }
        .padding(.vertical, ViewPrefs.rowPadding(density))
        .animation(Motion.change, value: density)
        .background(RoundedRectangle(cornerRadius: 6).fill(.tint.opacity(store.flashRun == run.id ? 0.16 : 0)).padding(.horizontal, -4))
        .animation(Motion.celebrate, value: run.meta?.star)
        .animation(Motion.change, value: store.flashRun == run.id)          // 바뀐 줄이 잠깐 빛난다
    }
}

struct MiniChip: View {
    let title: String
    var symbol: String? = nil
    let on: Bool
    var compact = false                                    // 좁을 때: 켜진 칩만 글자, 나머지는 아이콘(도움말에 이름)
    let action: () -> Void
    @State private var hover = false
    var body: some View {
        Button { withAnimation(.snappy) { action() } } label: {
            HStack(spacing: 3) {
                if let symbol { Image(systemName: symbol).font(.ui(9, weight: .bold)) }
                if !compact || on || symbol == nil {
                    Text(verbatim: title).font(.ui(11.5, weight: on ? .semibold : .regular)).lineLimit(1).fixedSize()
                        .transition(.opacity.combined(with: .move(edge: .leading)))
                }
            }
            .padding(.horizontal, 7).padding(.vertical, 3)
            .foregroundStyle(on ? AnyShapeStyle(.white) : AnyShapeStyle(.primary))
            .background(on ? AnyShapeStyle(.tint) : AnyShapeStyle(.primary.opacity(hover ? 0.1 : 0.05)), in: Capsule())
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(title)
        .accessibilityLabel(title)
    }
}
