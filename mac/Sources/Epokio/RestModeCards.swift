import SwiftUI

// 쉬는 모드 팝오버 카드. 제어 센터 모듈처럼 작은 유리 타일을 두 줄로 놓는다.
// 색: 강조색 하나(.brand) + 상태색(.good .warn .bad)만. 칸마다 다른 색은 쓰지 않는다.
// 값이 없는 칸은 숨긴다. 문구는 짧게, 자세한 것은 툴팁.

struct RestModeCards: View {
    let readings: RestReadings
    var onAddFolder: () -> Void = {}
    var onSamples: () -> Void = {}

    private let columns = [GridItem(.flexible(), spacing: Space.s), GridItem(.flexible(), spacing: Space.s),
                           GridItem(.flexible(), spacing: Space.s)]

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s) {
            if !readings.items.isEmpty {
                GlassGroup {
                    LazyVGrid(columns: columns, spacing: Space.s) {
                        ForEach(Array(readings.items.enumerated()), id: \.element) { i, item in
                            RestTile(item: item, readings: readings).appearRise(i)
                        }
                    }
                }
            }
            HStack(spacing: Space.m) {
                RestLink(title: "Add a Folder…", symbol: "folder.badge.plus",
                         help: "Watch the folder where your training results are saved", action: onAddFolder)
                RestLink(title: "Look Around with Samples", symbol: "sparkles",
                         help: "Adds three example runs so you can look around. Nothing trains. Remove them any time.",
                         action: onSamples)
                Spacer(minLength: 0)
            }
            .appearRise(readings.items.count)
        }
    }
}

/// 타일 하나: 위에 기호, 가운데 큰 값, 아래 작은 이름. 퍼센트 값은 가는 고리로 둘러 보인다
private struct RestTile: View {
    @Environment(\.ink) private var ink
    @Environment(\.accessibilityReduceMotion) private var reduce
    @AppStorage("animations") private var animations = true
    let item: RestMode.Item
    let readings: RestReadings
    @State private var hover = false

    private var still: Bool { reduce || !animations }
    private var tint: Color {
        switch readings.alarm(item) {
        case .good: .good
        case .warn: .warn
        case .bad: .bad
        case nil: .brand
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                symbol
                Spacer(minLength: 0)
                if let pct { Ring(value: pct, tint: tint, still: still) }
            }
            value
                .font(.ui(15, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .lineLimit(1).minimumScaleFactor(0.7)
                .contentTransition(.numericText())
                .animation(still ? nil : Motion.change, value: valueKey)
            Text(title).font(.role(.caption)).foregroundStyle(ink.soft).lineLimit(1)
        }
        .padding(Space.m)
        .frame(maxWidth: .infinity, minHeight: 78, alignment: .topLeading)
        .background(.quaternary.opacity(0.35), in: .rect(cornerRadius: Radius.card, style: .continuous))   // 유리가 안 그려지는 곳(스냅샷·투명도 줄이기)에서도 칸이 보이게
        .glass(RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
            .stroke(tint.opacity(hover ? 0.35 : 0), lineWidth: 1))
        .scaleEffect(hover && !still ? 1.02 : 1)
        .onHover { h in withAnimation(still ? nil : Motion.hover) { hover = h } }
        .animation(still ? nil : Motion.change, value: readings.alarm(item) == nil)
        .help(tooltip)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(title))
        .accessibilityValue(tooltip)
    }

    private var symbol: some View {
        let name = item == .battery ? readings.batterySymbol : item.symbol
        return Image(systemName: name)
            .font(.ui(13, weight: .semibold))
            .foregroundStyle(tint)
            .contentTransition(.symbolEffect(.replace))
            .symbolEffect(.pulse, isActive: !still && readings.alarm(item) == .bad)
            .frame(height: 16)
    }

    private var title: LocalizedStringKey {
        switch item {
        case .cpu: "CPU"
        case .memory: "Memory"
        case .temp: "Temperature"
        case .battery: readings.charging == true ? "Charging" : "Battery"
        case .disk: "Disk free"
        case .network: "Network"
        }
    }

    private var pct: Double? {
        switch item {
        case .cpu: readings.cpu
        case .memory: readings.memPct
        case .battery: readings.battery
        default: nil
        }
    }

    @ViewBuilder private var value: some View {
        switch item {
        case .cpu: Text(verbatim: "\(Int((readings.cpu ?? 0).rounded()))%")
        case .memory: Text(verbatim: "\(Int((readings.memPct ?? 0).rounded()))%")
        case .temp: Text(verbatim: "\(Int((readings.cpuTemp ?? 0).rounded()))°")
        case .battery: Text(verbatim: "\(Int((readings.battery ?? 0).rounded()))%")
        case .disk: Text(verbatim: RestFormat.gb(readings.diskFree))
        case .network:
            HStack(spacing: 4) {
                Image(systemName: "arrow.down").font(.ui(10, weight: .bold)).foregroundStyle(ink.soft)
                Text(verbatim: RestFormat.rate(readings.netDown))
            }
        }
    }

    /// 값이 바뀔 때만 숫자 전환을 건다
    private var valueKey: String {
        switch item {
        case .cpu: "\(Int(readings.cpu ?? 0))"
        case .memory: "\(Int(readings.memPct ?? 0))"
        case .temp: "\(Int(readings.cpuTemp ?? 0))"
        case .battery: "\(Int(readings.battery ?? 0))\(readings.charging == true)"
        case .disk: "\(Int(readings.diskFree ?? 0))"
        case .network: RestFormat.rate(readings.netDown)
        }
    }

    /// 툴팁: 큰 값 옆에 못 넣은 것(메모리 GB, 올림 속도 등)
    private var tooltip: String {
        switch item {
        case .memory: "\(RestFormat.gb(readings.memUsed)) / \(RestFormat.gb(readings.memTotal))"
        case .network: "↑ \(RestFormat.rate(readings.netUp))   ↓ \(RestFormat.rate(readings.netDown))"
        case .temp: L("SoC temperature") + " \(Int((readings.cpuTemp ?? 0).rounded()))°C"
        case .battery: L("Battery") + " \(Int((readings.battery ?? 0).rounded()))%"
            + (readings.charging == true ? " · " + L("Charging") : "")
        case .disk: L("Disk free") + " " + RestFormat.gb(readings.diskFree)
        case .cpu: "CPU \(Int((readings.cpu ?? 0).rounded()))%"
        }
    }
}

/// 작은 진행 고리(0~100)
private struct Ring: View {
    let value: Double
    let tint: Color
    let still: Bool
    var body: some View {
        ZStack {
            Circle().stroke(tint.opacity(0.15), lineWidth: 2.5)
            Circle().trim(from: 0, to: min(max(value, 0), 100) / 100)
                .stroke(tint, style: .init(lineWidth: 2.5, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(still ? nil : Motion.progress, value: value)
        }
        .frame(width: 14, height: 14)
        .accessibilityHidden(true)
    }
}

/// 글자 링크 하나(학습 폴더 연결 · 샘플). 올리면 밑줄 대신 옅은 배경
private struct RestLink: View {
    @Environment(\.ink) private var ink
    let title: LocalizedStringKey
    let symbol: String
    let help: LocalizedStringKey
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            Label(title, systemImage: symbol)
                .font(.role(.caption, weight: .medium))
                .foregroundStyle(hover ? AnyShapeStyle(.brand) : AnyShapeStyle(ink.soft))
                .padding(.horizontal, 6).padding(.vertical, 3)
                .background(Capsule().fill(Color.brand.opacity(hover ? 0.12 : 0)))
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(help)
    }
}
