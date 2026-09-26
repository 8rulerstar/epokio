import SwiftUI
import UniformTypeIdentifiers

// 바로 시험해 보기. 이미지를 끌어다 놓으면 모델이 찾은 것을 그 자리에 그린다.
// 레퍼런스 아이디어: Apple Create ML의 Preview, Google Teachable Machine의 "try it". (코드는 가져오지 않음)
struct Prediction: Decodable {
    let names: [String: String]
    let size: [Int]
    let boxes: [EvalBox]
    let device: String?
    let cpu_because_training: Bool?
    let error: String?
}

struct TryItView: View {
    @Environment(\.ink) private var ink
    @AppStorage("tryModel") private var modelPath = ""
    @State private var envs: [PyEnv] = []
    @State private var env: PyEnv?
    @State private var image: URL?
    @State private var shown: NSImage?
    @State private var result: Prediction?
    @State private var busy = false
    @State private var conf = 0.25
    @State private var error: String?
    @State private var dropHover = false
    @State private var history: [URL] = []

    var body: some View {
        VStack(spacing: 0) {
            controls
            Divider()
            stage
            if !history.isEmpty { strip }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task {
            struct P: Decodable { let envs: [PyEnv] }
            if let p: P = try? await AgentClient.local.get("pythons") { envs = p.envs; env = p.envs.first(where: \.ready) }
        }
    }

    private var controls: some View {
        HStack(spacing: 12) {
            Button {
                let p = NSOpenPanel(); p.allowedContentTypes = [UTType(filenameExtension: "pt")!]
                if p.runModal() == .OK, let u = p.url { modelPath = u.path; rerun() }
            } label: {
                Label(modelPath.isEmpty ? L("Choose model…") : URL(fileURLWithPath: modelPath).lastPathComponent, systemImage: "cube.box")
            }
            Picker("", selection: $env) {
                ForEach(envs) { e in Text(e.name).tag(Optional(e)) }
            }.labelsHidden().frame(width: 140)
            Text("Confidence").font(.ui(11.5)).foregroundStyle(ink.soft)
            Slider(value: Binding(get: { conf }, set: { conf = ($0 * 20).rounded() / 20 }), in: 0.05...0.9) { editing in
                if !editing { rerun() }                      // 놓는 순간 다시 예측
            }.frame(width: 120)
            Text(conf, format: .number.precision(.fractionLength(2))).font(.ui(11.5, design: .monospaced))
            Spacer()
            if let r = result, r.cpu_because_training == true {
                Label("Using CPU while training runs", systemImage: "cpu").font(.ui(11.5)).foregroundStyle(.warn)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
    }

    private var stage: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 16)
                .strokeBorder(style: StrokeStyle(lineWidth: 1.5, dash: shown == nil ? [6, 5] : []))
                .foregroundStyle(dropHover ? Color.brand : .secondary.opacity(0.4))
                .background(Color.brand.opacity(dropHover ? 0.06 : 0), in: .rect(cornerRadius: 16))
            if let shown {
                Image(nsImage: shown).resizable().scaledToFit()
                    .overlay {
                        if let r = result { PredOverlay(pred: r) }
                    }
                    .overlay { if busy { ProgressView().controlSize(.large).padding(20).glass(radius: Radius.card) } }
                    .clipShape(.rect(cornerRadius: 12))
                    .padding(12)
                    .transition(.opacity.combined(with: .scale(scale: 0.98)))
            } else {
                VStack(spacing: 10) {
                    Image(systemName: "photo.badge.arrow.down").font(.ui(40, weight: .light)).foregroundStyle(ink.faint)
                        .accessibilityHidden(true)
                        .symbolEffect(.bounce, value: dropHover)
                    Text("Drop an image to see what your model finds").font(.ui(15, weight: .semibold))
                    Text(modelPath.isEmpty ? "Choose a model first (best.pt)." : "Or click to choose.").foregroundStyle(ink.soft)
                }
            }
            if let error {
                Label(error, systemImage: "exclamationmark.triangle").font(.ui(11.5)).foregroundStyle(.bad)
                    .padding(8).glass(radius: Radius.control)
                    .frame(maxHeight: .infinity, alignment: .bottom).padding()
            }
        }
        .padding(16)
        .contentShape(.rect)
        .onTapGesture { pickImage() }
        .accessibilityAddTraits(.isButton)
        .onDrop(of: [.fileURL], isTargeted: $dropHover) { items in
            _ = items.first?.loadObject(ofClass: URL.self) { u, _ in if let u { Task { @MainActor in load(u) } } }
            return true
        }
        .animation(.smooth, value: shown != nil)
        .overlay(alignment: .topTrailing) { summary }
    }

    @ViewBuilder private var summary: some View {
        if let r = result, !busy {
            let counts = Dictionary(grouping: r.boxes, by: \.cls).mapValues(\.count)
            VStack(alignment: .trailing, spacing: 4) {
                Text(r.boxes.isEmpty ? L("Nothing found") : L("%d found", r.boxes.count)).font(.ui(13, weight: .bold))
                ForEach(counts.keys.sorted(), id: \.self) { k in
                    Label("\(r.names[String(k)] ?? "\(k)") \(counts[k]!)", systemImage: "square.fill")
                        .font(.ui(11.5)).foregroundStyle(classColor(k))
                }
            }
            .padding(10).glass(radius: Radius.control).padding(28)
            .transition(.opacity.combined(with: .move(edge: .trailing)))
        }
    }

    // 최근에 시험한 이미지들. 눌러서 다시 본다
    private var strip: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 8) {
                ForEach(history, id: \.self) { u in
                    StripThumb(url: u, active: u == image).onTapGesture { load(u) }
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(Text(verbatim: u.lastPathComponent))
                        .accessibilityAddTraits(u == image ? [.isButton, .isSelected] : .isButton)
                }
            }
            .padding(10)
        }
        .frame(height: 76)
        .background(.quaternary.opacity(0.3))
    }

    private func pickImage() {
        let p = NSOpenPanel(); p.allowedContentTypes = [.image]
        if p.runModal() == .OK, let u = p.url { load(u) }
    }

    private func load(_ u: URL) {
        image = u
        if !history.contains(u) { history.insert(u, at: 0); history = Array(history.prefix(20)) }
        Task {
            shown = await loadThumb(u, max: 2000)
            await predict()
        }
    }

    private func rerun() { if image != nil { Task { await predict() } } }

    private func predict() async {
        guard let image, let env, !modelPath.isEmpty else { return }
        busy = true; error = nil; defer { busy = false }
        do {
            let d = try await AgentClient.local.post("predict", ["model": modelPath, "image": image.path,
                                                               "python": env.path, "conf": conf])
            let data = try JSONSerialization.data(withJSONObject: d)
            withAnimation(.smooth) { result = try? JSONDecoder().decode(Prediction.self, from: data) }
        } catch { self.error = error.localizedDescription }
    }
}

struct PredOverlay: View {
    let pred: Prediction
    var body: some View {
        canvas
            .accessibilityElement()
            .accessibilityLabel(pred.boxes.isEmpty ? L("Nothing found") : L("%d found", pred.boxes.count))
    }

    private var canvas: some View {
        Canvas { ctx, size in
            for b in pred.boxes {
                let c = classColor(b.cls)
                let r = CGRect(x: (b.box[0] - b.box[2] / 2) * size.width, y: (b.box[1] - b.box[3] / 2) * size.height,
                               width: b.box[2] * size.width, height: b.box[3] * size.height)
                ctx.fill(Path(r), with: .color(c.opacity(0.14)))
                ctx.stroke(Path(roundedRect: r, cornerRadius: 3), with: .color(c), lineWidth: 2.5)
                for k in b.kpts where k.count >= 2 {
                    let p = CGRect(x: k[0] * size.width - 4, y: k[1] * size.height - 4, width: 8, height: 8)
                    ctx.fill(Path(ellipseIn: p), with: .color(.white))
                    ctx.fill(Path(ellipseIn: p.insetBy(dx: 1.5, dy: 1.5)), with: .color(c))
                }
                let label = "\(pred.names[String(b.cls)] ?? "\(b.cls)") \(String(format: "%.0f%%", (b.conf ?? 0) * 100))"
                let t = ctx.resolve(Text(label).font(.ui(12, weight: .semibold)).foregroundStyle(.white))
                let s = t.measure(in: size)
                let tag = CGRect(x: r.minX, y: max(r.minY - s.height - 6, 0), width: s.width + 10, height: s.height + 6)
                ctx.fill(Path(roundedRect: tag, cornerRadius: 4), with: .color(c))
                ctx.draw(t, at: CGPoint(x: tag.minX + 5, y: tag.minY + 3), anchor: .topLeading)
            }
        }
        .allowsHitTesting(false)
    }
}

struct StripThumb: View {
    let url: URL
    let active: Bool
    @State private var img: NSImage?
    var body: some View {
        Group { if let img { Image(nsImage: img).resizable().scaledToFill() } else { Color.secondary.opacity(0.2) } }
            .frame(width: 70, height: 56).clipShape(.rect(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(active ? Color.brand : .clear, lineWidth: 2))
            .task { img = await loadThumb(url, max: 160) }
    }
}
