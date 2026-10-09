import SwiftUI

// 학습 기록 표(W&B·MLflow의 runs 표): 학습 하나 = 한 줄. 칸 머리로 정렬, 위 칸에 조건으로 거르기, 여러 줄 골라 비교.
// 데이터는 기계마다 GET /runs/table(api/table.py). 설정값 칸은 한 번이라도 나온 것만.

struct TableRun: Identifiable, Hashable, Decodable {
    var id: String { "\(source)|\(path)" }
    var source = ""
    let path: String
    let name: String
    let state: String
    let epoch: Int
    let total: Int?
    let best: Double?
    let metric_name: String?
    let metric_higher: Bool?                 // 대표 점수 방향. 옛 agent는 안 보낸다
    let idle: Double?
    let tags: [String]
    let star: Bool
    let args: [String: String]
    var agentDisplay: String? = nil          // agent가 정한 보일 이름(/runs/table의 display, scan.display_name). 옛 agent엔 없다

    enum CodingKeys: String, CodingKey { case path, name, state, epoch, total, best, metric_name, metric_higher, idle, tags, star, args, agentDisplay = "display" }
    /// 옛 agent(필드 없음)면 열 이름으로 어림한다. Run.metricHigher와 같은 규칙
    var higher: Bool { metric_higher ?? !(metric_name ?? "").lowercased().contains("loss") }
    subscript(arg k: String) -> String { args[k] ?? "" }
    /// agent 이름이 먼저(Run.displayName과 같은 규칙), 옛 agent면 목록과 같은 규칙. ★Lightning version_0 셋이 같은 이름으로 보였다
    var display: String {
        if let agentDisplay, !agentDisplay.isEmpty { return agentDisplay }
        return runDisplayName(name, path)
    }
    /// 정렬 열쇠. ★낮을수록 좋은 점수는 부호를 뒤집어, 한 표에 섞여 있어도 "위가 더 좋은 쪽"이 된다
    var bestSort: Double { best.map { higher ? $0 : -$0 } ?? -.infinity }
    var totalSort: Int { total ?? 0 }
    var idleSort: Double { idle ?? .infinity }
}

/// 글자지만 숫자면 숫자로 비교한다("0.001" < "0.01", "16" < "128")
struct NumberAware: SortComparator {
    var order: SortOrder = .forward
    func compare(_ a: String, _ b: String) -> ComparisonResult {
        let r: ComparisonResult
        if let x = Double(a), let y = Double(b) { r = x < y ? .orderedAscending : x > y ? .orderedDescending : .orderedSame }
        else if a.isEmpty != b.isEmpty { r = a.isEmpty ? .orderedDescending : .orderedAscending }          // 빈 칸은 늘 아래
        else { r = a.localizedStandardCompare(b) }
        return order == .forward ? r : (r == .orderedAscending ? .orderedDescending : r == .orderedDescending ? .orderedAscending : .orderedSame)
    }
}

/// 거르기: "lr0<0.01 batch>=16 tag:sample coco" (조건은 모두 만족, 맨 글자는 이름에)
enum TableFilter {
    static func match(_ r: TableRun, _ q: String) -> Bool {
        for tok in q.split(separator: " ").map(String.init) where !tok.isEmpty {
            if tok.hasPrefix("tag:") { if !r.tags.contains(where: { $0.localizedCaseInsensitiveContains(tok.dropFirst(4)) }) { return false }; continue }
            if let (k, op, v) = split(tok) {
                let have = k == "best" ? r.best.map { String($0) } ?? "" : k == "epoch" ? String(r.epoch) : r[arg: k]
                if !test(have, op, v) { return false }
                continue
            }
            let hay = [r.display, r.path, r.state] + Array(r.args.values)     // 보이는 이름으로(웹 tMatch와 같다). 원래 이름은 path에 있다
            if !hay.contains(where: { $0.localizedCaseInsensitiveContains(tok) }) { return false }
        }
        return true
    }
    static func split(_ t: String) -> (String, String, String)? {
        for op in ["<=", ">=", "!=", "<", ">", "="] {
            if let r = t.range(of: op), r.lowerBound != t.startIndex { return (String(t[..<r.lowerBound]), op, String(t[r.upperBound...])) }
        }
        return nil
    }
    static func test(_ have: String, _ op: String, _ want: String) -> Bool {
        if let a = Double(have), let b = Double(want) {
            switch op { case "<": return a < b; case ">": return a > b; case "<=": return a <= b; case ">=": return a >= b
            case "!=": return a != b; default: return a == b }
        }
        let same = have.localizedCaseInsensitiveCompare(want) == .orderedSame || have.localizedCaseInsensitiveContains(want)
        return op == "!=" ? !same : op == "=" ? same : false
    }
}

struct RunsTable: View {
    let close: () -> Void
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var rows: [TableRun] = []
    @State private var keys: [String] = []
    @State private var query = ""
    @State private var selection = Set<TableRun.ID>()
    @State private var sort: [KeyPathComparator<TableRun>] = [KeyPathComparator(\.bestSort, order: .reverse)]
    @State private var loading = true

    private var shown: [TableRun] { rows.filter { TableFilter.match($0, query) }.sorted(using: sort) }

    /// 이 표에서 제일 좋은 점수인가. ★같은 지표끼리만 견준다: mAP 0.9와 rmse 0.1을 한 줄에 놓고
    /// max를 고르면 손실 계열 학습이 영영 "최고"가 못 되거나, 거꾸로 제일 나쁜 것이 강조된다
    private func isTop(_ r: TableRun) -> Bool {
        guard let b = r.best else { return false }
        let peers = rows.filter { $0.metric_name == r.metric_name }.compactMap(\.best)
        return b == (r.higher ? peers.max() : peers.min())
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Button { close() } label: { Label("List", systemImage: "sidebar.left") }.controlSize(.small)
                TextField("Filter: lr0<0.01  batch>=16  tag:sample  coco", text: $query)
                    .textFieldStyle(.roundedBorder).frame(maxWidth: 420)
                    .help("name or text, key<value · key>=value · key=value · key!=value, tag:name. All must match.")
                Text(L("%d of %d", shown.count, rows.count)).font(.role(.caption)).foregroundStyle(ink.soft)
                    .contentTransition(.numericText()).animation(Motion.change, value: shown.count)
                Spacer()
                Button {
                    store.pendingCompare = Array(selection.prefix(RunsView.maxCompare)); close()
                } label: { Label(L("Compare %d", selection.count), systemImage: "square.stack.3d.up") }
                .disabled(!(2...RunsView.maxCompare).contains(selection.count))
                .help(L("Pick 2 to %d rows (⌘-click or ⇧-click)", RunsView.maxCompare))
                Button {
                    if let id = selection.first { store.selectedRun = id; close() }
                } label: { Label("Open", systemImage: "arrow.up.right.square") }
                .disabled(selection.count != 1)
            }
            Table(shown, selection: $selection, sortOrder: $sort) {
                TableColumn("Training run", value: \.display) { r in
                    HStack(spacing: 6) {
                        Circle().fill(color(r.state)).frame(width: 7, height: 7)
                        if r.star { Image(systemName: "star.fill").font(.role(.badge)).foregroundStyle(.gold) }
                        Text(verbatim: r.display).lineLimit(1).truncationMode(.middle)
                    }
                    .help(r.path)
                }
                .width(min: 180, ideal: 240)
                TableColumn("Score", value: \.bestSort) { r in
                    Text(verbatim: r.best.map { String(format: "%.4f", $0) } ?? "–").monospacedDigit()
                        .foregroundStyle(isTop(r) ? AnyShapeStyle(.brand) : AnyShapeStyle(.primary))
                }
                .width(70)
                TableColumn("Epochs", value: \.totalSort) { r in Text(verbatim: "\(r.epoch)/\(r.total.map(String.init) ?? "?")").monospacedDigit() }
                    .width(70)
                TableColumnForEach(keys, id: \.self) { k in
                    TableColumn(k, value: \.[arg: k], comparator: NumberAware()) { r in
                        Text(verbatim: r[arg: k].isEmpty ? "–" : r[arg: k]).lineLimit(1).truncationMode(.middle)
                            .foregroundStyle(r[arg: k].isEmpty ? AnyShapeStyle(ink.faint) : AnyShapeStyle(.primary))
                    }
                    .width(min: ["model", "data"].contains(k) ? 120 : 44, ideal: ["model", "data"].contains(k) ? 150 : 64)   // 경로·파일 칸은 넓게(★"yol….pt")
                }
                TableColumn("Tags") { r in Text(verbatim: r.tags.map { "#" + $0 }.joined(separator: " ")).foregroundStyle(ink.soft).lineLimit(1) }
                    .width(min: 60, ideal: 90)
                TableColumn("Updated", value: \.idleSort) { r in Text(verbatim: r.idle.map { L("%@ ago", duration($0)) } ?? "–").foregroundStyle(ink.soft) }
                    .width(80)
            }
            .overlay { if loading { ProgressView() } else if rows.isEmpty { ContentUnavailableView("No runs yet", systemImage: "tablecells") } }
            .contextMenu(forSelectionType: TableRun.ID.self) { ids in
                if ids.count == 1, let id = ids.first { Button("Open") { store.selectedRun = id; close() } }
                if (2...RunsView.maxCompare).contains(ids.count) { Button("Compare") { store.pendingCompare = Array(ids); close() } }
            } primaryAction: { ids in
                if let id = ids.first { store.selectedRun = id; close() }                     // 두 번 누르면 연다
            }
        }
        .padding(16)
        .task(id: store.runs.map(\.id)) { await load() }
    }

    private func color(_ s: String) -> Color {
        switch s { case "running", "starting": .good; case "failed": .bad; case "stalled": .warn; case "done": .brand; default: .secondary }
    }

    private func load() async {
        struct P: Decodable { let label: String; let keys: [String]; let rows: [TableRun] }
        var all: [TableRun] = [], ks: [String] = []
        for u in store.agents {
            guard let p: P = try? await AgentClient(base: u).get("runs/table") else { continue }
            all += p.rows.map { var r = $0; r.source = p.label; return r }
            for k in p.keys where !ks.contains(k) { ks.append(k) }
        }
        withAnimation(Motion.change) { rows = all; keys = ks; loading = false }
    }
}
