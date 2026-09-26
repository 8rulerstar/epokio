import SwiftUI
import AppKit

/// 문제 신고. 자동 전송은 없다: 모은 정보를 먼저 보여 주고, 사람이 누르면 GitHub 새 이슈 창을 열거나 복사한다.
/// 오류 기록은 agent(errlog.py)가 ~/.epokio/logs/errors.log 에 남긴다. 홈 경로는 `~`로 바뀌어 있다.
enum ReportIssue {
    static let repoURL = "https://github.com/8rulerstar/epokio"
    /// 브라우저·GitHub가 받는 URL 길이 여유(약 8KB). 넘으면 기록을 줄이고 전문은 복사로 안내한다
    static let maxURLLength = 7000

    static var logDir: URL { FileManager.default.homeDirectoryForCurrentUser.appending(path: ".epokio/logs") }

    static func scrub(_ s: String) -> String {
        let home = FileManager.default.homeDirectoryForCurrentUser.path(percentEncoded: false)
        let h = home.hasSuffix("/") ? String(home.dropLast()) : home
        return h.count > 1 ? s.replacingOccurrences(of: h + "/", with: "~/") : s   // 뒤에 / 가 붙을 때만: /Users/a 가 /Users/ab 를 먹지 않게
    }

    /// 최근 오류 기록(끝에서 maxChars 글자)
    static func recentLog(maxChars: Int = 6000) -> String {
        let text = ["errors.log.1", "errors.log"]
            .compactMap { try? String(contentsOf: logDir.appending(path: $0), encoding: .utf8) }
            .joined()
        let s = scrub(text).trimmingCharacters(in: .whitespacesAndNewlines)
        return s.count > maxChars ? String(s.suffix(maxChars)) : s
    }

    static var environment: [(String, String)] {
        let info = Bundle.main.infoDictionary
        let v = info?["CFBundleShortVersionString"] as? String ?? "dev"
        let b = info?["CFBundleVersion"] as? String ?? "-"
        let os = ProcessInfo.processInfo.operatingSystemVersion
        var machine = utsname(); uname(&machine)
        let arch = withUnsafeBytes(of: &machine.machine) { String(decoding: $0.prefix { $0 != 0 }, as: UTF8.self) }
        return [("app", "\(v) (\(b))"), ("os", "macOS \(os.majorVersion).\(os.minorVersion).\(os.patchVersion)"), ("machine", arch)]
    }

    static func body(note: String, log: String) -> String {
        let env = environment.map { "- \($0.0): \($0.1)" }.joined(separator: "\n")
        let what = note.trimmingCharacters(in: .whitespacesAndNewlines)
        return """
        ### What happened
        \(what.isEmpty ? "(describe what you were doing)" : what)

        ### Environment
        \(env)

        ### Recent errors
        ```
        \(log.isEmpty ? "(no errors recorded)" : log)
        ```
        """
    }

    /// 새 이슈 URL. 길면 기록을 뒤에서부터 남기며 줄인다(truncated=true)
    static func issueURL(title: String, note: String, log: String) -> (url: URL, truncated: Bool) {
        var cut = log
        var truncated = false
        while true {
            var c = URLComponents(string: repoURL + "/issues/new")!
            c.queryItems = [URLQueryItem(name: "title", value: title), URLQueryItem(name: "body", value: body(note: note, log: cut))]
            let url = c.url!
            if url.absoluteString.count <= maxURLLength || cut.isEmpty { return (url, truncated) }
            truncated = true
            cut = String(cut.suffix(max(0, cut.count * 2 / 3)))
            if cut.count < 40 { cut = "" }
        }
    }
}

/// 문제 신고 시트. 보이는 내용이 곧 보내질 내용이다(사람이 고칠 수 있다)
struct ReportIssueSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduce
    @State private var title = ""
    @State private var note = ""
    @State private var log = ""
    @State private var shown = false
    @State private var copied = false
    @State private var truncated = false
    @State private var logLines = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "ladybug").foregroundStyle(Color.brand)
                    .symbolEffect(.bounce, value: shown)
                Text("Report a problem").font(.role(.headline))
                Spacer()
                IconButton(symbol: "xmark", help: "Close") { dismiss() }
            }
            Text("Nothing is sent automatically. Review what will be shared, then open a GitHub issue or copy it.")
                .font(.role(.caption)).foregroundStyle(.secondary)

            TextField("Title", text: $title).textFieldStyle(.roundedBorder)
            field("What happened?") {
                TextEditor(text: $note).font(.role(.body)).frame(height: 70)
            }
            field("Environment") {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(Array(ReportIssue.environment.enumerated()), id: \.offset) { i, kv in
                        Text("\(kv.0): \(kv.1)").font(.role(.caption).monospaced())
                            .appearRise(i)
                    }
                }
            }
            field("Recent errors") {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 4) {
                        Text("\(logLines)").contentTransition(.numericText())
                        Text("lines, home folder shown as ~")
                    }
                    .font(.role(.caption)).foregroundStyle(.secondary)
                    .animation(reduce ? nil : Motion.change, value: logLines)
                    TextEditor(text: $log).font(.role(.caption).monospaced()).frame(height: 140)
                }
            }
            if truncated {
                Text("The log was shortened to fit a link. Use Copy to share all of it.")
                    .font(.role(.caption)).foregroundStyle(Color.warn)
                    .transition(reduce ? .opacity : .opacity.combined(with: .move(edge: .top)))
            }
            HStack {
                ReportButton(label: copied ? "Copied" : "Copy", symbol: copied ? "checkmark" : "doc.on.doc", primary: false, action: copy)
                Spacer()
                ReportButton(label: "Open GitHub issue", symbol: "arrow.up.right.square", primary: true, action: open)
            }
        }
        .padding(18)
        .frame(width: 480)
        .opacity(shown ? 1 : 0)
        .offset(y: shown || reduce ? 0 : 6)
        .onChange(of: log) { _, v in logLines = v.isEmpty ? 0 : v.split(separator: "\n").count }
        .onAppear {
            log = ReportIssue.recentLog()
            withAnimation(reduce ? nil : Motion.appear) { shown = true }
        }
    }

    private func field<C: View>(_ label: LocalizedStringKey, @ViewBuilder _ content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.role(.caption, weight: .semibold))
            content()
        }
    }

    private var finalTitle: String {
        let t = title.trimmingCharacters(in: .whitespaces)
        return t.isEmpty ? "Problem report" : t
    }

    private func copy() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString("# \(finalTitle)\n\n" + ReportIssue.body(note: note, log: log), forType: .string)
        withAnimation(reduce ? nil : Motion.celebrate) { copied = true }
        Haptic.success()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) { withAnimation(reduce ? nil : Motion.change) { copied = false } }
    }

    private func open() {
        let r = ReportIssue.issueURL(title: finalTitle, note: note, log: log)
        withAnimation(reduce ? nil : Motion.change) { truncated = r.truncated }
        NSWorkspace.shared.open(r.url)
    }
}

/// 신고 시트의 글자 버튼. 누르면 살짝 눌리고(PressStyle), 올리면 바탕이 짙어지고, 아이콘이 바뀔 때 튄다
private struct ReportButton: View {
    let label: LocalizedStringKey
    let symbol: String
    let primary: Bool
    let action: () -> Void
    @State private var hover = false
    @Environment(\.accessibilityReduceMotion) private var reduce

    var body: some View {
        Button(action: action) {
            Label { Text(label) } icon: {
                Image(systemName: symbol).contentTransition(reduce ? .identity : .symbolEffect(.replace))
            }
            .font(.role(.body, weight: .medium))
            .padding(.horizontal, 12).padding(.vertical, 6)
            .foregroundStyle(primary ? Color.white : Color.primary)
            .background(primary ? AnyShapeStyle(Color.brand.opacity(hover ? 1 : 0.88))
                                : AnyShapeStyle(Color.primary.opacity(hover ? 0.12 : 0.06)),
                        in: .rect(cornerRadius: 8))
            .contentShape(.rect)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
    }
}
