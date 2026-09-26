import SwiftUI
import Security

// 원격 학습 기계. 토큰은 키체인에.
struct MachinesTab: View {
    @Environment(Store.self) private var store
    @State private var url = "http://"
    @State private var token = ""
    @State private var message: String?

    var body: some View {
        Form {
            Section("Watching") {
                ForEach(store.agents, id: \.self) { a in
                    HStack {
                        Image(systemName: store.offline.contains(a.absoluteString) ? "wifi.exclamationmark" : "checkmark.circle.fill")
                            .foregroundStyle(store.offline.contains(a.absoluteString) ? .warn : .good)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(a.absoluteString).font(.ui(13, design: .monospaced))
                            if let why = store.lastError[a.absoluteString] {
                                Text(verbatim: why).font(.ui(11)).foregroundStyle(.warn)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        Spacer()
                        if a != AgentLauncher.url {
                            Button("Remove", role: .destructive) { store.removeAgent(a) }
                        }
                    }
                }
            }
            SSHSection()
            Section("Add a machine with the agent") {
                TextField("Address", text: $url, prompt: Text("http://192.168.0.5:8787"))
                SecureField("Token", text: $token, prompt: Text("run `epokio-agent --show-token` there"))
                HStack {
                    if let message { Text(message).font(.ui(11.5)).foregroundStyle(.secondary) }
                    Spacer()
                    Button("Add") { Task { await add() } }.disabled(URL(string: url)?.host() == nil)
                }
            }
        }
        .formStyle(.grouped)
    }

    private func add() async {
        guard let u = URL(string: url.trimmingCharacters(in: .whitespaces)) else { return }
        let t = token.trimmingCharacters(in: .whitespacesAndNewlines)
        // 토큰이 필요한 /jobs로 시험한 뒤에만 저장한다.
        // ★예전엔 토큰 없이 열리는 /health만 봐서, 틀린 토큰도 '연결됨'이었고 대기열·학습이 나중에 조용히 비었다
        struct J: Decodable { let jobs: [Job] }
        do {
            let _: J = try await AgentClient(base: u, tokenOverride: t.isEmpty ? nil : t).get("jobs")
            if !t.isEmpty && !Keychain.set(t, for: u.absoluteString) {
                message = L("Connected, but the token could not be saved in the Keychain.")
                return
            }
            if !t.isEmpty { AgentClient.remoteTokens[u.absoluteString] = t }   // 2초마다 키체인을 묻지 않게 기억(새 토큰으로 갈아 끼움)
            store.addAgent(u); message = String(localized: "Connected"); url = "http://"; token = ""
        } catch AgentError.http(401, _) {
            message = t.isEmpty ? L("This machine needs its token. Run `epokio-agent --show-token` there and paste it here.")
                                : L("This machine did not accept the token. Copy it again with `epokio-agent --show-token`.")
        } catch AgentError.http(403, _) {
            message = L("This machine does not accept this address. Use its IP address, or set EPOKIO_ALLOWED_HOSTS there.")
        } catch {
            message = String(localized: "Could not reach this machine. Is the agent running with --host 0.0.0.0?")
        }
    }
}

enum Keychain {
    static let service = "io.github.8rulerstar.epokio"
    @discardableResult
    static func set(_ value: String, for account: String) -> Bool {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrService as String: service, kSecAttrAccount as String: account]
        SecItemDelete(q as CFDictionary)
        var add = q; add[kSecValueData as String] = Data(value.utf8)
        return SecItemAdd(add as CFDictionary, nil) == errSecSuccess   // ★실패를 버려 '토큰이 없다'로만 보였다
    }
    static func get(_ account: String) -> String? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account, kSecReturnData as String: true]
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data else { return nil }
        return String(data: d, encoding: .utf8)
    }
}

/// 자연어 명령(TypeSafe Jev). 기본 꺼짐. 무엇이 밖으로 나가는지 먼저 알린다
