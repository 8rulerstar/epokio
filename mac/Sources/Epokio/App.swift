import SwiftUI
import UserNotifications
import CoreSpotlight

@main
struct EpokioApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @State private var store = { SnapshotIsolation.boot(); return Store(agents: Config.agents) }()   // 스냅샷이면 설정을 읽기 전에 격리

    init() {
        SnapshotIsolation.boot()          // 스냅샷이면 무엇보다 먼저 격리(가짜 홈으로 다시 실행)
        Migration.run()
        SnapshotMode.runIfRequested()
        Task { @MainActor in await AgentLauncher.shared.ensureRunning() }
        Notifier.shared.requestPermission()
        NotificationCenter.default.addObserver(forName: NSApplication.willTerminateNotification,
                                               object: nil, queue: .main) { _ in
            MainActor.assumeIsolated { AgentLauncher.shared.stop() }     // 내가 띄운 agent는 같이 끈다
        }
    }

    var body: some Scene {
        MenuBarExtra {
            Popover().environment(store).withInk().followsTextSize()
        } label: {
            MenuBarLabel().modifier(StudioOpener()).environment(store)
        }
        .menuBarExtraStyle(.window)       // 팝오버 창. macOS 26+에서는 시스템이 리퀴드 글라스로 그린다

        Window("Epokio Studio", id: "studio") {
            Studio().environment(store).withInk().followsTextSize()
                .onContinueUserActivity(CSSearchableItemActionType) { a in       // Spotlight에서 학습을 눌렀을 때
                    if let id = a.userInfo?[CSSearchableItemActivityIdentifier] as? String { store.open(run: id) }
                }
                .onAppear { NSApp.setActivationPolicy(.regular); NSApp.activate() }   // 창이 열려 있는 동안 Dock·⌘Tab에 보인다
                .onDisappear { NSApp.setActivationPolicy(.accessory) }
        }
        .commands { GoCommands(store: store); RunCommands(store: store); UpdateCommands() }
        .defaultSize(width: 1040, height: 700)
        .windowResizability(.contentMinSize)      // ★기본값이면 학습을 고를 때마다 내용 폭만큼 창이 다시 커졌다
        .defaultPosition(.center)

        Settings { SettingsView().environment(store).withInk() }
    }
}

extension Notification.Name {
    static let trainLonger = Notification.Name("epokio.trainLonger")
    static let stopRun = Notification.Name("epokio.stopRun")
    static let openStudio = Notification.Name("epokio.openStudio")
    static let openRun = Notification.Name("epokio.openRun")        // object: Run.id
}

/// macOS 알림을 누르면 Studio에서 그 학습의 상세를 연다. 앱이 앞에 있을 때도 알림을 띄운다.
final class NotificationRouter: NSObject, UNUserNotificationCenterDelegate, Sendable {
    static let shared = NotificationRouter()
    func userNotificationCenter(_ c: UNUserNotificationCenter, didReceive r: UNNotificationResponse) async {
        guard let id = r.notification.request.content.userInfo["run"] as? String else { return }
        let name: Notification.Name = switch r.actionIdentifier { case "longer": .trainLonger; case "stop": .stopRun; default: .openRun }
        await MainActor.run { NotificationCenter.default.post(name: name, object: id) }
    }
    func userNotificationCenter(_ c: UNUserNotificationCenter, willPresent n: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .sound]
    }
}

/// 메뉴바 아이콘이 노치 뒤로 밀려 안 보여도 앱에 들어갈 수 있게: 실행할 때, 앱을 다시 열 때 Studio를 연다.
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ n: Notification) {
        UNUserNotificationCenter.current().delegate = NotificationRouter.shared
        MenuBarRightClick.install()
        guard !CommandLine.arguments.contains(where: { $0.hasPrefix("--snapshot") }) else { return }
        GlobalHotKey.shared.apply()                                   // ⌥⌘E: 어디서든 Studio
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { NotificationCenter.default.post(name: .openStudio, object: nil) }
    }
    /// Spotlight에서 학습을 누르면 여기로도 온다(메뉴바 앱이라 창이 없을 수 있다)
    func application(_ app: NSApplication, continue a: NSUserActivity, restorationHandler: @escaping ([any NSUserActivityRestoring]) -> Void) -> Bool {
        guard a.activityType == CSSearchableItemActionType, let id = a.userInfo?[CSSearchableItemActivityIdentifier] as? String else { return false }
        NotificationCenter.default.post(name: .openRun, object: id)
        return true
    }
    func applicationShouldHandleReopen(_ app: NSApplication, hasVisibleWindows: Bool) -> Bool {
        NotificationCenter.default.post(name: .openStudio, object: nil)
        return true
    }
}

private struct StudioOpener: ViewModifier {
    @Environment(\.openWindow) private var openWindow
    @Environment(Store.self) private var store
    func body(content: Content) -> some View {
        content
            .onReceive(NotificationCenter.default.publisher(for: .openStudio)) { _ in openWindow(id: "studio") }
            .onReceive(NotificationCenter.default.publisher(for: .openRun)) { n in
                if let id = n.object as? String { store.markRead(id); store.open(run: id) }
                openWindow(id: "studio"); NSApp.activate()
            }
            .onReceive(NotificationCenter.default.publisher(for: .trainLonger)) { n in     // 알림 "더 길게 학습"
                guard let id = n.object as? String, let run = store.runs.first(where: { $0.id == id }) else { return }
                Task {
                    guard let d: RunDetail = try? await store.client(for: run).get("run", ["path": run.path]) else { return }
                    var a = d.args
                    if let e = a["epochs"].flatMap(Double.init) { a["epochs"] = String(Int(e * 2)) }
                    a["weights"] = d.weights
                    store.pendingTrainArgs = a
                    store.section = .train
                    openWindow(id: "studio"); NSApp.activate()
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: .stopRun)) { n in         // 알림 "멈추기" · 메뉴바 우클릭 "멈추기"
                let path = (n.object as? String)?.split(separator: "|", maxSplits: 1).last.map(String.init)
                guard let job = store.jobs.first(where: { $0.state == "running" && (path == nil || $0.output == path) }) else {
                    store.say(L("Only trainings started from Epokio can be stopped here."), bad: true); return
                }
                Task { await store.act(L("Stopped %@", job.name)) { _ = try await AgentClient.local.post("jobs/\(job.id)/cancel") } }
            }
    }
}

enum Config {
    // 지금은 로컬 agent 하나. 원격 추가는 Studio 설정에서.
    static var agents: [URL] {
        let saved = UserDefaults.standard.stringArray(forKey: "agents") ?? ["http://127.0.0.1:8787"]
        return saved.compactMap(URL.init(string:))
    }
}

/// 메뉴 막대 "이동": ⌘1~7 화면, ⌘R 새로 고침, ⌘⇧N 알림. 메뉴에 보여서 단축키를 찾기 쉽다
struct GoCommands: Commands {
    let store: Store
    var body: some Commands {
        CommandMenu("Go") {
            let items: [(Studio.Section, KeyEquivalent)] = [(.home, "0"), (.runs, "1"), (.train, "2"), (.tryit, "3"), (.label, "4"),
                                                            (.review, "5"), (.queue, "6"), (.data, "7"), (.trophies, "8")]
            ForEach(items, id: \.0) { s, k in
                Button(s.title) { store.section = s }.keyboardShortcut(k, modifiers: .command)
            }
            Divider()
            Button("Notifications") { store.showInbox.toggle() }.keyboardShortcut("n", modifiers: [.command, .shift])
            Button("Refresh") { Task { _ = try? await AgentClient.local.post("refresh"); store.refresh() } }.keyboardShortcut("r", modifiers: .command)
        }
    }
}

/// 설정 열기. ★SettingsLink만 쓰면 메뉴바 앱(액세서리)이라 창이 다른 앱 뒤에 뜬다(2026-09-22 사용자 지적).
/// 앱을 앞으로 가져오고 설정 창을 맨 위로 올린다
struct SettingsButton<Label: View>: View {
    @Environment(\.openSettings) private var openSettings
    @ViewBuilder var label: () -> Label

    var body: some View {
        Button {
            NSApp.activate(ignoringOtherApps: true)
            openSettings()
            Task { @MainActor in
                for _ in 0..<10 {                       // 창이 생길 때까지 잠깐 기다렸다가 맨 앞으로
                    if let w = NSApp.windows.first(where: { $0.identifier?.rawValue.contains("Settings") == true && $0.isVisible }) {
                        w.makeKeyAndOrderFront(nil); w.orderFrontRegardless(); break
                    }
                    try? await Task.sleep(for: .milliseconds(50))
                }
            }
        } label: { label() }
    }
}
