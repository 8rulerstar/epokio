import SwiftUI

// 팝오버의 GPU·CPU·메모리 줄.

struct SystemStrip: View {
    @Environment(\.ink) private var ink
    @Environment(Store.self) private var store
    @Environment(\.accessibilityReduceMotion) private var reduce
    @AppStorage(TempChip.settingKey) private var showTemp = true

    var body: some View {
        ForEach(store.system.keys.sorted(), id: \.self) { key in
            if let s = store.system[key]?.now {
                HStack(spacing: 14) {
                    Gauge(label: "GPU", value: s.gpus.first?.util, tint: .mixup)
                    Gauge(label: "CPU", value: s.cpu, tint: .info)
                    Gauge(label: "MEM", value: memPct(s), tint: .brand2)
                    if showTemp, let t = s.cpu_temp {
                        TempChip(celsius: t)
                            .transition(.opacity.combined(with: .move(edge: .leading)))
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(verbatim: key).font(.ui(11.5, weight: .semibold)).lineLimit(1).truncationMode(.middle)
                            .help(key == s.host ? key : key + " · " + s.host)      // 별칭이 먼저, 실제 호스트는 툴팁에만
                        Text(verbatim: s.gpus.first?.name ?? s.host).font(.ui(11.5)).foregroundStyle(ink.soft)
                            .lineLimit(1).truncationMode(.middle)
                        GPUHistory(values: store.system[key]?.history.compactMap { $0 } ?? [])
                            .frame(height: 14)
                    }
                    Spacer(minLength: 0)
                }
                .padding(10)
                .animation(reduce ? nil : .smooth, value: showTemp && s.cpu_temp != nil)
                .background(.primary.opacity(0.04), in: .rect(cornerRadius: Radius.card, style: .continuous))
            }
        }
    }

    private func memPct(_ s: Snapshot) -> Double? {
        guard let u = s.mem_used, let t = s.mem_total, t > 0 else { return nil }
        return u / t * 100
    }
}

struct Gauge: View {
    @Environment(\.ink) private var ink
    let label: String
    let value: Double?
    let tint: Color

    var body: some View {
        ZStack {
            Circle().stroke(tint.opacity(0.15), lineWidth: 4)
            Circle().trim(from: 0, to: (value ?? 0) / 100)
                .stroke(tint, style: .init(lineWidth: 4, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(Motion.progress, value: value)
            VStack(spacing: 0) {
                Text(value.map { "\(Int($0))" } ?? "–")
                    .font(.ui(11, weight: .bold, design: .monospaced))
                    .contentTransition(.numericText())
                Text(label).font(.ui(7, weight: .semibold)).foregroundStyle(ink.soft)
            }
        }
        .frame(width: 40, height: 40)
    }
}

/// CPU(SoC) 온도. 숫자와 °만 보이고 설명은 툴팁. 90°C 이상이면 주의 색.
struct TempChip: View {
    static let settingKey = "showCPUTemp"
    static let hot = 90.0
    @Environment(\.accessibilityReduceMotion) private var reduce
    let celsius: Double
    @State private var hover = false

    var body: some View {
        let hot = celsius >= Self.hot
        Group {
            Text(verbatim: "\(Int(celsius.rounded()))°")
                .font(.ui(11, weight: .bold, design: .monospaced))
                .foregroundStyle(hot ? Color.warn : Color.primary)
                .contentTransition(.numericText(value: celsius))
                .animation(reduce ? nil : Motion.change, value: Int(celsius.rounded()))
        }
        .frame(width: 40, height: 40)
        .background(Circle().fill((hot ? Color.warn : Color.secondary).opacity(hover ? 0.16 : (hot ? 0.10 : 0))))
        .animation(reduce ? nil : Motion.hover, value: hot)
        .onHover { h in withAnimation(reduce ? nil : Motion.hover) { hover = h } }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(L("CPU temperature"))
        .accessibilityValue(Text(verbatim: "\(Int(celsius.rounded()))°C"))
        .help(L("CPU temperature"))
    }
}

struct GPUHistory: View {
    let values: [Double]
    var body: some View {
        GeometryReader { g in
            let v = Array(values.suffix(60))
            let pts = v.enumerated().map { i, x in
                CGPoint(x: g.size.width * CGFloat(i) / CGFloat(max(v.count - 1, 1)),
                        y: g.size.height * (1 - CGFloat(min(max(x, 0), 100) / 100)))
            }
            ZStack {
                Path { p in
                    guard let f = pts.first, let l = pts.last else { return }
                    p.move(to: CGPoint(x: f.x, y: g.size.height))
                    p.addLines(pts)
                    p.addLine(to: CGPoint(x: l.x, y: g.size.height))
                    p.closeSubpath()
                }
                .fill(LinearGradient(colors: [.mixup.opacity(0.35), .mixup.opacity(0.02)],
                                     startPoint: .top, endPoint: .bottom))
                Path { p in p.addLines(pts) }
                    .stroke(.mixup.opacity(0.8), style: .init(lineWidth: 1.2, lineJoin: .round))
            }
        }
    }
}

/// 팝오버 맨 위 "방금 끝남". 결과를 보러 가는 가장 짧은 길.
