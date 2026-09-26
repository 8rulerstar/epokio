import Foundation

// 쉬는 모드: 학습 기록이 하나도 없을 때 팝오버는 이 맥의 상태를 먼저 보이고, 메뉴바 캐릭터는 CPU로 달린다.
// 판정은 여기 한 곳. 팝오버·Store·메뉴바는 `RestMode.isResting(runs:)`만 부른다.

enum RestMode {
    /// 학습 기록이 0개면 쉬는 모드. 샘플이 있으면 쉬는 모드가 아니다:
    /// 사용자가 "샘플로 둘러보기"를 직접 눌렀으니 학습 화면을 보여 줘야 한다(쉬는 모드로 숨기면 누른 보람이 없다).
    static func isResting(runs: [Run]) -> Bool { runs.isEmpty }

    /// 시스템 카드 칸. 순서가 곧 화면 순서
    enum Item: String, CaseIterable, Identifiable {
        case cpu, memory, temp, battery, disk, network
        var id: String { rawValue }
        var symbol: String {
            switch self {
            case .cpu: "cpu"
            case .memory: "memorychip"
            case .temp: "thermometer.medium"
            case .battery: "battery.75percent"
            case .disk: "internaldrive"
            case .network: "arrow.up.arrow.down"
            }
        }
    }
}

/// 카드가 읽는 값. /system `now`의 키와 이름을 맞췄다(없으면 nil, 칸을 숨긴다).
/// 스냅샷·갤러리는 `demo`로 가짜 값만 쓴다(실제 호스트·폴더가 찍히지 않게).
struct RestReadings: Equatable {
    var cpu: Double? = nil            // %
    var memUsed: Double? = nil        // GB
    var memTotal: Double? = nil       // GB
    var cpuTemp: Double? = nil        // °C
    var battery: Double? = nil        // %
    var charging: Bool? = nil
    var diskFree: Double? = nil       // GB
    var netUp: Double? = nil          // 바이트/초
    var netDown: Double? = nil        // 바이트/초

    /// Snapshot(Models.swift)이 지금 디코딩하는 키만 채운다.
    /// 병합 때 Snapshot에 battery·charging·disk_free·net_up·net_down을 더하면 여기 네 줄을 켠다(보고서 참고)
    init(_ s: Snapshot) {
        cpu = s.cpu; memUsed = s.mem_used; memTotal = s.mem_total; cpuTemp = s.cpu_temp
        battery = s.battery; charging = s.charging; diskFree = s.disk_free; netUp = s.net_up; netDown = s.net_down
    }

    init(cpu: Double? = nil, memUsed: Double? = nil, memTotal: Double? = nil, cpuTemp: Double? = nil,
         battery: Double? = nil, charging: Bool? = nil, diskFree: Double? = nil,
         netUp: Double? = nil, netDown: Double? = nil) {
        self.cpu = cpu; self.memUsed = memUsed; self.memTotal = memTotal; self.cpuTemp = cpuTemp
        self.battery = battery; self.charging = charging; self.diskFree = diskFree
        self.netUp = netUp; self.netDown = netDown
    }

    static let demo = RestReadings(cpu: 23, memUsed: 11.2, memTotal: 16, cpuTemp: 48, battery: 18,
                                   charging: false, diskFree: 212, netUp: 38_000, netDown: 1_450_000)

    var memPct: Double? {
        guard let u = memUsed, let t = memTotal, t > 0 else { return nil }
        return u / t * 100
    }

    /// 값이 있는 칸만
    var items: [RestMode.Item] {
        RestMode.Item.allCases.filter { has($0) }
    }

    func has(_ i: RestMode.Item) -> Bool {
        switch i {
        case .cpu: cpu != nil
        case .memory: memPct != nil
        case .temp: cpuTemp != nil
        case .battery: battery != nil
        case .disk: diskFree != nil
        case .network: netUp != nil || netDown != nil
        }
    }

    /// 상태색이 필요한 칸만 판정(기능별 색은 쓰지 않는다). nil = 평소(강조색)
    func alarm(_ i: RestMode.Item) -> RestAlarm? {
        switch i {
        case .cpu: (cpu ?? 0) >= 90 ? .warn : nil
        case .memory: (memPct ?? 0) >= 90 ? .warn : nil
        case .temp: (cpuTemp ?? 0) >= 90 ? .warn : nil       // TempChip.hot과 같은 문턱
        case .battery:
            if charging == true { .good }
            else if let b = battery, b <= 10 { .bad }
            else if let b = battery, b <= 20 { .warn }
            else { nil }
        case .disk: (diskFree ?? .infinity) < 10 ? .bad : ((diskFree ?? .infinity) < 30 ? .warn : nil)
        case .network: nil
        }
    }

    /// 배터리 기호는 잔량·충전에 맞춘다
    var batterySymbol: String {
        if charging == true { return "battery.100percent.bolt" }
        switch battery ?? 100 {
        case ..<13: return "battery.0percent"
        case ..<38: return "battery.25percent"
        case ..<63: return "battery.50percent"
        case ..<88: return "battery.75percent"
        default: return "battery.100percent"
        }
    }
}

enum RestAlarm { case good, warn, bad }

enum RestFormat {
    /// 바이트/초 → "1.4 MB/s"
    static func rate(_ bps: Double?) -> String {
        guard let bps, bps.isFinite, bps >= 0 else { return "–" }
        return ByteCountFormatter.string(fromByteCount: Int64(bps), countStyle: .binary) + "/s"
    }
    /// GB → "212 GB"
    static func gb(_ v: Double?) -> String {
        guard let v, v.isFinite else { return "–" }
        return ByteCountFormatter.string(fromByteCount: Int64(v * 1_073_741_824), countStyle: .binary)
    }
}
