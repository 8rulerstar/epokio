import SwiftUI
import Charts

// 스윕 결과: 순위표 · 설정값별 점수 · 설정 영향도 · 최고 조합으로 더 길게 학습.
// 계산은 agent(epokio.sweep)가 한다. 앱은 GET /sweeps/<id> 를 그리기만 한다.

struct SweepSummary: Decodable, Identifiable, Hashable {
    let id: String
    let name: String
    let mode: String
    let prune: Bool
    let metric: String?
    let higher: Bool
    let rows: [Trial]
    let best: Trial?
    let importance: [Importance]
    let by_key: [String: ByKey]
    let done: Int
    let total: Int
    var best_so_far: [Double?]? = nil                   // 시도 순서대로 "지금까지 최고"(똑똑한 스윕이 얼마나 빨리 찾았나)
    var stopped: Bool? = nil
    var machines: [String]? = nil                      // 여러 기계 스윕이면 기계 목록("local" 포함)
    var needs_tokens: [String]? = nil                  // 토큰이 없어 새 시도를 못 넣는 기계
    var dispatch_errors: [String: String]? = nil
    var second: String? = nil                          // 두 번째 목표: size · time
    var pareto: [String]? = nil                        // 파레토 앞줄 시도(job id)

    struct Trial: Decodable, Hashable, Identifiable {
        var id: String { job }
        let job: String
        let trial: [String: Value]
        let state: String
        let run: String?
        let epochs: Int
        let best: Double?
        let best_epoch: Int?
        let curve: [Double]
        let rank: Int?
        var machine: String? = nil                     // 원격 기계에서 돈 시도면 그 주소
        var second: Double? = nil                      // 두 번째 목표 값(MB 또는 초)
    }
    struct Importance: Decodable, Hashable { let key: String; let share: Double }
    struct ByKey: Decodable, Hashable { let values: [KeyValue]; let spread: Double }
    struct KeyValue: Decodable, Hashable { let value: Value; let mean: Double; let n: Int }

    /// 숫자나 글자 (설정값)
    enum Value: Codable, Hashable, CustomStringConvertible {
        case num(Double), text(String)
        init(from d: Decoder) throws {
            let c = try d.singleValueContainer()
            if let x = try? c.decode(Double.self) { self = .num(x) } else { self = .text((try? c.decode(String.self)) ?? "") }
        }
        func encode(to e: Encoder) throws {
            var c = e.singleValueContainer()
            switch self { case .num(let x): try c.encode(x); case .text(let s): try c.encode(s) }
        }
        var description: String {
            switch self {
            case .num(let x): x == x.rounded() && abs(x) < 1e6 ? String(Int(x)) : String(format: "%g", x)
            case .text(let s): s
            }
        }
        var any: Any { switch self { case .num(let x): x == x.rounded() && abs(x) < 1e6 ? Int(x) : x; case .text(let s): s } }
    }

    var keys: [String] { importance.map(\.key) }
    var metricName: String { metric.map(prettyColumn) ?? L("score") }
}

/// 대기열 목록의 스윕 한 줄: 이름 · 진행 · 최고 점수
struct SweepRow: View {
    let s: SweepSummary
    @Environment(\.ink) private var ink
    @AppStorage(Fmt.scoreKey) private var scoreStyle = "3"   // 바꾸면 바로 다시 그린다

    var body: some View {
        HStack(spacing: 10) {
            ZStack {
                Circle().stroke(.quaternary, lineWidth: 3)
                Circle().trim(from: 0, to: CGFloat(s.done) / CGFloat(max(s.total, 1)))
                    .stroke(.tint, style: StrokeStyle(lineWidth: 3, lineCap: .round)).rotationEffect(.degrees(-90))
                    .animation(.smooth, value: s.done)
                Image(systemName: s.mode == "smart" ? "sparkle.magnifyingglass" : s.mode == "random" ? "dice" : "square.grid.3x3").font(.ui(10, weight: .semibold))
                    .help(s.mode == "smart" ? L("Smart search") : s.mode == "random" ? L("Random search") : L("Grid search"))
            }
            .frame(width: 28, height: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: s.name).font(.ui(13, weight: .semibold)).lineLimit(1)
                Text(verbatim: L("%d of %d runs", s.done, s.total) + (s.best?.best.map { "  ·  " + L("best %@", Fmt.metric($0, higher: s.higher, style: scoreStyle, raw: "%.3f")) } ?? ""))
                    .font(.ui(11.5)).foregroundStyle(ink.soft).contentTransition(.numericText())
            }
        }
        .padding(.vertical, 2)
    }
}

struct SweepDetail: View {
    let id: String
    var preset: SweepSummary? = nil                          // 스냅샷용: agent 대신 이 값을 그린다
    @AppStorage(Fmt.scoreKey) private var scoreStyle = "3"   // 바꾸면 바로 다시 그린다
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var s: SweepSummary?
    @State private var key: String?
    @State private var hover: String?

    var body: some View {
        ScrollView {
            if let s {
                VStack(alignment: .leading, spacing: 18) {
                    header(s)
                    machineNotes(s)
                    if let b = s.best { bestCard(s, b) }
                    if let g = s.second, !g.isEmpty { ParetoChart(s: s, goal: g) { openRun($0) } }
                    if let bs = s.best_so_far, bs.compactMap({ $0 }).count >= 2 { BestSoFar(values: bs, metric: s.metricName, smart: s.mode == "smart") }
                    if !s.importance.isEmpty && s.importance.count > 1 { importance(s) }
                    if s.rows.filter({ $0.best != nil }).count >= 2 { ParallelCoords(s: s) { openRun($0) } }
                    if let k = key ?? s.keys.first, let bk = s.by_key[k] { perValue(s, k, bk) }
                    leaderboard(s)
                }
                .padding(18)
                .transition(.opacity)
            } else {
                ProgressView().padding(40)
            }
        }
        .task(id: id) { await load() }
        .task(id: "\(id)|\(running)") {                     // 도는 동안만 조용히 새로고침(끝나면 멈추고, 다시 돌면 재개)
            while running && !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                if running { await load() }
            }
        }
    }

    private var running: Bool { s.map { $0.done < $0.total } ?? false }

    private func load() async {
        if let preset { s = preset; return }
        if let r: SweepSummary = try? await AgentClient.local.get("sweeps/\(id)") { withAnimation(.smooth) { s = r } }
    }

    /// 여러 기계 스윕: 토큰이 없어 멈춘 기계, 학습을 안 받은 기계
    @ViewBuilder private func machineNotes(_ s: SweepSummary) -> some View {
        let waiting = (s.needs_tokens ?? []).compactMap { URL(string: $0)?.host() }
        if !waiting.isEmpty {
            Label(L("Waiting for the token of %@. Add it in Settings → Machines if it is not there.", waiting.joined(separator: ", ")),
                  systemImage: "key.slash").font(.role(.caption)).foregroundStyle(.warn)
                .padding(10).frame(maxWidth: .infinity, alignment: .leading).background(.warn.opacity(0.08), in: .rect(cornerRadius: Radius.control))
                .transition(.opacity.combined(with: .move(edge: .top)))
        }
        ForEach(Array((s.dispatch_errors ?? [:]).keys.sorted()), id: \.self) { u in
            Label(L("%@ did not take a run: %@", URL(string: u)?.host() ?? u, s.dispatch_errors?[u] ?? ""), systemImage: "exclamationmark.triangle.fill")
                .font(.role(.caption)).foregroundStyle(.warn).lineLimit(2)
        }
    }

    private func header(_ s: SweepSummary) -> some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 3) {
                Text(verbatim: s.name).font(.ui(20, weight: .bold))
                Text(verbatim: (s.mode == "smart" ? L("Smart search") : s.mode == "random" ? L("Random search") : L("Chosen values")) + "  ·  " + L("%d of %d runs", s.done, s.total)
                     + (s.prune ? "  ·  " + L("stops runs that fall behind") : ""))
                    .font(.ui(12)).foregroundStyle(ink.soft)
            }
            Spacer()
            if s.done < s.total {
                Button(role: .destructive) {
                    Task { await store.act(L("Sweep stopped")) { _ = try await AgentClient.local.post("sweeps/\(s.id)/cancel") }; await load() }
                } label: { Label("Stop Sweep", systemImage: "stop.circle") }
            }
        }
    }

    /// 최고 조합 + "이 설정으로 더 길게". 좁으면 버튼이 아래 줄로
    private func bestCard(_ s: SweepSummary, _ b: SweepSummary.Trial) -> some View {
        let info = HStack(alignment: .top, spacing: 12) {
            Image(systemName: "trophy.fill").font(.ui(24)).foregroundStyle(.gold)
                .symbolEffect(.bounce, value: b.job).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 6) {
                Text(verbatim: L("Best %@ %@", s.metricName, Fmt.metric(b.best ?? 0, higher: s.higher, style: scoreStyle)))
                    .font(.ui(15, weight: .bold, design: .rounded)).contentTransition(.numericText())
                    .fixedSize(horizontal: false, vertical: true)
                FlowChips(items: s.keys.map { "\($0) = \(b.trial[$0]?.description ?? "–")" })
            }
        }
        let buttons = HStack(spacing: 8) {
            if let run = b.run {
                Button { openRun(run) } label: { Label("Open Run", systemImage: "chart.xyaxis.line") }
            }
            Button { trainLonger(s, b) } label: { Label("Train Longer", systemImage: "forward.fill") }
                .buttonStyle(.borderedProminent)
                .help("Open Train with this run's settings and twice the epochs")
        }
        .fixedSize()
        return ViewThatFits(in: .horizontal) {
            HStack(spacing: 16) { info; Spacer(minLength: 8); buttons }
            VStack(alignment: .leading, spacing: 12) { info; buttons }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.gold.opacity(0.08), in: .rect(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(.gold.opacity(0.35)))
    }

    /// 어느 설정이 점수를 가장 크게 바꿨나
    private func importance(_ s: SweepSummary) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            SectionTitle("What mattered most", hint: L("How much the average score changed across the values of each setting. Rough guide, not a proof."))
            ForEach(s.importance, id: \.key) { i in
                Button { withAnimation(.snappy) { key = i.key } } label: {
                    HStack(spacing: 8) {
                        Text(verbatim: i.key).font(.ui(12, weight: .semibold, design: .monospaced)).frame(width: 90, alignment: .leading)
                        GeometryReader { g in
                            Capsule().fill(.tint.opacity((key ?? s.keys.first) == i.key ? 0.9 : 0.45))
                                .frame(width: max(4, g.size.width * i.share))
                                .animation(.smooth, value: i.share)
                        }
                        .frame(height: 10)
                        Text(verbatim: "\(Int((i.share * 100).rounded()))%").font(.ui(11.5, design: .rounded)).frame(width: 40, alignment: .trailing)
                    }
                    .contentShape(.rect)
                }
                .buttonStyle(PressStyle())
            }
        }
    }

    /// 한 설정의 값마다 평균 점수 (막대). 가장 좋은 값은 진하게
    private func perValue(_ s: SweepSummary, _ k: String, _ bk: SweepSummary.ByKey) -> some View {
        let top = s.higher ? bk.values.map(\.mean).max() : bk.values.map(\.mean).min()
        return VStack(alignment: .leading, spacing: 6) {
            HStack {
                SectionTitle("Score by value", hint: L("Average best score of the runs that used each value."))
                Spacer()
                if s.keys.count > 1 {
                    Picker("Setting", selection: Binding(get: { key ?? s.keys.first ?? "" }, set: { key = $0 })) {
                        ForEach(s.keys, id: \.self) { Text(verbatim: $0).tag($0) }
                    }
                    .labelsHidden().frame(width: 140)
                }
            }
            Chart(bk.values, id: \.value) { v in
                BarMark(x: .value("Value", v.value.description), y: .value("Score", v.mean))
                    .foregroundStyle(v.mean == top ? Color.brand : Color.brand.opacity(0.4))
                    .cornerRadius(5)
                    .annotation(position: .top) { Text(Fmt.metric(v.mean, higher: s.higher, style: scoreStyle, raw: "%.3f")).font(.ui(10, design: .rounded)).foregroundStyle(ink.soft) }
            }
            .chartYScale(domain: .automatic(includesZero: false))
            .frame(height: 160)
            .animation(.smooth, value: k)
        }
    }

    /// 순위표. 멈춘 시도는 가위 표시
    private func leaderboard(_ s: SweepSummary) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            SectionTitle("All runs", hint: L("Best score of each run. Runs still waiting or running show their current state."))
            let rows = s.rows.sorted { ($0.rank ?? 999, $0.job) < ($1.rank ?? 999, $1.job) }
            HStack(spacing: 10) {                                  // 값만 줄에 쓰고 설정 이름은 여기 한 번
                Text(verbatim: "#").frame(width: 22)
                Text(verbatim: s.keys.joined(separator: "  ·  "))
                Spacer()
                Text(verbatim: s.metricName)
            }
            .font(.ui(11, weight: .semibold, design: .monospaced)).foregroundStyle(ink.soft).padding(.horizontal, 10)
            ForEach(rows) { r in
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 10) {
                        Text(verbatim: r.rank.map { "\($0)" } ?? "–").font(.ui(12, weight: .bold, design: .rounded)).frame(width: 22)
                            .foregroundStyle(r.rank == 1 ? .gold : .secondary)
                        Text(verbatim: s.keys.map { r.trial[$0]?.description ?? "–" }.joined(separator: "  ·  "))
                            .font(.ui(12, design: .monospaced)).lineLimit(1).truncationMode(.tail)
                        Spacer(minLength: 6)
                        Text(verbatim: r.best.map { Fmt.metric($0, higher: s.higher, style: scoreStyle) } ?? "–").font(.ui(12.5, weight: .semibold, design: .rounded))
                    }
                    HStack(spacing: 10) {
                        Color.clear.frame(width: 22, height: 1)
                        Sparkline(values: r.curve, tint: .brand).frame(width: 80, height: 16)
                        if let m = r.machine, !m.isEmpty {                                  // 어느 기계에서 돌았나
                            Label(URL(string: m)?.host() ?? m, systemImage: "server.rack").font(.role(.badge)).foregroundStyle(ink.soft)
                                .padding(.horizontal, 6).padding(.vertical, 1).background(.quaternary.opacity(0.6), in: Capsule())
                        } else if (s.machines?.count ?? 0) > 1 {
                            Label("This Mac", systemImage: "laptopcomputer").font(.role(.badge)).foregroundStyle(ink.soft)
                                .padding(.horizontal, 6).padding(.vertical, 1).background(.quaternary.opacity(0.6), in: Capsule())
                        }
                        Spacer()
                        stateBadge(r.state)
                    }
                }
                .padding(.horizontal, 10).padding(.vertical, 6)
                .background(.primary.opacity(hover == r.job ? 0.06 : 0.025), in: .rect(cornerRadius: 8))
                .onHover { h in withAnimation(Motion.tap) { hover = h ? r.job : nil } }
                .onTapGesture { if let run = r.run { openRun(run) } }
                .accessibilityAddTraits(r.run == nil ? [] : .isButton)
                .accessibilityAction { if let run = r.run { openRun(run) } }
                .help(r.run == nil ? "" : L("Click to open this run"))
                .contextMenu {                                      // 오른쪽 클릭: 결과 폴더 다루기
                    if let run = r.run {
                        Button("Show Results", systemImage: "chart.xyaxis.line") { openRun(run) }
                        Button("Show in Finder", systemImage: "folder") { NSWorkspace.shared.open(URL(fileURLWithPath: run)) }
                        Divider()
                        Button("Copy Path", systemImage: "doc.on.doc") { copyText(run, store) }
                    }
                }
            }
        }
    }

    /// 결과 폴더 경로로 학습 목록의 그 학습을 연다(없으면 목록만)
    private func openRun(_ path: String) {
        if let r = store.runs.first(where: { $0.path == path }) { store.open(run: r.id) } else { store.section = .runs }
    }

    private func stateBadge(_ st: String) -> some View {
        let (t, sym, c): (String, String, Color) = switch st {
        case "done": (L("Done"), "checkmark.circle.fill", .good)
        case "running": (L("Running"), "play.circle.fill", .brand)
        case "queued": (L("Waiting"), "clock", .gray)
        case "pruned": (L("Stopped early"), "scissors", .warn)
        case "failed": (L("Failed"), "xmark.octagon.fill", .bad)
        default: (L("Cancelled"), "minus.circle", .gray)
        }
        return Label(t, systemImage: sym).font(.ui(11, weight: .medium)).foregroundStyle(c)
    }

    private func trainLonger(_ s: SweepSummary, _ b: SweepSummary.Trial) {
        var a: [String: String] = [:]
        for (k, v) in b.trial { a[k] = v.description }
        if let run = b.run, let args = try? String(contentsOf: URL(fileURLWithPath: run).appending(path: "args.yaml"), encoding: .utf8) {
            for line in args.split(separator: "\n") where !line.hasPrefix(" ") {
                let kv = line.split(separator: ":", maxSplits: 1).map { $0.trimmingCharacters(in: .whitespaces) }
                if kv.count == 2, ["data", "task", "model", "epochs"].contains(kv[0]), a[kv[0]] == nil { a[kv[0]] = kv[1] }
            }
        }
        if let e = a["epochs"].flatMap(Double.init) { a["epochs"] = String(Int(e * 2)) }
        store.pendingTrainArgs = a
        withAnimation(.snappy) { store.section = .train }
        store.say(L("Filled in the best settings with twice the epochs."))
    }
}

/// 설정값 알약들. 폭이 모자라면 다음 줄로
struct FlowChips: View {
    let items: [String]
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 6) { ForEach(items, id: \.self) { chip($0) } }
            VStack(alignment: .leading, spacing: 4) { ForEach(items, id: \.self) { chip($0) } }
        }
    }
    private func chip(_ t: String) -> some View {
        Text(verbatim: t).font(.ui(11.5, weight: .semibold, design: .monospaced)).lineLimit(1).fixedSize()
            .padding(.horizontal, 7).padding(.vertical, 2)
            .background(.tint.opacity(0.14), in: Capsule())
    }
}

/// 차트 세로 범위: 값이 한 가지뿐이어도 그 값 둘레로(자동 눈금은 이때 엉뚱한 범위를 골랐다)
func yDomain(_ v: [Double]) -> ClosedRange<Double> {
    guard let lo = v.min(), let hi = v.max() else { return 0...1 }
    let pad = max((hi - lo) * 0.15, abs(hi) * 0.02, 0.01)
    return (lo - pad)...(hi + pad)
}

/// "지금까지 최고" 선: 시도가 늘수록 최고 점수가 언제 올랐나. 똑똑한 스윕이면 무작위 구간이 끝난 뒤를 표시한다
struct BestSoFar: View {
    let values: [Double?]
    let metric: String
    let smart: Bool
    @Environment(\.ink) private var ink

    var body: some View {
        let pts = values.enumerated().compactMap { i, v in v.map { (i + 1, $0) } }
        let foundAt = pts.last.flatMap { last in pts.first { $0.1 == last.1 }?.0 }
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Best so far", hint: foundAt.map { L("The best score was found at run %d of %d.", $0, values.count) })
            Chart {
                ForEach(pts, id: \.0) { i, v in
                    LineMark(x: .value("Training run", i), y: .value(metric, v)).interpolationMethod(.stepEnd).foregroundStyle(.brand)
                    PointMark(x: .value("Training run", i), y: .value(metric, v)).foregroundStyle(i == foundAt ? Color.gold : Color.brand).symbolSize(i == foundAt ? 80 : 24)
                }
                if smart && values.count > 4 {                       // 여기부터 앞 결과를 보고 골랐다
                    RuleMark(x: .value("Training run", 4.5)).foregroundStyle(ink.faint).lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                        .annotation(position: .top, alignment: .leading) { Text("guided from here").font(.role(.badge)).foregroundStyle(ink.soft) }
                }
            }
            .chartXAxisLabel(L("Training run"))
            .chartYScale(domain: yDomain(pts.map(\.1)))       // ★값이 다 같으면 자동 눈금이 -0.5~0으로 엉뚱했다
            .frame(height: 150)
            .padding(12)
            .background(.quaternary.opacity(0.25), in: .rect(cornerRadius: Radius.card))
        }
        .transition(.opacity.combined(with: .move(edge: .top)))
    }
}
