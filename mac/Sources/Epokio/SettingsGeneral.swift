import SwiftUI
import ServiceManagement

struct GeneralTab: View {
    @State private var atLogin = SMAppService.mainApp.status == .enabled
    @State private var loginError: String?
    @AppStorage("refreshSeconds") private var refresh = 2.0
    // 앱 언어. 시스템을 따르는 게 기본이고, 이 앱만 바꿀 수 있다(macOS 앱별 언어와 같은 자리에 저장). 다시 열어야 바뀐다
    @State private var lang = ((UserDefaults.standard.persistentDomain(forName: Bundle.main.bundleIdentifier ?? "")?["AppleLanguages"]
                                as? [String])?.first) ?? ""
    @State private var langChanged = false
    @AppStorage("shareOnLAN") private var shareOnLAN = false
    @AppStorage("keepAwake") private var keepAwake = true
    @AppStorage("globalHotKey") private var hotKey = true
    @Environment(Store.self) private var store
    @AppStorage("achievements") private var achievements = false
    @AppStorage(TempChip.settingKey) private var showCPUTemp = true

    var body: some View {
        Form {
            Picker("Language", selection: $lang) {
                Text("Same as system").tag("")
                Text(verbatim: "English").tag("en")
                Text(verbatim: "한국어").tag("ko")
            }
            .onChange(of: lang) { _, v in
                if v.isEmpty { UserDefaults.standard.removeObject(forKey: "AppleLanguages") }
                else { UserDefaults.standard.set([v], forKey: "AppleLanguages") }
                langChanged = true
            }
            if langChanged {
                HStack {
                    Text("Reopen Epokio to switch the language.").font(.ui(11.5)).foregroundStyle(.secondary)
                    Spacer()
                    Button("Reopen Now") { relaunch() }
                }
            }
            if Samples.present {
                Button("Remove Sample Runs", role: .destructive) { Task { await Samples.remove(store) } }
                    .help("Deletes the three example runs Epokio made. Your own runs are not touched.")
            }
            Button("Show the Welcome Guide Again") { UserDefaults.standard.set(false, forKey: "onboarded") }
                .help("It appears the next time you open the Studio window")
            Toggle(isOn: $hotKey) {
                HStack(spacing: 6) {
                    Text("Open Studio from anywhere")
                    Text(verbatim: "⌥⌘E").font(.ui(11.5, weight: .semibold, design: .rounded))
                        .padding(.horizontal, 6).padding(.vertical, 1).background(.quaternary, in: .rect(cornerRadius: Radius.chip))
                }
            }
            .onChange(of: hotKey) { GlobalHotKey.shared.apply() }
            ScanModeRow()
            UpdateSettingsRow()
            Toggle(L("Show SoC temperature"), isOn: $showCPUTemp)
            Toggle("Achievements", isOn: $achievements)
                .help("Badges for things like your first finished run. Adds an Achievements screen to the sidebar.")
                // 켜는 즉시 채점한다. 안 그러면 다음 새로고침까지 이미 딴 업적이 잠긴 것처럼 보인다(아이콘 갤러리의 자물쇠)
                .onChange(of: achievements) { _, on in if on { Trophies.shared.evaluate(store) } }
            Toggle("Keep the Mac awake while training", isOn: $keepAwake)
                .onChange(of: keepAwake) { KeepAwake.shared.update(training: false); store.refresh() }
            Text("Only while a run on this Mac is training. The screen can still turn off.")
                .font(.ui(12)).foregroundStyle(.secondary)
            Toggle("Let other devices on my network view Epokio", isOn: $shareOnLAN)
                .onChange(of: shareOnLAN) { Task { await AgentLauncher.shared.restart() } }
            if shareOnLAN {
                VStack(alignment: .leading, spacing: 4) {
                    if let ip = AgentLauncher.lanAddress() {
                        HStack {
                            Text(verbatim: "http://\(ip):\(AgentLauncher.livePort)/").font(.ui(13, design: .monospaced)).textSelection(.enabled)
                            Button("Copy") { copyText("http://\(ip):\(AgentLauncher.livePort)/", store, what: L("Address")) }
                                .controlSize(.small)
                        }
                    }
                    HStack {
                        Text("The page asks for this Mac's token once.").font(.ui(12)).foregroundStyle(.secondary)
                        Button("Copy Token") { if let t = AgentClient.local.token { copyText(t, store, what: L("Token")) } }.controlSize(.small)
                    }
                    Label("Traffic is not encrypted. Use this only on a network you trust, such as home Wi-Fi. For work or public networks, use SSH or Tailscale instead.",
                          systemImage: "exclamationmark.shield").font(.ui(12)).foregroundStyle(.warn).fixedSize(horizontal: false, vertical: true)
                }
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
            Toggle("Open Epokio at login", isOn: $atLogin)
                .onChange(of: atLogin) { _, on in
                    do { on ? try SMAppService.mainApp.register() : try SMAppService.mainApp.unregister(); loginError = nil }
                    catch { loginError = error.localizedDescription; atLogin = !on }
                }
            if let loginError { Text(loginError).font(.ui(11.5)).foregroundStyle(.warn) }
            Picker("Refresh every", selection: $refresh) {
                Text("1 second").tag(1.0); Text("2 seconds").tag(2.0); Text("5 seconds").tag(5.0); Text("10 seconds").tag(10.0)
            }
        }
        .formStyle(.grouped)
    }

    private func relaunch() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = ["-c", "sleep 1; open \"\(Bundle.main.bundlePath)\""]
        try? p.run()
        NSApp.terminate(nil)
    }
}
