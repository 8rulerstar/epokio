import SwiftUI

// 학습 화면의 초보자 도우미: 파이썬 환경 자동 설치, data.yaml 만들기.

/// 학습용 파이썬이 없을 때(또는 고른 파이썬에 ultralytics가 없을 때) 뜨는 안내 카드.
/// 가상환경이 무엇인지 쉬운 말로 먼저 알리고, 버튼 하나로 설치한다.
struct PythonSetupCard: View {
    let hasAnyReady: Bool
    /// 설치할 기계. ★늘 이 Mac(local)으로 보내서, 원격 기계의 학습 화면에서 누르면 이 Mac에 파이썬이 깔렸다
    var client: AgentClient = .local
    let onInstalled: () -> Void
    @Environment(\.ink) private var ink
    @State private var jobID: String?
    @State private var state = ""                   // "", "running", "done", "failed"
    @State private var expanded = false
    @State private var hover = false

    var body: some View {
        // 한 줄 알림: 아이콘 · 제목 · 설치 버튼. 설명은 툴팁, 자세한 건 (i)를 눌러 펼친다
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                Image(systemName: state == "done" ? "checkmark.circle.fill" : state == "failed" ? "exclamationmark.triangle" : "shippingbox")
                    .font(.ui(15, weight: .semibold))
                    .foregroundStyle(state == "done" ? AnyShapeStyle(.good) : state == "failed" ? AnyShapeStyle(.warn) : AnyShapeStyle(.tint))
                    .symbolEffect(.bounce, value: state)
                    .contentTransition(.symbolEffect(.replace))
                    .frame(width: 20)
                Group {
                    switch state {
                    case "running": Text("Installing… Progress is in Queue.")
                    case "done": Text("Ready. \"epokio\" is now in the Python list.").foregroundStyle(.good)
                    case "failed": Text("Setup failed. Open Queue to see the log.")
                    default: Text(hasAnyReady ? "This Python can't train yet" : "Set up Python for training")
                    }
                }
                .font(.ui(12.5, weight: .medium)).lineLimit(1)
                .help("Epokio makes a separate Python environment just for training and installs Ultralytics and PyTorch in it. Your other Python setups are not touched.")
                Button { withAnimation(.smooth) { expanded.toggle() } } label: {
                    Image(systemName: "info.circle").rotationEffect(.degrees(expanded ? 90 : 0))
                }
                .buttonStyle(PressStyle()).foregroundStyle(ink.soft)
                .help("What is a Python environment?").accessibilityLabel(Text("What is a Python environment?"))
                Spacer(minLength: 8)
                switch state {
                case "running": ProgressView().controlSize(.small)
                case "done": EmptyView()
                case "failed": Button("Try Again") { Task { await start() } }.controlSize(.small)
                default:
                    Button { Task { await start() } } label: {
                        Label("Set Up Automatically", systemImage: "wand.and.stars")
                    }
                    .primaryButton().controlSize(.small)
                    .scaleEffect(hover ? 1.03 : 1)
                    .onHover { h in withAnimation(Motion.hover) { hover = h } }
                }
            }
            if expanded {
                VStack(alignment: .leading, spacing: 6) {
                    fact("folder", "Where", "~/.epokio/envs/epokio. Delete this folder to remove it completely.")
                    fact("arrow.down.circle", "Download", "About 1 to 3 GB. Takes 5 to 15 minutes on a normal connection.")
                    fact("lock.shield", "Safe", "Nothing is installed system-wide and no password is needed.")
                    fact("cpu", "Speed", "Uses the Apple GPU on Apple Silicon Macs, or NVIDIA with CUDA on a PC.")
                }
                .padding(.leading, 30)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 9)
        .glass(.rect(cornerRadius: 12))
        .animation(.smooth, value: state)
        .task(id: jobID) { await watch() }
    }

    private func fact(_ symbol: String, _ title: LocalizedStringKey, _ text: LocalizedStringKey) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: symbol).font(.ui(12)).foregroundStyle(.tint).frame(width: 16)
            Text(title).font(.ui(12, weight: .semibold)).frame(width: 70, alignment: .leading)
            Text(text).font(.ui(12)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func start() async {
        withAnimation(.smooth) { state = "running" }
        if let r = try? await client.post("jobs", ["kind": "setup"]), let id = r["id"] as? String {
            jobID = id
        } else {
            withAnimation { state = "failed" }
        }
    }

    /// 설치 작업이 끝날 때까지 지켜본다
    private func watch() async {
        guard let id = jobID else { return }
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(4))
            struct P: Decodable { let jobs: [Job] }
            guard let p: P = try? await client.get("jobs"), let j = p.jobs.first(where: { $0.id == id }) else { continue }
            if j.state == "done" { withAnimation(.smooth) { state = "done" }; onInstalled(); return }
            if j.state == "failed" || j.state == "cancelled" { withAnimation { state = "failed" }; return }
        }
    }
}

/// data.yaml이 없을 때: 이미지 폴더와 클래스 이름만 받아 만들어 준다.
struct DataYamlBuilder: View {
    let onCreated: (URL) -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.ink) private var ink
    @State private var train: URL?
    @State private var val: URL?
    @State private var classes = ""
    @State private var error: String?

    private var names: [String] {
        classes.split(whereSeparator: { $0 == "\n" || $0 == "," }).map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Make a data.yaml").font(.ui(18, weight: .bold))
            Text("YOLO needs a small file that says where your images are and what the classes are called. Fill in these and Epokio writes it for you.")
                .font(.ui(12.5)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
            folderRow("Training images", hint: "for example dataset/images/train", url: $train)
            folderRow("Validation images", hint: "optional. Without it, the training images are reused and scores look better than they are", url: $val)
            VStack(alignment: .leading, spacing: 6) {
                Text("Class names").font(.ui(13, weight: .semibold))
                Text("One per line, in the order of the numbers in your label files (the first line is class 0).")
                    .font(.ui(12)).foregroundStyle(ink.soft)
                TextEditor(text: $classes)
                    .font(.ui(13, design: .monospaced))
                    .frame(height: 110)
                    .scrollContentBackground(.hidden)
                    .padding(6)
                    .background(.quaternary.opacity(0.4), in: .rect(cornerRadius: 8))
                Text(L("%d classes", names.count)).font(.ui(11.5)).foregroundStyle(ink.soft).contentTransition(.numericText())
            }
            if let error { Label(error, systemImage: "exclamationmark.triangle").font(.ui(12)).foregroundStyle(.warn) }
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Create and Use") { create() }
                    .primaryButton().keyboardShortcut(.defaultAction)
                    .disabled(train == nil || names.isEmpty)
            }
        }
        .padding(22)
        .frame(width: 520)
        .onChange(of: train) { _, u in if classes.isEmpty, let u { classes = Self.guessClasses(near: u) } }
    }

    private func folderRow(_ title: LocalizedStringKey, hint: LocalizedStringKey, url: Binding<URL?>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.ui(13, weight: .semibold))
            HStack {
                Button { if let u = pickFolder() { withAnimation(.snappy) { url.wrappedValue = u } } } label: {
                    Label(url.wrappedValue?.lastPathComponent ?? L("Choose Folder…"), systemImage: url.wrappedValue == nil ? "folder" : "checkmark.circle.fill")
                        .contentTransition(.symbolEffect(.replace))
                }
                if let u = url.wrappedValue {
                    Text(verbatim: u.deletingLastPathComponent().path).font(.ui(11.5)).foregroundStyle(ink.soft)
                        .lineLimit(1).truncationMode(.head)
                }
            }
            Text(hint).font(.ui(11.5)).foregroundStyle(ink.soft)
        }
    }

    private func pickFolder() -> URL? {
        let p = NSOpenPanel(); p.canChooseDirectories = true; p.canChooseFiles = false
        return p.runModal() == .OK ? p.url : nil
    }

    /// classes.txt가 있으면 미리 채운다
    static func guessClasses(near u: URL) -> String {
        var dir = u
        for _ in 0..<3 {
            if let s = try? String(contentsOf: dir.appending(path: "classes.txt"), encoding: .utf8) { return s }
            dir = dir.deletingLastPathComponent()
        }
        return ""
    }

    private func create() {
        guard let train else { return }
        // 데이터셋 뿌리: images/train 이면 images의 위, 아니면 이미지 폴더의 위
        let root = train.deletingLastPathComponent().lastPathComponent == "images"
            ? train.deletingLastPathComponent().deletingLastPathComponent() : train.deletingLastPathComponent()
        func rel(_ u: URL) -> String {
            u.path.hasPrefix(root.path + "/") ? String(u.path.dropFirst(root.path.count + 1)) : u.path
        }
        var yaml = "# Made by Epokio\npath: \(root.path)\ntrain: \(rel(train))\nval: \(rel(val ?? train))\n\nnames:\n"
        for (i, n) in names.enumerated() { yaml += "  \(i): \(n)\n" }
        // ★있는 파일은 덮어쓰지 않는다
        var out = root.appending(path: "data.yaml")
        if FileManager.default.fileExists(atPath: out.path) { out = root.appending(path: "data_epokio.yaml") }
        do {
            try yaml.write(to: out, atomically: true, encoding: .utf8)
            onCreated(out); dismiss()
        } catch {
            self.error = L("Could not write the file: %@", error.localizedDescription)
        }
    }
}

// 큰 선택 버튼 (작업 종류)
struct Choice: View {
    let title: LocalizedStringKey
    let symbol: String
    let on: Bool
    let action: () -> Void
    @State var hover = false
    var body: some View {
        Button(action: action) {
            VStack(spacing: 6) {
                Image(systemName: symbol).font(.ui(18, weight: .medium))
                    .symbolEffect(.bounce, value: on)
                Text(title).font(.ui(12, weight: .semibold))
            }
            .frame(maxWidth: .infinity).padding(.vertical, 12)
            .background(on ? Color.brand.opacity(0.16) : .primary.opacity(hover ? 0.07 : 0.04),
                        in: .rect(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(on ? Color.brand.opacity(0.35) : .clear, lineWidth: 1))
            .foregroundStyle(on ? Color.brand : .primary)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

// 설정 한 줄. 종류(불리언·숫자·문자)에 맞는 입력칸.
struct FieldRow: View {
    @Environment(\.ink) var ink
    let field: Field
    @Binding var value: String
    var changed: Bool { value != (field.default?.text ?? "") }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(field.key).font(.ui(12.5, weight: .semibold, design: .monospaced))
                    if changed { Circle().fill(Color.brand).frame(width: 6, height: 6).transition(.scale) }
                }
                Text(field.help.replacingOccurrences(of: "^\\([^)]*\\)\\s*", with: "", options: .regularExpression))
                    .font(.ui(11.5)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 12)
            Group {
                if field.type == "bool" {
                    Toggle("", isOn: Binding(get: { value == "true" }, set: { value = $0 ? "true" : "false" }))
                        .toggleStyle(.switch).labelsHidden().accessibilityLabel(Text(verbatim: field.key))
                } else {
                    TextField(field.default?.text ?? "", text: $value)
                        .textFieldStyle(.roundedBorder).frame(width: 150)
                        .font(.ui(12, design: .monospaced))
                }
            }
        }
        .animation(.snappy, value: changed)
    }
}
