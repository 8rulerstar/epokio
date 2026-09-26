import SwiftUI

// 학습 상세의 다음 할 일: 오른쪽 버튼 레일, 내보내기, 최고 대비 표시.

extension RunDetailView {
    /// 같은 프로젝트의 다른 학습과 비교: "지금까지 최고" 또는 "▼0.034 · 최고: 이름"
    @ViewBuilder func rankBadge(_ b: Double) -> some View {
        // ★점수 이름만 같다고 비교하면 다른 데이터셋·다른 작업(검출 vs 자세)끼리 비교됐다.
        //   같은 기계, 같은 부모 폴더(같은 프로젝트의 runs)에 있는 학습끼리만 비교한다
        let parent = URL(fileURLWithPath: run.path).deletingLastPathComponent().path
        let others = store.runs.filter {
            $0.id != run.id && $0.source == run.source && $0.metric_name == run.metric_name && $0.best != nil
                && URL(fileURLWithPath: $0.path).deletingLastPathComponent().path == parent
        }
        // ★낮을수록 좋은 지표(loss·rmse)에서는 최고를 거꾸로 골라 제일 나쁜 학습을 "최고"라고 했다
        // 사람이 대표 점수를 골랐으면(lower) 그 방향이 먼저, 아니면 agent가 준 지표 방향
        let higher = run.lower.map { !$0 } ?? run.metricHigher
        if let top = others.max(by: { x, y in higher ? (x.best ?? 0) < (y.best ?? 0) : (y.best ?? 0) < (x.best ?? 0) }),
           let tb = top.best {
            let d = b - tb
            Group {
                if higher ? d >= 0 : d <= 0 {
                    Label(L("Best of %d runs", others.count + 1), systemImage: "crown.fill")
                        .foregroundStyle(.gold)
                } else {
                    HStack(spacing: 6) {
                        // 못 미친 쪽 화살표는 지표 방향을 따른다(낮을수록 좋으면 값이 높은 것이 나쁨)
                        Text(verbatim: String(format: higher ? "▼%.3f" : "▲%.3f", abs(d)) + "  ·  " + L("best: %@", top.displayName))
                            .foregroundStyle(ink.soft)
                            .onTapGesture { store.selectedRun = top.id }
                            .help("Show the best run")
                        Button { store.pendingCompare = [run.id, top.id] } label: { Image(systemName: "square.stack.3d.up") }
                            .buttonStyle(.plain).foregroundStyle(.tint).help("Compare with the best run")
                            .accessibilityLabel("Compare with the best run")
                    }
                }
            }
            .font(.ui(11.5, weight: .medium)).lineLimit(1)
            .transition(.opacity)
        }
    }

    /// 모델 내보내기: 대기열 작업으로 돌린다(수 분 걸릴 수 있다). 결과는 weights 폴더에 생긴다
    func exportModel(_ o: ExportOptions) async {
        struct P: Decodable { let envs: [PyEnv] }
        guard let w = detail?.weights, let p: P = try? await AgentClient.local.get("pythons"),
              let env = p.envs.first(where: \.ready) else { store.say(L("No Python with ultralytics found. Set one up in Train."), bad: true); return }
        await store.act(L("Added to queue")) { try await AgentClient.local.post("jobs", ["kind": "export", "name": "export_\(o.format)_" + run.name,
                                                       "python": env.path, "params": o.params.merging(["model": w]) { a, _ in a }]) }
    }

    /// 이 학습만 담은 보고서(성적·해설·그래프·설정)를 만들어 Finder에서 보여 준다
    func exportReport() async {
        // 보고서는 학습한 기계가 그 기계의 폴더에 쓴다. ★원격 학습이면 맥에서 고른 폴더가 그 기계에 없어 조용히 아무 일도 없었다
        guard store.isLocal(run) else {
            store.say(L("Reports are saved on the machine that trained. Open the web page on that machine to save one."), bad: true)
            return
        }
        let p = NSOpenPanel(); p.canChooseDirectories = true; p.canChooseFiles = false; p.prompt = L("Save Here")
        guard p.runModal() == .OK, let folder = p.url else { return }
        await showReport(store) { try await store.client(for: run).post("report", ["paths": [run.path], "folder": folder.path]) }
    }

    /// 오른쪽 세로 레일: 다음 할 일. 주요(다시 학습·시험·평가) / 모델 보관(내보내기·상태) / 파일(보고서·폴더)을 간격으로 나눈다
    var actionRail: some View {
        let local = store.isLocal(run)
        let canTrain = local && detail?.args["data"] != nil, hasModel = local && detail?.weights != nil
        let resume = resumeState
        return VStack(spacing: 4) {
            RailAction(symbol: "arrow.clockwise", title: L("Train Again"), hint: L("Start a new run with the same settings"), enabled: canTrain) { trainAgain() }
            RailAction(symbol: "play.circle", title: L("Resume"), hint: resume.hint, enabled: resume.ok) { resumeRun() }
            // 끈 버튼에도 이유를 띄운다(resumeState와 같은 방식). 다른 기계면 그 사실이, 이 맥이면 best.pt가 없다는 것이 이유다
            RailAction(symbol: "eye", title: L("Try"), hint: hasModel ? L("Try the model on your own images") : noModelHint(L("This run has no best.pt to try.")), enabled: hasModel) { tryModel() }
            RailAction(symbol: "checkmark.rectangle.stack", title: L("Review"), hint: hasModel ? L("Review mistakes on the validation images") : noModelHint(L("This run has no best.pt to check.")), enabled: hasModel) { reviewModel() }
            RailGap()
            ExportRailButton(enabled: hasModel && run.framework.map { $0 != "ultralytics" } != true,
                             trainImgsz: detail?.args["imgsz"].flatMap { Int($0) }) { o in Task { await exportModel(o) } }
            StageMenu(run: run, detail: detail, stage: $stage)
            RailGap()
            RailAction(symbol: "doc.text", title: L("Report"), hint: L("Save a report with scores, notes and charts"), enabled: true) { Task { await exportReport() } }
            RailAction(symbol: "folder", title: L("Folder"), hint: L("Show the run folder in Finder"), enabled: local) { NSWorkspace.shared.open(URL(fileURLWithPath: run.path)) }
            Spacer()
        }
        .padding(.top, 20)
        .frame(width: 78)
        .glass(Rectangle())
        .contextMenu {
            Button(L("Train Again"), systemImage: "arrow.clockwise") { trainAgain() }.disabled(!canTrain).help(L("Start a new run with the same settings"))
            Button(L("Resume"), systemImage: "play.circle") { resumeRun() }.disabled(!resume.ok).help(resume.hint)
            Button(L("Try"), systemImage: "eye") { tryModel() }.disabled(!hasModel)
                .help(hasModel ? "" : noModelHint(L("This run has no best.pt to try.")))
            Button(L("Review"), systemImage: "checkmark.rectangle.stack") { reviewModel() }.disabled(!hasModel)
                .help(hasModel ? "" : noModelHint(L("This run has no best.pt to check.")))
            Divider()
            Button(L("Show in Finder"), systemImage: "folder") { NSWorkspace.shared.open(URL(fileURLWithPath: run.path)) }.disabled(!local)
        }
        .help(local ? "" : String(localized: "Available for runs on this Mac"))
    }

    /// 모델이 없어 끈 버튼의 이유. 다른 기계면 그 사실이 먼저다(그 맥에 파일이 있어도 여기서는 못 쓴다)
    func noModelHint(_ missing: String) -> String { store.isLocal(run) ? missing : L("Available for runs on this Mac") }

    /// 재개 가능 여부와 그 이유(끈 버튼에 그대로 띄운다). 판단은 agent와 같은 기준: 멈춘 run + weights/last.pt
    /// ★"끝난 학습"과 "멈춘 학습"을 안 가르면 done을 재개해 ultralytics가 0에폭으로 즉시 끝난다
    var resumeState: (ok: Bool, hint: String) {
        let hint = L("Pick up where it stopped, in the same folder")
        if run.isLive { return (false, L("Only for runs that stopped before finishing")) }
        if run.state == "done" { return (false, L("This run already finished")) }
        // 다른 기계: agent가 알려 준 last.pt로 그 기계 대기열에 이어 하기를 넣는다(파이썬은 그 기계가 고른다)
        guard store.isLocal(run) else {
            let ok = detail?.last != nil && run.state == "stopped" && run.framework == "ultralytics"
            return ok ? (true, hint) : (false, L("No last.pt in this run folder"))
        }
        let last = URL(fileURLWithPath: run.path).appendingPathComponent("weights/last.pt")
        guard FileManager.default.fileExists(atPath: last.path) else { return (false, L("No last.pt in this run folder")) }
        return (true, hint)
    }

    /// 같은 설정으로 새 학습(새 폴더). 경로를 주면 양식이 args.yaml 전체를 그대로 가져온다
    func trainAgain() {
        RetrainRequest.path = run.path; RetrainRequest.resume = false
        store.pendingTrainArgs = detail?.trainArgs; store.section = .train      // trainArgs: 기본값까지 모든 설정(옛 agent면 args)
    }

    /// 멈춘 지점부터 이어서(같은 폴더·last.pt). 옵티마이저와 에폭이 살아난다
    func resumeRun() {
        if !store.isLocal(run), let last = detail?.last {
            let client = store.client(for: run), name = run.displayName
            Task {
                await store.act(L("Added to queue")) {
                    try await client.post("jobs", ["kind": "train", "name": name, "params": ["model": last, "resume": true] as [String: Any]])
                }
            }
            return
        }
        RetrainRequest.path = run.path; RetrainRequest.resume = true
        store.pendingTrainArgs = detail?.args ?? [:]; store.section = .train
    }
    func tryModel() { UserDefaults.standard.set(detail?.weights ?? "", forKey: "tryModel"); store.section = .tryit }
    func reviewModel() { store.pendingReviewModel = detail?.weights; store.section = .review }
}

/// 레일 버튼 묶음 사이 간격(주요 / 보관 / 파일). 선은 옅게, 간격이 주된 구분
struct RailGap: View {
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        Rectangle().fill(Color(white: scheme == .dark ? 1 : 0).opacity(0.12)).frame(width: 28, height: 1).padding(.vertical, Space.s)
    }
}

struct RailLabel: View {
    let symbol: String
    let title: String
    var enabled = true
    @State private var hover = false
    @Environment(\.colorScheme) private var scheme
    /// ★.primary는 유리 위에서 뒤 배경 밝기를 따라 버튼마다 흰색·검정으로 뒤집혀(라이트에서 흰 아이콘) 꺼진 것처럼 보였다.
    ///   색 이름(의미색) 대신 화면 모드로 정한 실제 색을 쓴다. 흐림은 진짜 꺼졌을 때만
    private var ink: Color { scheme == .dark ? Color(white: 0.96) : Color(white: 0.12) }
    var body: some View {
        VStack(spacing: 3) {
            Image(systemName: symbol).font(.ui(15, weight: .semibold))
                .symbolRenderingMode(.monochrome)
                .foregroundStyle(ink.opacity(enabled ? 1 : 0.3))
                .frame(width: 40, height: 32)
                .background(ink.opacity(!enabled ? 0.03 : hover ? 0.14 : 0.07), in: .rect(cornerRadius: 9))
                .overlay(RoundedRectangle(cornerRadius: 9).strokeBorder(ink.opacity(hover && enabled ? 0.14 : 0), lineWidth: 1))
                .scaleEffect(hover && enabled ? 1.06 : 1)
                .symbolEffect(.bounce, value: hover && enabled)
            Text(verbatim: title).font(.ui(10.5, weight: .medium))
                .foregroundStyle(ink.opacity(enabled ? 0.85 : 0.3))
                .lineLimit(1).minimumScaleFactor(0.75)
        }
        .frame(width: 70)
        .contentShape(.rect)
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
    }
}

struct RailAction: View {
    let symbol: String
    let title: String
    /// 마우스를 올리면 뜨는 한 문장(동사로 시작)
    var hint: String? = nil
    let enabled: Bool
    let action: () -> Void
    var body: some View {
        Button(action: action) { RailLabel(symbol: symbol, title: title, enabled: enabled) }
            .buttonStyle(PressStyle()).disabled(!enabled).help(hint ?? title).accessibilityLabel(title)
            .accessibilityHint(hint ?? "")
    }
}
