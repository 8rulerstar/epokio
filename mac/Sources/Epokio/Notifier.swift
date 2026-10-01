import Foundation
import UserNotifications

// agent가 쌓아 둔 상태 변화를 가져와 맥 알림으로 띄운다.
// 원격 학습 PC의 사건도 여기로 모이므로, 알림은 항상 맥에서 뜬다.
@MainActor
final class Notifier {
    static let shared = Notifier()
    private var cursor: [String: Int] = [:]          // agent별 마지막으로 본 사건 번호
    private var boots: [String: String] = [:]        // agent별 boot 값. 바뀌면 다시 켠 것이라 번호가 1부터 다시 센다
    private var primed: Set<String> = []
    private var polling: Set<String> = []            // ★겹쳐 물으면 켤 때 옛 사건이 쏟아지고 커서가 뒤로 갔다

    struct Event: Decodable {
        let seq: Int; let kind: String; let run: Run
        var boot: String? = nil                      // 어느 boot의 번호인지(알림함 id에 쓴다)
        var key: String { "\(boot ?? "")|\(seq)" }
    }
    struct Payload: Decodable { let seq: Int; let events: [Event]; let boot: String? }

    func requestPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
        // 알림에 "결과 보기" 버튼. 누르면(알림 자체를 눌러도) 그 학습의 상세로 간다
        // 알림에서 바로: 끝남 → 결과 보기·더 길게 학습, 문제 → 결과 보기·멈추기 (미리 알림·메일처럼)
        let view = UNNotificationAction(identifier: "view", title: String(localized: "View Results"), options: [.foreground])
        let longer = UNNotificationAction(identifier: "longer", title: String(localized: "Train Longer"), options: [.foreground])
        let stop = UNNotificationAction(identifier: "stop", title: String(localized: "Stop Training"), options: [.destructive])
        UNUserNotificationCenter.current().setNotificationCategories([
            UNNotificationCategory(identifier: "run", actions: [view], intentIdentifiers: []),
            UNNotificationCategory(identifier: "done", actions: [view, longer], intentIdentifiers: []),
            UNNotificationCategory(identifier: "problem", actions: [view, stop], intentIdentifiers: [])])
    }

    /// 새 사건을 가져와 맥 알림을 띄우고, 알림함에 쌓을 수 있게 돌려준다.
    func poll(_ agent: URL, label: String) async -> [Event] {
        let key = agent.absoluteString
        guard !polling.contains(key) else { return [] }
        polling.insert(key)
        defer { polling.remove(key) }
        let client = AgentClient(base: agent)
        guard var p: Payload = try? await client.get("events", ["since": "\(cursor[key] ?? 0)"]) else { return [] }
        // 다시 켠 agent면 처음부터 다시 받는다. ★옛 커서로 물어 새 사건을 건너뛰었다
        let restarted = (p.boot != nil && boots[key] != nil && p.boot != boots[key]) || p.seq < (cursor[key] ?? 0)
        if restarted {
            guard let again: Payload = try? await client.get("events", ["since": "0"]) else { return [] }
            p = again
        }
        boots[key] = p.boot
        cursor[key] = p.seq
        guard primed.contains(key) else { primed.insert(key); return [] }   // 켤 때 옛 사건을 쏟아내지 않는다
        let events = p.events.map { ev -> Event in var e = ev; e.boot = p.boot; return e }
        for e in events where Self.enabled(e.kind) {
            // 끝남·실패·멈춤: 해설 첫 문장을 붙인다(왜 그런지 한 줄). 2초 안에 못 받으면 그냥 보낸다
            let why = ["finished", "failed", "stalled"].contains(e.kind) ? await Self.firstLine(agent, e.run.path) : nil
            post(e, machine: label, why: why)
        }
        return events
    }

    static func enabled(_ kind: String) -> Bool {
        // ★설정은 쉼표로 이은 문자열 하나로 저장한다(@AppStorage). stringArray로 읽으면 늘 nil이라 기본값만 쓰여
        //   알림 설정 스위치가 아무 효과가 없었다
        let raw = UserDefaults.standard.string(forKey: "notify") ?? "finished,failed,stalled,stopped_early,job_done,job_failed"
        let on = raw.split(separator: ",").map(String.init)
        return ["goal", "pruned", "disk_low", "gpu_hot", "gpu_mem", "fan_max"].contains(kind) || on.contains(kind)   // 사람이 건 목표·기계 경고는 항상
    }

    /// 조용한 시간(설정 → 알림). 23→7처럼 자정을 넘어도 된다
    static var quietNow: Bool {
        let d = UserDefaults.standard
        guard d.object(forKey: "quietMac") as? Bool ?? true else { return false }
        let a = d.integer(forKey: "quietFrom"), b = d.integer(forKey: "quietTo"), h = Calendar.current.component(.hour, from: .now)
        guard a != b else { return false }
        return a < b ? (a <= h && h < b) : (h >= a || h < b)
    }

    /// 메뉴바 우클릭 → "1시간 알림 끄기". 알림함에는 그대로 쌓인다
    static var pausedUntil: Date? {
        get { (UserDefaults.standard.object(forKey: "notifyPausedUntil") as? Double).map(Date.init(timeIntervalSince1970:)).flatMap { $0 > .now ? $0 : nil } }
        set { UserDefaults.standard.set(newValue?.timeIntervalSince1970, forKey: "notifyPausedUntil") }
    }

    /// 해설(explain.text)의 첫 문장
    private static func firstLine(_ agent: URL, _ path: String) async -> String? {
        guard UserDefaults.standard.object(forKey: "explainInAlerts") as? Bool ?? true else { return nil }
        var c = URLComponents(url: agent.appending(path: "run"), resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "path", value: path)]
        var req = URLRequest(url: c.url!); req.timeoutInterval = 2
        AgentClient(base: agent).authorize(&req)
        guard let (data, _) = try? await URLSession.shared.data(for: req),
              let d = try? JSONDecoder().decode(RunDetail.self, from: data), let t = d.explain?.text else { return nil }
        let first = t.split(separator: ".", maxSplits: 1).first.map { String($0).trimmingCharacters(in: .whitespaces) + "." }
        return first.map { $0.count > 140 ? String($0.prefix(139)) + "…" : $0 }
    }

    private func post(_ e: Event, machine: String, why: String? = nil) {
        guard !Self.quietNow, Self.pausedUntil == nil else { return }
        let c = UNMutableNotificationContent()
        c.title = switch e.kind {
        case "finished": String(localized: "Training finished")
        case "failed": String(localized: "Training failed")
        case "stalled": String(localized: "Training may have stopped")
        case "stopped_early": String(localized: "Stopped before the last epoch")
        case "started": String(localized: "Training started")
        case "job_done": String(localized: "Job finished")
        case "job_failed": String(localized: "Job failed")
        case "goal": String(localized: "Goal reached")
        case "pruned": String(localized: "Sweep stopped a run that fell behind")
        case "disk_low": String(localized: "Disk almost full")
        case "gpu_hot": String(localized: "GPU is very hot")
        case "gpu_mem": String(localized: "GPU memory is full")
        case "fan_max": String(localized: "Fans at full speed")
        default: String(localized: "Training resumed")
        }
                let plain = e.kind.hasPrefix("job_") || ["disk_low", "gpu_hot", "gpu_mem", "fan_max"].contains(e.kind)
        var body = plain ? e.run.name : e.run.name + " · " + (e.run.total == nil   // ★계획을 모르면 "3/?"로 보였다
            ? (e.run.isStepAxis ? L("step %@", e.run.epoch.formatted()) : L("epoch %@", "\(e.run.epoch)")) : e.run.progressText)
        if let b = e.run.best { body += " · " + L("best %@", String(format: "%.4f", b)) }
        if machine != "local" { body += " · \(machine)" }
        c.body = why.map { body + "\n" + $0 } ?? body
        c.userInfo = ["run": "\(machine)|\(e.run.path)"]      // 누르면 그 학습의 상세 화면으로
        if !["disk_low", "gpu_hot", "gpu_mem", "fan_max"].contains(e.kind) {
            c.categoryIdentifier = e.kind == "finished" || e.kind == "goal" ? "done" : ["stalled", "started"].contains(e.kind) ? "problem" : "run"
        }
        let bad = ["failed", "stalled", "job_failed"].contains(e.kind)
        switch UserDefaults.standard.string(forKey: "notifySound") ?? "problems" {          // 설정 → 알림 "소리"
        case "none": c.sound = nil
        case "all": c.sound = .default
        default: c.sound = bad ? .defaultCritical : .default
        }
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: "\(machine)-\(e.key)", content: c, trigger: nil))
    }
}
