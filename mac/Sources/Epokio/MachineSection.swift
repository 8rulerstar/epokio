import Charts
import SwiftUI

// 학습 상세의 "학습하는 동안의 기계": 학습 중 15초마다 남긴 GPU·CPU·메모리·팬 사용률(sysrec.py)과 평균.

struct RunSystem: Codable, Hashable {
    let minutes: [Double]
    let columns: [String: [Double?]]
    let samples: Int
    let shared: Bool
    let avg: [String: Double]
}

private func verbatim(_ s: String) -> String { s }     // 차트 축 이름: 번역 대상 아님

struct MachineSection: View {
    @Environment(\.ink) private var ink
    @Environment(\.accessibilityReduceMotion) private var reduce
    let system: RunSystem
    @State private var shown = false
    private var series: [(key: String, name: String)] { [("gpu", "GPU"), ("gmem", L("GPU memory")), ("cpu", "CPU"), ("mem", L("MEM")), ("fan", L("Fan"))] }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Machine while training", hint: L("Recorded every 15 seconds while this run trained. Averages below.")
                         + (system.shared ? " " + L("Other runs trained at the same time, so these are shared numbers.") : ""))
            Chart {
                ForEach(series.filter { system.columns[$0.key] != nil }, id: \.key) { s in
                    ForEach(Array(zip(system.minutes, system.columns[s.key] ?? []).enumerated()), id: \.offset) { _, p in
                        if let y = p.1 {
                            LineMark(x: .value(L("minutes"), p.0), y: .value(verbatim("%"), shown ? y : 0))
                                .foregroundStyle(by: .value(verbatim("Series"), s.name))
                                .interpolationMethod(.monotone)
                        }
                    }
                }
            }
            .chartYScale(domain: 0...100)
            .chartXAxisLabel(L("minutes"))
            .frame(height: 150)
            .animation(reduce ? nil : Motion.progress, value: shown)
            HStack(spacing: 8) {
                ForEach(avgTiles, id: \.0) { name, text in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(verbatim: text).font(.ui(15, weight: .bold, design: .rounded)).contentTransition(.numericText())
                        Text(verbatim: name).font(.ui(11)).foregroundStyle(ink.soft)
                    }
                    .padding(.horizontal, 10).padding(.vertical, 6)
                    .background(.quaternary.opacity(0.35), in: .rect(cornerRadius: 8))
                    .tip()
                }
            }
        }
        .onAppear { shown = true }
    }

    private var avgTiles: [(String, String)] {
        var out = series.compactMap { s in system.avg[s.key].map { (s.name, "\(Int($0.rounded()))%") } }
        if let t = system.avg["gtemp"] { out.append((L("GPU temperature"), "\(Int(t.rounded()))°C")) }
        if let t = system.avg["temp"] { out.append((L("SoC temperature"), "\(Int(t.rounded()))°C")) }
        return out
    }
}
