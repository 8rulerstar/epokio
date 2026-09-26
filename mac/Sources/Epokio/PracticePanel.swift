import SwiftUI

// 연습 학습: GPU·데이터 없이 "학습하는 척". 곡선·메뉴바·알림이 진짜처럼 움직인다(agent의 epokio.practice).
// 결과는 ~/.epokio/runs/practice/. 목록엔 "연습" 배지가 붙고 업적의 학습 개수에선 빠진다.

enum PracticeShape: String, CaseIterable, Identifiable {
    case good, overfit, plateau, fail
    var id: String { rawValue }
    var title: String { switch self { case .good: L("Goes well"); case .overfit: L("Overfits"); case .plateau: L("Gets stuck"); case .fail: L("Crashes") } }
    var symbol: String { switch self { case .good: "chart.line.uptrend.xyaxis"; case .overfit: "chart.line.flattrend.xyaxis"; case .plateau: "equal"; case .fail: "bolt.trianglebadge.exclamationmark" } }
    var tint: Color { switch self { case .good: .good; case .overfit: .warn; case .plateau: .info; case .fail: .bad } }
    var lesson: String {
        switch self {
        case .good: L("Loss goes down and the score climbs, then levels off. This is what you want.")
        case .overfit: L("The training loss keeps falling but the validation loss turns up. The model is memorizing.")
        case .plateau: L("The score rises fast and then stops moving. More epochs will not help much.")
        case .fail: L("The run stops halfway with an error, like running out of GPU memory. Watch the alert.")
        }
    }
}

extension Run {
    /// 연습 학습(GPU 없이 곡선만)
    var isPractice: Bool { path.contains("/.epokio/runs/practice/") }
}

struct PracticePanel: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var shape: PracticeShape = .good
    @State private var epochs = 20.0
    @State private var fast = true
    @State private var busy = false
    @State private var sent = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Pretend to train. No GPU, no data, nothing to install.", systemImage: "sparkles.tv")
                .font(.role(.headline))
            Text("Epokio writes a made-up training curve, one epoch at a time. The menu bar, alerts and charts move like a real run, so you can learn how to read them.")
                .font(.role(.callout)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 10)], spacing: 10) {
                ForEach(PracticeShape.allCases) { s in
                    Button { withAnimation(Motion.change) { shape = s } } label: {
                        VStack(alignment: .leading, spacing: 6) {
                            Image(systemName: s.symbol).font(.ui(18, weight: .semibold)).foregroundStyle(s.tint)
                                .symbolEffect(.bounce, value: shape == s)
                            Text(verbatim: s.title).font(.ui(13, weight: .semibold))
                        }
                        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
                        .background(RoundedRectangle(cornerRadius: Radius.control).fill(s.tint.opacity(shape == s ? 0.14 : 0.05)))
                        .overlay(RoundedRectangle(cornerRadius: Radius.control).strokeBorder(s.tint.opacity(shape == s ? 0.7 : 0.15), lineWidth: shape == s ? 2 : 1))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(PressStyle()).hoverLift()
                    .accessibilityAddTraits(shape == s ? .isSelected : [])
                }
            }
            Label { Text(verbatim: shape.lesson) } icon: { Image(systemName: "lightbulb").foregroundStyle(.gold) }
                .font(.role(.callout)).foregroundStyle(ink.soft)
                .contentTransition(.opacity).animation(Motion.change, value: shape)
                .id(shape)
                .tip()

            HStack(spacing: 16) {
                Stepper(value: $epochs, in: 5...100, step: 5) {
                    Text(verbatim: L("%d epochs", Int(epochs))).font(.ui(13)).monospacedDigit().contentTransition(.numericText())
                }
                .animation(Motion.change, value: epochs)
                Picker("Speed", selection: $fast) {
                    Text("1 second per epoch").tag(true)
                    Text("5 seconds per epoch").tag(false)
                }
                .pickerStyle(.segmented).labelsHidden().frame(width: 300)
            }

            HStack {
                Text(verbatim: L("About %@", duration(epochs * (fast ? 1 : 5)))).font(.ui(11.5)).foregroundStyle(ink.soft)
                Spacer()
                Button { Task { await start() } } label: {
                    Label(busy ? "Adding…" : "Start Practice Run", systemImage: "play.fill")
                        .font(.ui(14, weight: .semibold)).padding(.horizontal, 10).padding(.vertical, 4)
                        .symbolEffect(.bounce, value: sent)
                }
                .primaryButton().controlSize(.large).disabled(busy)
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
    }

    private func start() async {
        busy = true; defer { busy = false }
        let name = "practice_\(shape.rawValue)"
        let params: [String: Any] = ["shape": shape.rawValue, "epochs": Int(epochs), "seconds": fast ? 1 : 5, "name": name]
        nonisolated(unsafe) let body: [String: Any] = ["kind": "practice", "name": name, "params": params]
        do {
            _ = try await AgentClient.local.post("jobs", body)
            sent += 1; Haptic.success()
            store.say(L("Practice run started. Watch the menu bar."), actionTitle: L("Open Runs")) { store.section = .runs }
            store.refresh()
        } catch { store.say(error.localizedDescription, bad: true) }
    }
}
