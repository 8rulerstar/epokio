import SwiftUI


// Studio "학습 기록": 왼쪽 목록, 오른쪽 상세. 비교 모드에서는 여러 개를 골라 곡선을 겹쳐 본다.
struct RunsView: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var comparing = false
    @AppStorage("runsTable") private var table = false          // 표 보기(학습 기록 표)
    @AppStorage(Fmt.scoreKey) private var scoreStyle = "3"   // 바꾸면 바로 다시 그린다
    @AppStorage("runsGroupBy") private var groupByRaw = RunGroupBy.recent.rawValue   // 묶어 보기(RunGrouping.swift)
    private var groupBy: RunGroupBy { RunGroupBy(rawValue: groupByRaw) ?? .recent }
    @State private var runArgs: [String: [String: String]] = [:]   // 작업·데이터·모델로 묶을 때(표 API)
    @FocusState private var searchFocused: Bool
    @State private var dropOn: String?                                // 끌어 놓을 모음 머리(빛남)
    @State private var compareDrop = false
    @State private var collectionFor: Run?                          // "새 모음…" 이름 받기
    @State private var newCollection = ""
    @AppStorage("runsCollapsed") private var collapsedRaw = ""      // 접은 묶음(이름을 줄바꿈으로)
    private var collapsed: Set<String> { Set(collapsedRaw.split(separator: "\n").map(String.init)) }
    private func toggleGroup(_ t: String) {
        var c = collapsed
        if c.contains(t) { c.remove(t) } else { c.insert(t) }
        collapsedRaw = c.sorted().joined(separator: "\n")
    }
    private func expandedBinding(_ t: String) -> Binding<Bool> {
        Binding(get: { !collapsed.contains(t) }, set: { open in if open == collapsed.contains(t) { toggleGroup(t) } })
    }
    @State private var picked: [String] = []          // 비교할 학습 (고른 순서 = 색 순서)
    var startCompare: [String] = []                    // 스냅샷용: 경로 조각으로 비교할 학습을 미리 고른다
    static let maxCompare = 8                        // 표에서 여러 개 골라 비교(4→8, 차트 색 8개)
    @State private var query = ""
    @State private var show = "all"                    // all · star · live · problem

    /// 검색(이름·태그·메모·프레임워크) + 빠른 필터
    private var visible: [Run] {
        store.runs.filter { r in
            let okShow = switch show {
            case "star": r.meta?.star == true
            case "live": r.isLive
            case "problem": r.state == "failed" || r.state == "stalled"
            default: true
            }
            guard okShow else { return false }
            if query.isEmpty { return true }
            let hay = [r.displayName, r.frameworkName, r.source, r.meta?.note ?? ""] + (r.meta?.tags ?? [])
            return hay.contains { $0.localizedCaseInsensitiveContains(query) }
        }
    }

    var body: some View {
        if table {
            RunsTable { withAnimation(Motion.change) { table = false } }
                .transition(.opacity)
        } else {
            split
        }
    }

    @ViewBuilder private var split: some View {
        @Bindable var store = store
        HSplitView {                                     // 목록과 상세 사이 경계를 끌어 폭을 바꾼다
            VStack(spacing: 0) {
                HStack {
                    Text(comparing ? L("Pick up to %d runs", Self.maxCompare) : L("%d runs", visible.count))
                        .font(.ui(11.5)).foregroundStyle(ink.soft).lineLimit(1).fixedSize()
                    Spacer(minLength: 4)
                    // ★좁으면 "학습 12개"가 두 줄로 꺾이고 비교 버튼이 "…"가 됐다: 다 들어가면 글자까지, 아니면 아이콘만
                    ViewThatFits(in: .horizontal) { headerButtons(labels: true); headerButtons(labels: false) }
                }
                .padding(.horizontal, 12).padding(.top, 8)
                VStack(spacing: 6) {
                    TextField("Search names, tags, notes", text: $query).textFieldStyle(.roundedBorder).controlSize(.small)
                        .focused($searchFocused)
                        .onChange(of: store.focusSearch) { searchFocused = true }
                        .onKeyPress(.escape) { query = ""; searchFocused = false; return .handled }
                    // ★좁으면 "★…", "R…"로 잘렸다. 다 들어가면 글자까지, 아니면 고른 것만 글자·나머지는 아이콘만
                    ViewThatFits(in: .horizontal) {
                        chips(compact: false)
                        chips(compact: true)
                    }
                }
                .padding(.horizontal, 10).padding(.vertical, 8)
                Divider()
                List(selection: comparing ? .constant(nil) : $store.selectedRun) {
                    // 묶어 보기: 최근·날짜(연›월›일)·디스크 폴더·내 모음·작업… 파일 시스템처럼 접었다 편다
                    ForEach(RunTree.build(visible, by: groupBy, args: runArgs, recent: groups)) { top in
                        Section(isExpanded: expandedBinding(top.id)) {
                            nodeBody(top)
                        } header: {
                            // ★기본 머리는 화살표로만 열린다(닫기는 글자로도 됐다). 줄 전체를 눌러 열고 닫는다
                            Button { withAnimation(.snappy) { toggleGroup(top.id) } } label: {
                                HStack {
                                    Text(verbatim: top.title)
                                    Spacer()
                                    Text(verbatim: "\(top.count)").foregroundStyle(.tertiary).opacity(collapsed.contains(top.id) ? 1 : 0)
                                }
                                .contentShape(.rect)
                            }
                            .buttonStyle(.plain)
                            .padding(.horizontal, 4).padding(.vertical, 2)
                            .background(RoundedRectangle(cornerRadius: Radius.chip).fill(.tint.opacity(dropOn == top.id ? 0.2 : 0)))
                            .scaleEffect(dropOn == top.id ? 1.03 : 1)
                            .animation(Motion.hover, value: dropOn)
                            .dropDestination(for: String.self) { ids, _ in        // 학습을 끌어 모음 머리에 놓으면 그 모음에 넣는다
                                guard groupBy == .collection, top.id.count > 2 else { return false }
                                dropInto(ids, String(top.id.dropFirst(2))); return true
                            } isTargeted: { on in dropOn = on && groupBy == .collection && top.id.count > 2 ? top.id : (dropOn == top.id ? nil : dropOn) }
                        }
                    }
                }
                .listStyle(.sidebar)
                .onKeyPress(characters: .init(charactersIn: "s/")) { k in       // 목록에서 한 글자: S 별표 · / 검색
                    if k.characters == "/" { searchFocused = true } else { Task { await store.starSelected() } }
                    return .handled
                }
            }
            .frame(minWidth: 250, idealWidth: 290, maxWidth: 480)
            Group {
                if comparing {
                    CompareView(runs: picked.compactMap { id in store.runs.first { $0.id == id } })
                        .onAppear { if picked.count >= 2 { Trophies.shared.bump("compare") } }
                } else if let id = store.selectedRun, let run = store.runs.first(where: { $0.id == id }) {
                    RunDetailView(run: run).id(run.id)
                        .overlay {                                                // 다른 학습을 끌어 놓으면 이 학습과 비교
                            if compareDrop {
                                RoundedRectangle(cornerRadius: Radius.card).strokeBorder(.tint, style: StrokeStyle(lineWidth: 2, dash: [6, 4]))
                                    .background(RoundedRectangle(cornerRadius: Radius.card).fill(.tint.opacity(0.06)))
                                    .overlay { Label("Drop to compare", systemImage: "square.split.2x1").font(.role(.headline)).padding(12).glass(Capsule()) }
                                    .padding(8).transition(.opacity).allowsHitTesting(false)
                            }
                        }
                        .animation(Motion.hover, value: compareDrop)
                        .dropDestination(for: String.self) { ids, _ in
                            let others = ids.filter { id in id != run.id && store.runs.contains { $0.id == id } }
                            guard !others.isEmpty else { return false }
                            Haptic.success()
                            withAnimation(Motion.change) { comparing = true; picked = Array(([run.id] + others).prefix(Self.maxCompare)) }
                            return true
                        } isTargeted: { compareDrop = $0 }
                } else if store.runs.isEmpty {
                    // 빈 화면에도 다음 할 일
                    ContentUnavailableView {
                        Label("No runs yet", systemImage: "chart.xyaxis.line")
                    } description: {
                        Text("Add the folder where your training results are saved, or look around with three sample runs first. Nothing trains, and you can remove them in Settings.")
                    } actions: {
                        HStack {
                            Button("Add a Folder…") { addFolder() }
                            Button { Task { await Samples.add(store) } } label: { Label("Look Around with Samples", systemImage: "sparkles") }
                                .buttonStyle(.borderedProminent)
                        }
                    }
                } else {
                    ContentUnavailableView("Select a run", systemImage: "chart.xyaxis.line",
                                           description: Text("Pick a run on the left to see its results."))
                }
            }
            .frame(minWidth: 320, maxWidth: .infinity, maxHeight: .infinity)
            .layoutPriority(1)                          // 남는 폭은 상세 화면이 갖는다(목록은 기본 폭 유지)
        }
        .task(id: "\(groupByRaw)|\(store.runs.count)") { await loadArgs() }
        .alert("New Collection", isPresented: Binding(get: { collectionFor != nil }, set: { if !$0 { collectionFor = nil } })) {
            TextField("Name", text: $newCollection)
            Button("Add") {
                let name = newCollection.trimmingCharacters(in: .whitespaces)
                if let r = collectionFor, !name.isEmpty {
                    Task { await saveMeta(r, store, ["collections": (r.meta?.collections ?? []) + [name]], done: L("Added to %@", name), undo: ["collections": r.meta?.collections ?? []]) }
                    withAnimation(Motion.change) { groupByRaw = RunGroupBy.collection.rawValue }
                }
                collectionFor = nil
            }
            Button("Cancel", role: .cancel) { collectionFor = nil }
        } message: { Text("Collections are like folders you make yourself. A run can be in several.") }
        .onAppear {
            if store.selectedRun == nil { store.selectedRun = store.runs.first?.id }
            if let id = store.selectedRun { store.markRead(id) }
        }
        .onChange(of: store.selectedRun) { _, id in if let id { store.markRead(id) } }
        .onChange(of: store.pendingCompare, initial: true) { _, ids in
            guard let ids, ids.count >= 2 else { return }
            withAnimation(.smooth) { comparing = true; picked = Array(ids.prefix(Self.maxCompare)) }
            store.pendingCompare = nil
        }
        .onChange(of: store.runs.count) {
            if store.selectedRun == nil || !store.runs.contains(where: { $0.id == store.selectedRun }) {
                store.selectedRun = store.runs.first?.id          // 목록이 늦게 채워져도 빈 화면으로 두지 않는다
            }
            guard !startCompare.isEmpty, picked.isEmpty else { return }
            let ids = startCompare.compactMap { w in store.runs.first { $0.path.contains(w) }?.id }
            if ids.count >= 2 { comparing = true; picked = ids }
        }
    }

    @ViewBuilder private func menu(_ r: Run) -> some View {
        Button(r.meta?.star == true ? "Remove Star" : "Star", systemImage: r.meta?.star == true ? "star.slash" : "star") {
            let on = !(r.meta?.star ?? false)
            Task { await saveMeta(r, store, ["star": on], done: on ? L("Star added") : L("Star removed"), undo: ["star": !on]) }
        }
        if let sel = store.selectedRun, sel != r.id {
            Button("Compare with Selected", systemImage: "square.split.2x1") { store.pendingCompare = [sel, r.id] }
        }
        Menu("Add to Collection", systemImage: "folder.badge.plus") {
            ForEach(allCollections.filter { !(r.meta?.collections ?? []).contains($0) }, id: \.self) { c in
                Button(c) { Task { await saveMeta(r, store, ["collections": (r.meta?.collections ?? []) + [c]], done: L("Added to %@", c), undo: ["collections": r.meta?.collections ?? []]) } }
            }
            Divider()
            Button("New Collection…", systemImage: "plus") { newCollection = ""; collectionFor = r }
        }
        ForEach(r.meta?.collections ?? [], id: \.self) { c in
            Button(L("Remove from %@", c), systemImage: "minus.circle") { Task { await saveMeta(r, store, ["collections": (r.meta?.collections ?? []).filter { $0 != c }], done: L("Removed from %@", c), undo: ["collections": r.meta?.collections ?? []]) } }
        }
        Divider()
        if store.isLocal(r) {
            Button("Show in Finder", systemImage: "folder") { NSWorkspace.shared.open(URL(fileURLWithPath: r.path)) }
        }
        Button("Copy Path", systemImage: "doc.on.doc") { copyText(r.path, store) }
    }

    /// 끌어 놓은 학습들을 모음에 넣는다
    private func dropInto(_ ids: [String], _ c: String) {
        let rs = ids.compactMap { id in store.runs.first { $0.id == id } }.filter { !($0.meta?.collections ?? []).contains(c) }
        guard !rs.isEmpty else { return }
        Haptic.success()
        Task { for r in rs { await saveMeta(r, store, ["collections": (r.meta?.collections ?? []) + [c]], done: rs.count == 1 ? L("Added to %@", c) : nil) }
               if rs.count > 1 { store.say(L("Added %d runs to %@", rs.count, c)) } }
    }

    private func addFolder() {
        let p = NSOpenPanel(); p.canChooseDirectories = true; p.canChooseFiles = false; p.allowsMultipleSelection = true
        guard p.runModal() == .OK else { return }
        Task { for u in p.urls { await store.act(L("Watching %@", u.lastPathComponent)) { try await AgentClient.local.post("roots", ["path": u.path]) } } }
    }

    private func groups(_ runs: [Run]) -> [(String, [Run])] {
        let cal = Calendar.current, now = Date()
        func key(_ r: Run) -> String {
            if r.isLive { return L("Now") }
            let d = now.addingTimeInterval(-r.idle)
            if cal.isDateInToday(d) { return L("Today") }
            if cal.isDateInYesterday(d) { return L("Yesterday") }
            if now.timeIntervalSince(d) < 7 * 86_400 { return L("This week") }
            return L("Earlier")
        }
        var out: [(String, [Run])] = []
        for r in runs.sorted(by: { ($0.isLive ? 0 : 1, $0.idle) < ($1.isLive ? 0 : 1, $1.idle) }) {
            let k = key(r)
            if let i = out.firstIndex(where: { $0.0 == k }) { out[i].1.append(r) } else { out.append((k, [r])) }
        }
        return out
    }

    private func headerButtons(labels: Bool) -> some View {
        HStack(spacing: 6) {
            Menu {
                Picker("Group by", selection: $groupByRaw.animation(Motion.change)) {
                    ForEach(RunGroupBy.allCases) { g in Label(g.title, systemImage: g.symbol).tag(g.rawValue) }
                }
                .pickerStyle(.inline)
            } label: { Label(groupBy.title, systemImage: groupBy.symbol).labelStyle(labels ? AnyLabelStyle(.titleAndIcon) : AnyLabelStyle(.iconOnly)) }
            .menuStyle(.button).controlSize(.small).fixedSize()
            .help(L("Group by") + ": " + groupBy.title)
            Button { withAnimation(Motion.change) { table = true } } label: {
                Label("Table", systemImage: "tablecells").labelStyle(labels ? AnyLabelStyle(.titleAndIcon) : AnyLabelStyle(.iconOnly))
            }
            .controlSize(.small).help("See every run in one table: sort by any column, filter, pick several to compare")
            Button { exportRunsCSV(store.runs) } label: {
                Label("CSV", systemImage: "square.and.arrow.down").labelStyle(labels ? AnyLabelStyle(.titleAndIcon) : AnyLabelStyle(.iconOnly))
            }
            .controlSize(.small).disabled(store.runs.isEmpty).help("Save all runs as a spreadsheet (CSV)…")
            Toggle(isOn: $comparing.animation(.smooth)) {
                Label("Compare", systemImage: "square.stack.3d.up").labelStyle(labels ? AnyLabelStyle(.titleAndIcon) : AnyLabelStyle(.iconOnly))
            }
            .toggleStyle(.button).controlSize(.small).help("Compare")
        }
    }

    private var allCollections: [String] { Array(Set(store.runs.flatMap { $0.meta?.collections ?? [] })).sorted() }

    /// 마디 속: 바로 든 학습 줄, 그 아래 폴더들(접었다 폈다)
    private func nodeBody(_ n: RunNode) -> AnyView {
        AnyView(Group {
            ForEach(Array(n.runs.enumerated()), id: \.element.id) { i, r in
                RunRow(run: r, checked: comparing ? picked.contains(r.id) : nil)
                    .appearRise(i)
                    .contentShape(.rect)
                    .onTapGesture { if comparing { toggle(r.id) } else { store.selectedRun = r.id } }
                    .accessibilityAddTraits(comparing && picked.contains(r.id) ? [.isButton, .isSelected] : .isButton)
                    .contextMenu { menu(r) }
                    .draggable(r.id) { RunRow(run: r, checked: nil).frame(width: 260).padding(6).glass(RoundedRectangle(cornerRadius: Radius.control)) }
                    .tag(r.id)
            }
            ForEach(n.children) { c in
                DisclosureGroup(isExpanded: expandedBinding(c.id)) {
                    nodeBody(c)
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: c.symbol).foregroundStyle(.brand).font(.role(.caption)).accessibilityHidden(true)
                        Text(verbatim: c.title).font(.role(.body, weight: .medium)).lineLimit(1).truncationMode(.middle)
                        Spacer()
                        if let b = c.best, let higher = c.metricHigher {
                            Text(Fmt.metric(b, higher: higher, style: scoreStyle))
                                .font(.role(.badge)).monospacedDigit().foregroundStyle(ink.soft)
                        }
                        Text(verbatim: "\(c.count)").font(.role(.badge, weight: .semibold)).foregroundStyle(ink.soft)
                            .padding(.horizontal, 6).padding(.vertical, 1).background(.quaternary.opacity(0.6), in: Capsule())
                    }
                    .contentShape(.rect)
                    .accessibilityElement(children: .combine)
                    .help(c.title)
                }
            }
        })
    }

    /// 작업·데이터·모델로 묶을 때만 표 API에서 설정을 받아 온다
    private func loadArgs() async {
        guard [.task, .dataset, .model].contains(groupBy) else { return }
        struct P: Decodable { let rows: [TableRun] }
        var out: [String: [String: String]] = [:]
        for u in store.agents {
            if let p: P = try? await AgentClient(base: u).get("runs/table") { for r in p.rows { out[r.path] = r.args } }
        }
        withAnimation(Motion.change) { runArgs = out }
    }

    private func toggle(_ id: String) {
        withAnimation(.snappy) {
            if let i = picked.firstIndex(of: id) { picked.remove(at: i) }
            else if picked.count < Self.maxCompare { picked.append(id) }
        }
    }
}

// ── 상세 ─────────────────────────────────────────────

/// 작은 필터 칩(목록 위)
extension RunsView {
    func chips(compact: Bool) -> some View {
        HStack(spacing: 4) {
            MiniChip(title: L("All"), symbol: compact ? "square.stack" : nil, on: show == "all", compact: compact) { show = "all" }
            MiniChip(title: L("Starred"), symbol: "star.fill", on: show == "star", compact: compact) { show = "star" }
            MiniChip(title: L("Running"), symbol: "bolt.fill", on: show == "live", compact: compact) { show = "live" }
            MiniChip(title: L("Problems"), symbol: "exclamationmark.triangle.fill", on: show == "problem", compact: compact) { show = "problem" }
            Spacer(minLength: 0)
        }
        .fixedSize(horizontal: !compact, vertical: false)
    }
}


/// 예시 학습(agent /demo): 학습이 하나도 없을 때 모든 화면을 먼저 체험. 기록 파일만 만든다(학습하지 않음)
enum Samples {
    @MainActor static func add(_ store: Store) async {
        await store.act(L("Added 3 sample runs. Remove them any time in Settings.")) { _ = try await AgentClient.local.post("demo") }
        Haptic.success()
        try? await Task.sleep(for: .milliseconds(600))
        if let first = store.runs.first(where: { $0.path.contains("/.epokio/demo/") }) { withAnimation(Motion.change) { store.open(run: first.id) } }
    }
    @MainActor static func remove(_ store: Store) async {
        await store.act(L("Sample runs removed")) { _ = try await AgentClient.local.post("demo/remove") }
    }
    static var present: Bool { FileManager.default.fileExists(atPath: FileManager.default.homeDirectoryForCurrentUser.appending(path: ".epokio/demo").path) }
}
