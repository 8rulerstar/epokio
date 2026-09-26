import SwiftUI

// 업적: 이미 있는 기록(학습 목록·알림함·대기열)과 앱 안에서 센 횟수(스윕·비교·검수·라벨 고침)만 본다. 새로 모으는 데이터는 없다.
// 저장은 이 맥의 ~/.epokio/achievements.json 한 곳. 처음 켤 때 이미 채운 업적은 조용히 한꺼번에 준다(띠가 줄줄이 뜨지 않게).

enum Tier: Int, Codable { case bronze, silver, gold
    var color: Color { switch self { case .bronze: .warn; case .silver: .info; case .gold: .gold } }
    var title: String { switch self { case .bronze: L("Bronze"); case .silver: L("Silver"); case .gold: L("Gold") } }
}

struct Achievement: Identifiable {
    let id: String
    let title: String
    let detail: String
    let symbol: String
    let tier: Tier
    var goal = 1
    var hidden = false
    let progress: (Trophies.Context) -> Int
}

@MainActor @Observable
final class Trophies {
    static let shared = Trophies()

    struct Context { let runs: [Run]; let inbox: [InboxItem]; let jobs: [Job]; let counts: [String: Int] }
    private struct Saved: Codable { var unlocked: [String: Date] = [:]; var counts: [String: Int] = [:]; var seeded = false }

    private(set) var unlocked: [String: Date] = [:]
    private(set) var counts: [String: Int] = [:]
    private(set) var progress: [String: Int] = [:]
    private var seeded = false
    private static let file = FileManager.default.homeDirectoryForCurrentUser.appending(path: ".epokio/achievements.json")

    init() {
        let dec = JSONDecoder(); dec.dateDecodingStrategy = .iso8601
        if let d = try? Data(contentsOf: Self.file), let s = try? dec.decode(Saved.self, from: d) {
            unlocked = s.unlocked; counts = s.counts; seeded = s.seeded
        }
    }

    /// 앱 안에서 일어난 일을 센다(스윕·비교·판정·라벨 고침). 다음 평가 때 반영된다
    func bump(_ key: String, _ n: Int = 1) { counts[key, default: 0] += n; save() }

    /// 기록이 새로 들어올 때마다(Store.refresh) 부른다. 새로 딴 업적은 금색 띠
    func evaluate(_ store: Store) {
        let real = store.runs.filter { !$0.path.contains("/.epokio/demo/") && !$0.isPractice }     // 예시·연습은 세지 않는다
        let ctx = Context(runs: real, inbox: store.inbox, jobs: store.jobs,
                          counts: counts.merging(["demo": store.runs.contains { $0.path.contains("/.epokio/demo/") } ? 1 : 0,
                                                  "practice": store.runs.contains(where: \.isPractice) ? 1 : 0]) { a, b in max(a, b) })
        var fresh: [Achievement] = []
        for a in Self.all {
            let p = min(a.progress(ctx), a.goal)
            if progress[a.id] != p { progress[a.id] = p }
            if p >= a.goal, unlocked[a.id] == nil { unlocked[a.id] = .now; fresh.append(a) }
        }
        guard !fresh.isEmpty || !seeded else { return }
        let announce = seeded && UserDefaults.standard.bool(forKey: "achievements")         // 업적은 기본 꺼짐(설정 → 일반)
            && UserDefaults.standard.object(forKey: "achievementAlerts") as? Bool ?? true
        seeded = true
        save()
        guard announce, let a = fresh.last else { return }
        Haptic.success()
        if let s = BarStyle.allCases.first(where: { st in fresh.contains { $0.id == st.unlockedBy } }) {     // 아이콘이 열렸으면 그걸 먼저 알린다
            store.say(L("New icon: %@", s.name), actionTitle: L("Use It")) { UserDefaults.standard.set(s.rawValue, forKey: "barStyle") }
            return
        }
        store.say(fresh.count > 1 ? L("%d achievements unlocked", fresh.count) : L("Achievement unlocked: %@", a.title),
                  actionTitle: L("See")) { store.section = .trophies }
    }

    private func save() {
        let enc = JSONEncoder(); enc.dateEncodingStrategy = .iso8601
        try? FileManager.default.createDirectory(at: Self.file.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? enc.encode(Saved(unlocked: unlocked, counts: counts, seeded: seeded)).write(to: Self.file, options: .atomic)
    }

    /// 다음에 딸 만한 것: 숨은 것 빼고 진행률이 가장 높은 것
    var next: Achievement? {
        Self.all.filter { unlocked[$0.id] == nil && !$0.hidden }
            .max { Double(progress[$0.id] ?? 0) / Double($0.goal) < Double(progress[$1.id] ?? 0) / Double($1.goal) }
    }

    // ── 목록 ──
    static let all: [Achievement] = [
        // 시작
        Achievement(id: "first_run", title: L("Hello, Epokio"), detail: L("See your first training run"), symbol: "sparkle", tier: .bronze) { $0.runs.isEmpty ? 0 : 1 },
        Achievement(id: "first_done", title: L("Finish line"), detail: L("Have a training run finish"), symbol: "flag.checkered", tier: .bronze) { $0.runs.contains { $0.state == "done" } ? 1 : 0 },
        Achievement(id: "demo", title: L("Window shopper"), detail: L("Look around with the sample runs"), symbol: "eyeglasses", tier: .bronze) { $0.counts["demo"] ?? 0 },
        Achievement(id: "practice", title: L("Dress rehearsal"), detail: L("Start a practice run"), symbol: "sparkles.tv", tier: .bronze) { $0.counts["practice"] ?? 0 },
        Achievement(id: "star", title: L("Favorite"), detail: L("Star a run"), symbol: "star.fill", tier: .bronze) { $0.runs.contains { $0.meta?.star == true } ? 1 : 0 },
        // 성장
        Achievement(id: "runs10", title: L("Getting serious"), detail: L("Have 10 training runs"), symbol: "square.stack", tier: .bronze, goal: 10) { $0.runs.count },
        Achievement(id: "runs50", title: L("Lab regular"), detail: L("Have 50 training runs"), symbol: "square.stack.3d.up", tier: .silver, goal: 50) { $0.runs.count },
        Achievement(id: "runs100", title: L("Century"), detail: L("Have 100 training runs"), symbol: "crown.fill", tier: .gold, goal: 100) { $0.runs.count },
        Achievement(id: "goal", title: L("Bullseye"), detail: L("Reach a goal score you set"), symbol: "target", tier: .silver) { r in
            r.runs.contains { $0.meta?.goal_hit == true } || r.inbox.contains { $0.kind == "goal" } ? 1 : 0 },
        // 실험
        Achievement(id: "sweep", title: L("Many at once"), detail: L("Queue a sweep"), symbol: "square.grid.3x3", tier: .bronze) { $0.counts["sweep"] ?? 0 },
        Achievement(id: "smart", title: L("Let it think"), detail: L("Queue a smart sweep"), symbol: "brain", tier: .silver) { $0.counts["smart_sweep"] ?? 0 },
        Achievement(id: "compare", title: L("Side by side"), detail: L("Compare two runs"), symbol: "square.split.2x1", tier: .bronze) { $0.counts["compare"] ?? 0 },
        Achievement(id: "machines", title: L("Fleet"), detail: L("Train on two machines at the same time"), symbol: "server.rack", tier: .gold) { r in
            Set(r.runs.filter(\.isLive).map(\.source)).count >= 2 ? 1 : 0 },
        // 품질
        Achievement(id: "review100", title: L("Sharp eye"), detail: L("Judge 100 images in Review"), symbol: "checkmark.rectangle.stack", tier: .silver, goal: 100) { $0.counts["verdict"] ?? 0 },
        Achievement(id: "fix10", title: L("Label fixer"), detail: L("Fix 10 labels"), symbol: "pencil.and.outline", tier: .silver, goal: 10) { $0.counts["fix"] ?? 0 },
        Achievement(id: "autolabel", title: L("Robot helper"), detail: L("Finish an auto-label job"), symbol: "wand.and.stars", tier: .bronze) { r in
            r.jobs.contains { $0.kind == "autolabel" && $0.state == "done" } ? 1 : 0 },
        Achievement(id: "ship", title: L("Shipped"), detail: L("Put a model in use"), symbol: "shippingbox.fill", tier: .gold) { $0.runs.contains { $0.meta?.stage == "production" } ? 1 : 0 },
        // 숨은 것
        Achievement(id: "night", title: L("Night owl"), detail: L("A training run finished between 2 and 5 a.m."), symbol: "moon.stars.fill", tier: .silver, hidden: true) { r in
            r.inbox.contains { $0.kind == "finished" && (2..<5).contains(Calendar.current.component(.hour, from: $0.date)) } ? 1 : 0 },
        Achievement(id: "marathon", title: L("Marathon"), detail: L("Finish a run of 300 epochs or more"), symbol: "figure.run", tier: .gold, hidden: true) { r in
            r.runs.contains { $0.state == "done" && $0.epoch >= 300 } ? 1 : 0 },
        Achievement(id: "comeback", title: L("Comeback"), detail: L("Have a run finish after one failed"), symbol: "arrow.uturn.up", tier: .silver, hidden: true) { r in
            guard let f = r.inbox.last(where: { $0.kind == "failed" }) else { return 0 }
            return r.inbox.contains { $0.kind == "finished" && $0.date > f.date } ? 1 : 0 },
    ]
}
