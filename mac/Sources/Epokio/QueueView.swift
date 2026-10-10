import SwiftUI

// 대기열. 한 번에 하나씩 돈다 (GPU 하나 기준). 순서 바꾸기·취소·로그 보기.
struct QueueView: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var jobs: [Job] = []
    @State private var loadError: String?               // 대기열을 못 받은 이유(agent 꺼짐·토큰)
    @State private var selected: String?
    @State private var cancelling: Job?
    @State private var log = ""
    @State private var summary: AutoLabelSummary?
    @State private var sweeps: [SweepSummary] = []
    @State private var confirmStop = false
    @State private var hints: [Hint] = []               // 실패한 작업의 원인과 고칠 방법(agent diagnose)
    @State private var hintsFor: String?                 // 어느 작업의 것인지(한 번만 묻는다)

    var body: some View {
        HSplitView {
            List(selection: $selected) {
                LaunchOffCard()                                // pip 도우미(작업 시작 끔)를 쓰고 있으면 켜는 버튼(LaunchGate)
                // ★못 받아도 '대기열이 비었음'을 보여, agent가 꺼졌거나 토큰이 틀린 것을 알 수 없었다
                if let loadError {
                    Label(loadError, systemImage: "exclamationmark.triangle").font(.ui(12)).foregroundStyle(.warn)
                } else if jobs.isEmpty {
                    ContentUnavailableView("Queue is empty", systemImage: "list.number",
                                           description: Text("Start a training or an auto-label run."))
                }
                if !sweeps.isEmpty {
                    Section("Sweeps") {
                        ForEach(sweeps) { sw in SweepRow(s: sw).tag("sweep:" + sw.id) }
                    }
                }
                // 음악 앱 "다음 재생"처럼: 기다리는 작업은 끌어서 순서를 바꾼다
                let waiting = jobs.filter { $0.state == "queued" }
                if !waiting.isEmpty {
                    Section(L("Up next · drag to reorder")) {
                        ForEach(waiting) { j in JobRow(job: j).tag(j.id) }
                            .onMove { from, to in
                                var ids = waiting.map(\.id); ids.move(fromOffsets: from, toOffset: to)
                                withAnimation(Motion.change) {                       // 먼저 화면에서 옮기고(바로 반응) agent에 저장
                                    let rest = jobs.filter { $0.state != "queued" }
                                    jobs = rest + ids.compactMap { id in waiting.first { $0.id == id } }
                                }
                                Haptic.tick()
                                Task { await store.act { _ = try await AgentClient.local.post("jobs/reorder", ["ids": ids]) }; await refresh() }
                            }
                    }
                }
                Section(sweeps.isEmpty && waiting.isEmpty ? "" : L("Jobs")) {
                    ForEach(jobs.filter { $0.state != "queued" }.reversed()) { j in JobRow(job: j, run: liveRun(j)).tag(j.id) }
                }
            }
            .frame(minWidth: 320)
            .scrollContentBackground(.hidden)      // 다크에서 목록만 더 어두워 오른쪽과 톤이 갈리던 것
            .onKeyPress(keys: [.upArrow, .downArrow], phases: .down) { k in       // ⌥↑↓: 기다리는 작업 순서 옮기기
                guard k.modifiers.contains(.option), let id = selected, jobs.first(where: { $0.id == id })?.state == "queued" else { return .ignored }
                Task { await store.act { _ = try await AgentClient.local.post("jobs/\(id)/\(k.key == .upArrow ? "up" : "down")") }; Haptic.tick(); await refresh() }
                return .handled
            }
            .onKeyPress(.delete) {
                guard let id = selected, let j = jobs.first(where: { $0.id == id }), ["queued", "running"].contains(j.state) else { return .ignored }
                cancelling = j; return .handled
            }
            .confirmationDialog(L("Cancel %@?", cancelling?.name ?? ""), isPresented: Binding(get: { cancelling != nil }, set: { if !$0 { cancelling = nil } })) {
                Button("Cancel Job", role: .destructive) {
                    if let j = cancelling { Task { await store.act(L("Cancelled")) { try await AgentClient.local.post("jobs/\(j.id)/cancel") }; await refresh() } }
                }
                Button("Keep", role: .cancel) {}
            }
            .safeAreaInset(edge: .bottom) {
                HStack {
                    Spacer()
                    Button { Task { await clear() } } label: { Label("Clear Finished", systemImage: "trash.slash") }
                        .buttonStyle(.borderless).font(.role(.callout))
                        .disabled(!jobs.contains { !["queued", "running"].contains($0.state) })
                        .help("Remove finished jobs from this list. Result folders stay, and finished checks and auto-labels are kept so you can reopen them.")
                }
                .padding(8).glass(Rectangle())
            }
            detail.frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)      // ★없으면 창 아래에 붙고 위가 텅 빈다
        .task { await refresh() }
        .task { await poll() }
        .onChange(of: selected) { Task { await refresh() } }
    }

    @ViewBuilder private var detail: some View {
        if let sel = selected, sel.hasPrefix("sweep:") {
            SweepDetail(id: String(sel.dropFirst(6)))
        } else if let j = jobs.first(where: { $0.id == selected }) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top) {
                    let row = JobRow(job: j)
                    Image(systemName: row.symbol).font(.role(.headline)).foregroundStyle(row.tint)
                        .frame(width: 34, height: 34).background(row.tint.opacity(0.14), in: .rect(cornerRadius: Radius.control))
                        .symbolEffect(.bounce, value: j.id)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(j.name).font(.role(.title)).lineLimit(1).truncationMode(.middle)
                        Text(verbatim: j.kindTitle + "  ·  " + j.when).font(.role(.caption)).foregroundStyle(ink.soft)
                    }
                    Spacer()
                    if j.state == "queued" {
                        IconButton(symbol: "arrow.up", help: "Move up") { Task { await store.act { try await AgentClient.local.post("jobs/\(j.id)/up") }; Haptic.tick(); await refresh() } }
                        IconButton(symbol: "arrow.down", help: "Move down") { Task { await store.act { try await AgentClient.local.post("jobs/\(j.id)/down") }; Haptic.tick(); await refresh() } }
                    }
                    if j.state == "queued" {
                        Button("Cancel", role: .destructive) { Task { await store.act(L("Cancelled")) { try await AgentClient.local.post("jobs/\(j.id)/cancel") }; await refresh() } }
                    } else if j.state == "running" {
                        // ★도는 학습은 확인을 거친다(학습 상세·팝오버와 같은 규칙). 예전엔 누르면 바로 멈췄다
                        Button("Stop", role: .destructive) { confirmStop = true }
                            .confirmationDialog(L("Stop \"%@\"?", j.name), isPresented: $confirmStop) {
                                Button("Stop", role: .destructive) {
                                    Task { await store.act(L("Stopped")) { try await AgentClient.local.post("jobs/\(j.id)/cancel") }; await refresh() }
                                }
                            } message: { Text("The run keeps what it saved so far (last.pt, results.csv).") }
                    }
                    if !j.output.isEmpty {
                        IconButton(symbol: "folder", help: "Show output") { NSWorkspace.shared.open(URL(fileURLWithPath: j.output)) }
                    }
                    IconButton(symbol: "square.and.arrow.down", help: "Save Log…") { Task { await saveLog(j, store) } }
                }
                if let s = summary, s.images != nil, j.kind == "autolabel" { SummaryCard(s: s) }   // 끝나기 전엔 {"ready": false}라 0만 보였다
                if j.kind == "evaluate" && j.state == "done" {
                    Button {
                        store.pendingReviewJob = j.id
                        withAnimation(Motion.change) { store.section = .review }
                    } label: { Label("Open in Review", systemImage: "checkmark.rectangle.stack") }
                    .buttonStyle(.borderedProminent)
                }
                if j.imported {
                    Label("Imported from a predictions file. Nothing ran, so there is no log.", systemImage: "square.and.arrow.down.on.square")
                        .font(.role(.callout)).foregroundStyle(ink.soft)
                } else {
                Text("Log").font(.ui(12, weight: .semibold)).foregroundStyle(ink.soft)
                ScrollViewReader { proxy in
                    ScrollView {
                        Text(log.isEmpty ? L("Waiting for output…") : log)
                            .font(.ui(11, design: .monospaced))
                            .frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
                            .id("end")
                    }
                    .padding(10).background(.quaternary.opacity(0.4), in: .rect(cornerRadius: 10))
                    .onChange(of: log) { withAnimation { proxy.scrollTo("end", anchor: .bottom) } }
                }
                }
                if j.state == "failed" && hintsFor == j.id {
                    ForEach(hints, id: \.self) { h in HintRow(hint: h) }
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)   // ★가운데 떠 있었다: 위에 붙인다
            .id(j.id).transition(.opacity)
        } else {
            ContentUnavailableView("Select a job", systemImage: "sidebar.left")
        }
    }

    private func clear() async {
        await store.act {
            let r = try await AgentClient.local.post("jobs/clear")
            store.say(L("Removed %d finished jobs", r["removed"] as? Int ?? 0))
        }
        await refresh()
    }

    /// 2초 새로고침. Studio 창이 가려지거나 최소화되면 건너뛰고(다시 보이면 바로), 도는 것이 없으면 10초마다만
    private func poll() async {
        var last = Date.distantPast
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(2))
            guard studioVisible else { last = .distantPast; continue }
            let busy = jobs.contains { ["queued", "running"].contains($0.state) } || sweeps.contains { $0.done < $0.total }
            if busy || Date().timeIntervalSince(last) >= 10 { last = Date(); await refresh() }
        }
    }

    private var studioVisible: Bool {
        guard let w = NSApp.windows.first(where: { $0.identifier?.rawValue.hasPrefix("studio") ?? false || $0.title == "Epokio Studio" }) else { return true }
        return w.occlusionState.contains(.visible) && !w.isMiniaturized
    }

    private func refresh() async {
        struct R: Decodable { let jobs: [Job] }
        struct SW: Decodable { let sweeps: [SweepSummary] }
        if let w: SW = try? await AgentClient.local.get("sweeps") { withAnimation(.smooth) { sweeps = w.sweeps } }
        let got: R?
        do { got = try await AgentClient.local.get("jobs"); loadError = nil }
        catch { got = nil; loadError = (error as? AgentError ?? AgentError.bad).localizedDescription }
        if let r = got {
            withAnimation(.smooth) { jobs = r.jobs }
            // 처음 열면 도는 작업, 없으면 가장 최근 작업을 고른다(빈 화면으로 두지 않는다)
            if selected == nil || (!(selected?.hasPrefix("sweep:") ?? false) && !r.jobs.contains(where: { $0.id == selected })) {
                selected = (r.jobs.first { $0.state == "running" } ?? r.jobs.last)?.id
            }
        }
        if let id = selected {
            struct L: Decodable { let log: String }
            if let l: L = try? await AgentClient.local.get("jobs/\(id)/log", ["lines": "300"]) { log = l.log }
            summary = try? await AgentClient.local.get("jobs/\(id)/summary")
            // 실패한 작업은 로그 끝에서 원인·고칠 방법을 찾는다. 끝난 작업이라 바뀌지 않으니 한 번만
            if hintsFor != id, jobs.first(where: { $0.id == id })?.state == "failed" {
                struct D: Decodable { let hints: [Hint] }
                let d: D? = try? await AgentClient.local.get("jobs/\(id)/diagnose")
                withAnimation(.smooth) { hints = d?.hints ?? []; hintsFor = id }
            }
        }
    }

    /// 도는 학습의 진행은 감시기가 이미 안다(학습 기록과 같은 값). 작업 출력 폴더로 짝을 찾는다
    private func liveRun(_ j: Job) -> Run? {
        guard j.state == "running", !j.output.isEmpty else { return nil }
        func norm(_ p: String) -> String {
            var s = p.replacingOccurrences(of: "\\", with: "/").lowercased()
            while s.count > 1 && s.hasSuffix("/") { s.removeLast() }
            return s.precomposedStringWithCanonicalMapping          // 맥 NFD 폴더 이름과 NFC 문자열
        }
        let out = norm(j.output)
        // 도는 학습과만 짝짓는다(★이름이 겹치면 끝난 옛 학습이 잡혀 50/50이 보였다)
        return store.runs.first { store.isLocal($0) && ($0.isLive || $0.state == "stalled") && norm($0.path) == out }     // 이 대기열은 이 Mac 것
    }
}

/// 실패 원인 하나: 제목과 고칠 방법 (agent가 앱 언어로 보낸다)
struct Hint: Decodable, Hashable { let title: String; let fix: String }

struct HintRow: View {
    let hint: Hint
    @State private var hover = false
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: "stethoscope").foregroundStyle(.bad).font(.ui(12, weight: .semibold))
            VStack(alignment: .leading, spacing: 3) {
                Text(verbatim: hint.title).font(.ui(12, weight: .semibold))
                Text(verbatim: hint.fix).font(.ui(12)).fixedSize(horizontal: false, vertical: true)
            }
            .textSelection(.enabled)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.bad.opacity(hover ? 0.11 : 0.07), in: .rect(cornerRadius: 10))
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .transition(.opacity.combined(with: .move(edge: .top)))
    }
}

struct JobRow: View {
    @Environment(\.ink) private var ink
    let job: Job
    var run: Run? = nil                          // 도는 학습이면 그 학습(에폭·남은 시간)
    /// "에폭 3/50 · 약 20분 남음, 14:05쯤 끝남". 시각은 24시간(웹과 같다)
    var progress: String? {
        guard let r = run, let t = r.total, t > 0 else { return nil }
        let head = r.progressText
        guard let eta = r.eta, eta > 0 else { return head }
        let f = DateFormatter(); f.dateFormat = "HH:mm"
        return head + " · " + L("about %@ left, done around %@", duration(eta), f.string(from: Date().addingTimeInterval(eta)))
    }
    var tint: Color {
        switch job.state {
        case "running": .good; case "queued": .secondary; case "done": .brand
        case "failed": .bad; default: .gray
        }
    }
    var symbol: String {
        switch job.kind {
        case "train": "brain"; case "autolabel": "wand.and.stars"; case "evaluate": "checkmark.rectangle.stack"
        case "export": "shippingbox"; case "setup": "arrow.down.circle"; case "practice": "sparkles.tv"; default: "terminal"
        }
    }
    var stateSymbol: String {
        switch job.state {
        case "queued": "clock"; case "done": "checkmark.circle.fill"; case "failed": "xmark.circle.fill"
        case "cancelled": "minus.circle"; default: "circle"
        }
    }
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: symbol).foregroundStyle(tint).frame(width: 22)
                .symbolEffect(.pulse, isActive: job.state == "running")
            VStack(alignment: .leading, spacing: 2) {
                Text(job.name).font(.role(.body, weight: .semibold)).lineLimit(1)
                HStack(spacing: 4) {
                    Text(verbatim: job.kindTitle + "  ·  " + job.when)
                    if let rc = job.returncode, rc != 0 { Text(verbatim: "·  " + L("exit %d", rc)).foregroundStyle(.bad) }
                }
                .font(.role(.caption)).foregroundStyle(ink.soft).lineLimit(1)
                if let p = progress {                    // 도는 학습: 에폭·남은 시간
                    Text(verbatim: p).font(.role(.caption)).foregroundStyle(ink.soft).lineLimit(1)
                        .contentTransition(.numericText())
                        .animation(.smooth, value: p)
                }
            }
            Spacer()
            if job.state == "running" { ProgressView().controlSize(.small) }
            else {
                Image(systemName: stateSymbol).foregroundStyle(tint)
                    .contentTransition(.symbolEffect(.replace))
                    .help(jobStateName(job.state))
                    .accessibilityLabel(jobStateName(job.state))
            }
        }
        .padding(.vertical, 3)
    }
}

struct SummaryCard: View {
    @Environment(\.ink) private var ink
    let s: AutoLabelSummary
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 18) {
                stat("\(s.images ?? 0)", "images", "photo")
                stat("\(s.per_class?.values.reduce(0, +) ?? 0)", "boxes", "rectangle.dashed")
                stat("\(s.low?.count ?? 0)", "to review", "exclamationmark.circle")
                stat("\(s.empty?.count ?? 0)", "empty", "circle.dashed")
            }
            if let pc = s.per_class, !pc.isEmpty {
                Text(pc.sorted { $0.value > $1.value }.map { "\($0.key) \($0.value)" }.joined(separator: "  ·  "))
                    .font(.ui(11.5)).foregroundStyle(ink.soft)
            }
        }
        .padding(14).background(.quaternary.opacity(0.4), in: .rect(cornerRadius: 12))
    }
    private func stat(_ v: String, _ l: LocalizedStringKey, _ sym: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Label(v, systemImage: sym).font(.ui(16, weight: .bold, design: .rounded))
            Text(l).font(.ui(11.5)).foregroundStyle(ink.soft)
        }
        .accessibilityElement(children: .combine)
    }
}


/// 작업 로그 전체를 파일로 저장한다(앞부분 잘림 없이)
@MainActor func saveLog(_ j: Job, _ store: Store) async {
    struct Log: Decodable { let log: String }
    guard let l: Log = try? await AgentClient.local.get("jobs/\(j.id)/logfile") else { store.say(L("Couldn't read the log."), bad: true); return }
    let p = NSSavePanel()
    p.nameFieldStringValue = "\(j.name)-\(j.id).log"
    guard p.runModal() == .OK, let url = p.url else { return }
    let head = "# Epokio job log\n# name: \(j.name)\n# kind: \(j.kind)\n# state: \(j.state)\n# output: \(j.output)\n\n"
    do {
        try (head + l.log).write(to: url, atomically: true, encoding: .utf8)
        Haptic.success(); store.say(L("Saved %@", url.lastPathComponent))
        NSWorkspace.shared.activateFileViewerSelecting([url])
    } catch { store.say(error.localizedDescription, bad: true) }
}

func jobStateName(_ s: String) -> String {
    switch s {
    case "queued": L("Queued"); case "running": L("Running"); case "done": L("Done")
    case "failed": L("Failed"); case "cancelled": L("Cancelled"); default: s
    }
}
