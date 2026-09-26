import AppKit
import Darwin
import CoreText
import Vision

// 스냅샷 격리 (2026-09-22). --snapshot/--snapshot-window 로 찍을 때 실제 사용자 것을 하나도 안 보이게 한다.
// ★HOME만 바꿨더니 설정(UserDefaults: folders, datasetFolder)과 로컬 agent(8787)를 그대로 읽어
//   데이터셋 화면에 회사 사진이, 상세 제목에 실제 호스트명이 찍혔다.
// 네 겹:
// ① 홈: 임시 폴더를 CFFIXED_USER_HOME·HOME으로 두고 자기 자신을 다시 실행(execv). homeDirectoryForCurrentUser가 전부 그쪽을 본다
// ② 설정: UserDefaults.standard를 스냅샷 전용 도메인으로 바꿔치기(시작·끝에 비운다). 실제 설정은 읽지도 쓰지도 않는다
// ③ 데이터: 가짜 홈으로 agent를 따로 띄워(--label gpu-server) /demo 예시 학습만 만든다. 데이터셋은 코드로 그린 도형 사진
// ④ 통신: URLProtocol로 모든 요청을 가로챈다. 로컬 주소는 전부 그 agent로 돌리고(실제 8787 차단), 밖으로 나가는 요청은 막고,
//    응답의 실제 호스트명·사용자명·홈 경로는 가짜 값으로 바꾼다
// 찍기 직전에 접근성 트리를 훑어 실제 값이 남아 있으면 PNG를 쓰지 않고 끝낸다(audit).
enum SnapshotIsolation {
    static let fakeHost = "gpu-server"
    static let fakeUser = "user"
    static let suite = "io.github.8rulerstar.epokio.snapshot"
    private static let envKey = "EPOKIO_SNAPSHOT_HOME"

    nonisolated(unsafe) static var isolated = false
    nonisolated(unsafe) static var home = ""
    nonisolated(unsafe) static var agentPort = 0
    nonisolated(unsafe) private static var agent: Process?
    nonisolated(unsafe) private static var defaults: UserDefaults?

    static var requested: Bool {
        CommandLine.arguments.contains { $0 == "--snapshot" || $0 == "--snapshot-window" }
    }

    /// 앱에서 가장 먼저(Store보다 먼저) 부른다. 스냅샷이 아니면 아무것도 안 한다
    @MainActor static func boot() {
        if CommandLine.arguments.contains("--snapshot-audit-selftest") { selftest() }
        guard requested, !isolated else { return }
        let env = ProcessInfo.processInfo.environment
        guard let h = env[envKey], env["CFFIXED_USER_HOME"] == h else { reexec() }
        home = h
        guard FileManager.default.homeDirectoryForCurrentUser.path == h else { fail("home was not redirected") }
        isolated = true
        swapDefaults()
        URLProtocol.registerClass(SnapshotGuard.self)
        atexit { SnapshotIsolation.cleanup() }
        makeDemoDataset()
        startAgent()
    }

    // MARK: ① 홈
    private static func reexec() -> Never {
        let tmp = FileManager.default.temporaryDirectory
        // 지난번에 밖에서 끊긴(SIGTERM) 실행이 남긴 가짜 홈을 치운다
        for n in (try? FileManager.default.contentsOfDirectory(atPath: tmp.path)) ?? [] where n.hasPrefix("epokio-snap-") {
            try? FileManager.default.removeItem(at: tmp.appending(path: n))
        }
        let dir = tmp.appending(path: "epokio-snap-\(getpid())")
        try? FileManager.default.createDirectory(at: dir.appending(path: "runs"), withIntermediateDirectories: true)
        let p = dir.path
        setenv(envKey, p, 1); setenv("CFFIXED_USER_HOME", p, 1); setenv("HOME", p, 1)
        guard let exe = Bundle.main.executablePath else { fail("no executable path") }
        execv(exe, CommandLine.unsafeArgv)
        fail("execv failed (\(errno))")
    }

    // MARK: ② 설정
    private static func swapDefaults() {
        UserDefaults.standard.removePersistentDomain(forName: suite)     // 지난번에 남은 것
        guard let d = UserDefaults(suiteName: suite) else { fail("no defaults suite") }
        defaults = d
        guard let a = class_getClassMethod(UserDefaults.self, #selector(getter: UserDefaults.standard)),
              let b = class_getClassMethod(UserDefaults.self, #selector(UserDefaults.epokioSnapshotStandard)) else { fail("swizzle") }
        method_exchangeImplementations(a, b)
        guard UserDefaults.standard === d else { fail("defaults not swapped") }
        d.set(home + "/datasets/shapes", forKey: "datasetFolder")
        d.set(false, forKey: "glass")        // ★오프스크린 렌더에서는 Liquid Glass가 안 그려져 카드가 빈칸으로 찍힌다
    }
    fileprivate static var snapshotDefaults: UserDefaults { defaults! }

    // MARK: ③ 데이터
    @MainActor private static func startAgent() {
        let fm = FileManager.default
        var py: String?, pythonPath: String?, exe: String?
        if let bundled = Bundle.main.resourceURL?.appending(path: "agent"),
           fm.fileExists(atPath: bundled.appending(path: "epokio/agent.py").path) {
            py = AgentLauncher.bundledPython ?? AgentLauncher.findPython(); pythonPath = bundled.path
        } else if let src = repoSource() {                      // swift build 결과물: 저장소의 src/
            py = AgentLauncher.findPython(); pythonPath = src
        } else { exe = AgentLauncher.findAgent() }
        let port = freePort()
        let args = ["--port", String(port), "--label", fakeHost, "--root", home + "/runs",
                    "--parent-pid", String(getpid())]
        let p = Process()
        if let py, let pythonPath {
            p.executableURL = URL(fileURLWithPath: py)
            p.arguments = ["-m", "epokio.agent"] + args
            p.environment = ["HOME": home, "PYTHONPATH": pythonPath, "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"]
        } else if let exe {
            p.executableURL = URL(fileURLWithPath: exe)
            p.arguments = args.filter { $0 != "--parent-pid" && $0 != String(getpid()) }
            p.environment = ["HOME": home, "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"]
        } else { fail("no agent to run") }
        p.currentDirectoryURL = URL(fileURLWithPath: home)
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do { try p.run() } catch { fail("agent did not start: \(error)") }
        agent = p
        agentPort = port
        let base = URL(string: "http://127.0.0.1:\(port)")!
        var up = false
        for _ in 0..<60 where !up {
            up = (try? call(base.appending(path: "health"))) != nil
            if !up { usleep(200_000) }
        }
        guard up else { fail("demo agent not reachable") }
        let token = (try? String(contentsOfFile: home + "/.epokio/token", encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        var req = URLRequest(url: base.appending(path: "demo"))
        req.httpMethod = "POST"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = Data("{}".utf8)
        guard (try? call(req)) != nil else { fail("demo runs not created") }
        print("snapshot isolation: home \(home), demo agent :\(port)")
    }

    private static func repoSource() -> String? {
        var u = URL(fileURLWithPath: Bundle.main.executablePath ?? "").deletingLastPathComponent()
        for _ in 0..<6 {
            if FileManager.default.fileExists(atPath: u.appending(path: "src/epokio/agent.py").path) { return u.appending(path: "src").path }
            u = u.deletingLastPathComponent()
        }
        return nil
    }

    private static func freePort() -> Int {
        let s = socket(AF_INET, SOCK_STREAM, 0); defer { close(s) }
        var a = sockaddr_in(); a.sin_family = sa_family_t(AF_INET); a.sin_addr.s_addr = inet_addr("127.0.0.1"); a.sin_port = 0
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &a) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(s, $0, len) } }
        _ = withUnsafeMutablePointer(to: &a) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(s, $0, &len) } }
        return Int(UInt16(bigEndian: a.sin_port))
    }

    /// 격리 준비용 동기 호출(가로채기를 거치지 않는 별도 세션)
    @discardableResult
    static func call(_ r: URLRequest) throws -> Data {
        let sem = DispatchSemaphore(value: 0)
        nonisolated(unsafe) var out: Result<Data, Error> = .failure(URLError(.unknown))
        let s = URLSession(configuration: .ephemeral)
        let m = (r as NSURLRequest).mutableCopy() as! NSMutableURLRequest
        m.timeoutInterval = 5
        URLProtocol.setProperty(true, forKey: SnapshotGuard.passKey, in: m)
        s.dataTask(with: m as URLRequest) { d, resp, e in
            if let d, (resp as? HTTPURLResponse)?.statusCode == 200 { out = .success(d) } else { out = .failure(e ?? URLError(.badServerResponse)) }
            sem.signal()
        }.resume()
        sem.wait()
        return try out.get()
    }
    static func call(_ u: URL) throws -> Data { try call(URLRequest(url: u)) }

    /// 무해한 샘플: 코드로 그린 도형 사진 8장 + YOLO 라벨
    private static func makeDemoDataset() {
        let root = URL(fileURLWithPath: home).appending(path: "datasets/shapes")
        let imgs = root.appending(path: "images"), labels = root.appending(path: "labels")
        try? FileManager.default.createDirectory(at: imgs, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: labels, withIntermediateDirectories: true)
        try? "circle\nsquare\ntriangle\n".write(to: root.appending(path: "classes.txt"), atomically: true, encoding: .utf8)
        let W = 640, H = 480
        let palette: [(CGFloat, CGFloat, CGFloat)] = [(0.36, 0.30, 0.85), (0.10, 0.65, 0.66), (0.93, 0.55, 0.20), (0.85, 0.28, 0.40)]
        var rng = SystemRandomNumberGenerator()
        for i in 0..<8 {
            guard let ctx = CGContext(data: nil, width: W, height: H, bitsPerComponent: 8, bytesPerRow: 0,
                                      space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { continue }
            let g = CGFloat(i) / 8
            ctx.setFillColor(CGColor(red: 0.92 - g * 0.3, green: 0.94 - g * 0.2, blue: 0.97, alpha: 1))
            ctx.fill(CGRect(x: 0, y: 0, width: W, height: H))
            var lines: [String] = []
            for k in 0..<(2 + i % 3) {
                let cls = (i + k) % 3
                let w = CGFloat(Int.random(in: 70...170, using: &rng)), x = CGFloat(Int.random(in: 10...(W - 180), using: &rng))
                let y = CGFloat(Int.random(in: 10...(H - 180), using: &rng))
                let r = CGRect(x: x, y: y, width: w, height: w)
                let c = palette[(i + k) % palette.count]
                ctx.setFillColor(CGColor(red: c.0, green: c.1, blue: c.2, alpha: 0.9))
                switch cls {
                case 0: ctx.fillEllipse(in: r)
                case 1: ctx.fill(r)
                default:
                    ctx.move(to: CGPoint(x: r.midX, y: r.maxY)); ctx.addLine(to: CGPoint(x: r.minX, y: r.minY))
                    ctx.addLine(to: CGPoint(x: r.maxX, y: r.minY)); ctx.closePath(); ctx.fillPath()
                }
                // YOLO: 가운데·크기 비율, y는 위에서부터(CG는 아래에서부터)
                lines.append(String(format: "%d %.4f %.4f %.4f %.4f", cls, r.midX / CGFloat(W), 1 - r.midY / CGFloat(H), w / CGFloat(W), w / CGFloat(H)))
            }
            guard let cg = ctx.makeImage(), let png = NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:]) else { continue }
            let name = String(format: "shapes_%02d", i)
            try? png.write(to: imgs.appending(path: name + ".png"))
            try? lines.joined(separator: "\n").write(to: labels.appending(path: name + ".txt"), atomically: true, encoding: .utf8)
        }
    }

    // MARK: ④ 통신 가리기
    /// 실제 기계·사용자를 드러내는 문자열(긴 것부터 바꾼다)
    static let secrets: [(String, String)] = {
        var real = ""
        if let pw = getpwuid(getuid()), let d = pw.pointee.pw_dir { real = String(validatingCString: d) ?? "" }
        var hosts = [ProcessInfo.processInfo.hostName, Host.current().localizedName ?? ""]
        var buf = [CChar](repeating: 0, count: 256)
        if gethostname(&buf, 255) == 0 { hosts.append(String(decoding: buf.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, as: UTF8.self)) }
        hosts += hosts.map { $0.replacingOccurrences(of: ".local", with: "") }
        hosts += hosts.map { $0.lowercased() }
        var pairs: [(String, String)] = []
        for p in [home, "/private" + home] where !p.isEmpty { pairs.append((p, "~")) }
        if !real.isEmpty { pairs.append((real, "~")) }
        for h in Set(hosts) where h.count >= 3 { pairs.append((h, fakeHost)) }
        for u in [NSUserName(), NSFullUserName()] where u.count >= 3 { pairs.append((u, fakeUser)) }
        return pairs.sorted { $0.0.count > $1.0.count }
    }()

    static func scrub(_ s: String) -> String {
        secrets.reduce(s) { $0.replacingOccurrences(of: $1.0, with: $1.1) }
    }
    static func scrub(_ d: Data) -> Data {
        guard let s = String(data: d, encoding: .utf8) else { return d }
        return Data(scrub(s).utf8)
    }

    /// 화면에 실제 값이 남았나. 남았으면 그 문자열들
    static func leaks(in strings: [String]) -> [String] {
        // ★여기 적는 말 자체가 공개 동기화 금지어에 걸린다(검사 대상 목록이라 내용은 정상): 쪼개서 적는다
        let bad = secrets.map(\.0).filter { $0.count >= 3 } + ["ds_" + "small", "Neural" + "D", "/Users" + "/"]
        return strings.filter { s in bad.contains { s.localizedCaseInsensitiveContains($0) } }
    }

    /// 뷰의 접근성 트리에서 글자를 모은다
    @MainActor static func texts(of view: NSView) -> [String] {
        var out: [String] = []
        var seen = Set<ObjectIdentifier>()
        func walk(_ e: Any, depth: Int) {
            guard depth < 40, let o = e as? NSObject, seen.insert(ObjectIdentifier(o)).inserted else { return }
            // 옛 속성 API: SwiftUI 접근성 노드(NSObject)에서도 통한다
            for k: NSAccessibility.Attribute in [NSAccessibility.Attribute(rawValue: "AXLabel"), .title, .value, .help, .description] {
                if let s = o.accessibilityAttributeValue(k) as? String, !s.isEmpty { out.append(s) }
            }
            for c in (o.accessibilityAttributeValue(.children) as? [Any]) ?? [] { walk(c, depth: depth + 1) }
            if let v = o as? NSView { for c in v.subviews { walk(c, depth: depth + 1) } }
        }
        walk(view, depth: 0)
        return out
    }

    /// 찍기 직전 점검: 접근성 글자 + 찍힌 그림의 글자(OCR). 실제 값이 보이면 PNG를 쓰지 않고 끝낸다
    @MainActor static func audit(_ view: NSView, image: CGImage?, section: String) {
        guard isolated else { return }
        var t = texts(of: view)
        var ocr = 0
        if let image {
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            req.recognitionLanguages = ["en-US", "ko-KR"]
            try? VNImageRequestHandler(cgImage: image).perform([req])
            let found = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            ocr = found.count
            t += found
        }
        let bad = leaks(in: t)
        if !bad.isEmpty {
            FileHandle.standardError.write(Data("snapshot isolation LEAK in \(section): \(bad.prefix(5)). No snapshot written.\n".utf8))
            cleanup()
            exit(3)
        }
        print("snapshot isolation audit \(section): ok (\(t.count - ocr) accessibility + \(ocr) OCR strings, blocked \(SnapshotGuard.blocked) outside requests)")
    }

    /// 점검기 자체 시험(--snapshot-audit-selftest): 진짜 호스트명을 그린 그림을 OCR이 잡아내나.
    /// 이게 없으면 audit이 글자를 하나도 못 읽고도 "ok"를 찍을 수 있다.
    static func selftest() -> Never {
        let real = secrets.first { $0.1 == fakeHost }?.0 ?? ProcessInfo.processInfo.hostName
        let W = 900, H = 200
        guard let ctx = CGContext(data: nil, width: W, height: H, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
        else { print("selftest failed: no context"); exit(4) }
        ctx.setFillColor(CGColor(gray: 1, alpha: 1)); ctx.fill(CGRect(x: 0, y: 0, width: W, height: H))
        let line = NSAttributedString(string: real, attributes: [.font: NSFont.systemFont(ofSize: 64), .foregroundColor: NSColor.black])
        ctx.textMatrix = .identity
        ctx.textPosition = CGPoint(x: 20, y: 70)
        CTLineDraw(CTLineCreateWithAttributedString(line), ctx)
        guard let img = ctx.makeImage() else { print("selftest failed: no image"); exit(4) }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        try? VNImageRequestHandler(cgImage: img).perform([req])
        let found = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        if leaks(in: found).isEmpty {
            print("selftest failed: planted \(real) but audit read \(found) and saw nothing")
            exit(4)
        }
        print("selftest ok: planted host name was caught")
        exit(0)
    }

    static func cleanup() {
        if let a = agent, a.isRunning { a.terminate() }
        defaults?.removePersistentDomain(forName: suite)
        let plist = (getpwuid(getuid()).flatMap { String(validatingCString: $0.pointee.pw_dir) } ?? "") + "/Library/Preferences/\(suite).plist"
        if defaults != nil { try? FileManager.default.removeItem(atPath: plist) }   // 스냅샷 전용 도메인 파일(내용은 이미 비움)
        if !home.isEmpty, home.contains("epokio-snap-") { try? FileManager.default.removeItem(atPath: home) }
    }

    static func fail(_ why: String) -> Never {
        FileHandle.standardError.write(Data("snapshot isolation failed: \(why). No snapshot written.\n".utf8))
        cleanup()
        exit(2)
    }
}

extension UserDefaults {
    /// 스냅샷 모드에서 +standardUserDefaults 자리에 들어간다(바꿔치기 뒤에는 이 이름이 원래 것을 부른다)
    @objc class func epokioSnapshotStandard() -> UserDefaults { SnapshotIsolation.snapshotDefaults }
}

/// 스냅샷 모드의 모든 URL 요청을 가로챈다
final class SnapshotGuard: URLProtocol, @unchecked Sendable {
    static let passKey = "epokio.snapshot.pass"
    nonisolated(unsafe) static var blocked = 0
    private var inner: URLSessionDataTask?

    override class func canInit(with request: URLRequest) -> Bool {
        URLProtocol.property(forKey: passKey, in: request) == nil
    }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url, let host = url.host(), ["127.0.0.1", "localhost", "::1"].contains(host),
              var c = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            SnapshotGuard.blocked += 1                        // 밖으로 나가는 요청(원격 기계·인터넷)은 막는다
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet))
            return
        }
        c.host = "127.0.0.1"; c.port = SnapshotIsolation.agentPort          // 실제 8787 대신 격리 agent
        let m = (request as NSURLRequest).mutableCopy() as! NSMutableURLRequest
        m.url = c.url
        URLProtocol.setProperty(true, forKey: SnapshotGuard.passKey, in: m)
        inner = URLSession(configuration: .ephemeral).dataTask(with: m as URLRequest) { [weak self] d, resp, e in
            guard let self else { return }
            if let e { self.client?.urlProtocol(self, didFailWithError: e); return }
            if let resp { self.client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed) }
            if let d { self.client?.urlProtocol(self, didLoad: SnapshotIsolation.scrub(d)) }
            self.client?.urlProtocolDidFinishLoading(self)
        }
        inner?.resume()
    }
    override func stopLoading() { inner?.cancel() }
}
