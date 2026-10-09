import SwiftUI

// 자연어 명령 (선택 기능, 기본 꺼짐): "coco8 100에폭으로 다시 돌려" → 무엇을 · 어느 학습 · 몇 에폭.
// TypeSafe Jev는 고르기만 한다. 후보(동작 목록, 지금 학습 이름, 문장 속 숫자)는 코드가 만든다.
// ★보내는 것: 명령 문장과 학습 이름뿐. 학습 데이터·이미지·경로는 보내지 않는다.
// ★실행 전에 해석을 보여 주고 사람이 누른다. 멈추기는 확인 창을 한 번 더.

struct JevIntent: Equatable {
    enum Action: String { case trainAgain = "train_again", openResults = "open_results", compare, stop, tryModel = "try_model", none }
    var action: Action
    var runs: [Run]
    var epochs: Int?
    var confidence: Double
}

enum Jev {
    static let keychainKey = "typesafe.api"
    nonisolated(unsafe) static var testKey: String?          // 검증 모드에서만
    static var key: String? { testKey ?? Keychain.get(keychainKey) }
    static var enabled: Bool { UserDefaults.standard.bool(forKey: "jevEnabled") && key != nil }

    enum Failure: LocalizedError {
        case noKey, http(Int)
        var errorDescription: String? {
            switch self {
            case .noKey: L("Add your TypeSafe API key in Settings first.")
            case .http(let c): L("TypeSafe did not answer (%d).", c)
            }
        }
    }

    static func interpret(_ command: String, runs all: [Run]) async throws -> JevIntent {
        guard let key else { throw Failure.noKey }
        let runs = Array(all.prefix(12))
        let names = runs.map(\.displayName)
        let nums = Array(Set(command.matches(of: /\d+/).compactMap { Int($0.output) })).sorted()
        var q: [String: Any] = [
            "action": ["type": "choice",
                       "instructions": "What does the user want Epokio (a training monitor app) to do? The request is `command`.",
                       "criteria": ["train_again": "Start the same training again, possibly with changed settings",
                                    "open_results": "Show or open the results, scores or charts of a run",
                                    "compare": "Compare two or more runs",
                                    "stop": "Stop or cancel a run that is training now",
                                    "try_model": "Try or test the trained model on an image",
                                    "none": "Something else, or not a request about runs"]],
            "run": ["type": "choice",
                    "instructions": "Which single run does `command` refer to? Choose from `runs`. Pick none if no run is named or implied.",
                    "criteria": Dictionary(uniqueKeysWithValues: names.enumerated().map { ("r\($0.offset)", $0.element) }).merging(["none": "No specific run"]) { $1 }],
        ]
        // 비교처럼 여러 개일 수 있어 학습마다 따로 묻는다(한꺼번에 병렬로 돈다)
        for (i, n) in names.enumerated() {
            q["mentions_r\(i)"] = ["type": "noul", "instructions": "Does `command` refer to the run named \"\(n)\"?"]
        }
        if !nums.isEmpty {
            q["epochs"] = ["type": "choice", "instructions": "Which number in `command` is the number of epochs to train for?",
                           "criteria": Dictionary(uniqueKeysWithValues: nums.map { ("n\($0)", "\($0) epochs") }).merging(["none": "No epoch count is given"]) { $1 }]
        }
        let body: [String: Any] = ["model": "jev-latest", "state": ["command": command, "runs": names], "questions": q]
        let obj = try await post(body, key: key)

        let action = JevIntent.Action(rawValue: obj["action"]?["choice"] as? String ?? "none") ?? .none
        let conf = obj["action"]?["confidence"] as? Double ?? 0
        var picked: [Run] = []
        if action == .compare {
            picked = runs.enumerated().filter { (obj["mentions_r\($0.offset)"]?["noul"] as? Double ?? 0) > 0.5 }.map(\.element)
        } else if let c = obj["run"]?["choice"] as? String, c.hasPrefix("r"), let i = Int(c.dropFirst()), i < runs.count {
            picked = [runs[i]]
        }
        let ep = (obj["epochs"]?["choice"] as? String).flatMap { $0.hasPrefix("n") ? Int($0.dropFirst()) : nil }
        return JevIntent(action: action, runs: picked, epochs: ep, confidence: conf)
    }

    /// 공용 호출부: 본문 하나 보내고 answers를 돌려준다(명령·해설 다듬기가 같이 쓴다)
    static func post(_ body: [String: Any], key: String) async throws -> [String: [String: Any]] {
        var req = URLRequest(url: URL(string: "https://api.typesafe.ai/v1/systemone")!)
        req.httpMethod = "POST"
        req.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        req.timeoutInterval = 20
        let (data, resp) = try await URLSession.shared.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard code == 200 else { throw Failure.http(code) }
        return (try JSONSerialization.jsonObject(with: data) as? [String: Any])?["answers"] as? [String: [String: Any]] ?? [:]
    }
}

/// 팝오버의 명령 칸. 켜져 있을 때만 보인다
struct CommandBar: View {
    let go: () -> Void                           // Studio 열기
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var text = ""
    @State private var busy = false
    @State private var intent: JevIntent?
    @State private var error: String?
    @State private var confirmStop = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Image(systemName: "sparkles").foregroundStyle(.tint).symbolEffect(.pulse, isActive: busy)
                TextField("Ask Epokio, e.g. \"retrain coco8 for 100 epochs\"", text: $text)
                    .textFieldStyle(.plain).onSubmit { Task { await ask() } }
                if busy { ProgressView().controlSize(.small) }
            }
            .padding(.horizontal, 10).padding(.vertical, 7)
            .background(.quaternary.opacity(0.4), in: .rect(cornerRadius: 10))
            if let intent { preview(intent).transition(.opacity.combined(with: .move(edge: .top))) }
            if let error { Text(verbatim: error).font(.ui(11.5)).foregroundStyle(.warn) }
        }
        .animation(.smooth, value: intent)
    }

    private func preview(_ i: JevIntent) -> some View {
        HStack(spacing: 8) {
            Text(verbatim: describe(i)).font(.ui(12)).lineLimit(2)
            Spacer()
            if i.action != .none && (i.action == .compare ? i.runs.count >= 2 : !i.runs.isEmpty) {
                Button(i.action == .stop ? L("Stop…") : L("Do It")) { run(i) }
                    .primaryButton().controlSize(.small)
                    .confirmationDialog(L("Stop \"%@\"?", i.runs.first?.displayName ?? ""), isPresented: $confirmStop) {
                        Button("Stop", role: .destructive) { Task { await stop(i) } }
                    }
            }
            Button { intent = nil; text = "" } label: { Image(systemName: "xmark") }.buttonStyle(.plain).foregroundStyle(ink.soft)
        }
        .padding(8)
        .background(.tint.opacity(0.07), in: .rect(cornerRadius: 9))
    }

    private func describe(_ i: JevIntent) -> String {
        let names = i.runs.map(\.displayName).joined(separator: ", ")
        switch i.action {
        case .trainAgain: return L("Train %@ again", names.isEmpty ? "?" : names) + (i.epochs.map { " · " + L("%d epochs", $0) } ?? "")
        case .openResults: return L("Show results of %@", names.isEmpty ? "?" : names)
        case .compare: return L("Compare %@", names.isEmpty ? "?" : names)
        case .stop: return L("Stop %@", names.isEmpty ? "?" : names)
        case .tryModel: return L("Try the model of %@", names.isEmpty ? "?" : names)
        case .none: return L("Not sure what you mean. Try naming a run and what to do.")
        }
    }

    private func ask() async {
        guard !text.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        busy = true; error = nil; defer { busy = false }
        do {
            var i = try await Jev.interpret(text, runs: store.runs)
            if i.confidence < 0.6 { i.action = .none }       // 헷갈리면 아무것도 하지 않는다
            intent = i
        } catch { self.error = error.localizedDescription }
    }

    private func run(_ i: JevIntent) {
        guard let r = i.runs.first else { return }
        switch i.action {
        case .trainAgain:
            // 이 맥의 Ultralytics 학습만(RunActions canTrain·웹과 같은 규칙). ★다른 기계·SSH 학습의 경로로 이 맥 양식을 채웠다
            guard store.isLocal(r) else { error = L("Pick a run on this Mac first."); return }
            guard (r.framework ?? "ultralytics") == "ultralytics" else { error = L("Not available for this format"); return }
            Task {
                guard let d: RunDetail = try? await store.client(for: r).get("run", ["path": r.path]), d.args["data"] != nil else {
                    error = L("Not available for this format"); return
                }
                var args = d.trainArgs
                if let e = i.epochs { args["epochs"] = String(e) }
                store.pendingTrainArgs = args; store.section = .train; go()
            }
        case .openResults: store.open(run: r.id); go()
        case .compare: store.pendingCompare = i.runs.map(\.id); store.section = .runs; go()
        case .tryModel:
            UserDefaults.standard.set(r.path + "/weights/best.pt", forKey: "tryModel"); store.section = .tryit; go()
        case .stop: confirmStop = true; return
        case .none: return
        }
        intent = nil; text = ""
    }

    private func stop(_ i: JevIntent) async {
        guard let r = i.runs.first, let j = store.jobs.first(where: { $0.state == "running" && $0.output == r.path }) else {
            error = L("Only runs started from Epokio can be stopped here."); return
        }
        await store.act(L("Stopped")) { try await AgentClient.local.post("jobs/\(j.id)/cancel") }
        intent = nil; text = ""
    }
}
