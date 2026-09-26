import SwiftUI

// "첫 학습 따라하기": 학습이 처음인 사람용 5단계. Studio 오른쪽 아래에 떠 있는 안내 카드라 화면을 가리지 않고 같이 만질 수 있다.
//  1 학습이란  2 연습 학습 시작(GPU 없이)  3 곡선 읽기(도는 연습 학습을 실시간으로)  4 나쁜 곡선 보기(과적합)  5 진짜 학습으로
// ★진짜 학습은 자동으로 시작하지 않는다. 학습 화면으로 데려가기만 한다(사람이 시작을 누른다).
// 다시 보기: Help 메뉴 "첫 학습 따라하기", 처음 안내 마지막 장, 빈 홈.

extension Store {
    /// 따라하기 단계(0~4). nil이면 꺼짐
    static let tourSteps = 5
}

struct TrainingTour: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var busy = false
    @State private var bump = 0

    private var step: Int { store.tourStep ?? 0 }
    /// 따라하기가 시작한 연습 학습(가장 최근 것)
    private var practice: Run? { store.runs.filter(\.isPractice).min { $0.idle < $1.idle } }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "graduationcap.fill").foregroundStyle(.tint).symbolEffect(.bounce, value: step)
                Text("Your first training").font(.ui(13, weight: .semibold))
                Spacer()
                Text(verbatim: "\(step + 1)/\(Store.tourSteps)").font(.ui(11, design: .monospaced)).foregroundStyle(ink.soft)
                    .contentTransition(.numericText())
                IconButton(symbol: "xmark", help: "Close the tour") { withAnimation(Motion.change) { store.tourStep = nil } }
            }
            CapsuleBar(value: Double(step + 1) / Double(Store.tourSteps), tint: .brand, height: 4)
            Group {
                switch step {
                case 0: page("What is training?",
                             "A model looks at labeled pictures over and over. Each pass is an epoch. After each one it checks itself on pictures it did not study and gets a score.")
                case 1: page("Try it safely first",
                             "Start a practice run. It draws a made-up curve, one epoch per second. No GPU, no data, nothing to break.")
                case 2: watch
                case 3: page("What a bad run looks like",
                             "Overfitting: the training loss keeps falling, but the validation loss turns up. The model memorized its pictures instead of learning. Run one to see the shape.")
                default: page("Now a real one",
                              "You need a data.yaml (it says where the pictures and labels are). Pick it on the Train screen, choose Quick check, and press Start yourself. Epokio never starts real training for you.")
                }
            }
            .transition(.asymmetric(insertion: .move(edge: .trailing).combined(with: .opacity), removal: .opacity))
            .id(step)
            buttons
        }
        .padding(14)
        .frame(width: 330)
        .glass(RoundedRectangle(cornerRadius: Radius.card))
        .overlay(RoundedRectangle(cornerRadius: Radius.card).strokeBorder(Color.brand.opacity(0.35)))
        .shadow(color: .black.opacity(0.18), radius: 16, y: 6)
        .animation(Motion.change, value: step)
        .onChange(of: practice?.state) { _, s in                       // 연습 학습이 끝나면 저절로 다음 장
            if step == 2, s == "done" { Haptic.success(); advance() }
        }
    }

    private func page(_ title: LocalizedStringKey, _ text: LocalizedStringKey) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.ui(15, weight: .bold))
            Text(text).font(.ui(12.5)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
        }
    }

    /// 3단계: 도는 연습 학습을 실시간으로 읽어 준다
    private var watch: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Read the curve").font(.ui(15, weight: .bold))
            if let r = practice {
                HStack {
                    Text(verbatim: L("Epoch %d of %d", r.epoch, r.total ?? 0)).font(.ui(12, design: .monospaced)).contentTransition(.numericText())
                    Spacer()
                    if let b = r.best { Text(verbatim: L("best %@", String(format: "%.3f", b))).font(.ui(12, design: .monospaced)).foregroundStyle(.good).contentTransition(.numericText()) }
                }
                .animation(Motion.change, value: r.epoch)
                CapsuleBar(value: r.progress ?? 0, tint: .good, height: 6, shimmer: r.isLive)
            }
            Text("On the right, Loss should go down and Scores should go up, then flatten. Also look at the menu bar icon: it is running too. When this run ends you will get the same alert a real run sends.")
                .font(.ui(12.5)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder private var buttons: some View {
        HStack {
            if step > 0 { Button("Back") { withAnimation(Motion.change) { store.tourStep = step - 1 } }.buttonStyle(.plain).foregroundStyle(ink.soft) }
            Spacer()
            switch step {
            case 1: action("Start Practice Run", "play.fill") { await runPractice("good"); advance() }
            case 3: action("Run an Overfitting One", "chart.line.flattrend.xyaxis") { await runPractice("overfit") }
                Button("Next") { advance() }
            case 4: action("Go to Train", "arrow.right") {
                    store.section = .train; Haptic.success()
                    withAnimation(Motion.change) { store.tourStep = nil }
                    store.say(L("Tour done. Pick your data.yaml to begin."))
                }
            default: Button("Next") { advance() }.primaryButton().keyboardShortcut(.defaultAction)
            }
        }
        .controlSize(.regular)
    }

    private func action(_ title: LocalizedStringKey, _ symbol: String, _ run: @escaping () async -> Void) -> some View {
        Button { Task { busy = true; await run(); busy = false; bump += 1 } } label: {
            Label(title, systemImage: symbol).symbolEffect(.bounce, value: bump)
        }
        .primaryButton().disabled(busy)
    }

    private func advance() { Haptic.tick(); withAnimation(Motion.change) { store.tourStep = min(step + 1, Store.tourSteps - 1) } }

    private func runPractice(_ shape: String) async {
        let name = "tour_\(shape)"
        nonisolated(unsafe) let body: [String: Any] = ["kind": "practice", "name": name,
                                                       "params": ["shape": shape, "epochs": 20, "seconds": 1, "name": name]]
        do {
            _ = try await AgentClient.local.post("jobs", body)
            store.section = .runs
            store.refresh()
            for _ in 0..<10 {                                            // 목록에 뜨면 그 학습을 연다
                try? await Task.sleep(for: .milliseconds(700))
                if let r = store.runs.filter({ $0.isPractice && $0.path.contains(name) }).min(by: { $0.idle < $1.idle }) {
                    store.open(run: r.id); break
                }
            }
        } catch { store.say(error.localizedDescription, bad: true) }
    }
}
