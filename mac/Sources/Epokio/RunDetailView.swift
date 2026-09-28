import SwiftUI
import Charts

// 학습 하나의 결과: 요약·다음 할 일, 성적, 곡선, 자동 해설, 결과 이미지, 사용한 설정.

struct RunDetailView: View {
    let run: Run
    @Environment(Store.self) var store
    @Environment(\.ink) var ink
    @State var detail: RunDetail?
    @State var failed = false
    @AppStorage("detailCurve") var curve = 1           // 0 손실, 1 점수. 마지막으로 본 쪽을 기억
    @State var bigImage: String?
    @AppStorage("curveSmoothing") var smoothing = 0.0
    @AppStorage(ViewPrefs.curveWidthKey) var curveWidth = 2.0
    @AppStorage(Tips.key) var showTips = true
    @State var confirmStop = false
    @State var hoverEpoch: Double?                 // 곡선 위에 마우스를 올린 에폭      // 곡선 부드럽게(TensorBoard처럼). 0 = 원본

    @AppStorage("detailExpanded") var more = false
    @State var stage: Stage = .none

    var body: some View {
        HStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    if let d = detail {
                        if !run.isLive, let e = d.explain { ExplainCard(run: run, explain: e) } else { headline(d) }
                        if (d.lossKeys + d.scoreKeys).contains(where: { (d.columns[$0] ?? []).contains { $0 != nil } }) { curves(d) }
                        else {                                  // ★열은 있는데 값이 다 비어 0~1 축만 있는 빈 그래프가 나왔다
                            Label("No curve to draw yet. The results file has no scores.", systemImage: "chart.line.downtrend.xyaxis")
                                .font(.role(.callout)).foregroundStyle(ink.soft)
                                .frame(maxWidth: .infinity, minHeight: 90)
                                .background(.quaternary.opacity(0.25), in: .rect(cornerRadius: Radius.card))
                                .transition(.opacity)
                        }
                        // 아이폰 듀오처럼: 기본은 요약만, 나머지는 펼쳐서
                        DisclosureGroup(isExpanded: $more.animation(.smooth)) {
                            VStack(alignment: .leading, spacing: 18) {
                                if !d.heads.isEmpty { scores(d) } else if !d.scoreKeys.isEmpty { genericScores(d) }
                                if d.classes != nil || (d.weights != nil && d.framework == "ultralytics") { PerClassSection(run: run, classes: d.classes) }
                                if let s = d.snapshots { SnapshotsSection(snaps: s, url: imageURL, open: { bigImage = $0 }) }
                                if let s = d.system { MachineSection(system: s) }
                                if d.notes.count > 1 { notes(d) }
                                RunNotes(run: run)
                                if !d.images.isEmpty { gallery(d) }
                                if d.lineage != nil { LineageCard(run: run, detail: d) }
                                if let rp = d.repro { ReproSection(repro: rp) }
                                if !d.args.isEmpty { settings(d) }
                            }
                            .padding(.top, 10)
                        } label: {
                            Text(more ? "Less" : "Details: scores, images, history, settings, notes")
                                .font(.ui(13, weight: .semibold)).foregroundStyle(.tint)
                        }
                    } else if failed {
                        Label("Could not load this run from its machine.", systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.warn)
                    } else {
                        ProgressView().frame(maxWidth: .infinity).padding(40)
                    }
                }
                .padding(24)
                .frame(maxWidth: 860, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            Divider()
            actionRail                                        // 버튼은 오른쪽 세로 레일로(듀오의 사이드 레일)
        }
        .task(id: "\(run.epoch)|\(run.state)") { await load() }        // 에폭이 늘면 곡선도 다시
        .sheet(item: Binding(get: { bigImage.map(ImageRef.init) }, set: { bigImage = $0?.name })) { ref in
            BigImage(url: imageURL(ref.name), name: ref.name)
        }
    }

    func load() async {
        do {
            let d: RunDetail = try await store.client(for: run).get("run", ["path": run.path])
            // 처음만 부드럽게 나타난다. ★도는 학습은 에폭마다 다시 받는데 그때마다 곡선 전체를 애니메이션해 창 배치를 매 프레임 다시 쟀다
            let first = detail == nil
            withAnimation(first ? Motion.change : nil) { detail = d; failed = false; stage = Stage(rawValue: d.stage ?? "") ?? .none }
        } catch { failed = detail == nil }
    }

    func imageURL(_ name: String) -> URL? {
        // 옵셔널이 아닌 지역 변수로(★c?.x = c?.x... 는 같은 값을 읽으며 쓰는 것이라 컴파일 오류였다)
        guard var c = URLComponents(url: store.client(for: run).live.appending(path: "file"), resolvingAgainstBaseURL: false) else { return nil }
        c.queryItems = [URLQueryItem(name: "path", value: run.path + "/" + name)]
        c.percentEncodedQuery = c.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")   // + 가 공백으로 읽혀 그림이 안 떴다
        return c.url
    }

    // 요약 줄 + 다음 할 일
    var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(run.displayName).font(.ui(22, weight: .bold)).lineLimit(1).truncationMode(.middle)
                StarButton(run: run)
                StageBadge(stage: stage).animation(.bouncy, value: stage)
                Spacer()
            }
            Text(verbatim: [run.stateText, L("epoch %@", "\(run.epoch)/\(run.total.map(String.init) ?? "?")"),
                            run.frameworkName, run.source].joined(separator: "  ·  "))
                .font(.ui(12.5)).foregroundStyle(ink.soft)
            if let b = run.best {
                HStack(alignment: .lastTextBaseline, spacing: 12) {
                    Text(Fmt.metric(b, higher: run.metricHigher)).font(.role(.hero))       // 끝난 학습은 브랜드 그라데이션, 도는·실패는 상태색
                        .foregroundStyle(run.state == "done" ? AnyShapeStyle(LinearGradient.brand) : AnyShapeStyle(run.tint))
                        .contentTransition(.numericText())
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Score").font(.ui(13, weight: .semibold))
                        rankBadge(b)
                    }
                }
                .help(run.metric_name)
            }
            if run.isLive { CapsuleBar(value: run.progress ?? 0, tint: run.tint, height: 6, shimmer: false, gradient: true) }
            speedLine
            // 망한 학습 끄기: Epokio 대기열이 띄운 학습만(남이 띄운 프로세스는 건드리지 않는다). 두 번 확인한다
            if let job = store.jobs.first(where: { $0.state == "running" && $0.output == run.path }) {
                HStack(spacing: 8) {
                    if run.state == "failed" || run.state == "stalled" {
                        Label(run.state == "failed" ? "Loss became NaN. This run will not recover." : "No new epoch for a while.",
                              systemImage: "exclamationmark.triangle.fill").font(.ui(12)).foregroundStyle(.warn)
                    }
                    Spacer()
                    Button(role: .destructive) { confirmStop = true } label: { Label("Stop This Run", systemImage: "stop.fill") }
                        .controlSize(.small)
                        .confirmationDialog(L("Stop \"%@\"?", run.displayName), isPresented: $confirmStop) {
                            Button("Stop", role: .destructive) {
                                Task { await store.act(L("Stopped")) { try await AgentClient.local.post("jobs/\(job.id)/cancel") } }
                            }
                        } message: { Text("The run keeps what it saved so far (last.pt, results.csv).") }
                }
                .transition(.opacity)
            }
        }
    }

    /// 한 줄 요약: 지금 상태나 가장 중요한 해설 하나
    func headline(_ d: RunDetail) -> some View {
        let next = !showTips || run.state == "failed" || run.state == "stalled" ? nil : d.notes.first?.next
        let (symbol, tint, text, tip): (String, Color, String, String?) = {
            if run.state == "failed" { return ("xmark.octagon.fill", .bad, L("Loss became NaN. This run will not recover."), nil) }
            if run.state == "stalled" { return ("pause.circle.fill", .warn, L("No new epoch for a while."), nil) }
            if showTips, let n = d.notes.first { return ("lightbulb.fill", .gold, n.observation, n.try) }
            if run.isLive { return ("bolt.fill", .good, L("Training. Nothing unusual so far."), nil) }
            if run.state == "stopped" {                    // ★중단된 학습에도 "끝났습니다, 특별한 점 없음" 초록 체크가 떴다
                return ("stop.circle.fill", .secondary, L("Stopped at epoch %d before the last one.", run.epoch), L("Train again from last.pt, or start fresh with the same settings."))
            }
            return ("checkmark.seal.fill", .good, L("Finished. Nothing unusual."), nil)
        }()
        return HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol).font(.ui(18, weight: .semibold)).foregroundStyle(tint)
                .symbolRenderingMode(.multicolor)
            VStack(alignment: .leading, spacing: 4) {
                Text(verbatim: text).font(.ui(14, weight: .medium)).fixedSize(horizontal: false, vertical: true)
                if let tip { Text(verbatim: "→ " + tip).font(.ui(12.5)).foregroundStyle(ink.soft) }
                if let next, !next.isEmpty { NextRunButton(change: next, detail: d, run: run).padding(.top, 2) }
            }
            Spacer(minLength: 0)
        }
        .padding(14)
        .background(tint.opacity(0.08), in: .rect(cornerRadius: 14))
        .transition(.opacity.combined(with: .move(edge: .top)))
    }

}
