import Foundation
import Observation

// 여러 agent(로컬·원격)를 주기적으로 읽어 화면에 넘긴다.
@MainActor @Observable
final class Store {
    var runs: [Run] = []
    var system: [String: SystemPayload] = [:]
    var offline: Set<String> = []
    /// 읽지 못한 폴더(기계 이름 → 폴더들). 팝오버에 권한 안내를 띄운다
    var slowRoots: [String: [String]] = [:]
    /// 기계별로 지켜보는 폴더 수. 팝오버 바닥의 "N곳을 보는 중"이 이걸 합친다(기계 수가 아니다)
    var rootCount: [String: Int] = [:]
    /// 기계마다 마지막으로 못 받은 이유(토큰·주소 이름·오래된 판·꺼짐). ★전부 '오프라인'으로만 보여 원인을 알 수 없었다
    var lastError: [String: String] = [:]
    var agents: [URL]
    private var labels: [String: URL] = [:]          // 기계 이름 → agent 주소 (상세·그림을 그 기계에서 받는다)

    // Studio 이동: 팝오버·알림·알림함에서 특정 학습을 바로 연다
    var section: Studio.Section? = .home          // Studio를 열면 대시보드 홈부터
    var selectedRun: String?
    var showInbox = false                             // Studio 오른쪽 위 종 버튼의 알림 목록
    var gotRuns = false                               // 첫 /runs 응답을 받았나(받기 전에 "쉬는 모드"로 보이지 않게)
    var systemAt = Date.distantPast                   // 시스템 정보를 마지막으로 받은 때(오래된 CPU 값으로 캐릭터가 계속 달리지 않게)
    var scanMode = "auto"                             // agent의 기록 읽기 방식(ScanModeRow). manual이면 팝오버에 띠
    var showShortcuts = false                         // ⌘/ 단축키 목록
    var focusSearch = 0                               // ⌘F: 학습 목록 검색 칸으로(바뀔 때마다)
    var tourStep: Int?                                // "첫 학습 따라하기" 단계(TrainingTour). nil이면 꺼짐
    var toast: Toast?                                 // 잠깐 뜨는 알림 띠(실패·완료)

    struct Toast: Equatable {
        let text: String; let bad: Bool; let id = UUID()
        var actionTitle: String? = nil                   // 예: "되돌리기"
        var action: (() -> Void)? = nil
        static func == (a: Toast, b: Toast) -> Bool { a.id == b.id }
    }

    /// 실행 요청은 전부 여기로. 실패하면 알림 띠로 알린다(★예전엔 try?로 버려 눌러도 아무 일 없어 보였다)
    func act(_ done: String? = nil, _ work: @escaping () async throws -> Void) async {
        do {
            try await work()
            if let done { say(done) }
        } catch {
            say(error.localizedDescription, bad: true)
        }
        refresh()
    }

    /// 방금 바뀐 학습: 목록 줄이 잠깐 빛난다
    var flashRun: String?
    func flash(_ id: String) {
        flashRun = id
        Task { try? await Task.sleep(for: .seconds(1.2)); if flashRun == id { flashRun = nil } }
    }

    func say(_ text: String, bad: Bool = false, actionTitle: String? = nil, action: (() -> Void)? = nil) {
        let t = Toast(text: text, bad: bad, actionTitle: actionTitle, action: action)
        toast = t
        let wait: Double = action != nil ? 6 : bad ? 5 : 2.5          // 되돌리기가 있으면 누를 시간을 더 준다
        Task { try? await Task.sleep(for: .seconds(wait)); if toast == t { toast = nil } }
    }
    var pendingTrainArgs: [String: String]?           // "같은 설정으로 다시 학습" (args.yaml 값)
    var pendingReviewModel: String?                   // "실수 검수"로 넘길 best.pt
    var pendingReviewJob: String?                     // 대기열의 "검수에서 열기": 이 평가 결과를 연다
    var pendingCompare: [String]?                     // 명령으로 "비교해 줘": 이 학습들로 비교 화면을 연다
    var inbox: [InboxItem] = Store.loadInbox()
    var jobs: [Job] = []                              // 이 Mac 대기열 (팝오버 빠른 작업용)
    var runningJob: Job? { jobs.first { $0.state == "running" } }
    var queuedCount: Int { jobs.filter { $0.state == "queued" }.count }

    private var timer: Timer?
    private var lastFull = Date.distantPast
    private var lastTokenPush = Date.distantPast

    /// 팝오버·Studio가 열려 있는 수. 0이면 시스템 정보를 안 받고 갱신도 느리게 한다
    var viewers = 0 { didSet { if viewers > oldValue { refresh() }; reschedule() } }

    /// 앱의 Store (메뉴바 우클릭 메뉴처럼 SwiftUI 밖에서 상태를 볼 때)
    nonisolated(unsafe) static weak var current: Store?

    init(agents: [URL]) {
        self.agents = agents
        Store.current = self
        refresh()
        reschedule()
    }

    /// 보는 화면이 있거나 도는 학습이 있으면 설정한 간격(기본 2초), 아니면 10초.
    /// ★예전엔 항상 2초마다 전체 목록과 시스템 정보를 받아 agent가 쉬지 못했다
    private func reschedule() {
        let every = UserDefaults.standard.double(forKey: "refreshSeconds")
        let fast = every > 0 ? every : 2.0
        let want = (viewers > 0 || runs.contains(where: \.isLive)) ? fast : max(fast, 10)
        guard timer?.timeInterval != want else { return }
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: want, repeats: true) { _ in
            Task { @MainActor in self.refresh() }
        }
    }

    var lead: Run? { runs.first(where: \.isLive) }

    /// 기계 이름(연결된 agent의 label). 아직 모르면 주소의 호스트
    func label(for url: URL) -> String {
        labels.first(where: { $0.value == url })?.key ?? (url == AgentLauncher.url ? "local" : url.host() ?? url.absoluteString)
    }

    func client(for run: Run) -> AgentClient { AgentClient(base: labels[run.source] ?? AgentLauncher.url) }
    /// 이 Mac의 학습인가. SSH로 비춰 온 것은 사본이라 아니다(다시 학습·폴더 열기 같은 동작을 막는다)
    func isLocal(_ run: Run) -> Bool { run.ssh == nil && (labels[run.source] ?? AgentLauncher.url).host() == "127.0.0.1" }
    func open(run id: String) { selectedRun = id; section = .runs }

    // ── 알림함 ──
    var unread: Int { inbox.filter { !$0.read }.count }
    /// 팝오버 맨 위에 띄울 "방금 끝남": 6시간 안에 끝났고 아직 안 본 것
    var justFinished: InboxItem? { inbox.first { $0.isResult && !$0.read && -$0.date.timeIntervalSinceNow < 6 * 3600 } }
    func markRead(_ id: String? = nil) {
        for i in inbox.indices where id == nil || inbox[i].id == id || inbox[i].runID == id { inbox[i].read = true }
        saveInbox()
    }
    func clearInbox() { inbox.removeAll(); saveInbox() }
    private func record(_ events: [Notifier.Event], machine: String) {
        guard !events.isEmpty else { return }
        // id에 boot를 넣는다. ★agent를 다시 켜면 번호가 1부터라, 이미 있는 번호로 보고 새 알림을 알림함에서 뺐다
        for e in events where !inbox.contains(where: { $0.id == "\(machine)|\(e.key)" }) {
            inbox.insert(InboxItem(id: "\(machine)|\(e.key)", kind: e.kind, runID: "\(machine)|\(e.run.path)",
                                   runName: e.run.displayName, machine: machine, best: e.run.best,
                                   epoch: e.run.epoch, total: e.run.total, date: .now), at: 0)
        }
        if inbox.count > 300 { inbox.removeLast(inbox.count - 300) }
        saveInbox()
    }
    private static let inboxFile = FileManager.default.homeDirectoryForCurrentUser.appending(path: ".epokio/inbox.json")
    private static func loadInbox() -> [InboxItem] {
        guard let d = try? Data(contentsOf: inboxFile) else { return [] }
        let dec = JSONDecoder(); dec.dateDecodingStrategy = .iso8601
        return (try? dec.decode([InboxItem].self, from: d)) ?? []
    }
    private func saveInbox() {
        let enc = JSONEncoder(); enc.dateEncodingStrategy = .iso8601
        try? FileManager.default.createDirectory(at: Self.inboxFile.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? enc.encode(inbox).write(to: Self.inboxFile, options: .atomic)
    }

    func addAgent(_ u: URL) {
        guard !agents.contains(u) else { return }
        agents.append(u); save(); refresh()
    }
    func removeAgent(_ u: URL) {
        agents.removeAll { $0 == u }
        runs.removeAll { $0.source != "local" }     // 원격 run은 비우고 남은 기계에서 다시 받는다
        // ★뺀 기계의 GPU·CPU 고리가 팝오버와 메뉴바에 계속 남았다
        for l in labels.filter({ $0.value == u }).map(\.key) { system[l] = nil; labels[l] = nil }
        offline.remove(u.absoluteString); lastError[u.absoluteString] = nil; save(); refresh()
    }
    private func save() { UserDefaults.standard.set(agents.map(\.absoluteString), forKey: "agents") }

    func refresh() {
        pushRemoteTokens()
        // 대기열은 보는 화면이 있거나 도는 작업이 있을 때만(★쉴 때도 매번 물었다)
        if viewers > 0 || runningJob != nil {
            Task {
                struct J: Decodable { let jobs: [Job] }
                // ★/jobs는 토큰이 있어야 한다. 토큰 없는 fetch로 물어서 늘 401이었고 대기열·멈춤 버튼이 안 떴다
                if let j: J = try? await AgentClient.local.get("jobs") { jobs = j.jobs }
            }
        }
        for url in agents {
            Task {
                async let r: RunsPayload? = fetch(url, "runs")
                let resting = gotRuns && RestMode.isResting(runs: runs)
                let wantSystem = viewers > 0 || (UserDefaults.standard.string(forKey: "barShow") ?? "").contains("gpu")
                    || resting                                      // 쉬는 모드 카드가 CPU·메모리·온도를 보여 준다
                    || PaceSource.effectiveNow(resting: resting) != .train     // 캐릭터가 CPU 따라 달릴 때(RunnerPace)
                async let s: SystemPayload? = wantSystem ? fetch(url, "system") : nil
                let (runs, sys) = await (r, s)
                await MainActor.run {
                    guard agents.contains(url) else { return }     // 받는 사이 뺀 기계면 되살리지 않는다
                    let key = url.absoluteString
                    if let runs {
                        offline.remove(key)
                        gotRuns = true
                        lastError[key] = nil
                        labels[runs.label] = url
                        if url == AgentLauncher.url, let m = runs.scan_mode, m != scanMode { scanMode = m }
                        if let r = runs.roots, rootCount[runs.label] != r.count { rootCount[runs.label] = r.count }
                        let slow = runs.slow_roots ?? []
                        if slowRoots[runs.label] ?? [] != slow { slowRoots[runs.label] = slow.isEmpty ? nil : slow }      // 애니메이션은 팝오버가 건다
                        var merged = self.runs.filter { $0.source != runs.label }
                        merged += runs.runs.map { var x = $0; x.source = runs.label; return x }
                        merged.sort(by: Store.order)
                        // ★"몇 초 전"만 바뀐 경우까지 매번 바꾸면 화면 전체(그래프 포함)가 2초마다 다시 그려져 CPU 10%를 썼다.
                        //   진행·상태·점수가 바뀌었을 때만 바로, 시간 표시는 30초에 한 번 따라잡는다
                        if Store.meaningful(merged) != Store.meaningful(self.runs) || Date().timeIntervalSince(lastFull) > 30 {
                            self.runs = merged
                            SpotlightIndex.update(merged)
                            lastFull = Date()
                        }
                        KeepAwake.shared.update(training: self.runs.contains { $0.isLive && self.isLocal($0) })
                        Trophies.shared.evaluate(self)
                        reschedule()
                    } else {
                        offline.insert(key)
                    }
                    if let sys { system[sys.label] = sys; systemAt = .now }
                }
                let label = runs?.label ?? url.host() ?? "agent"
                let events = await Notifier.shared.poll(url, label: label)
                record(events, machine: label)
            }
        }
    }

    /// 여러 기계 스윕: 로컬 agent가 원격에 학습을 넣으려면 그 기계 토큰이 필요하다. 키체인에서 꺼내 넘겨 준다(1분에 한 번).
    /// agent는 ★메모리에만 둔다(디스크에 안 씀, 사용자 결정). agent가 다시 켜져 비어도 여기서 곧 다시 채운다
    func pushRemoteTokens(force: Bool = false) {
        guard force || Date().timeIntervalSince(lastTokenPush) > 60 else { return }
        lastTokenPush = Date()
        var tokens: [String: String] = [:]
        for u in agents where !(u.host == "127.0.0.1" || u.host == "localhost") {
            if let t = Keychain.get(u.absoluteString) { tokens[u.absoluteString.hasSuffix("/") ? String(u.absoluteString.dropLast()) : u.absoluteString] = t }
        }
        guard !tokens.isEmpty else { return }
        nonisolated(unsafe) let body: [String: Any] = ["tokens": tokens]
        Task { _ = try? await AgentClient.local.post("remotes/tokens", body) }
    }

    /// 화면에 의미 있는 부분만(흐른 시간 제외)
    static func meaningful(_ rs: [Run]) -> [String] {
        rs.map { "\($0.id)|\($0.state)|\($0.epoch)|\($0.best ?? -1)|\($0.total ?? -1)|\($0.meta?.hashValue ?? 0)" }
    }

    static let rank = ["running": 0, "starting": 1, "stalled": 2, "failed": 3, "stopped": 4, "done": 5]
    static func order(_ a: Run, _ b: Run) -> Bool {
        let ra = rank[a.state] ?? 9, rb = rank[b.state] ?? 9
        return ra != rb ? ra < rb : a.idle < b.idle
    }

    private func fetch<T: Decodable>(_ base: URL, _ path: String) async -> T? {
        // 이 Mac이면 agent가 옮겨 간 포트로 부른다(AgentLauncher.resolve)
        var req = URLRequest(url: AgentLauncher.resolve(base).appending(path: path))
        req.timeoutInterval = 3
        // 토큰도 싣는다. agent는 IP·자기 이름이 아닌 주소(DNS 리바인딩 막기)면 토큰이 있어야 답한다
        // (키체인 키는 기계 주소 그대로라 base를 그대로 넘긴다)
        AgentClient(base: base).authorize(&req)
        let key = base.absoluteString
        guard let (data, resp) = try? await URLSession.shared.data(for: req) else {
            if path == "runs" { lastError[key] = AgentError.bad.localizedDescription }
            return nil
        }
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard code == 200 else {
            if path == "runs" {
                let msg = ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any])?["error"] as? String ?? ""
                lastError[key] = AgentError.http(code, msg).localizedDescription
            }
            return nil
        }
        do { return try JSONDecoder().decode(T.self, from: data) } catch {
            if path == "runs" { lastError[key] = L("This machine sent something this app cannot read. Update Epokio on it, or update this app.") }
            return nil
        }
    }
}
