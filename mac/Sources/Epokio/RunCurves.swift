import SwiftUI
import Charts

// 학습 상세의 곡선: 손실·점수, 최고 에폭·과적합 선, 마우스 올리면 값, 부드럽게, 속도 줄.

extension RunDetailView {
    // 곡선
    func curves(_ d: RunDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                SectionTitle("Curves", hint: curve == 0 ? L("Loss should go down. If validation goes up while training goes down, it is overfitting.")
                                                         : L("Scores should go up and level off."))
                Spacer()
                Picker("", selection: $curve.animation(.smooth)) { Text("Loss").tag(0); Text("Scores").tag(1) }
                    .pickerStyle(.segmented).frame(width: 160).labelsHidden()
            }
            // 고른 쪽에 열이 없으면 다른 쪽을 그린다(★점수 탭인데 점수 열이 없으면 축만 있는 빈 그래프였다)
            let keys = (curve == 0 ? d.lossKeys : d.scoreKeys).isEmpty ? (curve == 0 ? d.scoreKeys : d.lossKeys)
                                                                        : (curve == 0 ? d.lossKeys : d.scoreKeys)
            Chart {
                ForEach(keys, id: \.self) { k in
                    ForEach(Array(zip(d.epochs, smooth(d.columns[k] ?? [], smoothing)).enumerated()), id: \.offset) { _, p in
                        if let y = p.1 {
                            LineMark(x: .value("Epoch", p.0), y: .value("Value", y))
                                .foregroundStyle(by: .value("Series", d.label(k)))
                                .lineStyle(StrokeStyle(lineWidth: curveWidth, dash: k.hasPrefix("val/") ? [5, 3] : []))
                                .interpolationMethod(.monotone)
                        }
                    }
                }
                // 최고 에폭: 점선 세로줄
                if let be = run.best_epoch {
                    RuleMark(x: .value("Best", Double(be)))
                        .foregroundStyle(.good.opacity(0.5))
                        .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                        .annotation(position: .top, alignment: .leading) {
                            Text(L("best %@", "\(be)")).font(.ui(10.5, weight: .semibold)).foregroundStyle(.good)
                        }
                }
                // 과적합 시작: 검증 손실이 가장 낮았던 에폭 뒤로 다시 오르면 빨간 점선
                if curve == 0, let o = overfitEpoch(d) {
                    RuleMark(x: .value("Overfit", o))
                        .foregroundStyle(.bad.opacity(0.55))
                        .lineStyle(StrokeStyle(lineWidth: 1.2, dash: [4, 3]))
                        .annotation(position: .top, alignment: .trailing) {
                            Text(L("overfitting after %@", "\(Int(o))")).font(.ui(10.5, weight: .semibold)).foregroundStyle(.bad)
                        }
                }
                // 마우스를 올린 에폭: 세로줄 + 그 에폭의 값들
                if let e = hoverEpoch {
                    RuleMark(x: .value("Hover", e))
                        .foregroundStyle(.secondary.opacity(0.6))
                        .annotation(position: .top, alignment: .center, overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                            hoverCard(d, keys: keys, epoch: e)
                        }
                }
            }
            .chartOverlay { proxy in
                GeometryReader { g in
                    Rectangle().fill(.clear).contentShape(.rect)
                        .onContinuousHover { phase in
                            switch phase {
                            case .active(let pt):
                                let x = pt.x - g[proxy.plotFrame!].origin.x
                                if let v: Double = proxy.value(atX: x) {
                                    let near = d.epochs.min { abs($0 - v) < abs($1 - v) }
                                    if near != hoverEpoch { hoverEpoch = near }
                                }
                            case .ended: hoverEpoch = nil
                            }
                        }
                }
            }
            .chartXAxisLabel(L("Epoch"))
            .chartYScale(domain: yDomain(d, keys))                // ★세로 선 표시(RuleMark)가 있으면 축이 0부터 잡혀 곡선이 납작해졌다
            .chartXScale(domain: .automatic(includesZero: false))
            .chartLegend(position: .bottom, alignment: .leading)
            .tokenChartColors(keys.map { d.label($0) })
            .frame(height: 240)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(curveSummary(d, keys))
            .animation(Motion.change, value: smoothing)
            .padding(12)
            .background(.quaternary.opacity(0.35), in: .rect(cornerRadius: 12))
            HStack(spacing: 8) {
                Image(systemName: "wave.3.right").foregroundStyle(ink.soft).font(.ui(12)).accessibilityHidden(true)
                Text("Smoothing").font(.ui(12)).foregroundStyle(ink.soft)
                Slider(value: $smoothing, in: 0...0.95).frame(maxWidth: 200).controlSize(.small)
                Text(verbatim: String(format: "%.2f", smoothing)).font(.ui(11.5, design: .monospaced)).foregroundStyle(ink.soft)
                    .contentTransition(.numericText())
            }
            .help("Averages out the jumps so the trend is easier to see. 0 shows the raw values.")
        }
    }

    /// 속도: 에폭당 시간, 도는 중이면 끝날 시각
    @ViewBuilder var speedLine: some View {
        let per = run.epoch > 0 && run.elapsed > 0 ? run.elapsed / Double(run.epoch) : nil
        HStack(spacing: 14) {
            if let per { Label(L("%@ per epoch", per < 1 ? L("under 1 s") : duration(per)), systemImage: "stopwatch") }
            if run.state == "running", let eta = run.eta, eta > 0 {
                Label(L("done around %@", Fmt.time(Date().addingTimeInterval(eta))), systemImage: "flag.checkered")
                Label(L("%@ left", duration(eta)), systemImage: "hourglass")
            }
        }
        .font(.ui(12)).foregroundStyle(ink.soft)
        .labelStyle(.titleAndIcon)
    }

    /// 검증 손실 합이 가장 낮은 에폭. 그 뒤 마지막이 10% 넘게 올랐을 때만(분석기와 같은 기준)
    func overfitEpoch(_ d: RunDetail) -> Double? {
        let vk = d.lossKeys.filter { $0.hasPrefix("val/") }
        guard !vk.isEmpty, d.epochs.count >= 8 else { return nil }
        let sums: [Double?] = d.epochs.indices.map { i in
            let vs = vk.compactMap { (d.columns[$0] ?? []).indices.contains(i) ? d.columns[$0]?[i] ?? nil : nil }
            return vs.count == vk.count && vs.contains(where: { $0 > 0 }) ? vs.reduce(0, +) : nil   // 0으로 적힌 초반 에폭은 뺀다(분석기와 같게)
        }
        guard let lo = sums.indices.filter({ sums[$0] != nil }).min(by: { sums[$0]! < sums[$1]! }),
              let last = sums.last ?? nil, let low = sums[lo], lo < d.epochs.count - 3, last > low * 1.10 else { return nil }
        return d.epochs[lo]
    }

    /// 보이는 곡선의 값 범위에 여백을 조금 둔 세로축
    func yDomain(_ d: RunDetail, _ keys: [String]) -> ClosedRange<Double> {
        let ys = keys.flatMap { smooth(d.columns[$0] ?? [], smoothing).compactMap { $0 } }
        guard let lo = ys.min(), let hi = ys.max() else { return 0...1 }
        let pad = max((hi - lo) * 0.12, 0.005)
        return (lo - pad)...(hi + pad)
    }

    /// 화면 낭독기용 한 줄: 곡선마다 가장 좋은 값과 그 에폭(손실은 가장 낮은, 점수는 가장 높은)
    func curveSummary(_ d: RunDetail, _ keys: [String]) -> String {
        let loss = keys.first.map { d.lossKeys.contains($0) } ?? false
        let parts: [String] = keys.prefix(4).compactMap { k in
            let pts = zip(d.epochs, d.columns[k] ?? []).compactMap { e, v in v.map { (e, $0) } }
            guard let b = loss ? pts.min(by: { $0.1 < $1.1 }) : pts.max(by: { $0.1 < $1.1 }) else { return nil }
            return L("%@ curve, best %@ at epoch %@", d.label(k), String(format: "%.3f", b.1), "\(Int(b.0))")
        }
        return parts.isEmpty ? L("Curves") : parts.joined(separator: ". ")
    }

    /// 곡선 위 작은 카드: 그 에폭의 값들
    func hoverCard(_ d: RunDetail, keys: [String], epoch: Double) -> some View {
        let i = d.epochs.firstIndex(of: epoch) ?? 0
        return VStack(alignment: .leading, spacing: 2) {
            Text(L("epoch %@", "\(Int(epoch))")).font(.ui(11, weight: .bold))
            ForEach(keys.prefix(6), id: \.self) { k in
                if let v = (d.columns[k] ?? []).indices.contains(i) ? d.columns[k]?[i] ?? nil : nil {
                    Text(verbatim: "\(d.label(k))  \(String(format: "%.4f", v))").font(.ui(10.5, design: .monospaced))
                }
            }
        }
        .padding(7)
        .glass(radius: Radius.control)
    }
}

/// 지수 이동 평균(TensorBoard와 같은 방식). 빈 값은 건너뛰고 자리를 지킨다
func smooth(_ ys: [Double?], _ w: Double) -> [Double?] {
    guard w > 0 else { return ys }
    var last: Double?
    return ys.map { y in
        guard let y else { return nil }
        let v = last.map { $0 * w + y * (1 - w) } ?? y
        last = v
        return v
    }
}
