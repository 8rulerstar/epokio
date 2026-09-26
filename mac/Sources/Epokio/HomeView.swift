import SwiftUI

// Studio 홈(대시보드): 들어오면 "지금 무엇이 돌고, 무엇을 챙겨야 하고, 최근에 무엇이 나왔나"가 한 화면에.
//  1 지금: 도는 학습 · 대기열 다음 · 기계 상태   2 챙길 것: 멈춤·실패 · 토큰 기다리는 스윕 · 검수할 평가 · 다음 학습 제안
//  3 최근 결과: 최근 5개와 같은 데이터의 이전 최고 대비   4 데이터셋별 최고   5 빠른 작업(머리 오른쪽 유리 막대)
// 모양: 카드는 쓰지 않는다. 맨 위 요약 하나만 크게, 나머지는 여백·글씨·가는 줄로 나눈다(2026-09-22)
// 계산은 가볍게: 표 API 한 번(설정·점수), 스윕 목록 한 번, 최근 끝난 학습 3개의 상세(다음 학습 제안).

struct HomeView: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var table: [TableRun] = []
    @State private var sweeps: [SweepSummary] = []
    @State private var suggestions: [(Run, RunDetail, RunDetail.Note)] = []

    private var live: [Run] { store.runs.filter(\.isLive) }
    private var trouble: [Run] { store.runs.filter { $0.state == "failed" || $0.state == "stalled" } }
    private var checks: [Job] { store.jobs.filter { $0.kind == "evaluate" && $0.state == "done" }.suffix(3).reversed() }
    private var waitingSweeps: [SweepSummary] { sweeps.filter { !($0.needs_tokens ?? []).isEmpty } }

    private var done: [TableRun] { table.filter { $0.state != "running" && $0.best != nil }.sorted { ($0.idle ?? .infinity) < ($1.idle ?? .infinity) } }
    /// 같은 데이터·같은 지표로 앞서 끝난 학습들의 최고. ★지표가 다르면(detect mAP vs classify 정확도,
    /// 또는 손실 계열) 나란히 놓을 수 없다. 방향도 지표를 따른다(낮을수록 좋은 점수는 min)
    private func before(_ r: TableRun) -> Double? {
        let peers = done.filter { ($0.idle ?? 0) > (r.idle ?? 0) && r.args["data"] != nil
            && $0.args["data"] == r.args["data"] && $0.metric_name == r.metric_name }.compactMap(\.best)
        return r.higher ? peers.max() : peers.min()
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 36) {
                header
                if !store.runs.isEmpty && UserDefaults.standard.bool(forKey: "achievements") { NextTrophy() }
                if store.runs.isEmpty { empty } else { hero }
                ForEach(tiles) { t in tile(t) }                  // 순서·숨김은 설정 → 꾸미기
            }
            .padding(.horizontal, 40).padding(.top, 32).padding(.bottom, 48)
            .frame(maxWidth: 900, alignment: .leading)
        }
        .epokioScroll(title: "Home")
        .defaultScrollAnchor(Self.snapshotAnchor)
        .task(id: store.runs.map(\.id)) { await load() }
    }
    /// 스냅샷 전용: `-homeScrollAnchor center|bottom`으로 스크롤 중간 상태를 찍는다(평소엔 위)
    private static var snapshotAnchor: UnitPoint {
        switch UserDefaults.standard.string(forKey: "homeScrollAnchor") { case "center": .center; case "bottom": .bottom; default: .top }
    }

    @AppStorage("homeOrder") private var homeOrder = ""
    @AppStorage("homeHidden") private var homeHidden = ""
    private var tiles: [HomeTile] {
        let off = Set(homeHidden.split(separator: ",").map(String.init)), o = homeOrder.split(separator: ",").map(String.init)
        let all = HomeTile.allCases
        return all.filter { !off.contains($0.rawValue) }
            .sorted { (o.firstIndex(of: $0.rawValue) ?? 999, all.firstIndex(of: $0)!) < (o.firstIndex(of: $1.rawValue) ?? 999, all.firstIndex(of: $1)!) }
    }
    @ViewBuilder private func tile(_ t: HomeTile) -> some View {
        let has = !store.runs.isEmpty
        switch t {
        case .now: if has && (live.count > 1 || store.jobs.contains { $0.state == "queued" } || !store.system.isEmpty) { now }
        case .attention: if has && (!trouble.isEmpty || !checks.isEmpty || !waitingSweeps.isEmpty || !suggestions.isEmpty) { attention }
        case .recent: if has { recent }
        case .best: if has { bestPerData }
        case .quick: EmptyView()                                       // 머리 오른쪽 유리 막대로 옮겼다
        }
    }

    // ── 머리: 제목 · 한 줄 요약 · 빠른 작업(아이콘) ──
    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Home").font(.role(.hero))
                Text(verbatim: summaryLine).font(.role(.body)).foregroundStyle(ink.soft).contentTransition(.opacity)
                    .animation(Motion.change, value: summaryLine)
            }
            Spacer(minLength: 16)
            if !homeHidden.split(separator: ",").contains("quick") { quick }
        }
        .padding(.horizontal, 8)
    }
    private var summaryLine: String {
        var parts: [String] = []
        if !live.isEmpty { parts.append(L("%d training", live.count)) }
        if store.queuedCount > 0 { parts.append(L("%d waiting", store.queuedCount)) }
        if let last = store.runs.filter({ !$0.isLive }).min(by: { $0.idle < $1.idle }) {
            parts.append(L("last finished %@ ago", duration(last.idle)))
        }
        return parts.isEmpty ? L("Nothing is training right now") : parts.joined(separator: "  ·  ")
    }

    // ── 요약 하나를 크게: 도는 학습이 있으면 그것, 없으면 가장 최근 결과 ──
    @ViewBuilder private var hero: some View {
        if let r = live.first {
            Button { store.open(run: r.id) } label: {
                VStack(alignment: .leading, spacing: 12) {
                    LiveTile(run: r, big: true)
                    if r.history.count > 1 { HeroCurve(values: r.history).frame(height: 140).padding(.horizontal, 8) }
                }
                .contentShape(.rect)
            }
            .buttonStyle(PressStyle()).appearRise()
        } else if let r = done.first {
            Button { store.open(run: r.id) } label: {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Latest result").font(.role(.callout, weight: .semibold)).foregroundStyle(ink.soft)
                    HStack(alignment: .firstTextBaseline, spacing: 14) {
                        Text(Fmt.metric(r.best ?? 0, higher: r.higher)).font(.ui(64, weight: .bold, design: .rounded)).monospacedDigit()
                            .foregroundStyle(.brand).contentTransition(.numericText())
                        if let b = r.best, let p = before(r) { delta(b - p, higher: r.higher, than: p).font(.role(.headline)) }
                    }
                    Text(verbatim: [r.display, r.args["data"], r.idle.map { L("%@ ago", duration($0)) }].compactMap { $0 }.joined(separator: "  ·  "))
                        .font(.role(.body)).foregroundStyle(ink.soft).lineLimit(1).truncationMode(.middle)
                    if let h = store.runs.first(where: { $0.path == r.path })?.history, h.count > 1 {
                        HeroCurve(values: h).frame(height: 120).padding(.top, 12)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading).padding(8).rowHover()
            }
            .buttonStyle(PressStyle()).appearRise()
        }
    }

    // ── 1 지금 ──
    private var now: some View {
        section("Now") {
            ForEach(Array(live.dropFirst().enumerated()), id: \.element.id) { i, r in
                Button { store.open(run: r.id) } label: { LiveTile(run: r) }.buttonStyle(PressStyle()).appearRise(i)
            }
            if let j = store.jobs.first(where: { $0.state == "queued" }) {
                line(symbol: "list.number", title: j.name, text: L("Next in queue")) { store.section = .queue }
            }
            ForEach(store.system.keys.sorted(), id: \.self) { k in
                if let s = store.system[k]?.now {
                    HStack(spacing: 12) {
                        Gauge(label: "GPU", value: s.gpus.first?.util, tint: .brand)
                        Gauge(label: "CPU", value: s.cpu, tint: .brand)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: k).font(.role(.callout, weight: .semibold))
                            Text(verbatim: s.gpus.first?.name ?? s.host).font(.role(.caption)).foregroundStyle(ink.soft).lineLimit(1)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 8)
                }
            }
        }
    }

    // ── 2 챙길 것 ──
    private var attention: some View {
        section("Needs attention") {
            ForEach(trouble) { r in
                line(symbol: r.state == "failed" ? "xmark.octagon.fill" : "pause.circle.fill", tint: r.state == "failed" ? .bad : .warn,
                     title: r.displayName, text: r.state == "failed" ? L("Failed") : L("No new epoch for a while."), action: L("Open")) { store.open(run: r.id) }
            }
            ForEach(waitingSweeps) { s in
                line(symbol: "key.slash", tint: .warn, title: s.name, text: L("Sweep waiting for a machine token"), action: L("Open")) { store.section = .queue }
            }
            ForEach(checks) { j in
                line(symbol: "checkmark.rectangle.stack", title: j.name, text: L("Check finished. Review the mistakes."), action: L("Review")) {
                    store.pendingReviewJob = j.id; store.section = .review
                }
            }
            ForEach(suggestions, id: \.0.id) { r, d, n in
                HStack(alignment: .top, spacing: 14) {
                    Image(systemName: "lightbulb").foregroundStyle(ink.soft).frame(width: 20).padding(.top, 2).accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(verbatim: r.displayName).font(.role(.body, weight: .semibold))
                        Text(verbatim: n.observation).font(.role(.callout)).foregroundStyle(ink.soft).lineLimit(2)
                        if let c = n.next { NextRunButton(change: c, detail: d, run: r).padding(.top, 2) }
                    }
                    Spacer(minLength: 0)
                }
                .padding(.vertical, 10).padding(.horizontal, 8).rowHover().divided()
                .transition(.opacity)
                .tip()
            }
        }
    }

    // ── 3 최근 결과(같은 데이터의 이전 최고 대비) ──
    private var recent: some View {
        section("Recent results") {
            ForEach(Array(done.prefix(5).enumerated()), id: \.element.id) { i, r in
                Button { store.open(run: r.id) } label: {
                    HStack(spacing: 12) {
                        Text(verbatim: r.display).font(.role(.body, weight: .medium)).lineLimit(1).truncationMode(.middle)
                        Text(verbatim: r.args["data"] ?? "").font(.role(.callout)).foregroundStyle(ink.soft).lineLimit(1)
                        Spacer()
                        if let b = r.best, let p = before(r) { delta(b - p, higher: r.higher, than: p).font(.role(.caption, weight: .semibold)) }
                        Text(Fmt.metric(r.best ?? 0, higher: r.higher)).font(.role(.body, weight: .semibold)).monospacedDigit()
                        Text(verbatim: r.idle.map { L("%@ ago", duration($0)) } ?? "").font(.role(.caption)).foregroundStyle(ink.soft).frame(width: 70, alignment: .trailing)
                    }
                    .padding(.horizontal, 8).padding(.vertical, 10).rowHover()
                }
                .buttonStyle(PressStyle()).divided().appearRise(i)
            }
            if done.isEmpty { Text("No finished runs yet.").font(.role(.callout)).foregroundStyle(ink.soft) }
        }
    }

    // ── 4 데이터셋별 최고: 카드 없이 숫자 열 ──
    private var bestPerData: some View {
        // ★데이터 + 지표로 묶는다: 같은 데이터라도 지표가 다르면(mAP vs 정확도 vs rmse) 한 칸에 겹칠 수 없다
        let groups = Dictionary(grouping: table.filter { $0.best != nil && $0.args["data"] != nil },
                                by: { ($0.args["data"] ?? "") + "\u{1}" + ($0.metric_name ?? "") })
        let best = groups.compactMap { $0.value.max { $0.bestSort < $1.bestSort } }      // bestSort가 이미 방향을 담는다
        // 방향이 섞여 있으면 점수로 줄 세우는 것 자체가 뜻이 없다: 그때는 데이터 이름 순
        let mixed = Set(best.map(\.higher)).count > 1
        let sorted = mixed ? best.sorted { ($0.args["data"] ?? "") < ($1.args["data"] ?? "") } : best.sorted { $0.bestSort > $1.bestSort }
        return Group {
            if !sorted.isEmpty {
                section("Best per dataset") {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 200), spacing: 24, alignment: .leading)], alignment: .leading, spacing: 16) {
                        ForEach(Array(sorted.prefix(6).enumerated()), id: \.element.id) { i, r in
                            Button { store.open(run: r.id) } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(verbatim: r.args["data"] ?? "").font(.role(.callout)).foregroundStyle(ink.soft).lineLimit(1)
                                    Text(Fmt.metric(r.best ?? 0, higher: r.higher)).font(.role(.display)).monospacedDigit()
                                    Text(verbatim: [r.display, r.args["epochs"].map { L("%@ epochs", $0) }].compactMap { $0 }.joined(separator: " · "))
                                        .font(.role(.caption)).foregroundStyle(ink.soft).lineLimit(1).truncationMode(.middle)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading).padding(8).rowHover()
                                .help(r.args["model"] ?? "")
                            }
                            .buttonStyle(PressStyle()).appearRise(i)
                        }
                    }
                }
            }
        }
    }

    // ── 5 빠른 작업: 아이콘만 있는 유리 막대 ──
    private var quick: some View {
        QuickBar(items: quickItems)
    }
    private var quickItems: [QuickBar.Item] {
        var items: [QuickBar.Item] = [
            .init(title: "New training", symbol: "play.fill") { store.section = .train },
            .init(title: "Try a model", symbol: "eye") { store.section = .tryit },
            .init(title: "All runs as a table", symbol: "tablecells") { UserDefaults.standard.set(true, forKey: "runsTable"); store.section = .runs },
            .init(title: "Review", symbol: "checkmark.rectangle.stack") { store.section = .review },
        ]
        if !store.runs.isEmpty {                                       // 빈 화면에는 아래 "둘러보기" 링크가 있어 같은 학사모를 두 번 두지 않는다
            items.append(.init(title: "Training tour", symbol: "graduationcap") { withAnimation(Motion.appear) { store.tourStep = 0 } })
        }
        return items
    }

    private var empty: some View {
        VStack(alignment: .leading, spacing: 14) {
            Image(systemName: "chart.xyaxis.line").font(.ui(40, weight: .light)).foregroundStyle(.brand).accessibilityHidden(true)
            Text("No runs yet").font(.role(.display))
            Text("Add your results folder, or try three sample runs.").font(.role(.body)).foregroundStyle(ink.soft)
            HStack(spacing: 18) {
                Button { Task { await Samples.add(store) } } label: { Label("Look Around with Samples", systemImage: "sparkles") }
                    .primaryButton()
                Button { withAnimation(Motion.appear) { store.tourStep = 0 } } label: { Label("New to Training? Take the Tour", systemImage: "graduationcap") }
                    .buttonStyle(BrandLink()).font(.role(.body, weight: .medium))
            }
            .padding(.top, 6)
        }
        .padding(.horizontal, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .containerRelativeFrame(.vertical, alignment: .center) { h, _ in h * 0.62 }   // 빈 화면 아래 3분의 2가 비지 않게 가운데로
        .appearRise()
    }

    // ── 부품 ──
    private func section<C: View>(_ title: LocalizedStringKey, @ViewBuilder _ c: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.role(.headline)).padding(.horizontal, 8)
            c()
        }
        .scrollRise()
        .transition(.opacity.combined(with: .move(edge: .top)))
    }

    /// 이전 최고와의 차. ★화살표는 값의 부호, 색은 "좋아졌나"다. 손실·rmse는 내려가는 것이 개선이라
    /// 예전처럼 d >= 0을 초록으로 칠하면 개선이 빨간 악화로 뒤집혔다
    private func delta(_ d: Double, higher: Bool, than p: Double) -> some View {
        let better = higher ? d >= 0 : d <= 0
        return Label(String(format: "%+.3f", d), systemImage: d >= 0 ? "arrow.up.right" : "arrow.down.right")
            .foregroundStyle(better ? .good : .bad)
            .help(L("Compared with the best earlier run on the same data (%@)", Fmt.metric(p, higher: higher)))
    }

    /// 목록 한 줄: 아이콘 · 이름 · 설명 · (있으면) 동작 링크. 줄 전체를 눌러도 같은 동작
    private func line(symbol: String, tint: Color? = nil, title: String, text: String, action: String? = nil, go: @escaping () -> Void) -> some View {
        Button(action: go) {
            HStack(spacing: 14) {
                Image(systemName: symbol).foregroundStyle(tint.map(AnyShapeStyle.init) ?? AnyShapeStyle(ink.soft)).frame(width: 20).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(verbatim: title).font(.role(.body, weight: .semibold)).lineLimit(1)
                    Text(verbatim: text).font(.role(.callout)).foregroundStyle(ink.soft)
                }
                Spacer()
                if let action { Text(verbatim: action).font(.role(.callout, weight: .medium)).foregroundStyle(.brand) }
            }
            .padding(.horizontal, 8).padding(.vertical, 10).rowHover()
        }
        .buttonStyle(PressStyle()).divided()
    }

    // ── 불러오기 ──
    private func load() async {
        struct T: Decodable { let label: String; let rows: [TableRun] }
        struct W: Decodable { let sweeps: [SweepSummary] }
        var rows: [TableRun] = []
        for u in store.agents {
            if let p: T = try? await AgentClient(base: u).get("runs/table") { rows += p.rows.map { var r = $0; r.source = p.label; return r } }
        }
        let sw: W? = try? await AgentClient.local.get("sweeps")
        var sug: [(Run, RunDetail, RunDetail.Note)] = []
        for r in store.runs.filter({ !$0.isLive && store.isLocal($0) }).sorted(by: { $0.idle < $1.idle }).prefix(3) {
            if let d: RunDetail = try? await store.client(for: r).get("run", ["path": r.path]), let n = d.notes.first(where: { $0.next != nil }) {
                sug.append((r, d, n))
            }
        }
        withAnimation(Motion.change) { table = rows; sweeps = sw?.sweeps ?? []; suggestions = sug }
    }
}

/// 홈의 도는 학습 한 칸: 진행 고리 · 이름 · 에폭 · 끝날 시각 · 점수. big이면 홈 맨 위 요약(카드 없이 크게)
struct LiveTile: View {
    let run: Run
    var big = false
    @Environment(\.ink) private var ink
    var body: some View {
        let ring: CGFloat = big ? 96 : 40, w: CGFloat = big ? 8 : 4
        HStack(spacing: big ? 24 : 14) {
            if let p = run.progress {
                ZStack {
                    Circle().stroke(run.tint.opacity(0.18), lineWidth: w)
                    Circle().trim(from: 0, to: max(p, 0.02)).stroke(run.tint, style: StrokeStyle(lineWidth: w, lineCap: .round))
                        .rotationEffect(.degrees(-90)).animation(Motion.progress, value: p)
                    Text(verbatim: "\(Int((p * 100).rounded()))").font(big ? .role(.display) : .role(.caption, weight: .bold)).monospacedDigit()
                        .contentTransition(.numericText())
                }
                .frame(width: ring, height: ring)
            } else {                                                   // 총 에폭을 모르면 고리 대신 지금 에폭 숫자만
                Text(verbatim: "\(run.epoch)").font(big ? .role(.hero) : .role(.headline)).monospacedDigit()
                    .foregroundStyle(run.tint).contentTransition(.numericText())
                    .frame(minWidth: ring)
            }
            VStack(alignment: .leading, spacing: big ? 6 : 2) {
                Text(verbatim: run.displayName).font(big ? .role(.title) : .role(.body, weight: .semibold)).lineLimit(1).truncationMode(.middle)
                Text(verbatim: L("epoch %@", "\(run.epoch)/\(run.total.map(String.init) ?? "?")") + (run.eta.map { "  ·  " + L("done around %@", Fmt.time(Date().addingTimeInterval($0))) } ?? ""))
                    .font(big ? .role(.body) : .role(.caption)).foregroundStyle(ink.soft).lineLimit(1)
            }
            Spacer(minLength: 0)
            if let b = run.best {
                Text(Fmt.metric(b, higher: run.metricHigher)).font(big ? .ui(44, weight: .bold, design: .rounded) : .role(.headline)).monospacedDigit()
                    .foregroundStyle(big ? AnyShapeStyle(.brand) : AnyShapeStyle(.primary)).contentTransition(.numericText())
            }
        }
        .padding(.horizontal, 8).padding(.vertical, big ? 4 : 10).rowHover()
    }
}
