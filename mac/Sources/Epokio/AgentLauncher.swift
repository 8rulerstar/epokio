import Foundation
import os

// 초보자가 터미널을 열 일이 없게, 앱이 로컬 agent를 알아서 띄운다.
// 포트: 기본 8787이 막혀 있으면 agent가 빈 포트로 옮기고 ~/.epokio/agent.json 에 적는다. 앱은 그 파일 → /health 순으로 찾는다.
// 순서: 이미 떠 있나(/health) → 앱에 든 agent를 앱에 든 파이썬으로 → (없으면) 이 맥의 파이썬으로 → pip으로 깔린 epokio-agent → 설치 안내.
@MainActor
final class AgentLauncher {
    static let shared = AgentLauncher()
    private var process: Process?
    private(set) var status: Status = .unknown

    enum Status: Equatable { case unknown, running, launched(String), notInstalled, portTaken, crashed }

    /// agent가 남긴 말(표준 출력·오류). ★버려서, 띄우자마자 죽어도 이유를 알 길이 없었다
    nonisolated static let logFile = FileManager.default.homeDirectoryForCurrentUser.appending(path: ".epokio/agent.log")

    /// "이 Mac" 을 가리키는 이름표(목록·설정에 저장되는 값). 실제로 부를 땐 resolve()로 지금 포트로 바꾼다
    nonisolated static let url = URL(string: "http://127.0.0.1:8787")!
    nonisolated static let defaultPort = 8787
    nonisolated private static let live = OSAllocatedUnfairLock(initialState: 8787)
    nonisolated static var livePort: Int { live.withLock { $0 } }

    /// 이 Mac 이름표 주소를 agent가 실제로 떠 있는 포트로 바꾼다. 원격 주소는 그대로 둔다
    nonisolated static func resolve(_ u: URL) -> URL {
        let port = livePort
        guard port != defaultPort, u.host() == "127.0.0.1", u.port == defaultPort,
              var c = URLComponents(url: u, resolvingAgainstBaseURL: false) else { return u }
        c.port = port
        return c.url ?? u
    }

    func ensureRunning() async {
        if await Self.locate() { status = .running; return }
        let taken = await Self.probe(Self.defaultPort) == .other      // 8787을 다른 프로그램(예: RStudio Server)이 쓰고 있다
        // 설정 "같은 네트워크의 다른 기기에서 보기"를 켜면 LAN에 연다(보기만 누구나, 실행은 토큰)
        let lan = UserDefaults.standard.bool(forKey: "shareOnLAN")
        let args = ["--label", "local"]      // 포트는 agent가 고른다(8787부터 빈 곳) + (lan ? ["--host", "0.0.0.0"] : [])
            + (UserDefaults.standard.stringArray(forKey: "folders") ?? []).flatMap { ["--root", $0] }
        let p = Process()
        let exe: String
        if let bundled = Bundle.main.resourceURL?.appending(path: "agent"),
           FileManager.default.fileExists(atPath: bundled.appending(path: "epokio/agent.py").path),
           let py = Self.bundledPython ?? Self.findPython() {
            exe = py
            p.executableURL = URL(fileURLWithPath: py)
            // 앱이 비정상 종료돼도 agent가 스스로 끝난다. 앱에 든 agent만 넘긴다(pip으로 깔린 옛 판은 이 인자를 몰라 기동이 실패한다)
            p.arguments = ["-m", "epokio.agent"] + args + ["--parent-pid", String(ProcessInfo.processInfo.processIdentifier), "--launch-runs"]   // 앱의 학습·대기열 화면은 이 도우미로 작업을 시작한다(pip 도우미는 epokio config launch_runs on)
            p.environment = ProcessInfo.processInfo.environment.merging(["PYTHONPATH": bundled.path, "PYTHONUNBUFFERED": "1"]) { $1 }   // ★버퍼에 남아 agent.log가 비어 있었다
        } else if let installed = Self.findAgent() {
            exe = installed
            p.executableURL = URL(fileURLWithPath: installed)
            p.arguments = args
        } else { status = .notInstalled; return }
        p.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser   // '/'에서 띄우지 않는다
        try? FileManager.default.createDirectory(at: Self.logFile.deletingLastPathComponent(), withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: Self.logFile.path, contents: nil)      // 켤 때마다 새로
        let log = (try? FileHandle(forWritingTo: Self.logFile)) ?? FileHandle.nullDevice
        p.standardOutput = log
        p.standardError = log
        // 곧바로 죽으면 알린다. ★'도우미를 켜는 중…'이 끝없이 돌았다
        let me = ObjectIdentifier(p)
        p.terminationHandler = { _ in
            Task { @MainActor in
                let l = AgentLauncher.shared
                if let cur = l.process, ObjectIdentifier(cur) == me { l.process = nil; l.status = .crashed }
            }
        }
        do {
            try p.run()
            process = p
            status = .launched(exe)
        } catch {
            status = .notInstalled
            return
        }
        for _ in 0..<40 {                              // 막 띄운 agent가 포트를 적을 때까지(최대 8초)
            if await Self.locate() { return }
            try? await Task.sleep(for: .milliseconds(200))
        }
        if taken { status = .portTaken }
    }

    /// 내가 띄운 agent만 끈다(터미널에서 직접 띄운 것·원격은 process가 nil이라 건드리지 않는다).
    /// SIGTERM → 최대 1.5초 대기 → 그래도 살아 있으면 SIGKILL.
    func stop() {
        guard let p = process else { return }
        process = nil
        guard p.isRunning else { return }
        p.terminate()
        let deadline = Date().addingTimeInterval(1.5)
        while p.isRunning && Date() < deadline { usleep(50_000) }
        if p.isRunning { kill(p.processIdentifier, SIGKILL); p.waitUntilExit() }
    }

    /// 설정을 바꿨을 때: 내가 띄운 agent를 다시 띄운다
    func restart() async {
        stop()                                            // process를 먼저 비우므로 일부러 끈 것은 '죽음'(crashed)으로 보지 않는다
        try? await Task.sleep(for: .milliseconds(400))
        await ensureRunning()
    }

    /// 이 Mac의 LAN 주소(폰에서 열 주소를 보여 주려고)
    nonisolated static func lanAddress() -> String? {
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0, let first = ifaddr else { return nil }
        defer { freeifaddrs(ifaddr) }
        for p in sequence(first: first, next: { $0.pointee.ifa_next }) {
            let a = p.pointee
            guard a.ifa_addr.pointee.sa_family == UInt8(AF_INET), String(cString: a.ifa_name).hasPrefix("en") else { continue }
            var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            if getnameinfo(a.ifa_addr, socklen_t(a.ifa_addr.pointee.sa_len), &host, socklen_t(host.count), nil, 0, NI_NUMERICHOST) == 0 {
                // 배열을 받는 String(cString:)은 폐기 예정(빌드 경고 18번). 0 앞까지를 UTF-8로 읽는다
                return String(decoding: host.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, as: UTF8.self)
            }
        }
        return nil
    }

    enum Probe { case epokio, other, none }

    /// 그 포트에서 답하는 게 Epokio agent인가(/health가 ok·label·version을 주는가)
    static func probe(_ port: Int) async -> Probe {
        var req = URLRequest(url: URL(string: "http://127.0.0.1:\(port)/health")!)
        req.timeoutInterval = 1
        guard let (data, resp) = try? await URLSession.shared.data(for: req) else { return .none }
        struct Health: Decodable { let ok: Bool; let label: String; let version: String }
        guard (resp as? HTTPURLResponse)?.statusCode == 200,
              let h = try? JSONDecoder().decode(Health.self, from: data), h.ok else { return .other }
        return .epokio
    }

    /// ~/.epokio/agent.json → 기본 포트 순으로 이 Mac의 agent를 찾고, 찾으면 실제 포트를 기억한다
    static func locate() async -> Bool {
        let f = FileManager.default.homeDirectoryForCurrentUser.appending(path: ".epokio/agent.json")
        struct Record: Decodable { let port: Int }
        var ports = [defaultPort]
        if let d = try? Data(contentsOf: f), let r = try? JSONDecoder().decode(Record.self, from: d) { ports.insert(r.port, at: 0) }
        for port in ports where await probe(port) == .epokio {
            live.withLock { $0 = port }
            return true
        }
        return false
    }

    /// 앱 안에 든 파이썬(build_app.sh). agent 전용이라 학습용 패키지는 없다
    static var bundledPython: String? {
        guard let p = Bundle.main.resourceURL?.appending(path: "python/bin/python3").path,
              FileManager.default.isExecutableFile(atPath: p) else { return nil }
        return p
    }

    /// 앱에 든 agent를 돌릴 파이썬. 3.10 이상이면 되고, 학습용 환경이 아니어도 된다(학습 환경은 agent가 따로 찾는다).
    static func findPython() -> String? {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        var c = [PythonInstaller.python.path,                          // Epokio가 받아 둔 것(있으면 가장 확실하다)
                 "/opt/homebrew/bin/python3", "/usr/local/bin/python3",
                 "/opt/anaconda3/bin/python3", "/opt/miniconda3/bin/python3",
                 "\(home)/miniconda3/bin/python3", "\(home)/anaconda3/bin/python3"]
        // 기본 /usr/bin/python3은 개발자 도구가 없으면 설치 창을 띄우는 껍데기라, 도구가 있을 때만 쓴다
        if FileManager.default.fileExists(atPath: "/Library/Developer/CommandLineTools/usr/bin/python3")
            || FileManager.default.fileExists(atPath: "/Applications/Xcode.app") { c.append("/usr/bin/python3") }
        // 3.10 이상만. ★개발자 도구의 /usr/bin/python3은 3.9라, agent가 뜨자마자 죽었다
        return c.first { FileManager.default.isExecutableFile(atPath: $0) && isNewEnough($0) }
    }

    nonisolated static func isNewEnough(_ python: String) -> Bool {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: python)
        p.arguments = ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"]
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        guard (try? p.run()) != nil else { return false }
        p.waitUntilExit()
        return p.terminationStatus == 0
    }

    /// pip으로 깔린 epokio-agent를 흔한 자리에서 찾는다.
    static func findAgent() -> String? {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        var candidates = [
            "\(home)/Projects/epokio/.venv/bin/epokio-agent",
            "/opt/homebrew/bin/epokio-agent", "/usr/local/bin/epokio-agent",
            "\(home)/.local/bin/epokio-agent",
        ]
        // conda·pyenv 환경들
        for base in ["/opt/anaconda3/envs", "/opt/miniconda3/envs", "\(home)/miniconda3/envs", "\(home)/anaconda3/envs"] {
            if let envs = try? FileManager.default.contentsOfDirectory(atPath: base) {
                candidates += envs.map { "\(base)/\($0)/bin/epokio-agent" }
            }
        }
        candidates += ["/opt/anaconda3/bin/epokio-agent", "\(home)/miniconda3/bin/epokio-agent"]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }
}
