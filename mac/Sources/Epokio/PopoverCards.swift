import SwiftUI

// 팝오버의 상황별 카드: 쉬는 중, 폴더 없음, 방금 끝남.

struct RestCard: View {
    @Environment(\.ink) private var ink
    let last: Run?
    @State private var hover = false

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "moon.zzz")
                .font(.ui(16, weight: .medium))
                .foregroundStyle(ink.soft)
                .symbolEffect(.bounce, value: hover)
                .frame(width: 34, height: 34)
                .background(.primary.opacity(0.06), in: Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text("All quiet").font(.ui(13.5, weight: .semibold))
                Text(last.map { L("Last run: %@", $0.displayName) + "  ·  " + L("%@ ago", duration($0.idle)) } ?? L("Nothing is training right now"))
                    .font(.ui(11.5)).foregroundStyle(ink.soft).lineLimit(1).truncationMode(.middle)
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .glass(RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(last.map { $0.path } ?? "")
    }
}

// 비어 있을 때. 원인에 따라 다른 안내 (초보자가 터미널을 열 일이 없게).

struct EmptyHint: View {
    @Environment(\.ink) private var ink
    @Environment(\.accessibilityReduceMotion) private var reduce
    @Environment(Store.self) private var store
    @State private var installing = false
    @State private var failure: String?

    var body: some View {
        let offline = !store.offline.isEmpty
        let missing = AgentLauncher.shared.status == .notInstalled
        let taken = AgentLauncher.shared.status == .portTaken
        if AgentLauncher.shared.status == .crashed { crashedCard } else {
        VStack(spacing: 8) {
            // 연결 중은 고장이 아니다: 경고 아이콘 대신 조용한 돌림표, 경고색은 포트 충돌(실제 문제)에만
            Group {
                if offline && !missing && !taken {
                    Image(systemName: "ellipsis").font(.ui(22, weight: .semibold)).foregroundStyle(ink.soft)
                        .symbolEffect(.variableColor.iterative, isActive: !reduce)
                        .frame(width: 28, height: 28)
                } else {
                    Image(systemName: missing ? "shippingbox" : taken ? "exclamationmark.triangle" : "folder.badge.plus")
                        .font(.ui(24, weight: .regular))
                        .foregroundStyle(taken ? AnyShapeStyle(.warn) : ink.soft)
                        .symbolEffect(.bounce, value: missing)
                }
            }
            .transition(.opacity.combined(with: .scale(scale: 0.9)))
            Text(missing ? "One more step" : taken ? "Port 8787 is used by another program" : offline ? "Starting the helper…" : "No training folder yet")
                .font(.ui(13, weight: .semibold))
                .contentTransition(.opacity)
            Text(missing ? "Epokio needs a small Python to run its helper. It can download one for itself (about 25 MB). Nothing is installed system-wide."
                 : taken ? "Another program (for example RStudio Server) answers on 8787 and Epokio could not start on a nearby port. Quit that program or free a port, then reopen Epokio."
                 : offline ? "This takes a few seconds the first time."
                 : "Click the folder button below and choose where your runs are saved.")
                .font(.ui(11.5)).foregroundStyle(ink.soft).multilineTextAlignment(.center)
                .textSelection(.enabled)
            if missing {
                Button {
                    installing = true; failure = nil
                    Task {
                        do { try await PythonInstaller.install(); await AgentLauncher.shared.ensureRunning(); store.refresh() }
                        catch { failure = error.localizedDescription }
                        installing = false
                    }
                } label: {
                    HStack(spacing: 6) {
                        if installing { ProgressView().controlSize(.small) }
                        Text(installing ? "Downloading…" : "Get Python for Epokio")
                    }
                    .padding(.horizontal, 6)
                }
                .primaryButton().disabled(installing)
                .transition(.opacity.combined(with: .scale(scale: 0.95)))
                if let failure { Text(verbatim: failure).font(.ui(11.5)).foregroundStyle(.warn).multilineTextAlignment(.center) }
            }
        }
        .frame(maxWidth: .infinity).padding(.vertical, 20)
        .animation(Motion.change, value: offline)
        }
    }

    /// 띄운 agent가 곧바로 끝났다. ★'도우미를 켜는 중…'이 끝없이 돌았다. 이유는 로그에
    private var crashedCard: some View {
        VStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle").font(.ui(24, weight: .regular)).foregroundStyle(.warn)
            Text("The helper stopped").font(.ui(13, weight: .semibold))
            Text("It closed right after starting. The reason is in ~/.epokio/agent.log.")
                .font(.ui(11.5)).foregroundStyle(ink.soft).multilineTextAlignment(.center)
            HStack {
                Button("Show Log") { NSWorkspace.shared.open(AgentLauncher.logFile) }
                Button("Try Again") { Task { await AgentLauncher.shared.ensureRunning(); store.refresh() } }
                    .primaryButton()
            }
            .controlSize(.small)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 20)
    }
}

// GPU·CPU·메모리 고리. 런캣·활성 상태 보기 느낌.

/// 팝오버 맨 위 "방금 끝남". 결과를 보러 가는 가장 짧은 길.
struct JustFinishedCard: View {
    let item: InboxItem
    let open: () -> Void
    @Environment(\.ink) private var ink
    @State private var hover = false

    private var tint: Color { item.kind == "finished" ? .good : item.kind == "failed" ? .bad : .warn }

    var body: some View {
        Button(action: open) {
            HStack(spacing: 12) {
                Image(systemName: item.symbol).font(.ui(20, weight: .semibold)).foregroundStyle(tint)
                    .symbolEffect(.bounce, value: item.id)
                    .frame(width: 42, height: 42).background(tint.opacity(0.16), in: Circle())
                VStack(alignment: .leading, spacing: 2) {
                    Text(verbatim: item.title).font(.ui(13, weight: .semibold))
                    Text(verbatim: item.runName).font(.ui(12)).lineLimit(1).truncationMode(.middle)
                    if let b = item.best {
                        Text(verbatim: L("best %@", String(format: "%.4f", b)) + "  ·  " + L("%@ ago", duration(-item.date.timeIntervalSinceNow)))
                            .font(.ui(11.5)).foregroundStyle(ink.soft)
                    }
                }
                Spacer()
                Text("View Results").font(.ui(11, weight: .semibold))
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(tint.opacity(hover ? 0.3 : 0.18), in: Capsule())
            }
            .padding(12)
            .background(tint.opacity(0.08), in: .rect(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(tint.opacity(0.35), lineWidth: 1))
            .contentShape(.rect)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
    }
}

/// 팝오버의 빠른 작업. Studio는 자세히 보는 곳이고, 메뉴바에서는 자주 하는 일을 한 번에 한다.
struct QuickActions: View {
    let go: (Studio.Section) -> Void
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var confirmStop = false

    var body: some View {
        VStack(spacing: 8) {
            if let j = store.runningJob {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text(verbatim: j.name).font(.ui(12.5, weight: .medium)).lineLimit(1).truncationMode(.middle)
                    Spacer()
                    if store.queuedCount > 0 {
                        Text(L("%d waiting", store.queuedCount)).font(.ui(11.5)).foregroundStyle(ink.soft)
                            .contentTransition(.numericText())
                    }
                    Button("Stop", role: .destructive) { confirmStop = true }
                        .controlSize(.small)
                        .confirmationDialog(L("Stop \"%@\"?", j.name), isPresented: $confirmStop) {
                            Button("Stop", role: .destructive) {
                                Task { await store.act(L("Stopped")) { try await AgentClient.local.post("jobs/\(j.id)/cancel") } }
                            }
                        } message: { Text("The run keeps what it saved so far (last.pt, results.csv).") }
                }
                .padding(.horizontal, 10).padding(.vertical, 7)
                .background(.good.opacity(0.08), in: .rect(cornerRadius: 10))
                .transition(.move(edge: .top).combined(with: .opacity))
            }
            HStack(spacing: 4) {
                QuickTile(title: "Train", symbol: "play.fill", tint: .brand) { go(.train) }
                QuickTile(title: "Try it", symbol: "eye", tint: .mixup) { go(.tryit) }
                QuickTile(title: "Auto-label", symbol: "wand.and.stars", tint: .warn) { go(.label) }
                QuickTile(title: "Queue", symbol: "list.number", tint: .brand2,
                          badge: store.queuedCount + (store.runningJob == nil ? 0 : 1)) { go(.queue) }
            }
            .padding(4)
            .background(.quaternary.opacity(0.35), in: Capsule())
        }
        .animation(.smooth, value: store.runningJob?.id)
    }
}

struct QuickTile: View {
    let title: LocalizedStringKey
    let symbol: String
    let tint: Color
    var badge = 0
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: symbol).font(.role(.caption, weight: .semibold)).foregroundStyle(tint)
                    .symbolEffect(.bounce, value: hover)
                Text(title).font(.role(.caption, weight: .medium)).lineLimit(1).fixedSize()
            }
            .frame(maxWidth: .infinity).padding(.vertical, 7)
            .background(tint.opacity(hover ? 0.16 : 0), in: Capsule())
            .overlay(alignment: .topTrailing) {
                if badge > 0 {
                    Text(verbatim: "\(badge)").font(.ui(10, weight: .bold)).foregroundStyle(.white)
                        .padding(.horizontal, 5).frame(minHeight: 15).background(tint, in: Capsule()).offset(x: -5, y: 5)
                        .contentTransition(.numericText())
                }
            }
            .contentShape(.rect)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
    }
}

/// 진행 중인 학습 하나를 크게. 큰 숫자는 진행률 하나, 얇은 막대, 작은 보조 줄(에폭·끝날 시각), 오른쪽에 점수와 지표 이름
struct LiveCard: View {
    let run: Run
    let open: () -> Void
    @Environment(\.ink) private var ink
    @State private var hover = false

    private var pct: Int { Int(((run.progress ?? 0) * 100).rounded()) }
    private var metric: String { run.metric_name.isEmpty ? L("Score") : MetricLabel.short(run.metric_name) }

    var body: some View {
        Button(action: open) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 6) {
                    Circle().fill(run.tint).frame(width: 7, height: 7)
                        .help(run.stateText)
                    Text(verbatim: run.displayName).font(.ui(13, weight: .semibold))
                        .lineLimit(1).truncationMode(.middle)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").font(.ui(11, weight: .semibold)).foregroundStyle(ink.soft)
                        .opacity(hover ? 1 : 0).offset(x: hover ? 0 : -4)
                }
                HStack(alignment: .lastTextBaseline) {
                    Text(verbatim: run.progress == nil ? "–" : "\(pct)%")
                        .font(.ui(30, weight: .semibold, design: .rounded)).monospacedDigit()
                        .contentTransition(.numericText(value: Double(pct)))
                    Spacer(minLength: 8)
                    if let b = run.best {
                        HStack(alignment: .lastTextBaseline, spacing: 4) {
                            Text(Fmt.metric(b, higher: run.metricHigher)).font(.ui(17, weight: .semibold, design: .rounded)).monospacedDigit()
                                .contentTransition(.numericText(value: b))
                            Text(verbatim: metric).font(.ui(11, weight: .medium)).foregroundStyle(ink.soft)
                        }
                        .help(L("Best score") + " · " + run.metric_name)
                    }
                }
                if let p = run.progress { ThinProgress(value: p, tint: run.tint) }
                HStack(spacing: 6) {
                    Text(verbatim: L("epoch %@", "\(run.epoch)/\(run.total.map(String.init) ?? "?")"))
                        .contentTransition(.numericText(value: Double(run.epoch)))
                    Spacer(minLength: 6)
                    if let eta = run.eta, eta > 0 {
                        Text(verbatim: L("done around %@", Fmt.time(Date().addingTimeInterval(eta))))
                            .help(duration(eta))
                    } else {
                        Text(verbatim: run.stateText)
                    }
                }
                .font(.ui(11.5)).foregroundStyle(ink.soft).lineLimit(1)
            }
            .padding(14)
            .glass(RoundedRectangle(cornerRadius: Radius.card, style: .continuous), interactive: true)
            .overlay(RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                        .strokeBorder(.primary.opacity(hover ? 0.12 : 0), lineWidth: 1))
            .contentShape(.rect)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .animation(Motion.change, value: run.state)
        .help("Show results")
    }
}

/// 폴더를 제때 못 읽었을 때. 대개 macOS가 폴더 접근 권한을 묻고 있다(새로 설치한 직후). 설정의 해당 칸을 바로 연다
struct SlowRootsNote: View {
    let paths: [String]
    @Environment(\.ink) private var ink
    @State private var hover = false

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "lock.trianglebadge.exclamationmark.fill").font(.role(.headline)).foregroundStyle(.warn)
                .symbolEffect(.pulse, options: .repeat(2))
            VStack(alignment: .leading, spacing: 3) {
                Text(L("Can't read %d folders yet", paths.count)).font(.role(.callout, weight: .semibold))
                Text("macOS may be asking whether Epokio can open these folders. Allow it, or turn Epokio on in Files and Folders.")
                    .font(.role(.caption)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
                Button {
                    NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_FilesAndFolders")!)
                } label: { Label("Open Privacy Settings", systemImage: "hand.raised") }
                    .buttonStyle(BrandLink()).font(.role(.caption, weight: .medium))
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(.warn.opacity(hover ? 0.14 : 0.09), in: .rect(cornerRadius: Radius.card))
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(paths.joined(separator: "\n"))
    }
}
