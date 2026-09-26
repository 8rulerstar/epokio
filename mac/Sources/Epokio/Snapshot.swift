import SwiftUI

// `Epokio --snapshot out.png` : 팝오버를 PNG로. 화면 권한 없이 결과를 눈으로 확인하는 용도.
// ★파이썬판에서 결과를 안 보고 "예쁘다"고 보고했다가 두 번 깨진 화면을 받았다. 여기선 늘 찍어 본다.
@MainActor
enum SnapshotMode {
    /// --warmup <초>: 찍기 전에 더 기다린다(샘플 학습이 0%가 아니라 돌아가는 모습으로 나오게)
    static var warmup: Double {
        let a = CommandLine.arguments
        return a.firstIndex(of: "--warmup").flatMap { a.count > $0 + 1 ? Double(a[$0 + 1]) : nil } ?? 0
    }

    static func runIfRequested() {
        let args = CommandLine.arguments
        // 명령 해석 시험: --jev "문장"  (키는 환경 변수 TYPESAFE_API_KEY를 잠깐 키체인 대신 쓴다)
        if let i = args.firstIndex(of: "--jev"), i + 1 < args.count, let k = ProcessInfo.processInfo.environment["TYPESAFE_API_KEY"] {
            Jev.testKey = k
            let store = Store(agents: Config.agents)
            let deadline = Date().addingTimeInterval(3)
            while Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.1)) }
            Task { @MainActor in
                do {
                    let r = try await Jev.interpret(args[i + 1], runs: store.runs)
                    print("jev:", r.action.rawValue, r.runs.map(\.displayName), r.epochs.map(String.init) ?? "-", String(format: "%.2f", r.confidence))
                } catch { print("jev error:", error.localizedDescription) }
                exit(0)
            }
            RunLoop.main.run()
        }
        // 형식 계약 시험: --contract <폴더>  (tests/contract의 agent 응답을 앱 모델로 읽어 본다. 실패하면 1로 끝남)
        if let i = args.firstIndex(of: "--contract"), i + 1 < args.count {
            let dir = URL(fileURLWithPath: args[i + 1])
            func check<T: Decodable>(_ t: T.Type, _ name: String) -> Bool {
                do { _ = try JSONDecoder().decode(t, from: Data(contentsOf: dir.appendingPathComponent(name))); print("ok", name); return true }
                catch { print("FAIL", name, error); return false }
            }
            var checks = [check(RunsPayload.self, "runs.json"), check(RunDetail.self, "run.json")]
            let fm = FileManager.default
            if fm.fileExists(atPath: dir.appendingPathComponent("sweep.json").path) { checks.append(check(SweepSummary.self, "sweep.json")) }
            if fm.fileExists(atPath: dir.appendingPathComponent("eval.json").path) { checks.append(check(EvalResult.self, "eval.json")) }
            let ok = checks.allSatisfy { $0 }
            exit(ok ? 0 : 1)
        }
        if let f = args.firstIndex(of: "--folder"), f + 1 < args.count {
            UserDefaults.standard.set(args[f + 1], forKey: "datasetFolder")
        }
        if let i = args.firstIndex(of: "--import-anim"), i + 1 < args.count {             // 시험용: "내 애니메이션" 저장 경로를 그대로 탄다
            let n = CustomAnim.save(from: args[(i + 1)...].map { URL(fileURLWithPath: $0) })
            let f = CustomAnim.frames()
            print("frames saved:", n, "loaded:", f.count, "size:", f.first.map { "\(Int($0.size.width))x\(Int($0.size.height))" } ?? "-")
            exit(n > 0 ? 0 : 1)
        }
        if let i = args.firstIndex(of: "--export-characters"), i + 1 < args.count {       // README용: 캐릭터 프레임을 PNG로(4배)
            let dir = URL(fileURLWithPath: args[i + 1])
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            for r in Runner.allCases {
                for k in 0..<Runner.frames {
                    let src = r.image(Double(k) / Double(Runner.frames))
                    let big = NSImage(size: NSSize(width: src.size.width * 4, height: src.size.height * 4), flipped: false) { rect in
                        NSGraphicsContext.current?.imageInterpolation = .high
                        src.draw(in: rect); return true
                    }
                    if let t = big.tiffRepresentation, let png = NSBitmapImageRep(data: t)?.representation(using: .png, properties: [:]) {
                        try? png.write(to: dir.appendingPathComponent(String(format: "%@_%02d.png", r.rawValue, k)))
                    }
                }
            }
            print("characters:", dir.path); exit(0)
        }
        if let i = args.firstIndex(of: "--snapshot-window"), i + 2 < args.count {
            windowShot(section: args[i + 1], out: URL(fileURLWithPath: args[i + 2]), dark: args.contains("--dark"))
        }
        guard let i = args.firstIndex(of: "--snapshot"), i + 1 < args.count else { return }
        let out = URL(fileURLWithPath: args[i + 1])
        let dark = args.contains("--dark")
        if let k = args.firstIndex(of: "--skin"), k + 1 < args.count { UserDefaults.standard.set(args[k + 1], forKey: "skin") }
        let store = Store(agents: Config.agents)
        if args.contains("--demo-inbox") { store.inbox = demoInbox() }      // README용: 방금 끝남 카드
        // agent 응답을 기다린다. --warmup 초를 주면 그만큼 더 기다린다(도는 샘플 학습이 진행된 모습으로 찍으려고)
        let deadline = Date().addingTimeInterval(4 + warmup)
        while Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.1)) }

        let view = Popover()
            .environment(store)
            .withInk()
            .background(dark ? Color(white: 0.16) : Color(white: 0.96))
            .environment(\.colorScheme, dark ? .dark : .light)
        let r = ImageRenderer(content: view)
        r.scale = 2
        if let img = r.nsImage, let tiff = img.tiffRepresentation,
           let rep = NSBitmapImageRep(data: tiff) {
            SnapshotIsolation.audit(NSHostingView(rootView: view), image: rep.cgImage, section: "popover")
        }
        if let img = r.nsImage, let tiff = img.tiffRepresentation,
           let rep = NSBitmapImageRep(data: tiff),
           let png = rep.representation(using: .png, properties: [:]) {
            try? png.write(to: out)
            print("snapshot:", out.path)
        }
        exit(0)
    }
}

extension SnapshotMode {
    /// 실제 창에 올려서 캡처한다. 창 안의 시스템 컨트롤(토글·슬라이더·입력칸)도 제대로 찍힌다.
    /// ★ImageRenderer로는 이 컨트롤들이 노란 🚫로 나왔다.
    static func windowShot(section: String, out: URL, dark: Bool) {
        _ = NSApplication.shared
        NSApp.setActivationPolicy(.accessory)
        let store = Store(agents: Config.agents)
        if section == "inbox" { store.inbox = demoInbox() }
        if let i = CommandLine.arguments.firstIndex(of: "--section"), i + 1 < CommandLine.arguments.count,
           let sec = Studio.Section(rawValue: CommandLine.arguments[i + 1]) { store.section = sec }     // Studio 안의 화면
        if let i = CommandLine.arguments.firstIndex(of: "--tour"), i + 1 < CommandLine.arguments.count { store.tourStep = Int(CommandLine.arguments[i + 1]) }
        func arg(_ k: String) -> String? { CommandLine.arguments.firstIndex(of: k).map { CommandLine.arguments[$0 + 1] } }
        // --select 이름조각 : 목록이 채워진 뒤 그 학습을 고른다
        if let want = arg("--select") {
            Task { @MainActor in
                for _ in 0..<40 {
                    if let r = store.runs.first(where: { $0.path.contains(want) }) { store.selectedRun = r.id; break }
                    try? await Task.sleep(for: .milliseconds(100))
                }
            }
        }
        let root: AnyView = switch section {
        case "train": AnyView(TrainView())
        case "health": AnyView(ScrollView { HealthCard(data: URL(fileURLWithPath: CommandLine.arguments.firstIndex(of: "--data").map { CommandLine.arguments[$0 + 1] } ?? "")).padding(24) })
        case "label": AnyView(AutoLabelView())
        case "queue": AnyView(QueueView())
        case "data": AnyView(DatasetView())
        case "review": AnyView(ReviewView())
        case "home": AnyView(HomeView())
        case "runs": AnyView(RunsView())
        case "runs-table": AnyView(RunsTable {}.frame(width: 1000, height: 600))
        case "compare": AnyView(RunsView(startCompare: arg("--compare")?.split(separator: ",").map(String.init) ?? []))
        case "inbox": AnyView(InboxView())
        case "sweep": AnyView(SweepDetail(id: "demo", preset: arg("--data").flatMap { try? JSONDecoder().decode(SweepSummary.self, from: Data(contentsOf: URL(fileURLWithPath: $0))) }).frame(width: 760, height: 1400))
        case "menubar": AnyView(MenuBarGallery())
        case "design": AnyView(DesignGallery().frame(width: 760, height: 1480))
        case "onboarding": AnyView(Onboarding())
        case "palette": AnyView(CommandPalette())
        case "detail": AnyView(DetailProbe().frame(width: 820, height: 840))
        case "lineage": AnyView(LineageProbe().padding(20).frame(width: 620, height: 260, alignment: .topLeading))       // 학습 상세만, 좁은 폭에서
        case "settings-appearance": AnyView(AppearanceTab().frame(width: 520, height: 460))
        case "settings-notify": AnyView(NotificationsTab().frame(width: 520, height: 420))
        case "settings-machines": AnyView(MachinesTab().frame(width: 560, height: 640))
        case "settings-customize": AnyView(CustomizeTab().frame(width: 560, height: 900))
        case "shortcuts": AnyView(ShortcutsSheet())
        case "settings-assistant": AnyView(AssistantTab().frame(width: 560, height: 440))
        default: AnyView(Studio())
        }
        // ★실제 창처럼 배경을 깐다. 투명하게 찍으면 옅은 색이 원색처럼, 글자가 배경에 묻힌 것처럼 보여
        //   멀쩡한 화면을 고치려 들게 된다
        let host = NSHostingView(rootView: root.environment(store).withInk()
            .background(Color(nsColor: .windowBackgroundColor))
            .environment(\.colorScheme, dark ? .dark : .light))
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 780, height: 860),
                           styleMask: [.titled], backing: .buffered, defer: false)
        win.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        win.contentView = host
        win.orderFrontRegardless()
        let deadline = Date().addingTimeInterval(6 + warmup)  // agent에서 환경·설정표 받을 시간(+ --warmup)
        while Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.1)) }
        host.layoutSubtreeIfNeeded()
        if let rep = host.bitmapImageRepForCachingDisplay(in: host.bounds) {
            host.cacheDisplay(in: host.bounds, to: rep)
            SnapshotIsolation.audit(host, image: rep.cgImage, section: section)
            try? rep.representation(using: .png, properties: [:])?.write(to: out)
            print("window snapshot:", out.path)
        }
        exit(0)
    }
}

/// 알림함 스냅샷용 가짜 사건(저장하지 않는다)
@MainActor func demoInbox() -> [InboxItem] {
    let now = Date()
    return [
        InboxItem(id: "d1", kind: "finished", runID: "local|x", runName: "coco8", machine: "local", best: 0.6405, epoch: 5, total: 5, date: now.addingTimeInterval(-300)),
        InboxItem(id: "d2", kind: "stalled", runID: "local|y", runName: "defect_det/train", machine: "gpu-pc", best: 0.3848, epoch: 41, total: 80, date: now.addingTimeInterval(-3600 * 3), read: true),
        InboxItem(id: "d3", kind: "failed", runID: "local|z", runName: "pose_v2", machine: "local", best: nil, epoch: 3, total: 100, date: now.addingTimeInterval(-86400 - 600), read: true),
    ]
}

/// 메뉴바 모양 확인용: 진행률·맥박 단계별로 크게 그려 본다
struct MenuBarGallery: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            ForEach(Runner.allCases, id: \.self) { r in                // 캐릭터: 한 바퀴를 8칸으로
                HStack(spacing: 14) {
                    ForEach(0..<8, id: \.self) { k in
                        Image(nsImage: r.image(Double(k) / 8)).renderingMode(.template).resizable().interpolation(.high)
                            .frame(width: 24 * 3, height: 16 * 3)
                    }
                }
            }
            ForEach(["mark", "bar", "gauge"], id: \.self) { kind in
                HStack(spacing: 22) {
                    ForEach([0.1, 0.45, 0.8, 1.0], id: \.self) { p in
                        ForEach([0.0, 0.25], id: \.self) { ph in
                            let img = kind == "mark" ? markImage(p, pulse: ph) : kind == "bar" ? barImage(p, sheen: ph + 0.3) : gaugeImage(p, wobble: ph)
                            Image(nsImage: img).renderingMode(.template).resizable().interpolation(.high)
                                .frame(width: img.size.width * 4, height: img.size.height * 4)
                        }
                    }
                }
            }
        }
        .padding(30)
    }
}

/// 상세 화면만 찍는다(HSplitView는 스냅샷에서 배치가 안 된다)
struct DetailProbe: View {
    @Environment(Store.self) private var store
    var body: some View {
        if let id = store.selectedRun, let r = store.runs.first(where: { $0.id == id }) {
            RunDetailView(run: r).onAppear { if CommandLine.arguments.contains("--expand") { UserDefaults.standard.set(true, forKey: "detailExpanded") } }
        }
        else { ProgressView() }
    }
}

/// 스냅샷: 고른 학습의 계보 카드만
struct LineageProbe: View {
    @Environment(Store.self) private var store
    @State private var d: RunDetail?
    var body: some View {
        Group {
            if let d, let id = store.selectedRun, let r = store.runs.first(where: { $0.id == id }) { LineageCard(run: r, detail: d) }
            else { ProgressView() }
        }
        .task(id: store.selectedRun) {
            guard let id = store.selectedRun, let r = store.runs.first(where: { $0.id == id }) else { return }
            d = try? await store.client(for: r).get("run", ["path": r.path])
        }
    }
}
