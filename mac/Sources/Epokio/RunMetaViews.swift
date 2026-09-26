import SwiftUI

// 학습에 사람이 붙이는 기록: 별표(아끼는 모델), 태그, 메모, 목표 점수.
// 저장은 그 학습이 있는 기계의 agent(~/.epokio/runmeta.json). 웹 화면·터미널에서도 같이 보인다.

/// 성공했는지 돌려준다(★실패해도 '저장됨'이 떠서 메모가 사라졌다). done을 주면 끝난 뒤 알림 띠, undo를 주면 그 띠에 "되돌리기"(되돌릴 값). 바뀐 줄은 목록에서 잠깐 빛난다(store.flashRun)
@discardableResult
@MainActor func saveMeta(_ run: Run, _ store: Store, _ changes: [String: Any], done: String? = nil, undo: [String: Any]? = nil) async -> Bool {
    nonisolated(unsafe) let body = changes.merging(["path": run.path]) { $1 }     // JSON 값만 담긴 사전
    do {
        try await store.client(for: run).post("meta", body)
        store.flash(run.id)
        if let done {
            Haptic.tick()
            nonisolated(unsafe) let back = undo
            if let back { store.say(done, actionTitle: L("Undo")) { Task { await saveMeta(run, store, back) } } } else { store.say(done) }
        }
        store.refresh()
        return true
    } catch {
        store.say(error.localizedDescription, bad: true)
        return false
    }
}

/// 내보내기 파일 쓰기: 되면 "저장함"과 Finder, 안 되면 빨간 띠(★예전엔 try?로 버려 실패해도 조용했다)
@MainActor func writeExport(_ text: String, to url: URL, _ store: Store) {
    do {
        try text.write(to: url, atomically: true, encoding: .utf8)
        Haptic.success(); store.say(L("Saved %@", url.lastPathComponent))
        NSWorkspace.shared.activateFileViewerSelecting([url])
    } catch { store.say(error.localizedDescription, bad: true) }
}

/// agent가 만든 보고서를 Finder에서 보여 준다. 실패도 알린다
@MainActor func showReport(_ store: Store, _ work: () async throws -> [String: Any]) async {
    do {
        guard let path = try await work()["path"] as? String else { throw URLError(.cannotParseResponse) }
        Haptic.success(); store.say(L("Report ready"))
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
    } catch { store.say(error.localizedDescription, bad: true) }
}

/// 글자를 클립보드에 넣고 "복사함" 알림 띠
@MainActor func copyText(_ text: String, _ store: Store, what: String = L("Path")) {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(text, forType: .string)
    Haptic.tick()
    store.say(L("Copied %@", what))
}

/// 별표. 누르면 튀어 오른다
struct StarButton: View {
    let run: Run
    @Environment(Store.self) private var store
    @State private var on = false
    var body: some View {
        Button {
            withAnimation(Motion.celebrate) { on.toggle() }
            Haptic.tick()
            Task { await saveMeta(run, store, ["star": on]) }
        } label: {
            Image(systemName: on ? "star.fill" : "star")
                .font(.ui(17, weight: .semibold))
                .foregroundStyle(on ? AnyShapeStyle(.gold) : AnyShapeStyle(.secondary))
                .symbolEffect(.bounce, value: on)
                .contentTransition(.symbolEffect(.replace))
        }
        .buttonStyle(PressStyle())
        .help(on ? "Starred. Click to remove." : "Star this run to find it again")
        .accessibilityLabel(on ? "Remove star" : "Star")
        .onAppear { on = run.meta?.star ?? false }
        .onChange(of: run.meta?.star) { _, v in on = v ?? false }
    }
}

/// 상세 화면의 "내 기록" 칸
struct RunNotes: View {
    let run: Run
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var tags = ""
    @State private var note = ""
    @State private var goal = ""
    @State private var saved = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle("Your notes", hint: L("Only on this machine. Also shown on the web page and in the terminal view."))
            HStack(spacing: 10) {
                Image(systemName: "tag").foregroundStyle(ink.soft).accessibilityHidden(true)
                TextField("Tags, separated by commas (for example: baseline, best)", text: $tags)
                    .textFieldStyle(.roundedBorder).onSubmit(save)
            }
            TextEditor(text: $note)
                .font(.ui(13))
                .frame(minHeight: 60, maxHeight: 120)
                .scrollContentBackground(.hidden)
                .padding(6)
                .background(.quaternary.opacity(0.35), in: .rect(cornerRadius: 8))
                .overlay(alignment: .topLeading) {
                    if note.isEmpty {
                        Text("What did you change in this run? What did you learn?").font(.ui(13)).foregroundStyle(ink.soft)
                            .padding(.horizontal, 11).padding(.vertical, 6).allowsHitTesting(false)
                    }
                }
            HStack(spacing: 8) {
                Image(systemName: run.meta?.goal_hit == true ? "target" : "scope")
                    .foregroundStyle(run.meta?.goal_hit == true ? AnyShapeStyle(.good) : AnyShapeStyle(ink.soft))
                    .symbolEffect(.bounce, value: run.meta?.goal_hit)
                    .accessibilityLabel(run.meta?.goal_hit == true ? "Goal reached" : "Goal")
                Text(L("Tell me when %@ reaches", run.metric_name.replacingOccurrences(of: "metrics/", with: ""))).font(.ui(12.5))
                TextField("0.80", text: $goal).textFieldStyle(.roundedBorder).frame(width: 70).onSubmit(save)
                if run.meta?.goal_hit == true {
                    Text("Reached").font(.ui(12, weight: .semibold)).foregroundStyle(.good)
                        .transition(.scale.combined(with: .opacity))
                }
                Spacer()
                if saved {
                    Label("Saved", systemImage: "checkmark").font(.ui(12)).foregroundStyle(.good)
                        .transition(.opacity.combined(with: .move(edge: .trailing)))
                }
                Button("Save", action: save).controlSize(.small).keyboardShortcut("s", modifiers: .command)
            }
        }
        .onAppear(perform: fill)
        .onChange(of: run.id) { fill() }
    }

    private func fill() {
        tags = (run.meta?.tags ?? []).joined(separator: ", ")
        note = run.meta?.note ?? ""
        goal = run.meta?.goal.map { String($0) } ?? ""
    }

    private func save() {
        let t = tags.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        var changes: [String: Any] = ["tags": t, "note": note]
        // 유한한 숫자만. ★Double("nan")·("inf")도 숫자로 읽혀, JSON으로 바꿀 때 앱이 죽을 수 있었다
        if let g = Double(goal.replacingOccurrences(of: ",", with: ".")), g.isFinite { changes["goal"] = g } else if goal.isEmpty { changes["goal"] = NSNull() }
        Task {
            guard await saveMeta(run, store, changes) else { return }
            withAnimation(.smooth) { saved = true }
            try? await Task.sleep(for: .seconds(1.6))
            withAnimation(.smooth) { saved = false }
        }
    }
}
