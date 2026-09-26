import SwiftUI

// 키보드만으로: "학습" 메뉴(고른 학습에 하는 일) · 화면 앞뒤(⌘[ ⌘]) · 검색(⌘F) · 단축키 목록(⌘/).
// 목록 안의 한 글자 키(S 별표 등)는 각 목록의 onKeyPress. 여기 표(ShortcutList.all)가 ⌘/ 화면과 같은 한 벌이다.

extension Store {
    var selected: Run? { selectedRun.flatMap { id in runs.first { $0.id == id } } }

    /// 고른 학습에 하는 일(메뉴·단축키·명령 팔레트가 같이 쓴다)
    func starSelected() async {
        guard let r = selected else { return }
        let on = !(r.meta?.star ?? false)
        await saveMeta(r, self, ["star": on], done: on ? L("Star added") : L("Star removed"), undo: ["star": !on])
    }
    func trainAgainSelected() async {
        guard let r = selected, isLocal(r), let d: RunDetail = try? await client(for: r).get("run", ["path": r.path]) else {
            say(L("Pick a run on this Mac first."), bad: true); return
        }
        pendingTrainArgs = d.args; section = .train               // ★양식만 채운다. 시작은 사람이
    }
    func trySelected() {
        guard let r = selected, isLocal(r), FileManager.default.fileExists(atPath: r.path + "/weights/best.pt") else {
            say(L("This run has no best.pt to try."), bad: true); return
        }
        UserDefaults.standard.set(r.path + "/weights/best.pt", forKey: "tryModel"); section = .tryit
    }
    func reviewSelected() {
        guard let r = selected, isLocal(r), FileManager.default.fileExists(atPath: r.path + "/weights/best.pt") else {
            say(L("This run has no best.pt to check."), bad: true); return
        }
        pendingReviewModel = r.path + "/weights/best.pt"; section = .review
    }
    /// ⌘[ ⌘]: 옆 막대 순서대로 앞뒤 화면
    func stepSection(_ d: Int) {
        let all = Studio.Section.main + Studio.Section.more
        let i = all.firstIndex(of: section ?? .home) ?? 0
        section = all[(i + d + all.count) % all.count]
        Haptic.tick()
    }
}

struct RunCommands: Commands {
    let store: Store
    var body: some Commands {
        CommandMenu("Training run") {
            Button("Star or Unstar") { Task { await store.starSelected() } }.keyboardShortcut("d", modifiers: .command)
            Button("Copy Path") { if let r = store.selected { copyText(r.ssh?.path ?? r.path, store) } }
                .keyboardShortcut("c", modifiers: [.command, .option])
            Divider()
            Button("Train Again with These Settings") { Task { await store.trainAgainSelected() } }.keyboardShortcut("t", modifiers: [.command, .shift])
            Button("Try This Model") { store.trySelected() }.keyboardShortcut("y", modifiers: .command)
            Button("Check Mistakes in Review") { store.reviewSelected() }.keyboardShortcut("e", modifiers: [.command, .shift])
            Button("Open Folder") { if let r = store.selected, store.isLocal(r) { NSWorkspace.shared.open(URL(fileURLWithPath: r.path)) } }
                .keyboardShortcut("o", modifiers: [.command, .shift])
        }
        CommandGroup(after: .sidebar) {
            Button("Previous Screen") { store.stepSection(-1) }.keyboardShortcut("[", modifiers: .command)
            Button("Next Screen") { store.stepSection(1) }.keyboardShortcut("]", modifiers: .command)
            Button("Search Runs") { store.section = .runs; store.focusSearch += 1 }.keyboardShortcut("f", modifiers: .command)
        }
        CommandGroup(replacing: .help) {
            Button("Keyboard Shortcuts") { store.showShortcuts = true }.keyboardShortcut("/", modifiers: .command)
            Button("Your First Training (Tour)") { store.section = .home; store.tourStep = 0 }
        }
    }
}

enum ShortcutList {
    static let all: [(String, [(String, String)])] = [
        (L("Anywhere"), [("⌘K", L("Go to anything")), ("⌘0 – ⌘8", L("Screens")), ("⌘[  ⌘]", L("Previous or next screen")),
                         ("⌘F", L("Search runs")), ("⌘R", L("Refresh")), ("⇧⌘N", L("Notifications")), ("⌘,", L("Settings")),
                         ("⌥⌘E", L("Open Studio from anywhere")), ("⌘/", L("This list"))]),
        (L("Runs"), [("↑ ↓", L("Pick a run")), ("S · ⌘D", L("Star")), ("⌥⌘C", L("Copy path")), ("⇧⌘T", L("Train again (fills the form)")),
                     ("⌘Y", L("Try the model")), ("⇧⌘E", L("Check mistakes")), ("⇧⌘O", L("Open folder")), ("/", L("Search"))]),
        (L("Queue"), [("↑ ↓", L("Pick a job")), ("⌥↑  ⌥↓", L("Move up or down")), ("⌫", L("Cancel (asks first)"))]),
        (L("Review"), [("Space", L("Open or close the image")), ("← →", L("Previous or next image")), ("1 – 4", L("Mark the image")),
                       ("E", L("Fix the label")), ("⌘A", L("Select all")), ("Esc", L("Clear the selection")), ("⌘Z", L("Undo the last mark"))]),
        (L("Forms"), [("⌘Return", L("Start or save")), ("Esc", L("Cancel or close")), ("Tab", L("Next field"))]),
    ]
}

struct ShortcutsSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.ink) private var ink
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("Keyboard Shortcuts", systemImage: "keyboard").font(.role(.title))
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            ScrollView {
                LazyVGrid(columns: [GridItem(.flexible(), alignment: .top), GridItem(.flexible(), alignment: .top)], alignment: .leading, spacing: 18) {
                    ForEach(Array(ShortcutList.all.enumerated()), id: \.offset) { i, g in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(verbatim: g.0).font(.role(.headline))
                            ForEach(g.1, id: \.0) { k, what in
                                HStack(alignment: .firstTextBaseline) {
                                    Text(verbatim: k).font(.ui(12, weight: .semibold, design: .rounded))
                                        .padding(.horizontal, 6).padding(.vertical, 2)
                                        .background(.quaternary, in: RoundedRectangle(cornerRadius: Radius.chip))
                                        .frame(minWidth: 86, alignment: .leading)
                                    Text(verbatim: what).font(.ui(12.5)).foregroundStyle(ink.soft)
                                }
                            }
                        }
                        .appearRise(i)
                    }
                }
            }
        }
        .padding(22)
        .frame(width: 640, height: 520)
    }
}
