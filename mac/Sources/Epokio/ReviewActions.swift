import SwiftUI
import UniformTypeIdentifiers

// 검수 화면의 동작: 판정 저장 · 고친 라벨 목록 · 일괄 표시 · 재학습 세트 · CSV · 새 평가 시작. 저장은 전부 agent를 거친다.

extension ReviewView {
    /// 판정을 바꾸는 곳은 전부 여기로: 되돌리기 기록 · 저장 · 진동. announce면 "되돌리기" 달린 알림
    func mark(_ ids: [String], _ v: Verdict?, announce: Bool = false) {
        guard !ids.isEmpty else { return }
        history.append(Dictionary(uniqueKeysWithValues: ids.map { ($0, verdicts[$0]) }))
        if history.count > 50 { history.removeFirst() }
        withAnimation(Motion.change) { for id in ids { verdicts[id] = v } }
        save(); Haptic.tick()
        if v != nil { Trophies.shared.bump("verdict", ids.filter { (history.last?[$0] ?? nil) == nil }.count) }     // 새로 판정한 장만 센다
        Trophies.shared.evaluate(store)
        if announce {
            store.say(v == nil ? L("Cleared %d marks", ids.count) : L("Marked %d images", ids.count), actionTitle: L("Undo")) { undo() }
        }
    }

    /// ⌘Z: 마지막으로 바꾼 판정을 되돌린다(한 번에 여러 장 바꾼 것도 한 단계)
    func undo() {
        guard let last = history.popLast() else { return }
        withAnimation(Motion.change) { for (k, v) in last { verdicts[k] = v } }
        save()
        store.say(L("Undone: %d images", last.count))
    }

    /// 누르기: 그냥 = 크게 보기(고른 게 있으면 고르기), ⌘ = 하나 더 고르기, ⇧ = 범위로 고르기 (사진 앱과 같다)
    func tap(_ row: EvalRow) {
        let f = NSEvent.modifierFlags
        withAnimation(Motion.hover) {
            if f.contains(.shift), let a = anchor, let i = shown.firstIndex(where: { $0.id == a }), let j = shown.firstIndex(of: row) {
                for r in shown[min(i, j)...max(i, j)] { selection.insert(r.id) }
            } else if f.contains(.command) || !selection.isEmpty {
                if selection.contains(row.id) { selection.remove(row.id) } else { selection.insert(row.id) }
                anchor = row.id
            } else {
                open = row
                anchor = row.id
            }
        }
    }

    /// 여러 장 골랐을 때 아래에 뜨는 막대
    var selectionBar: some View {
        HStack(spacing: 10) {
            Text(L("%d selected", selection.count)).font(.role(.body, weight: .semibold)).contentTransition(.numericText())
            Divider().frame(height: 18)
            ForEach(Verdict.allCases, id: \.self) { v in
                Button { mark(Array(selection), v, announce: true); withAnimation(Motion.change) { selection = [] } } label: {
                    Label(v.title, systemImage: v.symbol)
                }
                .tint(v.color).help(L("Press %@", String(v.key)))
            }
            Button { withAnimation(Motion.change) { selection = [] } } label: { Image(systemName: "xmark.circle.fill") }
                .buttonStyle(.borderless).help("Clear selection (Esc)")
                .accessibilityLabel("Clear selection")
        }
        .controlSize(.small)
        .padding(.horizontal, 14).padding(.vertical, 9)
        .glass(Capsule(), interactive: true)
        .padding(.bottom, 16)
    }
    /// 검수 결과는 평가 폴더의 review.csv 에 바로 남는다 (재학습·라벨 수정 때 쓴다)
    func save() {
        guard let id = jobID else { return }
        let body = verdicts.mapValues(\.rawValue)
        Task { await store.act { _ = try await AgentClient.local.post("review/verdicts", ["job": id, "verdicts": body]) } }
    }

    func stem(_ image: String) -> String { let n = URL(fileURLWithPath: image).lastPathComponent; return String(n[..<(n.lastIndex(of: ".") ?? n.endIndex)]) }

    func loadFixed() async {
        guard let id = jobID, let d = try? await AgentClient.local.post("review/fixed", ["job": id]),
              let f = d["fixed"] as? [String: Any] else { fixed = []; return }
        fixed = Set(f.keys)
    }

    /// 보이는 이미지 전부에 같은 판정
    var batchMenu: some View {
        Menu {
            ForEach(Verdict.allCases, id: \.self) { v in
                Button { mark(shown.map(\.id), v, announce: true) } label: {
                    Label(v.title, systemImage: v.symbol)
                }
            }
            Divider()
            Button(role: .destructive) { mark(shown.map(\.id), nil, announce: true) } label: {
                Label("Clear Marks", systemImage: "eraser")
            }
        } label: { Label(L("Mark %d Shown", shown.count), systemImage: "checklist").labelStyle(.iconOnly) }
        .fixedSize()
        .help("Give every image on screen the same mark")
    }

    /// 고른 판정 + 고친 라벨로 재학습 세트를 만들고 학습 화면으로
    func buildRetrain() async {
        guard let id = jobID else { return }
        building = true
        defer { building = false }
        await store.act {
            let d = try await AgentClient.local.post("review/retrain", ["job": id, "want": ["model_wrong", "label_wrong", "unsure"], "repeat": 2])
            guard let yaml = d["data"] as? String else { return }
            let n = d["images"] as? Int ?? 0
            let moved = d["moved_from_val"] as? Int ?? 0
            if let w = d["warning"] as? String, !w.isEmpty {
                store.say(L("Made a set of %d images. Check before training: %@", n, w), bad: true)
            } else if moved > 0 {
                store.say(L("Made a retrain set with %d images. %d came from validation, so they were moved out of it to keep the score honest.", n, moved))
            } else {
                store.say(L("Made a retrain set: %d images added to the original training data.", n))
            }
            store.pendingTrainArgs = ["data": yaml]
            withAnimation(.snappy) { store.section = .train }
        }
    }

    /// 점수와 판정을 CSV로 저장한다(라벨 고치기·재학습 목록으로 쓴다)
    func exportCSV() {
        guard let r = result else { return }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "epokio-review.csv"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        var csv = "image,score,correct,extra,missed,verdict\n"
        for row in r.rows {
            csv += "\"\(row.image)\",\(String(format: "%.4f", row.score)),\(row.tp),\(row.fp),\(row.fn),\(verdicts[row.id]?.rawValue ?? "")\n"
        }
        writeExport(csv, to: url, store)
    }

    func start() async {
        guard let model, let folder, let env, !busy else { return }
        withAnimation(Motion.change) { busy = true }
        defer { withAnimation(Motion.change) { busy = false } }
        do {
            try await AgentClient.local.post("jobs", ["kind": "evaluate", "name": "eval_" + folder.lastPathComponent,
                                                      "python": env.path, "params": ["model": model.path, "source": folder.path, "conf": 0.25]])
            status = String(localized: "Added to queue. Results appear here when it finishes.")
        } catch { status = error.localizedDescription }
    }
}

/// 다른 프레임워크의 모델: 이미지별 정답·예측을 JSONL로 내보내면 여기서 연다(agent /review/import)
struct ImportPredictionsCard: View {
    let onImported: (String) -> Void
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var showFormat = false
    @State private var busy = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "square.and.arrow.down.on.square").font(.ui(20)).foregroundStyle(.tint)
                .symbolEffect(.bounce, value: busy)
            VStack(alignment: .leading, spacing: 4) {
                Text("Using another framework?").font(.ui(13.5, weight: .semibold))
                Text("Export your model's answers as a JSONL file (one image per line) and open it here. Hugging Face, PyTorch, Keras and anything else work the same way.")
                    .font(.ui(12)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 10) {
                    Button { Task { await pick() } } label: { Label("Open Predictions File…", systemImage: "doc.badge.plus") }
                        .disabled(busy)
                    Button("File Format") { showFormat.toggle() }.buttonStyle(BrandLink())
                        .popover(isPresented: $showFormat, arrowEdge: .bottom) { format.padding(14).frame(width: 520) }
                }
                .padding(.top, 2)
            }
        }
        .padding(14)
        .background(.quaternary.opacity(0.35), in: .rect(cornerRadius: 12))
    }

    private var format: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("One JSON object per line").font(.ui(13, weight: .semibold))
            Text(verbatim: #"{"names": {"0": "cat", "1": "dog"}}                     (optional first line)"#)
            Text("Detection (boxes are 0 to 1: center x, center y, width, height)").font(.ui(12, weight: .medium))
            Text(verbatim: #"{"image": "/data/a.jpg", "gt": [{"cls": 0, "box": [0.5, 0.5, 0.2, 0.3]}], "pred": [{"cls": 0, "box": [0.51, 0.5, 0.2, 0.3], "conf": 0.91}]}"#)
            Text("Classification (class number or name)").font(.ui(12, weight: .medium))
            Text(verbatim: #"{"image": "/data/b.jpg", "label": "cat", "probs": [0.87, 0.13]}"#)
            Text(verbatim: #"{"image": "/data/c.jpg", "label": 1, "pred": 0, "conf": 0.6}"#)
        }
        .font(.ui(11.5, design: .monospaced)).textSelection(.enabled)
    }

    private func pick() async {
        let p = NSOpenPanel(); p.allowedContentTypes = [.json, .text, .data]; p.allowsMultipleSelection = false
        guard p.runModal() == .OK, let u = p.url else { return }
        busy = true
        defer { busy = false }
        await store.act {
            let r = try await AgentClient.local.post("review/import", ["path": u.path])
            store.say(L("Opened %d images from %@", r["images"] as? Int ?? 0, u.lastPathComponent))
            if let id = r["id"] as? String { onImported(id) }
        }
    }
}
