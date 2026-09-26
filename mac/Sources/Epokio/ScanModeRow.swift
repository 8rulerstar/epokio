import SwiftUI

// 설정 → 일반 "기록 읽기": 자동(기본) · 절전 · 수동. agent config.scan_mode(pace.py)
// 수동은 알림이 오지 않으므로 고르는 순간 눈에 띄게 경고하고, 메뉴바 팝오버에도 계속 표시한다(잊고 "알림이 안 와요" 막기).
struct ScanModeRow: View {
    @Environment(Store.self) private var store
    @State private var mode = "auto"
    @State private var battery = true
    @State private var loaded = false
    private struct Cfg: Decodable { let scan_mode: String?; let saver_on_battery: Bool?; let reads_token: String? }
    @State private var readsToken = "auto"

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker("Reading run folders", selection: $mode.animation(Motion.change)) {
                Text("Automatic").tag("auto"); Text("Battery saver").tag("saver"); Text("Only when I refresh").tag("manual")
            }
            .pickerStyle(.segmented)
            Group {
                switch mode {
                case "saver":
                    Text("Checks every 30 seconds while training and every 2 minutes otherwise. Alerts can come a few minutes late.")
                case "manual":
                    Label("Epokio will not read your folders on its own, so finished, failed, stalled and goal alerts will not come. Press Refresh (⌘R) to update.",
                          systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.warn).font(.ui(12, weight: .semibold))
                default:
                    Text("Often while something trains, then less and less on quiet days. Anything new makes it quick again.")
                }
            }
            .font(.ui(11.5)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            .transition(.opacity)
            if mode == "auto" {
                Toggle("Save battery automatically when unplugged", isOn: $battery)
            }
            Toggle("Ask for the token even on this Mac", isOn: Binding(get: { readsToken == "always" }, set: { readsToken = $0 ? "always" : "auto" }))
                .help("For machines other people can log in to: then a local curl cannot read your runs either")
        }
        .task {
            if let c: Cfg = try? await AgentClient.local.get("config") {
                mode = c.scan_mode ?? "auto"; battery = c.saver_on_battery ?? true; readsToken = c.reads_token ?? "auto"
            }
            loaded = true
        }
        .onChange(of: mode) { _, m in save(); if m == "manual" { Haptic.tick() } }
        .onChange(of: battery) { save() }
        .onChange(of: readsToken) { save(); store.say(L("Restart Epokio for this to take effect.")) }
    }

    private func save() {
        guard loaded else { return }
        nonisolated(unsafe) let body: [String: Any] = ["scan_mode": mode, "saver_on_battery": battery, "reads_token": readsToken]
        Task { await store.act { _ = try await AgentClient.local.post("config", body) }; store.scanMode = mode }
    }
}

/// 팝오버 위: 수동 모드일 때 늘 보이는 띠
struct ManualScanBanner: View {
    @Environment(Store.self) private var store
    @State private var spin = 0
    var body: some View {
        if store.scanMode == "manual" {
            HStack(spacing: 8) {
                Image(systemName: "pause.circle.fill").foregroundStyle(.warn)
                Text("Manual updates: no alerts").font(.ui(12, weight: .medium))
                Spacer()
                Button { spin += 1; Task { await store.act { _ = try await AgentClient.local.post("refresh") } } } label: {
                    Label("Refresh", systemImage: "arrow.clockwise").symbolEffect(.rotate, value: spin)
                }
                .buttonStyle(.borderless).font(.ui(12))
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(Color.warn.opacity(0.12), in: RoundedRectangle(cornerRadius: Radius.control))
            .transition(.move(edge: .top).combined(with: .opacity))
        }
    }
}
