import AppIntents
import CoreSpotlight

// Siri·단축어·Spotlight가 보는 학습 한 개. 이 Mac의 agent(/runs)만 읽는다(원격 기계는 넣지 않는다).
struct RunEntity: AppEntity, IndexedEntity {
    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Training Run"
    static let defaultQuery = RunQuery()

    let id: String                 // Run.id 와 같다("출처|경로"), 앱의 .openRun 알림이 이 값을 받는다
    @Property(title: "Name") var name: String
    @Property(title: "Status") var status: String
    @Property(title: "Progress") var progress: Double
    @Property(title: "Best Score") var best: Double?
    let run: Run

    init(_ r: Run) {
        id = r.id; run = r
        name = r.displayName; status = r.stateText; progress = r.progress ?? 0; best = r.best
    }

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(name)", subtitle: "\(IntentText.line(run))")
    }

    var attributeSet: CSSearchableItemAttributeSet {
        let a = defaultAttributeSet
        a.contentDescription = IntentText.line(run)
        a.keywords = ["epokio", "training", run.name] + (run.meta?.tags ?? [])
        return a
    }
}

struct RunQuery: EntityStringQuery {
    func entities(for identifiers: [RunEntity.ID]) async throws -> [RunEntity] {
        try await IntentAgent.runs().filter { identifiers.contains($0.id) }.map(RunEntity.init)
    }
    func entities(matching string: String) async throws -> [RunEntity] {
        try await IntentAgent.runs().filter { $0.displayName.localizedCaseInsensitiveContains(string) }.map(RunEntity.init)
    }
    func suggestedEntities() async throws -> [RunEntity] {
        try await Array(IntentAgent.runs().prefix(20)).map(RunEntity.init)
    }
}

/// 인텐트가 부르는 agent 호출. 앱 화면과 같은 AgentClient.local 을 쓴다(외부 전송 없음)
enum IntentAgent {
    @MainActor static func runs() async throws -> [Run] {
        let p: RunsPayload = try await AgentClient.local.get("runs")
        return p.runs.map { var r = $0; r.source = p.label; return r }.sorted(by: Store.order)
    }

    /// 같은 설정으로 다시: 양식과 같은 본문(retrain_args.py). args.yaml 전체를 타입 그대로, 이름·저장 위치만 새로, 모델은 원래 것
    static func retrain(_ r: Run) async throws -> String {
        let got = try await RetrainBody.fetch(AgentClient.local, path: r.path)
        guard got["model_ok"] as? Bool == true, let params = got["params"] as? [String: Any] else {
            throw AgentError.http(0, L("The original model %@ is not on this Mac. Use Train Again in Studio to pick one.", got["model"] as? String ?? "?"))
        }
        struct Envs: Decodable { let envs: [PyEnv] }
        let e: Envs = try await AgentClient.local.get("envs")
        guard let env = e.envs.first(where: \.ready) else { throw AgentError.http(0, L("No ready Python. Set one up in Studio, Train.")) }
        let name = r.name + "_again"
        nonisolated(unsafe) let body: [String: Any] = ["kind": "train", "name": name, "python": env.path, "params": params]
        try await AgentClient.local.post("jobs", body)
        return name
    }
}

/// 짧은 대답 문장. 한두 문장만
enum IntentText {
    static func line(_ r: Run) -> String {
        var s = [r.stateText, L("epoch %@", "\(r.epoch)/\(r.total.map(String.init) ?? "?")")]
        if let b = r.best { s.append(L("best %@", String(format: "%.3f", b))) }
        return s.joined(separator: " · ")
    }
    static func eta(_ sec: Double?) -> String? {
        guard let sec, sec > 0 else { return nil }
        let m = Int(sec / 60)
        return m >= 60 ? L("%dh %dm left", m / 60, m % 60) : L("%d min left", max(m, 1))
    }
    static func status(_ runs: [Run]) -> String {
        let live = runs.filter(\.isLive)
        guard let r = live.first else {
            guard let last = runs.first else { return L("No training runs yet.") }
            return L("Nothing is training. Last run %@: %@.", last.displayName, line(last))
        }
        let tail = eta(r.eta).map { ", " + $0 } ?? ""
        let more = live.count > 1 ? " " + L("%d more running.", live.count - 1) : ""
        return L("%@: %@%@.", r.displayName, line(r), tail) + more
    }
}
