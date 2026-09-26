import SwiftUI

// 메뉴바를 눌렀을 때 뜨는 창. 한눈에 보기 전용 (자세한 건 Studio).
struct Popover: View {
    @Environment(\.ink) private var ink
    @Environment(Store.self) private var store
    @Environment(\.openWindow) private var openWindow
    @AppStorage("showSystem") private var showSystem = true
    @AppStorage("popJustFinished") private var popJustFinished = true
    @AppStorage("popQuick") private var popQuick = true
    @AppStorage("popRecent") private var popRecent = 3
    @AppStorage("popWidth") private var popWidth = "regular"
    @AppStorage("jevEnabled") private var jevEnabled = false
    @AppStorage("barStyle") private var barStyle = BarStyle.mark.rawValue
    private var jevOn: Bool { jevEnabled && Jev.key != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            ManualScanBanner().animation(Motion.change, value: store.scanMode)
            if popJustFinished, let j = store.justFinished {
                JustFinishedCard(item: j) { store.markRead(j.id); store.open(run: j.runID); openStudio() }
                    .transition(.move(edge: .top).combined(with: .opacity))
            }
            let resting = store.gotRuns && RestMode.isResting(runs: store.runs)      // 학습이 하나도 없으면 시스템 카드만(RestMode)
            if resting, let now = store.system.values.first?.now {
                RestModeCards(readings: RestReadings(now), onAddFolder: addFolder, onSamples: { Task { await Samples.add(store) } })
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
            if showSystem && !resting { SystemStrip().transition(.opacity) }
            if (BarStyle.characters + [.customAnim]).contains(BarStyle(rawValue: barStyle) ?? .mark) { PaceToggle().transition(.opacity) }
            if popQuick && !resting { QuickActions { s in store.section = s; openStudio() } }
            if jevOn { CommandBar { openStudio() }.transition(.opacity.combined(with: .move(edge: .top))) }
            let live = store.runs.filter(\.isLive)
            if store.runs.isEmpty {
                if !resting { EmptyHint() }
            } else if live.isEmpty {
                let recent = store.runs.filter { $0.idle < 7 * 86_400 }
                // ★같은 말이 네 번 나왔다: 머리말 "Idle" · RestCard 의 "All quiet" 과 "마지막 학습 N 전" ·
                //   바로 아래 첫 카드의 시계 값(같은 학습을 min(idle)로 고르므로 숫자까지 같다).
                //   아래에 보일 카드가 있으면 그 카드가 이미 다 말해 주므로 RestCard 를 넣지 않는다
                if recent.isEmpty && !(popJustFinished && store.justFinished != nil) {
                    RestCard(last: store.runs.min(by: { $0.idle < $1.idle }))
                }
                ForEach(recent.prefix(popRecent)) { card($0) }
            } else {
                LiveCard(run: live[0]) { store.open(run: live[0].id); openStudio() }
                    .transition(.opacity.combined(with: .scale(scale: 0.97)))
                ForEach(store.runs.filter { $0.id != live[0].id }.prefix(popRecent)) { card($0) }
            }
            if let slow = store.slowRoots["local"], !slow.isEmpty { SlowRootsNote(paths: slow).transition(.move(edge: .bottom).combined(with: .opacity)) }
            Divider()
            footer
        }
        .padding(Space.l)
        .frame(width: popWidth == "compact" ? 340 : 400)
        .overlay { ToastView() }
        .onAppear { store.viewers += 1 }
        .onDisappear { store.viewers = max(0, store.viewers - 1) }
        .animation(Motion.change, value: store.runs.map(\.id))
        .animation(Motion.change, value: store.justFinished?.id)
        .animation(Motion.change, value: store.slowRoots)
    }

    /// 카드를 누르면 Studio에서 그 학습의 상세가 열린다
    private func card(_ r: Run) -> some View {
        Button { store.open(run: r.id); openStudio() } label: { RunCard(run: r).contentShape(.rect) }   // 누르면 살짝 눌린다(탭 제스처는 반응이 없었다)
            .buttonStyle(PressStyle())
            .help("Show results")
            .contextMenu {                                  // 오른쪽 클릭: 자주 하는 일
                Button("Show Results", systemImage: "chart.xyaxis.line") { store.open(run: r.id); openStudio() }
                if store.isLocal(r) {
                    Button("Show in Finder", systemImage: "folder") { NSWorkspace.shared.open(URL(fileURLWithPath: r.path)) }
                    let best = r.path + "/weights/best.pt"
                    if FileManager.default.fileExists(atPath: best) {
                        Button("Try This Model", systemImage: "wand.and.stars") { UserDefaults.standard.set(best, forKey: "tryModel"); store.section = .tryit; openStudio() }
                    }
                }
                Divider()
                Button("Copy Path", systemImage: "doc.on.doc") { copyText(r.path, store) }
            }
    }

    private func openStudio() {
        openWindow(id: "studio")
        NSApp.activate()
    }

    private var header: some View {
        HStack(spacing: 10) {
            Image(nsImage: NSApplication.shared.applicationIconImage).resizable().frame(width: 30, height: 30)
                .shadow(color: .black.opacity(0.12), radius: 2, y: 1)
            VStack(alignment: .leading, spacing: 1) {
                Text("Training").font(.role(.headline, weight: .bold))
                let n = store.runs.filter(\.isLive).count
                HStack(spacing: 5) {
                    Circle().fill(n > 0 ? Color.good : Color.secondary.opacity(0.5)).frame(width: 6, height: 6)
                        .shadow(color: n > 0 ? .good.opacity(0.6) : .clear, radius: 3)
                    Text(n > 0 ? "\(n) active" : "Idle")
                        .font(.role(.caption)).foregroundStyle(ink.soft)
                        .contentTransition(.numericText())
                }
                .animation(Motion.change, value: n)
            }
            Spacer()
            IconButton(symbol: store.unread > 0 ? "bell.badge" : "bell", help: "Notifications") {
                store.showInbox = true; openStudio()
            }
            .symbolEffect(.bounce, value: store.unread)
            .overlay(alignment: .topTrailing) {
                if store.unread > 0 {
                    Text(verbatim: "\(min(store.unread, 99))").font(.role(.badge, weight: .bold)).foregroundStyle(.white)
                        .padding(.horizontal, 4).frame(minWidth: 15, minHeight: 15).background(.bad, in: Capsule())
                        .offset(x: 5, y: -4).allowsHitTesting(false)
                        .transition(.scale.combined(with: .opacity))
                }
            }
            IconButton(symbol: "macwindow", help: "Open Studio") { openStudio() }
            Menu {
                Button { store.refresh() } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                Button { Task { await exportReport() } } label: { Label("Export report", systemImage: "doc.text") }
            } label: { IconFace(symbol: "ellipsis.circle") }                  // 다른 아이콘 버튼처럼 올리면 바탕이 찬다
            .menuStyle(.button).buttonStyle(.plain).menuIndicator(.hidden).fixedSize().help("More")
        }
    }

    private var footer: some View {
        HStack {
            // ★기계 수가 아니라 지켜보는 폴더 수다. 옆 버튼이 폴더를 더하는데 숫자는 계속 1이었다.
            //   옛 agent는 roots를 안 보내므로 그때만 기계 수로 떨어진다
            let watched = store.rootCount.isEmpty ? store.agents.count : store.rootCount.values.reduce(0, +)
            Label(store.offline.isEmpty ? sources(watched, "Watching")
                                        : sources(store.offline.count, "offline", after: true),
                  systemImage: store.offline.isEmpty ? "folder" : "exclamationmark.triangle")
                .font(.ui(11))
                .foregroundStyle(store.offline.isEmpty ? ink.soft : AnyShapeStyle(.warn))
                .help(store.lastError.values.sorted().joined(separator: "\n"))      // 왜 끊겼는지
            Spacer()
            IconButton(symbol: "folder.badge.plus", help: "Watch another folder") { addFolder() }
            SettingsButton { IconFace(symbol: "gearshape") }
                .buttonStyle(PressStyle()).help("Settings")
            IconButton(symbol: "power", help: "Quit Epokio") { NSApp.terminate(nil) }
        }
    }

    private func exportReport() async {
        await showReport(store) { try await AgentClient.local.post("report", ["all": true]) }     // 감시 폴더가 여럿이면 범위를 밝혀야 한다
    }

    private func addFolder() {
        let p = NSOpenPanel()
        p.canChooseDirectories = true; p.canChooseFiles = false; p.allowsMultipleSelection = true
        p.prompt = String(localized: "Watch This Folder")
        p.message = String(localized: "Choose the folder where your training results are saved (usually 'runs')")
        NSApp.activate()
        guard p.runModal() == .OK else { return }
        Task {
            for u in p.urls { await store.act(L("Watching %@", u.lastPathComponent)) { try await AgentClient.local.post("roots", ["path": u.path]) } }
        }
    }

    private func sources(_ n: Int, _ word: String, after: Bool = false) -> String {
        // "source(s)" 금지. 언어마다 어순이 달라 문장 틀째로 번역한다
        switch (word, n == 1) {
        case ("Watching", true): return L("Watching 1 source")
        case ("Watching", false): return L("Watching %d sources", n)
        case (_, true): return L("1 source offline")
        default: return L("%d sources offline", n)
        }
    }
}
