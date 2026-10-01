import SwiftUI
import Charts

// 학습 2~4개를 한 그래프와 표로 비교한다.

struct CompareView: View {
    @AppStorage(Fmt.scoreKey) private var scoreStyle = "3"   // 바꾸면 바로 다시 그린다
    let runs: [Run]
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var details: [String: RunDetail] = [:]
    @State private var dataDiff: LineageCard.DiffKey?
    @State private var key = ""

    private var keys: [String] {
        let all = runs.compactMap { details[$0.id] }.flatMap { $0.scoreKeys + $0.lossKeys }
        return Array(Set(all)).sorted { a, b in (a.hasPrefix("metrics/") ? 0 : 1, a) < (b.hasPrefix("metrics/") ? 0 : 1, b) }
    }

    var body: some View {
        if runs.count < 2 {
            ContentUnavailableView("Pick runs to compare", systemImage: "square.stack.3d.up",
                                   description: Text("Tick two to four runs on the left."))
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HStack {
                        SectionTitle("Compare runs", hint: L("Same chart, one line per run."))
                        Spacer()
                        Picker("Curve", selection: $key) {
                            ForEach(keys, id: \.self) { Text(verbatim: prettyColumn($0)).tag($0) }
                        }
                        .frame(width: 240)
                    }
                    Chart {
                        ForEach(runs) { r in
                            if let d = details[r.id], let ys = d.columns[key] {
                                ForEach(Array(zip(d.epochs, ys).enumerated()), id: \.offset) { _, p in
                                    if let y = p.1 {
                                        LineMark(x: .value("Epoch", p.0), y: .value("Value", y))
                                            .foregroundStyle(by: .value("Training run", r.displayName))
                                            .interpolationMethod(.monotone)
                                    }
                                }
                            }
                        }
                    }
                    .chartXAxisLabel(L("Epoch"))
            .chartYScale(domain: .automatic(includesZero: false))
            .chartXScale(domain: .automatic(includesZero: false))
                    .chartLegend(position: .bottom, alignment: .leading)
                    .chartForegroundStyleScale(range: chartPalette)               // 디자인 토큰 색(기본 파랑·초록 대신)
                    .frame(height: 280)
                    .padding(12)
                    .background(.quaternary.opacity(0.35), in: .rect(cornerRadius: 12))
                    if dataDiffers {
                        HStack(spacing: 10) {
                            Label("These runs used different data, so their scores are not directly comparable.", systemImage: "exclamationmark.triangle.fill")
                                .font(.ui(12.5)).foregroundStyle(.warn)
                            let fps = runs.compactMap { details[$0.id]?.versions?.data }.reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
                            if fps.count > 1 {
                                Button("What changed in the data") { dataDiff = LineageCard.DiffKey(a: fps[0], b: fps[1]) }
                                    .buttonStyle(BrandLink()).font(.ui(12.5, weight: .medium))
                            }
                        }
                        .transition(.opacity)
                    }
                    ScrollView(.horizontal, showsIndicators: false) { table }      // 좁은 창: 8칸 표가 창 밖으로 잘렸다
                    if runs.allSatisfy({ details[$0.id] != nil }) {       // 다 받기 전엔 "모두 같다"로 잘못 보인다
                        Group {
                            if differing.isEmpty {
                                Text("Same settings in all of them.").font(.ui(12)).foregroundStyle(ink.soft)
                            } else { diffTable }
                        }
                        .transition(.opacity.combined(with: .move(edge: .top)))
                    }
                }
                .padding(24)
            }
            .task(id: runs.map(\.id)) { await load() }
            .sheet(item: $dataDiff) { k in DataDiffSheet(a: k.a, b: k.b).frame(minWidth: 560, minHeight: 480) }
        }
    }

    /// 데이터 지문이 서로 다르면 점수를 그대로 비교하면 안 된다
    private var dataDiffers: Bool {
        Set(runs.compactMap { details[$0.id]?.versions?.data }).count > 1
    }

    private var table: some View {
        Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 8) {
            GridRow {
                ForEach([L("Training run"), L("Epochs"), L("Precision"), L("Recall"), "F1", "mAP50-95", L("Data"), L("Settings")], id: \.self) {
                    Text(verbatim: $0).font(.ui(11.5, weight: .semibold)).foregroundStyle(ink.soft).lineLimit(1).fixedSize()
                }
            }
            Divider()
            ForEach(runs) { r in
                let h = details[r.id]?.heads.first
                let best = runs.compactMap { details[$0.id]?.heads.first?.f1 }.max()
                GridRow {
                    Text(verbatim: r.displayName).lineLimit(2).frame(minWidth: 120, maxWidth: 200, alignment: .leading)
                    Text(verbatim: r.countText)
                    Text(verbatim: h?.precision.map { Fmt.score($0, style: scoreStyle) } ?? "–")
                    Text(verbatim: h?.recall.map { Fmt.score($0, style: scoreStyle) } ?? "–")
                    Text(verbatim: h?.f1.map { Fmt.score($0, style: scoreStyle) } ?? "–")
                        .fontWeight(h?.f1 != nil && h?.f1 == best ? .bold : .regular)
                        .foregroundStyle(h?.f1 != nil && h?.f1 == best ? AnyShapeStyle(.tint) : AnyShapeStyle(.primary))
                    Text(verbatim: h?.map5095.map { Fmt.score($0, style: scoreStyle) } ?? "–")
                    Text(verbatim: details[r.id]?.versions?.data ?? "–").foregroundStyle(dataDiffers ? AnyShapeStyle(.warn) : AnyShapeStyle(ink.soft))
                    Text(verbatim: summary(details[r.id]?.args ?? [:])).font(.ui(11.5)).foregroundStyle(ink.soft)
                        .lineLimit(2).frame(minWidth: 120, maxWidth: 180, alignment: .leading)
                }
                .font(.ui(12, design: .monospaced))
            }
        }
        .padding(14)
        .background(.quaternary.opacity(0.3), in: .rect(cornerRadius: 12))
    }

    /// 학습마다 값이 다른 설정만(MLflow·W&B 비교 화면처럼). 경로·이름·시각처럼 늘 다른 것은 뺀다
    private var differing: [String] {
        let noise = perRunArgs.union(["device", "workers", "seed_run", "time"])
        let ds = runs.compactMap { details[$0.id]?.trainArgs }             // 기본값까지 모든 설정(옛 agent면 주요 설정만)
        guard ds.count == runs.count, ds.count >= 2 else { return [] }
        // 모두에게 있는 설정만. ★옛 agent는 주요 11개만 줘서 섞이면 70줄이 전부 '다름'으로 나왔다
        var common = Set(ds[0].keys)
        for d in ds.dropFirst() { common.formIntersection(d.keys) }
        return common.subtracting(noise)
            .filter { k in Set(ds.map { $0[k] ?? "–" }).count > 1 }
            .sorted { a, b in (priority(a), a) < (priority(b), b) }
    }
    private func priority(_ k: String) -> Int { ["model", "data", "epochs", "imgsz", "batch", "lr0", "optimizer"].firstIndex(of: k) ?? 99 }

    private var diffTable: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Settings that differ", hint: L("Only the settings that were not the same in every run. Everything else matched."))
            Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 6) {
                GridRow {
                    Text("Setting").font(.role(.caption, weight: .semibold)).foregroundStyle(ink.soft)
                    ForEach(runs) { r in Text(verbatim: r.displayName).font(.role(.caption, weight: .semibold)).foregroundStyle(ink.soft).lineLimit(1).truncationMode(.middle).frame(maxWidth: 200, alignment: .leading) }
                }
                Divider()
                ForEach(Array(differing.enumerated()), id: \.element) { i, k in
                    GridRow {
                        Text(verbatim: k).font(.ui(12, design: .monospaced)).foregroundStyle(.brand)
                        ForEach(runs) { r in
                            Text(verbatim: shown(k, details[r.id]?.trainArgs[k] ?? "–")).font(.ui(12, design: .monospaced)).lineLimit(1).truncationMode(.middle)
                                .frame(maxWidth: 200, alignment: .leading)                      // 긴 값이 표를 창 밖으로 밀었다
                                .help(details[r.id]?.trainArgs[k] ?? "")
                        }
                    }
                    .appearRise(i)
                }
            }
            .padding(14)
            .background(.quaternary.opacity(0.3), in: .rect(cornerRadius: Radius.card))
        }
    }
    /// 경로는 파일 이름만
    /// 파일 이름이 같으면(data.yaml·data.yaml) 다른 곳이 안 보인다: 그땐 폴더 하나를 더 붙인다
    private func shown(_ k: String, _ v: String) -> String {
        let names = Set(runs.compactMap { details[$0.id]?.trainArgs[k] }.map(short))
        guard names.count == 1 else { return short(v) }
        let parts = v.split(whereSeparator: { $0 == "/" || $0 == "\\" })
        return parts.suffix(2).joined(separator: "/")
    }
    private func short(_ v: String) -> String {                       // 윈도에서 학습한 경로(\\)도 파일 이름만
        v.contains("/") || v.contains("\\") ? String(v.split(whereSeparator: { $0 == "/" || $0 == "\\" }).last ?? Substring(v)) : v
    }

    /// 설정 차이를 한눈에: 모델 · imgsz · batch
    private func summary(_ a: [String: String]) -> String {
        [a["model"].map { String($0.split(whereSeparator: { $0 == "/" || $0 == "\\" }).last ?? Substring($0)) }, a["imgsz"].map { "imgsz \($0)" }, a["batch"].map { "batch \($0)" }]
            .compactMap { $0 }.joined(separator: " · ")
    }

    private func load() async {
        for r in runs where details[r.id] == nil {
            if let d: RunDetail = try? await store.client(for: r).get("run", ["path": r.path]) {
                withAnimation(.smooth) { details[r.id] = d }
            }
        }
        if !keys.contains(key) {
            key = keys.first { $0.hasPrefix("metrics/mAP50-95") } ?? keys.first ?? ""
        }
    }
}
