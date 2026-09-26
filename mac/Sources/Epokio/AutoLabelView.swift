import SwiftUI
import UniformTypeIdentifiers

// 오토라벨링: 모델 고르기 → 폴더 고르기 → 시작 → 결과 보고.
// ★기존 라벨은 절대 덮어쓰지 않는다. 결과는 대상 폴더 옆 labels_auto/ 에 따로 쓴다.
struct AutoLabelView: View {
    @Environment(\.ink) private var ink
    @State private var envs: [PyEnv] = []
    @State private var env: PyEnv?
    @State private var model: URL?
    @State private var folder: URL?
    @State private var conf = 0.25
    @State private var lowConf = 0.5
    @State private var status: String?
    @State private var busy = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Auto-label").font(.ui(22, weight: .bold))
                Text("Let a trained model draw the first boxes. You only fix what it got wrong.")
                    .foregroundStyle(ink.soft)
                HStack(spacing: 12) {
                    PickCard(title: "Model", hint: "your best.pt", symbol: "cube.box", url: $model,
                             types: [UTType(filenameExtension: "pt")!], folder: false)
                    Image(systemName: "arrow.right").foregroundStyle(ink.faint).accessibilityHidden(true)
                    PickCard(title: "Images", hint: "a folder of images", symbol: "photo.on.rectangle",
                             url: $folder, types: [], folder: true)
                }
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 7) {
                        Image(systemName: "slider.horizontal.below.rectangle").foregroundStyle(.tint).accessibilityHidden(true)
                        Text("Confidence").font(.ui(14, weight: .semibold))
                        Image(systemName: "info.circle").font(.ui(11)).foregroundStyle(ink.soft)
                            .help("Boxes below this are dropped. Lower keeps more (and more mistakes).")
                            .accessibilityLabel("Boxes below this are dropped. Lower keeps more (and more mistakes).")
                    }
                    HStack {
                        Slider(value: Binding(get: { conf }, set: { conf = ($0 * 20).rounded() / 20 }), in: 0.05...0.9)
                            .accessibilityLabel("Confidence").accessibilityValue(Text(conf, format: .number.precision(.fractionLength(2))))
                        Text(conf, format: .number.precision(.fractionLength(2)))
                            .font(.ui(13, design: .monospaced)).frame(width: 44)
                    }
                    Label("Flag for review when a box is below", systemImage: "flag").font(.ui(12)).foregroundStyle(ink.soft)
                    HStack {
                        Slider(value: Binding(get: { lowConf }, set: { lowConf = ($0 * 20).rounded() / 20 }), in: conf...0.95)
                        Text(lowConf, format: .number.precision(.fractionLength(2)))
                            .font(.ui(13, design: .monospaced)).frame(width: 44)
                    }
                }
                Picker("Python", selection: $env) {
                    ForEach(envs) { e in
                        Label("\(e.name)  ·  \(e.device)", systemImage: e.ready ? "checkmark.circle.fill" : "exclamationmark.circle")
                            .tag(Optional(e))
                    }
                }
                if let folder {
                    Label("Labels will be written to \(folder.deletingLastPathComponent().lastPathComponent)/labels_auto/. Your existing labels are not touched.",
                          systemImage: "lock.shield")
                        .font(.ui(11.5)).foregroundStyle(ink.soft)
                }
                HStack {
                    Spacer()
                    if let status { Text(status).font(.ui(11.5)).foregroundStyle(ink.soft) }
                    else if !busy, let why: LocalizedStringKey = model == nil ? "Choose a model first" : folder == nil ? "Choose a folder of images first" : env == nil ? "Choose a Python first" : nil {
                        Label(why, systemImage: "info.circle").font(.role(.caption)).foregroundStyle(ink.soft)   // 꺼진 이유를 글로
                    }
                    Button {
                        Task { await start() }
                    } label: {
                        Label(busy ? "Adding…" : "Start Auto-label", systemImage: "wand.and.stars")
                            .font(.ui(14, weight: .semibold)).padding(.horizontal, 10).padding(.vertical, 4)
                    }
                    .primaryButton().controlSize(.large)
                    .disabled(model == nil || folder == nil || env == nil || busy)
                }
            }
            .padding(28).frame(maxWidth: 720, alignment: .leading)
            .frame(maxWidth: .infinity)          // 가운데 두고 스크롤 영역은 창 끝까지
        }
        .task {
            struct R: Decodable { let envs: [PyEnv] }
            if let r: R = try? await AgentClient.local.get("pythons") {
                envs = r.envs; env = r.envs.first(where: \.ready)
            }
        }
    }

    private func start() async {
        guard let model, let folder, let env else { return }
        busy = true; defer { busy = false }
        do {
            try await AgentClient.local.post("jobs", [
                "kind": "autolabel", "name": folder.lastPathComponent, "python": env.path,
                "params": ["model": model.path, "source": folder.path, "conf": conf, "low_conf": lowConf]])
            withAnimation { status = L("Added to queue") }
        } catch { withAnimation { status = error.localizedDescription } }
    }
}

struct PickCard: View {
    @Environment(\.ink) private var ink
    let title: LocalizedStringKey
    let hint: LocalizedStringKey
    let symbol: String
    @Binding var url: URL?
    let types: [UTType]
    let folder: Bool
    @State private var hover = false

    private func choose() {
        let p = NSOpenPanel()
        p.canChooseDirectories = folder; p.canChooseFiles = !folder
        if !types.isEmpty { p.allowedContentTypes = types }
        if p.runModal() == .OK { url = p.url }
    }

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: url == nil ? symbol : "checkmark.circle.fill")
                .font(.ui(24, weight: .light))
                .foregroundStyle(url == nil ? AnyShapeStyle(ink.faint) : AnyShapeStyle(.good))
                .symbolEffect(.bounce, value: url)
            Text(title).font(.role(.body, weight: .semibold))                          // 무엇을 고르는지가 먼저, 고른 것은 아래
            Text(url?.lastPathComponent ?? String(localized: "Choose"))
                .font(.role(.caption)).foregroundStyle(url == nil ? AnyShapeStyle(ink.soft) : AnyShapeStyle(.good))
                .lineLimit(1).truncationMode(.middle)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 20)
        .background(.primary.opacity(hover ? 0.07 : 0.04), in: .rect(cornerRadius: 14))
        .contentShape(.rect)
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .onTapGesture { choose() }
        // Tab 으로 옮겨 오고 Space·Return 으로도 열리게 한다.
        // Button 으로 감싸는 길은 막혀 있다. .buttonStyle(.plain) 인 Button 은 Tab 이 들르지 않는다(작은 시험 앱으로 확인).
        // focusable 이라야 포커스를 받고, 그래서 키도 직접 받는다
        .focusable()
        .onKeyPress(.space) { choose(); return .handled }
        .onKeyPress(.return) { choose(); return .handled }
        .onDrop(of: [.fileURL], isTargeted: $hover) { items in
            _ = items.first?.loadObject(ofClass: URL.self) { u, _ in if let u { Task { @MainActor in url = u } } }
            return true
        }
    }
}
