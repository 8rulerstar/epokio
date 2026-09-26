import Foundation

// agent의 실행 API. 보기(GET)는 그냥, 실행(POST)은 토큰을 붙인다.
// 같은 맥의 agent 토큰은 ~/.epokio/token 을 직접 읽는다. 원격 토큰은 사용자가 붙여 넣은 값.

struct PyEnv: Codable, Identifiable, Hashable {
    var id: String { path }
    let path: String
    let name: String
    let python: String?
    let ultralytics: String?
    let torch: String?
    let cuda: Bool?
    let mps: Bool?
    let ready: Bool
    var device: String { cuda == true ? "CUDA" : mps == true ? "Apple GPU" : "CPU" }
}

struct Field: Codable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let `default`: JSONValue?
    let type: String
    let help: String
    let section: String
    let basic: Bool?
}

struct SchemaPayload: Codable {
    let ok: Bool
    let ultralytics: String?
    let fields: [Field]?
    let reason: String?
}

struct Job: Codable, Identifiable, Hashable {
    let id: String
    let kind: String
    let name: String
    let state: String
    let created: Double
    let started: Double?
    let ended: Double?
    let returncode: Int?
    let output: String
    var python: String?
    /// 실행 없이 기록만 한 작업(예측 파일 가져오기)
    var imported: Bool { python == "" }
    var kindTitle: String {
        switch kind {
        case "train": L("Training"); case "evaluate": imported ? L("Imported check") : L("Check"); case "autolabel": L("Auto-label")
        case "export": L("Export"); case "setup": L("Python setup"); case "practice": L("Practice"); default: L("Script")
        }
    }
    /// "2시간 전" (끝났으면 끝난 때, 아니면 만든 때)
    var when: String {
        let f = RelativeDateTimeFormatter(); f.unitsStyle = .abbreviated
        return f.localizedString(for: Date(timeIntervalSince1970: ended ?? started ?? created), relativeTo: .now)
    }
}

struct AutoLabelSummary: Codable {
    let images: Int?
    let empty: [String]?
    let low: [LowConf]?
    let per_class: [String: Int]?
    let conf_hist: [Int]?
    struct LowConf: Codable, Hashable { let image: String; let min_conf: Double }
}

/// JSON의 아무 값 (설정표 기본값이 숫자·문자·불리언·null로 섞여 있다)
enum JSONValue: Codable, Hashable {
    case string(String), number(Double), bool(Bool), null
    init(from d: Decoder) throws {
        let c = try d.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else { self = .string(try c.decode(String.self)) }
    }
    func encode(to e: Encoder) throws {
        var c = e.singleValueContainer()
        switch self {
        case .string(let s): try c.encode(s)
        case .number(let n): try c.encode(n)
        case .bool(let b): try c.encode(b)
        case .null: try c.encodeNil()
        }
    }
    var text: String {
        switch self {
        case .string(let s): s
        case .number(let n): n == n.rounded() && abs(n) < 1e9 ? String(Int(n)) : String(n)
        case .bool(let b): b ? "true" : "false"
        case .null: ""
        }
    }
}

enum AgentError: LocalizedError {
    case noToken, http(Int, String), bad
    var errorDescription: String? {
        switch self {
        case .noToken: L("No access token for this machine. Run `epokio-agent --show-token` there and paste it in Settings.")
        case .http(401, _): L("This machine did not accept the token. Paste it again in Settings, Machines.")
        case .http(403, _): L("This machine does not accept this address. Use its IP address, or set EPOKIO_ALLOWED_HOSTS there.")
        case .http(let c, let m): L("The helper refused (%d): %@", c, m)
        case .bad: L("Could not reach the helper. Is it running?")
        }
    }
}

struct AgentClient {
    let base: URL
    var tokenOverride: String? = nil                   // 기계를 더할 때, 저장하기 전에 붙여 넣은 토큰을 먼저 시험한다

    static let local = AgentClient(base: AgentLauncher.url)
    /// 실제로 부를 주소(이 Mac이면 agent가 옮겨 간 포트)
    var live: URL { AgentLauncher.resolve(base) }

    var token: String? {
        if let tokenOverride { return tokenOverride }
        if base.host == "127.0.0.1" || base.host == "localhost" {
            let f = FileManager.default.homeDirectoryForCurrentUser.appending(path: ".epokio/token")
            return (try? String(contentsOf: f, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        let key = base.absoluteString
        if let t = Self.remoteTokens[key] { return t }          // ★목록은 2초마다 읽는다. 키체인을 매번 묻지 않게 기억
        let t = Keychain.get(key)
        Self.remoteTokens[key] = t
        return t
    }
    nonisolated(unsafe) static var remoteTokens: [String: String] = [:]
    /// 보기(GET)에 붙이는 토큰. 네트워크에 연 agent는 보기에도 토큰을 요구한다(server.py reads_need_token)
    func authorize(_ req: inout URLRequest) { if let token { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") } }

    func get<T: Decodable>(_ path: String, _ query: [String: String] = [:]) async throws -> T {
        var c = URLComponents(url: live.appending(path: path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            c.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
            // URLQueryItem은 + 를 그대로 둔다. 파이썬 parse_qs는 + 를 공백으로 읽어 'yolo+aug' 같은 경로가 404였다
            c.percentEncodedQuery = c.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        }
        var req = URLRequest(url: c.url!)
        req.setValue(appLanguage, forHTTPHeaderField: "Accept-Language")
        // ★GET도 토큰을 싣는다. agent가 /jobs·/pythons·/schema·/health-check를 토큰 뒤로 옮긴 뒤(2026-09-23)
        //   여기만 안 실어서 대기열·학습 폼·검진·멈춤 버튼이 전부 조용히 비어 있었다(try?라 오류도 안 보였다)
        req.timeoutInterval = 30
        authorize(&req)
        let (data, resp) = try await URLSession.shared.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        // 401(토큰)·403(주소 이름)은 따로. ★전부 '연결 안 됨'으로 보여 엉뚱한 곳(--host)을 고치게 했다
        guard code == 200 else { throw code == 401 || code == 403 ? AgentError.http(code, "") : AgentError.bad }
        return try JSONDecoder().decode(T.self, from: data)
    }

    @discardableResult
    func post(_ path: String, _ body: [String: Any] = [:]) async throws -> [String: Any] {
        guard let token else { throw AgentError.noToken }
        var req = URLRequest(url: live.appending(path: path))
        req.setValue(appLanguage, forHTTPHeaderField: "Accept-Language")
        req.httpMethod = "POST"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, resp) = try await URLSession.shared.data(for: req)
        let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard code == 200 else { throw AgentError.http(code, obj["error"] as? String ?? "") }
        return obj
    }
}

/// agent가 검진·보고서 문장을 이 언어로 돌려준다. 앱 화면과 같은 언어(설정의 언어 선택 포함).
let appLanguage = Bundle.main.preferredLocalizations.first ?? "en"
