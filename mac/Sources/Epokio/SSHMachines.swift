import SwiftUI

// SSH 가벼운 모드(설정 → 기계): 서버에 아무것도 설치하지 않고 학습을 본다. 보기 전용.
// ~/.ssh/config 의 호스트를 고르거나 user@host 를 적는다. 추가를 누르면 바로 한 번 읽어 보고, 안 되면 이유를 보여 준다.
// 본체는 agent의 ssh_source.py(비밀번호·호스트 키 확인은 우회하지 않는다).

struct SSHHost: Decodable, Hashable {
    let host: String
    let paths: [String]?
    let auto: Bool?
    let status: Status?
    struct Status: Decodable, Hashable { let ok: Bool?; let error: String?; let runs: Int?; let at: Double?; let python: String?; let truncated: Bool?; let skipped: [Skipped]? }
    struct Skipped: Decodable, Hashable { let path: String; let name: String; let size: Int?; let kept: Int? }   // 한도를 넘은 기록 파일. kept가 있으면 끝부분만 받음
}
private struct SSHList: Decodable { let hosts: [SSHHost]; let config_hosts: [String] }

struct SSHSection: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var hosts: [SSHHost] = []
    @State private var known: [String] = []
    @State private var host = ""
    @State private var paths = ""
    @State private var auto = true
    @State private var busy = false
    @State private var error: String?
    @State private var added = 0

    var body: some View {
        Section {
            ForEach(hosts, id: \.host) { h in row(h).transition(.opacity.combined(with: .move(edge: .top))) }
            HStack(spacing: 8) {
                TextField("Host", text: $host, prompt: Text(verbatim: known.first ?? "user@gpu-server"))
                    .textFieldStyle(.roundedBorder)
                if !known.isEmpty {
                    Menu {
                        ForEach(known.filter { k in !hosts.contains { $0.host == k } }, id: \.self) { k in Button(k) { host = k } }
                    } label: { Image(systemName: "list.bullet") }
                    .menuStyle(.button).fixedSize().help("Hosts from ~/.ssh/config")
                }
            }
            Toggle("Find training folders by itself", isOn: $auto)
                .help("Looks through the home folder on the server (skips datasets and Python installs)")
            TextField("Other folders (optional, comma separated)", text: $paths, prompt: Text(verbatim: "/data/runs, ~/exp"))
                .textFieldStyle(.roundedBorder)
            HStack(spacing: 8) {
                if busy {
                    ProgressView().controlSize(.small)
                    Text("Connecting…").font(.ui(11.5)).foregroundStyle(ink.soft)
                } else if let error {
                    Label(error, systemImage: "exclamationmark.triangle.fill").font(.ui(11.5)).foregroundStyle(.warn)
                        .lineLimit(3).transition(.opacity)
                }
                Spacer()
                Button { Task { await add() } } label: { Label("Add over SSH", systemImage: "plus").symbolEffect(.bounce, value: added) }
                    .disabled(host.trimmingCharacters(in: .whitespaces).isEmpty || busy || (!auto && paths.isEmpty))
            }
            .animation(Motion.change, value: busy)
            .animation(Motion.change, value: error)
        } header: {
            Text("Over SSH (nothing to install)")
        } footer: {
            Text("Uses your SSH keys and ~/.ssh/config. The server only needs python3. Epokio copies the small log files (results.csv and similar) every 15 seconds, never pictures or weights. View only: to start training there, install the agent.")
                .font(.ui(11)).foregroundStyle(ink.soft)
        }
        .task { await load() }
        .animation(Motion.change, value: hosts)
    }

    private func row(_ h: SSHHost) -> some View {
        let ok = h.status?.ok ?? false
        return HStack(spacing: 8) {
            Image(systemName: h.status == nil ? "clock" : ok ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                .foregroundStyle(h.status == nil ? AnyShapeStyle(ink.soft) : ok ? AnyShapeStyle(.good) : AnyShapeStyle(.warn))
                .symbolEffect(.bounce, value: ok)
                .contentTransition(.symbolEffect(.replace))
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: h.host).font(.ui(13, design: .monospaced))
                Text(verbatim: ok ? L("%d runs · python %@", h.status?.runs ?? 0, h.status?.python ?? "?") : (h.status?.error ?? L("Waiting for the first read")))
                    .font(.ui(11)).foregroundStyle(ok ? AnyShapeStyle(ink.soft) : AnyShapeStyle(.warn)).lineLimit(2)
                    .contentTransition(.opacity)
            }
            Spacer()
            if h.status?.truncated == true {
                Label("Too many folders to read", systemImage: "exclamationmark.triangle.fill").font(.ui(11)).foregroundStyle(.warn)
                    .help("Only part of the server was read. Add the exact folders below so Epokio does not have to search.")
            }
            if let sk = h.status?.skipped?.filter({ $0.kept == nil }), !sk.isEmpty {
                Label(L("%d log files over the size limit were skipped", sk.count), systemImage: "exclamationmark.triangle.fill")
                    .font(.ui(11)).foregroundStyle(.warn)
                    .help(sk.map { "\($0.path)/\($0.name)" }.joined(separator: "\n"))
                    .transition(.opacity)
            }
            if let part = h.status?.skipped?.filter({ $0.kept != nil }), !part.isEmpty {   // 늘어나는 기록: 앞쪽 기록이 빠졌다
                Label(L("%d large log files: only the last part was loaded", part.count), systemImage: "exclamationmark.triangle.fill")
                    .font(.ui(11)).foregroundStyle(.warn)
                    .help(part.map { "\($0.path)/\($0.name)" }.joined(separator: "\n"))
                    .transition(.opacity)
            }
            IconButton(symbol: "arrow.clockwise", help: "Read now") {
                Task { await store.act { _ = try await AgentClient.local.post("ssh/refresh") }; try? await Task.sleep(for: .seconds(3)); await load() }
            }
            Button("Remove", role: .destructive) {
                Task {
                    await store.act(L("Stopped watching %@", h.host)) { _ = try await AgentClient.local.post("ssh/remove", ["host": h.host]) }
                    await load()
                }
            }
        }
    }

    private func load() async {
        if let l: SSHList = try? await AgentClient.local.get("ssh") { hosts = l.hosts; known = l.config_hosts }
    }

    private func add() async {
        busy = true; error = nil; defer { busy = false }
        let h = host.trimmingCharacters(in: .whitespaces)
        let ps = paths.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        nonisolated(unsafe) let body: [String: Any] = ["host": h, "paths": ps, "auto": auto]
        do {
            let r = try await AgentClient.local.post("ssh/add", body)
            let n = (r["status"] as? [String: Any])?["runs"] as? Int ?? 0
            added += 1; Haptic.success()
            store.say(L("Watching %@ over SSH: %d runs", h, n))
            host = ""; paths = ""
            await load(); store.refresh()
        } catch {
            withAnimation(Motion.change) { self.error = error.localizedDescription }
            Haptic.tick()
        }
    }
}
