import SwiftUI

// 학습 화면 "내 스크립트" 모드: 아무 파이썬 학습 스크립트를 대기열에서 돌린다(Hugging Face·Lightning·Keras…).

extension TrainView {
    // ── 내 스크립트 ──
    var scriptPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Run any Python training script. Epokio reads what it writes: Hugging Face trainer_state.json, Lightning metrics.csv, Keras CSVLogger or results.csv.")
                .font(.ui(12.5)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
            field("doc.text.fill", "Script", placeholder: remote ? "D:\\code\\train.py" : "~/code/train.py", text: $script, pick: remote ? nil : .file)
            field("text.cursor", "Arguments", placeholder: "--epochs 3 --output_dir runs/bert", text: $scriptArgs, pick: nil)
            field("folder", "Run in folder", placeholder: L("optional, default: the script's folder"), text: $scriptFolder, pick: remote ? nil : .folder)
            field("eye", "Watch results in", placeholder: L("optional, the folder where the script saves results"), text: $watchFolder, pick: remote ? nil : .folder)
            step("Python", "Where to run.", symbol: "terminal") {
                Picker("", selection: $env) {
                    ForEach(envs) { e in Text(verbatim: "\(e.name)  ·  \(e.device)").tag(Optional(e)) }
                }.labelsHidden()
            }
        }
    }

    enum Pick { case file, folder }

    func field(_ symbol: String, _ title: LocalizedStringKey, placeholder: String, text: Binding<String>, pick: Pick?) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Label(title, systemImage: symbol).font(.ui(13, weight: .semibold))
            HStack {
                TextField(placeholder, text: text).textFieldStyle(.roundedBorder).font(.ui(12.5, design: .monospaced))
                if let pick {
                    IconButton(symbol: pick == .file ? "doc.badge.ellipsis" : "folder.badge.plus", help: "Choose") {
                        let p = NSOpenPanel(); p.canChooseFiles = pick == .file; p.canChooseDirectories = pick == .folder
                        if p.runModal() == .OK, let u = p.url { text.wrappedValue = u.path }
                    }
                }
            }
        }
    }

    /// 인자 문자열을 나눈다. 따옴표로 묶은 부분은 한 덩어리
    static func splitArgs(_ s: String) -> [String] {
        var out: [String] = [], cur = "", quote: Character?
        for ch in s {
            if let q = quote { if ch == q { quote = nil } else { cur.append(ch) } }
            else if ch == "\"" || ch == "'" { quote = ch }
            else if ch == " " { if !cur.isEmpty { out.append(cur); cur = "" } }
            else { cur.append(ch) }
        }
        if !cur.isEmpty { out.append(cur) }
        return out
    }

    func startScript() async {
        guard let env, !script.isEmpty else { return }
        busy = true; defer { busy = false }
        let path = (script as NSString).expandingTildeInPath
        let folder = scriptFolder.isEmpty ? (path as NSString).deletingLastPathComponent : (scriptFolder as NSString).expandingTildeInPath
        nonisolated(unsafe) let body: [String: Any] = ["kind": "script", "name": name.isEmpty ? (path as NSString).lastPathComponent : name,
                                                       "python": env.path, "cwd": folder,
                                                       "params": ["args": ["-u", path] + Self.splitArgs(scriptArgs)]]
        await store.act(L("Added to queue")) {
            try await client.post("jobs", body)
            if !watchFolder.isEmpty {                                  // 결과 폴더를 지켜보기에 넣어 목록에 뜨게
                try await client.post("roots", ["path": (watchFolder as NSString).expandingTildeInPath])
            }
        }
    }
}
