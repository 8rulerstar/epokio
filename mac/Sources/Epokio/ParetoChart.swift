import SwiftUI
import Charts

// 두 목표 스윕: 가로 = 두 번째 목표(작은 모델 MB · 학습 시간), 세로 = 점수. 앞줄(어느 쪽으로도 더 나은 시도가 없는 것)은
// 강조색 큰 점을 이어 보여 주고, 나머지는 옅게. 점에 올리면 설정이 뜬다.

struct ParetoChart: View {
    let s: SweepSummary
    let goal: String
    var open: (String) -> Void = { _ in }
    @Environment(\.ink) private var ink
    @State private var hover: String?

    private var pts: [(SweepSummary.Trial, Double, Double)] {
        s.rows.compactMap { r in r.best.flatMap { b in r.second.map { (r, $0, b) } } }
    }
    private var unit: String { goal == "size" ? L("Model size (MB)") : L("Training time (seconds)") }

    var body: some View {
        let front = Set(s.pareto ?? [])
        let line = pts.filter { front.contains($0.0.job) }.sorted { $0.1 < $1.1 }
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Best trade-offs", hint: goal == "size"
                ? L("Each dot is a run. The highlighted ones are not beaten on both the score and the model size. Pick the one that fits.")
                : L("Each dot is a run. The highlighted ones are not beaten on both the score and the training time. Pick the one that fits."))
            Chart {
                ForEach(line, id: \.0.job) { r, x, y in
                    LineMark(x: .value(unit, x), y: .value(s.metricName, y)).foregroundStyle(Color.brand.opacity(0.5))
                        .interpolationMethod(.stepEnd)
                }
                ForEach(pts, id: \.0.job) { r, x, y in
                    let on = front.contains(r.job)
                    PointMark(x: .value(unit, x), y: .value(s.metricName, y))
                        .foregroundStyle(on ? Color.brand : Color.secondary.opacity(0.45))
                        .symbolSize(hover == r.job ? 160 : on ? 90 : 40)
                        .annotation(position: .top) {
                            if hover == r.job {
                                Text(verbatim: s.keys.map { "\($0) \(r.trial[$0]?.description ?? "–")" }.joined(separator: " · "))
                                    .font(.role(.badge)).padding(4).glass(radius: Radius.chip)
                            }
                        }
                }
            }
            .chartXAxisLabel(unit)
            .chartYScale(domain: yDomain(pts.map(\.2)))
            .chartOverlay { proxy in
                GeometryReader { g in
                    Rectangle().fill(.clear).contentShape(.rect)
                        .onContinuousHover { phase in
                            guard case .active(let p) = phase, let frame = proxy.plotFrame else { withAnimation(Motion.hover) { hover = nil }; return }
                            let o = g[frame].origin
                            let near = pts.min { a, b in
                                dist(proxy, a, p, o) < dist(proxy, b, p, o)
                            }
                            withAnimation(Motion.hover) { hover = near.flatMap { dist(proxy, $0, p, o) < 24 ? $0.0.job : nil } }
                        }
                }
            }
            .frame(height: 200)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(L("Best trade-offs chart"))
            .accessibilityValue(L("%d runs, %d on the best trade-off line", pts.count, line.count))
            .contextMenu { TrialOpenMenu(s: s, rows: line.map(\.0) + pts.map(\.0).filter { !front.contains($0.job) }, open: open) }
            .accessibilityActions { TrialOpenMenu(s: s, rows: line.map(\.0), open: open) }
            .padding(12)
            .background(.quaternary.opacity(0.25), in: .rect(cornerRadius: Radius.card))
        }
        .transition(.opacity.combined(with: .move(edge: .top)))
    }

    private func dist(_ proxy: ChartProxy, _ r: (SweepSummary.Trial, Double, Double), _ p: CGPoint, _ o: CGPoint) -> CGFloat {
        guard let x = proxy.position(forX: r.1), let y = proxy.position(forY: r.2) else { return .infinity }
        return hypot(x + o.x - p.x, y + o.y - p.y)
    }
}

/// 그림의 점·선 누르기와 같은 동작(학습 열기)을 우클릭 메뉴와 VoiceOver 동작으로도. 마우스 없이도 연다
struct TrialOpenMenu: View {
    let s: SweepSummary
    let rows: [SweepSummary.Trial]
    let open: (String) -> Void
    var body: some View {
        let list = rows.filter { $0.run != nil }
        ForEach(Array(list.prefix(20))) { r in
            Button(trialTitle(r)) { if let run = r.run { open(run) } }
        }
    }
    private func trialTitle(_ r: SweepSummary.Trial) -> String {
        let score = r.best.map { Fmt.metric($0, higher: s.higher) } ?? "–"
        let set = s.keys.map { "\($0) \(r.trial[$0]?.description ?? "–")" }.joined(separator: ", ")
        return L("Open run #%@ (%@): %@", r.rank.map(String.init) ?? "–", score, set)
    }
}
