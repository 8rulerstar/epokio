import SwiftUI

// 버전 관리 깊이: 계보(어디서 시작했나 · 여기서 시작한 학습) · 데이터에서 바뀐 것 · 모델 단계(후보·배포·보관).
// 계산은 agent(epokio.lineage). 앱은 /run 의 lineage·stage 와 /data-diff · /models/promote 를 쓴다.

enum Stage: String, CaseIterable {
    case none = "", candidate, production, archived
    var title: String {
        switch self { case .none: L("No status"); case .candidate: L("Candidate"); case .production: L("In use"); case .archived: L("Archived") }
    }
    var symbol: String {
        switch self { case .none: "circle.dashed"; case .candidate: "flag"; case .production: "checkmark.seal.fill"; case .archived: "archivebox" }
    }
    var color: Color { switch self { case .none: .gray; case .candidate: .warn; case .production: .good; case .archived: .secondary } }
}

/// 단계 알약 (학습 상세 머리·목록에서)
struct StageBadge: View {
    let stage: Stage
    var body: some View {
        if stage != .none {
            Label(stage.title, systemImage: stage.symbol)
                .font(.ui(11, weight: .semibold)).foregroundStyle(stage.color)
                .padding(.horizontal, 7).padding(.vertical, 2)
                .background(stage.color.opacity(0.14), in: Capsule())
                .transition(.scale.combined(with: .opacity))
        }
    }
}

/// 계보 카드: 시작 가중치 → 조상 → 이 학습, 자식들, 부모와 데이터가 다르면 "바뀐 것 보기"
struct LineageCard: View {
    let run: Run
    let detail: RunDetail
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var diff: DiffKey?

    struct DiffKey: Identifiable { let a: String; let b: String; var id: String { a + b } }

    var body: some View {
        if let lin = detail.lineage {
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle("Where it came from", hint: L("Which weights this run started from, and which runs started from this one."))
                chain(lin)
                if let p = lin.parent, let pd = p.data, let mine = detail.versions?.data {
                    if pd != mine {
                        Button { diff = DiffKey(a: pd, b: mine) } label: {
                            Label(L("Data changed since %@", p.name), systemImage: "arrow.triangle.branch")
                        }
                        .buttonStyle(BrandLink()).font(.ui(12.5, weight: .medium))
                    } else {
                        Label(L("Same data as %@", p.name), systemImage: "equal.circle").font(.ui(12)).foregroundStyle(ink.soft)
                    }
                }
                if !lin.children.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Label(L("%d runs started from this one", lin.children.count), systemImage: "arrow.turn.down.right").font(.ui(12, weight: .medium))
                        ForEach(lin.children.prefix(6), id: \.path) { c in link(c.name, c.path) }
                    }
                }
                Button {
                    var a = detail.args
                    a["weights"] = detail.weights
                    store.pendingTrainArgs = a
                    withAnimation(.snappy) { store.section = .train }
                } label: { Label("Train From This Model", systemImage: "arrow.turn.down.right") }
                .disabled(detail.weights == nil || !store.isLocal(run))
                .help("Start a new training that begins from this run's best.pt (fine-tuning)")
            }
            .sheet(item: $diff) { k in DataDiffSheet(a: k.a, b: k.b).frame(minWidth: 560, minHeight: 480) }
        }
    }

    /// 사전학습 가중치 → 조상 … → 이 학습 (가로 사슬)
    private func chain(_ lin: RunDetail.Lineage) -> some View {
        let steps: [(String, String?)] = lin.ancestors.reversed().map { ($0.name, $0.path) }
        let root = lin.weights.flatMap { w in lin.pretrained ? URL(fileURLWithPath: w).lastPathComponent : nil }
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                if let root { node(root, symbol: "shippingbox", path: nil) ; arrow }
                ForEach(Array(steps.enumerated()), id: \.offset) { _, s in node(s.0, symbol: "chart.xyaxis.line", path: s.1); arrow }
                node(run.displayName, symbol: "star.circle.fill", path: nil, me: true)
            }
            .padding(.vertical, 2)
        }
    }

    private var arrow: some View { Image(systemName: "chevron.right").font(.ui(10, weight: .bold)).foregroundStyle(ink.faint) }

    private func node(_ name: String, symbol: String, path: String?, me: Bool = false) -> some View {
        Button { if let path { store.selectedRun = "\(run.source)|\(path)" } } label: {
            Label(name, systemImage: symbol).font(.ui(12, weight: me ? .semibold : .regular)).lineLimit(1)
                .padding(.horizontal, 9).padding(.vertical, 4)
                .background(me ? AnyShapeStyle(.tint.opacity(0.18)) : AnyShapeStyle(.quaternary.opacity(0.6)), in: Capsule())
        }
        .buttonStyle(PressStyle()).disabled(path == nil)
        .help(path ?? name)
    }

    private func link(_ name: String, _ path: String) -> some View {
        Button { store.selectedRun = "\(run.source)|\(path)" } label: {
            Text(verbatim: URL(fileURLWithPath: path).deletingLastPathComponent().lastPathComponent + "/" + name).font(.ui(12)).lineLimit(1)
        }
        .buttonStyle(BrandLink())
    }
}

/// 두 데이터 버전 사이에 더해진·빠진·바뀐 파일
struct DataDiffSheet: View {
    let a: String
    let b: String
    @Environment(\.dismiss) private var dismiss
    @Environment(\.ink) private var ink
    @State private var d: Diff?
    @State private var error: String?
    @State private var tab = 0

    struct Diff: Decodable {
        let images: Counts
        let labels: Counts
        let boxes: [Box]
        let added: [String]; let removed: [String]; let changed: [String]
        let truncated: Bool
        struct Counts: Decodable { let added: Int; let removed: Int; let changed: Int; var before: Int?; var after: Int? }
        struct Box: Decodable, Hashable { let cls: String; let before: Int; let after: Int }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("What changed in the data", systemImage: "arrow.triangle.branch").font(.ui(17, weight: .bold))
                Spacer()
                Text(verbatim: "\(a) → \(b)").font(.ui(11.5, design: .monospaced)).foregroundStyle(ink.soft)
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            if let d {
                HStack(spacing: 10) {
                    tile(L("Images added"), d.images.added, .good, "plus.circle.fill")
                    tile(L("Images removed"), d.images.removed, .bad, "minus.circle.fill")
                    tile(L("Labels changed"), d.labels.changed + d.labels.added, .warn, "pencil.circle.fill")
                }
                if !d.boxes.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Boxes per class").font(.ui(12, weight: .semibold))
                        ForEach(d.boxes, id: \.self) { x in
                            HStack {
                                Text(verbatim: x.cls).font(.ui(12, design: .monospaced)).frame(width: 60, alignment: .leading)
                                Text(verbatim: "\(x.before) → \(x.after)").font(.ui(12, design: .rounded))
                                let delta = x.after - x.before
                                if delta != 0 {
                                    Text(verbatim: delta > 0 ? "+\(delta)" : "\(delta)").font(.ui(11.5, weight: .bold)).foregroundStyle(delta > 0 ? .good : .bad)
                                }
                            }
                        }
                    }
                }
                Picker("", selection: $tab) {
                    Text(L("Added %d", d.added.count)).tag(0); Text(L("Removed %d", d.removed.count)).tag(1); Text(L("Changed %d", d.changed.count)).tag(2)
                }
                .pickerStyle(.segmented).labelsHidden()
                List([d.added, d.removed, d.changed][tab], id: \.self) { Text(verbatim: $0).font(.ui(12, design: .monospaced)).textSelection(.enabled) }
                    .listStyle(.bordered)
                    .animation(.smooth, value: tab)
                Text(d.truncated ? L("Showing the first 300 of each. The list was recorded when Epokio first saw each data version.")
                                 : L("The list was recorded when Epokio first saw each data version."))
                    .font(.ui(11)).foregroundStyle(ink.soft)
            } else if let error {
                ContentUnavailableView("Can't compare", systemImage: "exclamationmark.triangle", description: Text(error))
            } else {
                ProgressView().frame(maxWidth: .infinity)
            }
        }
        .padding(18)
        .task {
            do { let r: Diff = try await AgentClient.local.get("data-diff", ["a": a, "b": b]); withAnimation(.smooth) { d = r } }
            catch { self.error = error.localizedDescription }
        }
    }

    private func tile(_ t: String, _ n: Int, _ c: Color, _ sym: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Image(systemName: sym).foregroundStyle(c).accessibilityHidden(true)
            Text(verbatim: "\(n)").font(.ui(20, weight: .bold, design: .rounded)).contentTransition(.numericText())
            Text(verbatim: t).font(.ui(11)).foregroundStyle(ink.soft)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10).background(c.opacity(0.08), in: .rect(cornerRadius: 10))
        .accessibilityElement(children: .combine)
    }
}

/// 버튼 레일의 "상태" 메뉴(옛 이름 Stage). "사용 중"으로 올리면 best.pt를 모델 등록부에 새 버전으로 복사한다
struct StageMenu: View {
    let run: Run
    let detail: RunDetail?
    @Binding var stage: Stage
    @Environment(Store.self) private var store

    var body: some View {
        Menu {
            ForEach([Stage.candidate, .archived, .none], id: \.self) { s in
                Button { set(s) } label: { Label(s.title, systemImage: s.symbol) }
            }
            Divider()
            Button { Task { await promote() } } label: { Label("Put In Use (Copy to Model Registry)", systemImage: Stage.production.symbol) }
                .disabled(detail?.weights == nil)
            Button { NSWorkspace.shared.open(FileManager.default.homeDirectoryForCurrentUser.appending(path: ".epokio/models")) } label: {
                Label("Open Model Registry", systemImage: "folder")
            }
        } label: { RailLabel(symbol: stage.symbol, title: stage == .none ? L("Status") : stage.title, enabled: store.isLocal(run)) }
            .menuStyle(.button).buttonStyle(.plain).menuIndicator(.hidden).fixedSize()
            .disabled(!store.isLocal(run))
            .help(L("Mark this model as a candidate, in use or archived"))
    }

    private func set(_ s: Stage) {
        let old = stage
        withAnimation(.bouncy) { stage = s }
        Task { await saveMeta(run, store, ["stage": s.rawValue], done: s == .none ? L("Status cleared") : L("Marked as %@", s.title), undo: ["stage": old.rawValue]) }
    }

    private func promote() async {
        await store.act {
            let r = try await store.client(for: run).post("models/promote", ["path": run.path])
            withAnimation(Motion.celebrate) { stage = .production }; Haptic.success()
            store.say(L("Copied to the model registry as %@ v%d", r["name"] as? String ?? "", r["version"] as? Int ?? 0))
        }
    }
}
