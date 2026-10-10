import SwiftUI

/// 작업 시작(학습·대기열·스윕)이 꺼진 도우미.
/// ★pip으로 깔고 `epokio setup --autostart`로 켜 둔 도우미(launch_runs 끔)가 이미 떠 있으면 앱이 그것을 그대로 쓰고,
///   학습·대기열 화면은 403(launch_off)만 받아 막혔다. 이제 꺼져 있으면 이유와 켜는 버튼을 보여 준다.
/// 켜기 = 이 Mac의 ~/.epokio/config.json에 launch_runs: true(`epokio config launch_runs on`과 같은 파일·같은 값).
///   도우미가 요청마다 파일을 읽어 다시 켤 필요가 없다. 이 Mac에서 사람이 누르는 것이라 웹(POST /config)으로 못 켜는 규칙과 맞다.
///   원격 기계는 파일을 건드릴 수 없으니 그 기계에서 칠 명령만 알려 준다
enum LaunchGate {
    static let file = FileManager.default.homeDirectoryForCurrentUser.appending(path: ".epokio/config.json")
    static let command = "epokio config launch_runs on"

    /// /health의 launch_runs. 옛 도우미(열쇠 없음)·연결 실패는 nil(안내를 띄우지 않는다)
    static func isOn(_ base: URL) async -> Bool? {
        var req = URLRequest(url: AgentLauncher.resolve(base).appending(path: "health"))
        req.timeoutInterval = 3
        AgentClient(base: base).authorize(&req)
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return nil }
        return obj["launch_runs"] as? Bool
    }

    /// 다른 설정은 그대로 두고 launch_runs만 켠다. 읽을 수 없는 파일은 덮어쓰지 않는다(기준값이 사라지지 않게)
    static func turnOn() throws {
        var c: [String: Any] = [:]
        if FileManager.default.fileExists(atPath: file.path) {
            guard let d = try? Data(contentsOf: file),
                  let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any] else {
                throw AgentError.refused(L("Could not read ~/.epokio/config.json. Run this in Terminal instead: %@", command))
            }
            c = o
        }
        c["launch_runs"] = true
        try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: c, options: [.prettyPrinted, .sortedKeys]).write(to: file, options: .atomic)
    }
}

/// 학습·대기열 화면 맨 위. 켜져 있거나 알 수 없으면 아무것도 그리지 않는다
struct LaunchOffCard: View {
    var machine: URL = AgentLauncher.url
    @State private var off = false
    @State private var problem: String?
    private var local: Bool { machine == AgentLauncher.url }

    var body: some View {
        Group {
            if off {
                VStack(alignment: .leading, spacing: 8) {
                    Label("Starting jobs is off on this helper", systemImage: "lock").font(.ui(13, weight: .semibold))
                    Text(local ? L("Epokio is only watching your logs here. Turn this on to start training and queue jobs from the app. It is the same as running %@.", LaunchGate.command)
                               : L("Run this on that machine to start training there: %@", LaunchGate.command))
                        .font(.ui(12)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    if local {
                        Button("Turn on") {
                            do {
                                try LaunchGate.turnOn()
                                problem = nil
                                Task { off = await LaunchGate.isOn(machine) == false }
                            } catch { problem = error.localizedDescription }
                        }
                    }
                    if let problem { Text(problem).font(.ui(12)).foregroundStyle(.warn) }
                }
                .padding(12).frame(maxWidth: .infinity, alignment: .leading)
                .background(.quaternary.opacity(0.4), in: .rect(cornerRadius: 10))
            }
        }
        .task(id: machine) { off = await LaunchGate.isOn(machine) == false }
    }
}
