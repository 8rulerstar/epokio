import SwiftUI
import UniformTypeIdentifiers

// 잘 맞춘·못 맞춘 이미지 모아 보기 + 검수.
// 평가 작업이 이미지마다 점수(검출=F1, 포즈=키포인트 점수)를 매겨 두면,
// 여기서 정답(초록)과 예측(빨강)을 겹쳐 보고 "모델 틀림 / 라벨 틀림 / 애매함"을 표시한다.

struct ReviewView: View {
    @Environment(\.ink) var ink
    @State var jobs: [Job] = []
    @State var jobID: String?
    @State var startNew = false              // 새 평가를 준비 중이면 지난 평가로 자동 전환하지 않는다
    @State var result: EvalResult?
    @State var sort = ReviewSort.lowest
    @State var filter = "all"
    @State var search = ""
    @State var limit = 48                    // 0 = 전부
    @State var verdicts: [String: Verdict] = [:]
    @State var open: EvalRow?
    @State var conf = 0.25                   // 문턱: 바꾸면 agent가 다시 채점
    @State var classFilter: Int?
    @State var cell: ConfusionCell?
    @State var fixed: Set<String> = []       // 라벨을 고친 이미지(이름, 확장자 뺀 것)
    @State var building = false
    // 새 평가
    @State var envs: [PyEnv] = []
    @State var env: PyEnv?
    @State var model: URL?
    @State var folder: URL?
    @Environment(Store.self) var store
    @State var status: String?
    @State var busy = false                  // 시작 요청이 도는 중: 연타로 평가가 두 번 큐에 들어가는 것을 막는다
    // 되돌리기 · 여러 장 선택 · 훑어보기
    @State var history: [[String: Verdict?]] = []      // 판정 바꾸기 전 값(⌘Z로 한 단계씩)
    @State var selection: Set<String> = []             // ⌘·⇧ 클릭으로 고른 이미지
    @State var anchor: String?                         // ⇧ 클릭 범위의 시작
    @State var hovered: String?                        // 스페이스로 훑어볼 이미지
    @State var focusedID: String?                      // 방향키로 옮기는 키보드 포커스
    @State var gridWidth: CGFloat = 600
    @AppStorage("reviewInsightsOpen") var inspectorOpen = false   // 예전 "자세히" 펼침 키를 그대로 쓴다

    /// 학습 상세의 "실수 검수": 그 학습의 best.pt로 새 평가를 준비한다
    func takePending() {
        if let id = store.pendingReviewJob {                 // 대기열에서 고른 평가 결과
            store.pendingReviewJob = nil
            startNew = false
            jobID = id
            Task { await load() }
            return
        }
        guard let m = store.pendingReviewModel else { return }
        store.pendingReviewModel = nil
        model = URL(fileURLWithPath: m)
        startNew = true
        jobID = nil
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            if let r = result {
                HStack(spacing: 0) {
                    VStack(spacing: 0) { filterBar(r); grid(r) }
                    if inspectorOpen {
                        ReviewInspector(result: r, conf: $conf, classFilter: $classFilter, cell: $cell, metricName: metricName(r.metric))
                            .transition(.move(edge: .trailing).combined(with: .opacity))
                    }
                }
                .animation(Motion.change, value: inspectorOpen)
            } else { starter }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task { await load() }
        .task(id: conf) {                                   // 슬라이더를 멈추면 다시 채점(끄는 중엔 기다린다)
            guard result != nil, let id = jobID else { return }
            try? await Task.sleep(for: .milliseconds(160))
            guard !Task.isCancelled, let r: EvalResult = try? await AgentClient.local.get("jobs/\(id)/eval", ["conf": String(conf)]) else { return }
            withAnimation(Motion.change) { result = r }
        }
        .onAppear(perform: takePending)
        .onChange(of: store.pendingReviewModel) { takePending() }
        .onChange(of: store.pendingReviewJob) { takePending() }
        .sheet(item: $open) { row in
            ReviewDetail(row: row, verdict: Binding(get: { verdicts[row.id] }, set: { mark([row.id], $0) }),
                         rows: shown, open: $open, verdicts: $verdicts, onSave: save,
                         onMark: { ids, v in mark(ids, v) }, onUndo: { undo() },
                         job: jobID, names: result?.names, onFixed: { fixed.insert($0) },
                         classify: result?.isClassify ?? false, canFix: result?.canFix ?? true)
                .frame(minWidth: 900, minHeight: 700)
        }
    }

    /// 필터 → 검색 → 정렬 → 개수 제한
    var shown: [EvalRow] {
        guard let r = result else { return [] }
        var rows = r.rows.filter { matches($0, filter) }
        if let c = classFilter { rows = rows.filter { $0.hasClass(c) } }
        if let c = cell { rows = rows.filter { $0.has(c) } }
        if !search.isEmpty { rows = rows.filter { URL(fileURLWithPath: $0.image).lastPathComponent.localizedCaseInsensitiveContains(search) } }
        switch sort {
        case .lowest: rows.sort { $0.score < $1.score }
        case .highest: rows.sort { $0.score > $1.score }
        case .unreviewedFirst: rows.sort { (verdicts[$0.id] == nil ? 0 : 1, $0.score) < (verdicts[$1.id] == nil ? 0 : 1, $1.score) }
        case .reviewedFirst: rows.sort { (verdicts[$0.id] != nil ? 0 : 1, $0.score) < (verdicts[$1.id] != nil ? 0 : 1, $1.score) }
        }
        return limit == 0 ? rows : Array(rows.prefix(limit))
    }

    func matches(_ row: EvalRow, _ f: String) -> Bool {
        switch f {
        case "missed": row.fn > 0
        case "extra": row.fp > 0
        case "wrongclass": (row.gt_status ?? []).contains("cls")
        case "fixed": fixed.contains(stem(row.image))
        case "todo": verdicts[row.id] == nil
        case "done": verdicts[row.id] != nil
        case "all": true
        default: verdicts[row.id]?.rawValue == f
        }
    }

    /// 점수가 무엇인지 사람 말로
    func metricName(_ m: String) -> String {
        m.lowercased().contains("keypoint") ? L("Keypoint match") : L("Box F1")
    }

    /// 화면 낭독기용 카드 요약: 파일명 · 점수 · 맞춤/더함/놓침 · 판정
    func reviewA11y(_ row: EvalRow) -> String {
        let name = URL(fileURLWithPath: row.image).lastPathComponent
        var s = L("%@, score %@, %lld found correctly, %lld extra, %lld missed", name, String(format: "%.2f", row.score), row.tp, row.fp, row.fn)
        if let v = verdicts[row.id] { s += ", " + String(localized: v.titleResource) } else { s += ", " + L("Not reviewed") }
        return s
    }

    func grid(_ r: EvalResult) -> some View {
        ScrollView {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 6)], spacing: 6) {
                ForEach(Array(shown.enumerated()), id: \.element.id) { i, row in
                    ReviewCard(row: row, verdict: verdicts[row.id], names: r.names, classify: r.isClassify,
                               selected: selection.contains(row.id), focused: focusedID == row.id, onHover: { h in hovered = h ? row.id : (hovered == row.id ? nil : hovered) })
                        .onTapGesture { tap(row) }
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(reviewA11y(row))
                        .accessibilityAddTraits(selection.contains(row.id) ? [.isButton, .isSelected] : .isButton)
                        .accessibilityAction { tap(row) }
                        .accessibilityAction(named: Text("Open")) { open = row }
                        .modifier(VerdictActions { v in mark([row.id], v, announce: true) })
                        .appearRise(i)
                        .transition(.opacity.combined(with: .scale(scale: 0.96)))
                }
            }
            .padding(.horizontal, 12).padding(.bottom, 12)
            .animation(Motion.change, value: shown.map(\.id))
            if shown.isEmpty {
                ContentUnavailableView("Nothing matches", systemImage: "line.3.horizontal.decrease.circle",
                                       description: Text("Try another filter or clear the search."))
                    .padding(.top, 40)
            }
        }
        // 키보드: 스페이스 = 훑어보기(파인더처럼), 1~4 = 고른 이미지에 판정, Esc = 선택 풀기, ⌘A = 보이는 것 전부 고르기
        .focusable().focusEffectDisabled()
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { gridWidth = $0 }
        // 방향키 = 포커스 이동, 스페이스 = 포커스 카드 고르기(포커스가 없으면 예전처럼 훑어보기), 리턴 = 크게 보기
        .onKeyPress(keys: [.leftArrow, .rightArrow, .upArrow, .downArrow]) { k in moveFocus(k.key); return .handled }
        .onKeyPress(.return) { if let id = focusedID, let row = shown.first(where: { $0.id == id }) { open = row }; return .handled }
        .onKeyPress(.space) {
            if let id = focusedID {
                withAnimation(Motion.change) { if selection.contains(id) { selection.remove(id) } else { selection.insert(id); anchor = id } }
            } else if let id = hovered ?? selection.first, let row = shown.first(where: { $0.id == id }) { open = row }
            return .handled
        }
        .onKeyPress(.escape) { withAnimation(Motion.change) { selection = [] }; return .handled }
        .onKeyPress(characters: .init(charactersIn: "1234")) { k in
            guard !selection.isEmpty, let v = Verdict.allCases.first(where: { String($0.key) == k.characters }) else { return .ignored }
            mark(Array(selection), v, announce: true); withAnimation(Motion.change) { selection = [] }
            return .handled
        }
        .background {
            Button("") { undo() }.keyboardShortcut("z", modifiers: .command).disabled(history.isEmpty).hidden()
            Button("") { withAnimation(Motion.change) { selection = Set(shown.map(\.id)) } }.keyboardShortcut("a", modifiers: .command).hidden()
        }
        .overlay(alignment: .bottom) { if !selection.isEmpty { selectionBar.transition(.move(edge: .bottom).combined(with: .opacity)) } }
        .animation(Motion.appear, value: selection.isEmpty)
    }

    /// 방향키 포커스: 좌우 한 칸, 위아래 한 줄(열 수는 그리드 폭으로 센다)
    func moveFocus(_ key: KeyEquivalent) {
        let ids = shown.map(\.id)
        guard !ids.isEmpty else { return }
        let cols = max(1, Int((gridWidth - 24 + 6) / (140 + 6)))
        let i = focusedID.flatMap { ids.firstIndex(of: $0) } ?? -1
        let step = switch key { case .leftArrow: -1; case .rightArrow: 1; case .upArrow: -cols; default: cols }
        let n = i < 0 ? 0 : min(max(i + step, 0), ids.count - 1)
        withAnimation(Motion.hover) { focusedID = ids[n] }
    }

    // 평가가 아직 없을 때: 모델 + 검증 이미지 폴더 → 시작
    var starter: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Check where your model goes wrong").font(.ui(22, weight: .bold))
            Text("Epokio runs your model on images that already have labels and scores each image by how well the two agree. You then look at the worst ones first and mark what went wrong: the model or the label. Works for detection, pose, segmentation and classification models.")
                .foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 12) {
                PickCard(title: "Model", hint: "best.pt", symbol: "cube.box", url: $model,
                         types: [UTType(filenameExtension: "pt")!], folder: false)
                Image(systemName: "arrow.right").foregroundStyle(ink.faint).accessibilityHidden(true)
                PickCard(title: "Images with labels", hint: "validation images", symbol: "photo.on.rectangle",
                         url: $folder, types: [], folder: true)
            }
            Picker("Python", selection: $env) {
                ForEach(envs) { e in Label("\(e.name)  ·  \(e.device)", systemImage: e.ready ? "checkmark.circle.fill" : "exclamationmark.circle").tag(Optional(e)) }
            }
            HStack {
                Spacer()
                if let status { Text(status).font(.ui(11.5)).foregroundStyle(ink.soft) }
                else if !busy, let why: LocalizedStringKey = model == nil ? "Choose a model first" : folder == nil ? "Choose a folder of images first" : env == nil ? "Choose a Python first" : nil {
                    Label(why, systemImage: "info.circle").font(.role(.caption)).foregroundStyle(ink.soft)   // 꺼진 이유를 글로
                }
                Button {
                    Task { await start() }
                } label: {
                    Label(busy ? "Adding…" : "Start Check", systemImage: "sparkle.magnifyingglass").padding(.horizontal, 10).padding(.vertical, 4)
                }
                .primaryButton().controlSize(.large)
                .disabled(model == nil || folder == nil || env == nil || busy)
            }
            ImportPredictionsCard { id in
                Task { await load(); withAnimation(.smooth) { startNew = false; jobID = id } }
            }
        }
        .padding(28).frame(maxWidth: 720, alignment: .leading)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    func load() async {
        if ReviewDemo.enabled { result = ReviewDemo.result(); return }   // 스냅샷용 내장 데모: agent를 부르지 않는다
        struct J: Decodable { let jobs: [Job] }
        struct P: Decodable { let envs: [PyEnv] }
        if let j: J = try? await AgentClient.local.get("jobs") {
            jobs = j.jobs
            if jobID == nil && !startNew { jobID = j.jobs.last(where: { $0.kind == "evaluate" && $0.state == "done" })?.id }
        }
        if let p: P = try? await AgentClient.local.get("pythons") { envs = p.envs; env = p.envs.first(where: \.ready) }
        await loadResult()
    }

    func loadResult() async {
        if ReviewDemo.enabled { return }
        guard let id = jobID else { result = nil; return }
        let first = result == nil
        let r: EvalResult? = try? await AgentClient.local.get("jobs/\(id)/eval", first ? [:] : ["conf": String(conf)])
        withAnimation(.smooth) { result = r }
        if first, let c = r?.conf { conf = c }
        await loadFixed()
        verdicts = [:]
        if let out = jobs.first(where: { $0.id == id })?.output,
           let s = try? String(contentsOf: URL(fileURLWithPath: out).appending(path: "review.csv"), encoding: .utf8) {
            for line in s.split(separator: "\n").dropFirst() {
                let c = line.split(separator: ",", maxSplits: 1).map(String.init)
                if c.count == 2, let v = Verdict(rawValue: c[1]) { verdicts[c[0].replacingOccurrences(of: "\"", with: "")] = v }
            }
        }
    }
}
