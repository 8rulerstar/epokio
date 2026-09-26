import SwiftUI

// 평행 좌표(W&B·ClearML의 스윕 핵심 그림): 설정마다 세로축 하나, 맨 오른쪽이 점수. 학습 하나 = 선 하나.
// 점수가 좋을수록 진한 강조색, 나쁠수록 옅게. 선에 올리면 그 학습만 도드라지고 값이 뜬다. 누르면 그 학습이 열린다(우클릭 메뉴·VoiceOver 동작으로도).
// 숫자 설정은 최소~최대 사이에, 글자 설정(optimizer 등)은 값마다 같은 간격에 놓는다.

struct ParallelCoords: View {
    @AppStorage(Fmt.scoreKey) private var scoreStyle = "3"   // 바꾸면 바로 다시 그린다
    let s: SweepSummary
    var open: (String) -> Void = { _ in }
    @Environment(\.ink) private var ink
    @State private var hover: String?
    @State private var drawn = false
    @Environment(\.accessibilityReduceMotion) private var reduce

    private var rows: [SweepSummary.Trial] { s.rows.filter { $0.best != nil } }
    private var ranked: [SweepSummary.Trial] { rows.sorted { ($0.rank ?? .max) < ($1.rank ?? .max) } }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("How settings led to the score", hint: L("One line per run, from each setting to its score. Darker lines scored better. Point at a line to see its values."))
            GeometryReader { g in
                let axes = s.keys + ["__score"]
                let W = g.size.width, H = g.size.height - 34
                let x = { (i: Int) in 30 + (W - 60) * CGFloat(i) / CGFloat(max(axes.count - 1, 1)) }
                let (lo, hi) = scoreRange
                let lw = max(40, min(120, (W - 60) / CGFloat(max(axes.count - 1, 1)) - 6))    // 이름 칸 폭 = 축 간격(좁으면 겹쳤다)
                ZStack(alignment: .topLeading) {
                    ForEach(rows) { r in
                        let q = rank(r.best!, lo, hi)
                        Path { p in
                            for (i, k) in axes.enumerated() {
                                let pt = CGPoint(x: x(i), y: 14 + H * (1 - pos(k, r)))
                                i == 0 ? p.move(to: pt) : p.addLine(to: pt)
                            }
                        }
                        .trim(from: 0, to: drawn ? 1 : 0)
                        .stroke(Color.brand.opacity(hover == nil ? 0.2 + 0.8 * q : hover == r.id ? 1 : 0.08),
                                style: StrokeStyle(lineWidth: hover == r.id ? 3 : 1.2 + 1.3 * q, lineCap: .round, lineJoin: .round))
                        .contentShape(.interaction, Path { p in
                            for (i, k) in axes.enumerated() {
                                let pt = CGPoint(x: x(i), y: 14 + H * (1 - pos(k, r)))
                                i == 0 ? p.move(to: pt) : p.addLine(to: pt)
                            }
                        }.strokedPath(StrokeStyle(lineWidth: 8)))
                        .onHover { h in withAnimation(Motion.hover) { hover = h ? r.id : (hover == r.id ? nil : hover) } }
                        .onTapGesture { if let run = r.run { open(run) } }
                    }
                    ForEach(Array(axes.enumerated()), id: \.offset) { i, k in
                        Rectangle().fill(.primary.opacity(0.18)).frame(width: 1, height: H).offset(x: x(i), y: 14)
                        VStack(spacing: 1) {
                            Text(verbatim: k == "__score" ? s.metricName : k).font(.role(.caption, weight: .semibold)).lineLimit(1).minimumScaleFactor(0.7).truncationMode(.middle)
                            if let r = rows.first(where: { $0.id == hover }) {
                                Text(verbatim: k == "__score" ? Fmt.metric(r.best!, higher: s.higher, style: scoreStyle) : r.trial[k]?.description ?? "–")
                                    .font(.role(.caption)).monospacedDigit().foregroundStyle(.brand).lineLimit(1).minimumScaleFactor(0.7)
                                    .contentTransition(.numericText())
                            } else {
                                Text(verbatim: range(k)).font(.role(.badge)).foregroundStyle(ink.soft).lineLimit(1).truncationMode(.tail)
                            }
                        }
                        .frame(width: lw).offset(x: x(i) - lw / 2, y: H + 18)
                        .help(k == "__score" ? s.metricName : k)
                    }
                }
            }
            .frame(height: 230)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(L("Settings to score chart"))
            .accessibilityValue(L("%d runs across %d settings, %@ from %@ to %@", rows.count, s.keys.count, s.metricName,
                                  Fmt.metric(scoreRange.0, higher: s.higher, style: scoreStyle, raw: "%.3f"), Fmt.metric(scoreRange.1, higher: s.higher, style: scoreStyle, raw: "%.3f")))
            .contextMenu { TrialOpenMenu(s: s, rows: ranked, open: open) }       // 선 누르기와 같은 동작을 메뉴로도
            .accessibilityActions { TrialOpenMenu(s: s, rows: ranked, open: open) }
            .padding(12)
            .background(.quaternary.opacity(0.25), in: .rect(cornerRadius: Radius.card))
        }
        .onAppear { if reduce { drawn = true } else { withAnimation(Motion.appear) { drawn = true } } }
    }

    private var scoreRange: (Double, Double) {
        let v = rows.compactMap(\.best)
        return (v.min() ?? 0, v.max() ?? 1)
    }
    /// 0(나쁨)~1(좋음). 낮을수록 좋은 점수면 뒤집는다
    private func rank(_ b: Double, _ lo: Double, _ hi: Double) -> Double {
        let t = hi > lo ? (b - lo) / (hi - lo) : 1
        return s.higher ? t : 1 - t
    }

    /// 축 위 위치 0~1
    private func pos(_ k: String, _ r: SweepSummary.Trial) -> CGFloat {
        if k == "__score" { let (lo, hi) = scoreRange; return CGFloat(rank(r.best!, lo, hi)) }   // ★위 = 좋음. 낮을수록 좋은 점수(손실)는 뒤집는다
        let vals = rows.compactMap { $0.trial[k] }
        let nums = vals.compactMap { if case .num(let x) = $0 { x } else { nil } }
        if nums.count == vals.count, vals.count == rows.count, let lo = nums.min(), let hi = nums.max(), case .num(let x)? = r.trial[k] {
            let logScale = lo > 0 && hi / lo >= 20                                         // lr0처럼 자릿수가 넓으면 로그 눈금
            if hi == lo { return 0.5 }
            return CGFloat(logScale ? (log(x) - log(lo)) / (log(hi) - log(lo)) : (x - lo) / (hi - lo))
        }
        let cats = Array(Set(rows.map { $0.trial[k]?.description ?? "–" })).sorted()   // 값이 없는 학습은 "–" 칸(★가운데에 그려 없는 값처럼 보였다)
        guard let i = cats.firstIndex(of: r.trial[k]?.description ?? "–") else { return 0.5 }
        return cats.count == 1 ? 0.5 : CGFloat(i) / CGFloat(cats.count - 1)
    }

    private func range(_ k: String) -> String {
        if k == "__score" {                                           // 위가 좋은 쪽: 위 값 – 아래 값 순서로
            let (lo, hi) = scoreRange
            return s.higher ? Fmt.score(hi, style: scoreStyle) + " – " + Fmt.score(lo, style: scoreStyle) : String(format: "%.3f – %.3f", lo, hi)
        }
        let v = Array(Set(rows.map { $0.trial[k]?.description ?? "–" }))
        return v.count <= 3 ? v.sorted().joined(separator: " · ") : L("%d values", v.count)
    }
}
