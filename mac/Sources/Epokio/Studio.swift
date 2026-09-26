import SwiftUI

// 메인 창. 초보자 모드와 전문가 모드가 여기서 갈린다. (지금은 뼈대)
struct Studio: View {
    @Environment(Store.self) private var store
    @State private var showPalette = false
    @AppStorage("onboarded") private var onboarded = false
    @State private var showOnboarding = false
    @State private var fileDrop = false                    // 파일을 창 위로 끌고 있다

    enum Section: String, CaseIterable, Identifiable {
        case home = "Home", runs = "Runs", train = "Train", tryit = "Try it", label = "Auto-label", review = "Review", queue = "Queue", data = "Datasets", trophies = "Achievements"
        // ★알림은 오른쪽 위 종(팝오버). 예전 "알림·시스템" 화면은 "곧 제공"만 떠서 지웠다
        var id: String { rawValue }
        var title: String {
            switch self {
            case .home: L("Home"); case .runs: L("Runs"); case .train: L("Train"); case .tryit: L("Try it"); case .label: L("Auto-label")
            case .review: L("Review"); case .queue: L("Queue"); case .data: L("Labels"); case .trophies: L("Achievements")
            }
        }
        var symbol: String {
            switch self {
            case .home: "house"
            case .runs: "chart.line.uptrend.xyaxis"
            case .train: "play.circle"
            case .tryit: "eye"
            case .data: "photo.stack"
            case .queue: "list.number"
            case .label: "wand.and.stars"
            case .review: "checkmark.rectangle.stack"
            case .trophies: "trophy"
            }
        }
    }

    var body: some View {
        @Bindable var store = store
        // 아이폰 듀오식: 왼쪽 가는 아이콘 레일 + 넓은 내용 (예전 220pt 글자 사이드바를 72pt로)
        HStack(spacing: 0) {
            IconRail().background(WindowFitter())
            Divider()
            Group {
            switch store.section ?? .home {
            case .home: HomeView()
            case .runs: RunsView()
            case .train: TrainView()
            case .tryit: TryItView()
            case .label: AutoLabelView()
            case .queue: QueueView()
            case .data: DatasetView()
            case .review: ReviewView()
            case .trophies: AchievementsView()
            }
            }
            // ★화면마다 최소 크기가 달라, 큰 화면(검수·데이터셋)으로 가면 창이 거기 맞춰 늘었다.
            //   여기서 최소 크기를 하나로 못박는다. 넘치는 내용은 각 화면의 스크롤이 받는다
            .frame(minWidth: 520, maxWidth: .infinity, minHeight: 420, maxHeight: .infinity, alignment: .top)
            .background(Color(nsColor: .windowBackgroundColor))      // ★화면마다 배경이 달라 오른쪽에 색 다른 띠가 남았다
            .overlay { ToastView() }
            .overlay { if fileDrop { FileDropHint().transition(.opacity) } }
            .animation(Motion.hover, value: fileDrop)
            .dropDestination(for: URL.self) { urls, _ in FileDrop.handle(urls, store) } isTargeted: { fileDrop = $0 }
            .overlay(alignment: .bottomTrailing) {
                if store.tourStep != nil {
                    TrainingTour().padding(18).transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .animation(Motion.appear, value: store.tourStep != nil)
            .onAppear { store.viewers += 1; ViewPrefs.applyStart(store) }
            .onDisappear { store.viewers = max(0, store.viewers - 1) }
        }
        .navigationTitle((store.section ?? .home).title)
        // 알림함: 사이드바가 아니라 오른쪽 위 종 버튼(macOS 앱들의 알림 자리)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { showPalette = true } label: { Image(systemName: "command") }
                    .help("Go to anything (⌘K)")
                    .keyboardShortcut("k", modifiers: .command)
            }
            ToolbarItem(placement: .primaryAction) {
                SettingsButton { Image(systemName: "gearshape") }.help("Settings")      // Studio에서도 설정을 바로 연다
            }
            ToolbarItem(placement: .primaryAction) {
                Button { store.showInbox.toggle() } label: {
                    Image(systemName: store.unread > 0 ? "bell.badge" : "bell")
                        .symbolRenderingMode(store.unread > 0 ? .multicolor : .monochrome)
                }
                .help("Notifications")
                .popover(isPresented: $store.showInbox, arrowEdge: .bottom) {
                    InboxView().frame(width: 400, height: 520).environment(store).withInk()
                }
            }
        }
        .sheet(isPresented: $showPalette) { CommandPalette().withInk() }
        .sheet(isPresented: $showOnboarding) { Onboarding().withInk() }
        .sheet(isPresented: $store.showShortcuts) { ShortcutsSheet().withInk() }
        .task { if !onboarded && !CommandLine.arguments.contains(where: { $0.hasPrefix("--snapshot") }) { showOnboarding = true } }
    }
}

/// 창이 화면보다 크게 열리면(옛 크기 기록, 작은 모니터로 옮김) 화면 안에 맞게 줄이고 가운데로.
private struct WindowFitter: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let v = NSView()
        DispatchQueue.main.async {
            guard let w = v.window, let screen = w.screen ?? NSScreen.main else { return }
            let vis = screen.visibleFrame
            if w.frame.height > vis.height * 0.92 || w.frame.width > vis.width * 0.95 {
                let size = NSSize(width: min(1040, vis.width * 0.85), height: min(700, vis.height * 0.85))
                w.setFrame(NSRect(x: vis.midX - size.width / 2, y: vis.midY - size.height / 2,
                                  width: size.width, height: size.height), display: true, animate: false)
            }
        }
        return v
    }
    func updateNSView(_ v: NSView, context: Context) {}
}
