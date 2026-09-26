import SwiftUI
import Charts

// 검수 깊이: 문턱 조절 · 클래스별 성적 · 혼동 행렬.
// 모델을 다시 돌리지 않는다. agent(epokio.review)가 저장된 정답·예측으로 다시 채점한다.
// 아이폰 듀오 원칙: 요약(정밀도·재현율·F1 + 문턱)이 먼저, 표와 행렬은 "자세히"를 눌러야 펼쳐진다.

/// 문턱 슬라이더와 그 문턱에서의 성적. 추천 문턱 버튼, 작은 F1 곡선
struct ThresholdBar: View {
    @AppStorage(Fmt.scoreKey) private var scoreStyle = "3"   // 바꾸면 바로 다시 그린다
    let result: EvalResult
    @Binding var conf: Double
    @Environment(\.ink) private var ink
    @State private var pulse = false

    var body: some View {
        ViewThatFits(in: .horizontal) {                     // 지표 한 줄: 공식 배지 · Epokio P/R/F1 · 문턱. 좁으면 문턱만 다음 줄
            HStack(spacing: 12) { official; stats; slider; best }
            VStack(alignment: .leading, spacing: 6) { HStack(spacing: 12) { official; stats }; HStack(spacing: 8) { slider; best } }
        }
        .animation(.snappy, value: result.best_conf)
    }

    private var slider: some View {
            HStack(spacing: 6) {
                Image(systemName: "slider.horizontal.3").foregroundStyle(.tint).help("Confidence").accessibilityLabel(Text("Confidence"))
                Slider(value: Binding(get: { conf }, set: { conf = ($0 * 20).rounded() / 20 }), in: (result.conf_floor ?? 0.05)...0.95)
                    .frame(width: 120).controlSize(.mini)
                    .help("Boxes below this confidence are ignored. Changing it rescores instantly, without running the model again.")
                Text(verbatim: String(format: "%.2f", conf)).font(.ui(12, weight: .bold, design: .monospaced))
                    .contentTransition(.numericText()).foregroundStyle(.tint)
            }
            .fixedSize()
    }

    @ViewBuilder private var best: some View {
            if let b = result.best_conf, abs(b - conf) > 0.001 {
                Button {
                    withAnimation(.snappy) { conf = b }
                } label: {
                    Label(L("Best F1 at %@", String(format: "%.2f", b)), systemImage: "wand.and.stars")
                        .labelStyle(.iconOnly).symbolEffect(.bounce, value: pulse)
                }
                .controlSize(.small).buttonStyle(.borderless).tint(.brand)
                .help(L("Best F1 at %@", String(format: "%.2f", b)))
                .transition(.scale.combined(with: .opacity))
                .onAppear { pulse.toggle() }
            }
    }

    /// 공식 규칙 값: 문턱과 무관하므로 슬라이더 앞에 둔다
    @ViewBuilder private var official: some View {
            if let o = result.official {
                if let t = o.top1 {
                    stat("Top-1", t, trainedHint(L("Same as Ultralytics val top-1 accuracy")))
                } else {
                    stat("mAP50", o.map50, trainedHint(L("Ultralytics val rules on these images")))
                    stat("P", o.precision, trainedHint(L("Ultralytics val precision on these images")))
                    stat("R", o.recall, trainedHint(L("Ultralytics val recall on these images")))
                }
                Divider().frame(height: 22)
            }
    }

    private func trainedHint(_ base: String) -> LocalizedStringKey {   // base는 이미 번역된 글
        guard let t = result.trained, let m = t.map50 else { return LocalizedStringKey(base) }
        return LocalizedStringKey(base + "\n" + L("results.csv: mAP50 %@ (training val set)", Fmt.score(m, style: scoreStyle)))
    }

    @ViewBuilder private var stats: some View {
            if let o = result.overall {
                if result.official != nil { EpokioBadge() }
                stat("Precision", o.precision, "How many found boxes are right")
                stat("Recall", o.recall, "How many real objects were found")
                stat("F1", o.f1, "Balance of the two")
            }
    }

    /// 인스펙터에 두는 작은 F1 곡선
    @ViewBuilder var curveView: some View {
        if let c = result.curve, c.count > 2 { curve(c) }
    }

    private func stat(_ name: LocalizedStringKey, _ v: Double?, _ hint: LocalizedStringKey) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(v.map { Fmt.score($0, style: scoreStyle) } ?? "–").font(.ui(14, weight: .bold, design: .rounded))
                .contentTransition(.numericText())
            Text(name).font(.ui(10.5)).foregroundStyle(ink.soft)
        }
        .fixedSize()
        .help(Text(hint))
        .accessibilityElement(children: .combine)
        .accessibilityHint(Text(hint))
    }

    /// 문턱별 F1. 지금 문턱은 세로줄
    private func curve(_ c: [EvalResult.CurvePoint]) -> some View {
        Chart {
            ForEach(c, id: \.conf) { p in
                if let f = p.f1 { LineMark(x: .value("conf", p.conf), y: .value("F1", f)).interpolationMethod(.monotone) }
            }
            RuleMark(x: .value("now", conf)).foregroundStyle(.tint.opacity(0.6)).lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 2]))
        }
        .chartXAxis(.hidden).chartYAxis(.hidden).chartXScale(domain: 0...1)
        .help("F1 at each confidence. The dashed line is the current setting.")
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(L("F1 by confidence, best %@ at %@", Fmt.score(c.compactMap(\.f1).max() ?? 0, style: scoreStyle),
                              String(format: "%.2f", c.max { ($0.f1 ?? 0) < ($1.f1 ?? 0) }?.conf ?? 0)))
    }
}

/// 클래스별 성적 표. 줄을 누르면 그 클래스 이미지만
struct ClassTable: View {
    let result: EvalResult
    @Binding var classFilter: Int?
    @Environment(\.ink) private var ink

    var body: some View {
        let rows = (result.per_class ?? []).sorted { ($0.f1 ?? 0, $0.name) < ($1.f1 ?? 0, $1.name) }   // 약한 클래스가 위로
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("Class").frame(maxWidth: .infinity, alignment: .leading)
                ForEach(["#", "P", "R", "F1"], id: \.self) { Text(LocalizedStringKey($0)).lineLimit(1).minimumScaleFactor(0.7).frame(width: 36, alignment: .trailing) }
            }
            .font(.ui(11, weight: .semibold)).foregroundStyle(ink.soft)
            ScrollView {
                VStack(spacing: 2) {
                    ForEach(rows) { c in ClassRow(c: c, on: classFilter == c.cls) {
                        withAnimation(.snappy) { classFilter = classFilter == c.cls ? nil : c.cls }
                    } }
                }
            }
            .frame(maxHeight: 190)
        }
    }
}

private struct ClassRow: View {
    @AppStorage(Fmt.scoreKey) private var scoreStyle = "3"   // 바꾸면 바로 다시 그린다
    let c: EvalResult.ClassCounts
    let on: Bool
    let tap: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: tap) {
            HStack {
                HStack(spacing: 6) {
                    Circle().fill(color(c.f1)).frame(width: 7, height: 7)
                    Text(verbatim: c.name).lineLimit(1)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Text(verbatim: "\(c.support)").frame(width: 36, alignment: .trailing)
                num(c.precision); num(c.recall)
                num(c.f1).fontWeight(.bold).foregroundStyle(color(c.f1))
            }
            .font(.ui(12, design: .rounded))
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(on ? AnyShapeStyle(.tint.opacity(0.18)) : AnyShapeStyle(.primary.opacity(hover ? 0.06 : 0)), in: .rect(cornerRadius: 6))
            .contentShape(.rect)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.tap) { hover = h } }
        .help(L("%d found right, %d wrong, %d missed. Click to show only this class.", c.tp, c.fp, c.fn))
    }
    private func num(_ v: Double?) -> some View { Text(v.map { Fmt.score($0, style: scoreStyle) } ?? "–").frame(width: 36, alignment: .trailing) }
    private func color(_ f: Double?) -> Color { guard let f else { return .gray }; return f < 0.5 ? .bad : f < 0.8 ? .warn : .good }
}

/// 혼동 행렬: 줄 = 정답, 칸 = 모델 답. 마지막 줄·칸 = 배경(헛검출·놓침). 칸을 누르면 그 이미지만
struct ConfusionGrid: View {
    let result: EvalResult
    @Binding var cell: ConfusionCell?
    @Environment(\.ink) private var ink
    @State private var hover: ConfusionCell?

    var body: some View {
        if let c = result.confusion, !c.matrix.isEmpty {
            let n = c.classes.count
            let top = c.matrix.flatMap { $0 }.max() ?? 1
            let side = min(26.0, 300.0 / Double(n))
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 4) {
                    Text("Label ↓  Model →").font(.ui(10.5)).foregroundStyle(ink.soft)
                    if let h = hover { Text(verbatim: describe(h, c)).font(.ui(10.5, weight: .semibold)).transition(.opacity) }
                }
                ScrollView([.horizontal, .vertical]) {
                    Grid(horizontalSpacing: 2, verticalSpacing: 2) {
                        ForEach(0..<n, id: \.self) { i in
                            GridRow {
                                Text(verbatim: c.classes[i] == -1 ? L("Background") : c.labels[i]).font(.ui(10)).lineLimit(1).frame(width: 74, alignment: .trailing)
                                ForEach(0..<n, id: \.self) { j in
                                    let v = c.matrix[i][j], k = ConfusionCell(g: c.classes[i], p: c.classes[j])
                                    square(v, top: top, diag: i == j && i < n - 1, k: k).frame(width: side, height: side)
                                }
                            }
                        }
                    }
                }
                .frame(maxHeight: 220)
            }
            .animation(Motion.hover, value: hover)
        }
    }

    private func square(_ v: Int, top: Int, diag: Bool, k: ConfusionCell) -> some View {
        let a = v == 0 ? 0.04 : 0.2 + 0.8 * Double(v) / Double(max(top, 1))
        return Button { withAnimation(.snappy) { cell = cell == k ? nil : k } } label: {
            RoundedRectangle(cornerRadius: 3)
                .fill((diag ? Color.good : Color.bad).opacity(a))
                .overlay { if v > 0 { Text(verbatim: "\(v)").font(.ui(9, weight: .bold, design: .rounded)).foregroundStyle(a > 0.55 ? .white : .primary) } }
                .overlay { if cell == k { RoundedRectangle(cornerRadius: 3).stroke(.tint, lineWidth: 2) } }
                .scaleEffect(hover == k ? 1.15 : 1)
        }
        .buttonStyle(.plain).disabled(v == 0)
        .onHover { h in hover = h ? k : (hover == k ? nil : hover) }
    }

    private func describe(_ k: ConfusionCell, _ c: EvalResult.Confusion) -> String {
        let name = { (x: Int) in x == -1 ? L("Background") : c.labels[c.classes.firstIndex(of: x) ?? 0] }
        if k.p == -1 { return L("%@ missed", name(k.g)) }
        if k.g == -1 { return L("%@ found where nothing is", name(k.p)) }
        if k.g == k.p { return L("%@ found right", name(k.g)) }
        return L("%@ taken for %@", name(k.g), name(k.p))
    }
}

/// 오른쪽 인스펙터(접기 가능): 평균 점수 · F1 곡선 · 클래스 표 · 혼동 행렬 · 설명. 떠 있는 유리 표면
struct ReviewInspector: View {
    let result: EvalResult
    @Binding var conf: Double
    @Binding var classFilter: Int?
    @Binding var cell: ConfusionCell?
    let metricName: String
    @Environment(\.ink) private var ink

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 6) {
                    Text(verbatim: L("Average score %@", String(format: "%.2f", result.mean))).font(.ui(12.5, weight: .medium))
                        .contentTransition(.numericText())
                    Image(systemName: "info.circle").font(.ui(11.5)).foregroundStyle(ink.soft)
                        .help(L("Score = how well the model's answer matches your labels, from 0 (all wrong) to 1 (perfect). Measured as %@. Average %@.",
                                metricName, String(format: "%.2f", result.mean)))
                }
                .accessibilityElement(children: .combine)
                ThresholdBar(result: result, conf: $conf).curveView.frame(height: 40)
                if result.deep {
                    ClassTable(result: result, classFilter: $classFilter)
                    ConfusionGrid(result: result, cell: $cell)
                    Text(result.isClassify ? "Counted from each image's top answer. Below the confidence, the answer counts as \"not sure\"."
                                           : "Epokio counts pool all boxes at one confidence. mAP50, P and R follow Ultralytics.")
                        .font(.ui(11.5)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(14)
        }
        .frame(width: 272)
        .glass(radius: Radius.card)
        .padding(.trailing, 10).padding(.vertical, 10)
    }
}

/// 값의 출처 배지(Epokio 자체 계산 · COCO 방식). 설명은 툴팁으로 (UI에 글을 늘리지 않는다)
struct SourceBadge: View {
    let text: String
    let label: LocalizedStringKey
    let help: LocalizedStringKey
    @Environment(\.ink) private var ink
    var body: some View {
        Text(verbatim: text).font(.ui(9.5, weight: .semibold)).foregroundStyle(ink.soft)
            .lineLimit(1).fixedSize()
            .padding(.horizontal, 5).padding(.vertical, 1.5)
            .background(Capsule().strokeBorder(ink.faint, lineWidth: 1))
            .hoverLift(1.06)
            .transition(.scale.combined(with: .opacity))
            .help(help)
            .accessibilityLabel(Text(label))
    }
}

struct EpokioBadge: View {
    var body: some View {
        SourceBadge(text: "Epokio", label: "Epokio counts", help: "Epokio counts: all boxes pooled at the confidence you pick, matched by confidence. Ultralytics averages per class at its best-F1 confidence and matches by overlap.")
    }
}
