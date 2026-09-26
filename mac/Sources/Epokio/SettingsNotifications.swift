import SwiftUI
import UserNotifications

struct NotificationsTab: View {
    @State private var hooks = ""
    @State private var hookMsg: String?
    @State private var savedHosts: [String] = []          // 기계에 이미 저장된 웹후크(주소 전체는 비밀이라 호스트만 온다)
    @AppStorage("notify") private var raw = "finished,failed,stalled,stopped_early,job_done,job_failed"
    let kinds: [(String, LocalizedStringKey, String)] = [
        ("finished", "A run finishes", "checkmark.circle"),
        ("failed", "Loss becomes NaN", "xmark.octagon"),
        ("stalled", "A run stops updating", "pause.circle"),
        ("stopped_early", "A run ends before its last epoch", "stop.circle"),
        ("job_done", "A queued job finishes", "list.bullet.circle"),
        ("job_failed", "A queued job fails", "exclamationmark.circle"),
        ("started", "A run starts", "play.circle"),
    ]
    var on: Set<String> { Set(raw.split(separator: ",").map(String.init)) }
    // 기준값(agent의 ~/.epokio/config.json). 바꾸면 바로 저장
    @State private var cfg = AgentConfig()
    @State private var loaded = false
    @State private var configLoaded = false
    @State private var denied = false                     // macOS가 알림을 막았다(처음 물었을 때 '허용 안 함')
    @AppStorage("quietMac") private var quietMac = true
    @AppStorage("notifySound") private var sound = "problems"
    @AppStorage("explainInAlerts") private var explainInAlerts = true

    struct AgentConfig: Codable, Equatable {
        var stall_min = 3, disk_low_gb = 5.0, gpu_hot_c = 85, gpu_mem_pct = 97, quiet_from = 0, quiet_to = 0
    }

    var body: some View {
        Form {
            // ★막혀 있어도 아무 말이 없어, 아래 스위치를 켜도 알림이 오지 않는 이유를 알 수 없었다
            if denied {
                Section {
                    HStack {
                        Label("macOS is blocking Epokio's notifications.", systemImage: "bell.slash")
                            .foregroundStyle(.warn)
                        Spacer()
                        Button("Open System Settings") {
                            if let u = URL(string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension") {
                                NSWorkspace.shared.open(u)
                            }
                        }
                    }
                }
            }
            Section("Tell me when") {
                ForEach(kinds, id: \.0) { k in
                    Toggle(isOn: Binding(get: { on.contains(k.0) }, set: { v in
                        var s = on; if v { s.insert(k.0) } else { s.remove(k.0) }
                        raw = s.sorted().joined(separator: ",")
                    })) { Label(k.1, systemImage: k.2) }
                }
                Toggle("Add a one-line reason", isOn: $explainInAlerts).help("Finished, failed and stalled alerts say why in one line")
                Picker("Sound", selection: $sound) {
                    Text("Louder for problems").tag("problems"); Text("Same for all").tag("all"); Text("No sound").tag("none")
                }
            }
            Section {
                Stepper(value: $cfg.stall_min, in: 2...240) { Label(L("Call a run stalled after at least %d min without a new epoch", cfg.stall_min), systemImage: "pause.circle") }
                Stepper(value: $cfg.disk_low_gb, in: 1...200, step: 1) { Label(L("Warn when less than %d GB of disk is free", Int(cfg.disk_low_gb)), systemImage: "externaldrive") }
                Stepper(value: $cfg.gpu_hot_c, in: 60...100) { Label(L("Warn when the GPU is hotter than %d °C", cfg.gpu_hot_c), systemImage: "thermometer.high") }
                Stepper(value: $cfg.gpu_mem_pct, in: 50...100) { Label(L("Warn when GPU memory is %d%% full", cfg.gpu_mem_pct), systemImage: "memorychip") }
            } header: { Text("Thresholds") } footer: {
                Text("Saved on the training machine, so they also apply to phone pushes and the web page.").font(.ui(11.5))
            }
            Section("Quiet hours") {
                HStack {
                    Label("From", systemImage: "moon").frame(width: 80, alignment: .leading)
                    Picker("", selection: $cfg.quiet_from) { ForEach(0..<24) { Text(String(format: "%02d:00", $0)).tag($0) } }.labelsHidden()
                    Text("to")
                    Picker("", selection: $cfg.quiet_to) { ForEach(0..<24) { Text(String(format: "%02d:00", $0)).tag($0) } }.labelsHidden()
                }
                Toggle("Also silence notifications on this Mac", isOn: $quietMac)
                Text(cfg.quiet_from == cfg.quiet_to ? L("Off. Pick different hours to turn it on.") : L("No phone pushes in these hours. Everything still shows up in Notifications."))
                    .font(.ui(11.5)).foregroundStyle(.secondary)
            }
            Section {
                TextField("Webhook URLs, one per line", text: $hooks, axis: .vertical)
                    .lineLimit(2...5).font(.ui(13, design: .monospaced))
                HStack {
                    if let hookMsg { Text(hookMsg).font(.ui(11.5)).foregroundStyle(.secondary) }
                    Spacer()
                    Button("Save") { Task { await saveHooks() } }
                }
            } header: {
                Text("Send to phone")
            } footer: {
                Text("Slack, Discord or Telegram webhooks. The training machine sends them itself, so they arrive even when your Mac is asleep.")
                    .font(.ui(11.5)).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .task {
            denied = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus == .denied
            // 읽었을 때만 저장을 켠다. ★못 읽어도 켜서, 기본값이 보이는 폼을 한 번 만지면 기계의 기준값이 전부 기본값으로 덮였다
            if let c: AgentConfig = try? await AgentClient.local.get("config") { cfg = c; configLoaded = true }
            struct H: Decodable { let hosts: [String] }
            if let h: H = try? await AgentClient.local.get("webhooks") {
                savedHosts = h.hosts
                if !h.hosts.isEmpty { hookMsg = L("Now sending to %@", h.hosts.joined(separator: ", ")) }
            }
            loaded = true
        }
        .onChange(of: cfg) { _, c in
            guard loaded, configLoaded else { return }
            UserDefaults.standard.set(c.quiet_from, forKey: "quietFrom"); UserDefaults.standard.set(c.quiet_to, forKey: "quietTo")
            Task {
                guard let data = try? JSONEncoder().encode(c), let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
                nonisolated(unsafe) let body = obj
                _ = try? await AgentClient.local.post("config", body)
            }
        }
    }

    private func saveHooks() async {
        let urls = hooks.split(whereSeparator: \.isNewline).map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        // ★칸이 비어 있는데 저장하면 기계에 있던 웹후크가 전부 지워졌다(칸은 저장된 값을 모른다). 비어 있으면 저장하지 않는다
        guard !urls.isEmpty else {
            hookMsg = savedHosts.isEmpty ? L("Paste at least one webhook address.") : L("Nothing changed. Paste new addresses to replace the saved ones.")
            return
        }
        // 목표 점수·기계 경고는 스위치가 없어도 폰으로 간다(★예전엔 저장할 때 빠져서 영영 안 왔다)
        let kinds = Array(on.union(["goal", "disk_low", "gpu_hot", "gpu_mem"])).sorted()
        do {
            let r = try await AgentClient.local.post("webhooks", ["urls": urls, "kinds": kinds])
            let n = r["count"] as? Int ?? 0
            hookMsg = n == 1 ? String(localized: "Saved 1 webhook") : String(localized: "Saved \(n) webhooks")
        } catch { hookMsg = error.localizedDescription }
    }
}

// 원격 학습 기계. 토큰은 키체인에.
