import SwiftUI

// 새 학습 "무엇에서 시작할까요?": 프리셋·최근 학습·데이터셋별 최고 학습을 누르면 양식이 한 번에 채워진다.
// ★양식만 채운다. 시작은 사람이 누른다("원터치 학습"은 누수·표본적합을 쉽게 만들어 안 넣기로 함).
// 채운 뒤 바뀐 칸을 보이고 되돌릴 수 있게, 데이터가 다르면 알린다. 살짝 비틀기(에폭×2, 학습률÷3, 한 단계 크게)도 한 번에.

extension TrainView {
    static let presets: [(String, String, [String: String])] = [
        (L("Quick check"), "hare", ["size": "n", "epochs": "10"]),
        (L("Balanced"), "scalemass", ["size": "s", "epochs": "100"]),
        (L("Best accuracy"), "target", ["size": "m", "epochs": "200", "imgsz": "800"]),
    ]

    /// 지금 양식 값(비교용)
    func currentArgs() -> [String: String] {
        var a = overrides
        a["task"] = task; a["size"] = size; a["epochs"] = String(Int(epochs))
        return a
    }

    /// 기준에서 바뀐 칸
    var changedKeys: [String] {
        guard let b = baseline else { return [] }
        let now = currentArgs()
        return Set(b.keys).union(now.keys).filter { b[$0] != now[$0] }.sorted()
    }

    var startStrip: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Start from", systemImage: "arrow.triangle.branch").font(.role(.headline))
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(Array(Self.presets.enumerated()), id: \.offset) { i, p in
                        StartCard(title: p.0, detail: presetDetail(p.2), symbol: p.1, score: nil, tint: .brand2) { applyPreset(p.0, p.2) }
                            .appearRise(i)
                    }
                    if !starts.isEmpty { Divider().frame(height: 44) }
                    ForEach(Array(starts.enumerated()), id: \.element.id) { i, r in
                        StartCard(title: r.display, detail: runDetail(r), symbol: "clock.arrow.circlepath", score: r.best, tint: .brand) { applyRun(r) }
                            .appearRise(i + 3)
                    }
                }
                .padding(.vertical, 2)
            }
            if let b = baseline {
                changeBar(b)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .task(id: machine) { await loadStarts() }
    }

    private func presetDetail(_ p: [String: String]) -> String {
        [p["size"].map { L("size %@", $0) }, p["epochs"].map { L("%@ epochs", $0) }, p["imgsz"].map { "imgsz \($0)" }].compactMap { $0 }.joined(separator: " · ")
    }
    private func runDetail(_ r: TableRun) -> String {
        [r.args["model"], r.args["epochs"].map { L("%@ epochs", $0) }, r.args["imgsz"].map { "imgsz \($0)" }].compactMap { $0 }.joined(separator: " · ")
    }

    /// 바뀐 칸 + 되돌리기 + 살짝 비틀기
    func changeBar(_ b: [String: String]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill").foregroundStyle(.good)
                Text(changedKeys.isEmpty ? L("Filled in from %@. Change anything, then start.", baseName)
                                         : L("Based on %@ · %d changed: %@", baseName, changedKeys.count, changedKeys.joined(separator: ", ")))
                    .font(.role(.callout)).contentTransition(.opacity)
                if !changedKeys.isEmpty {
                    Button("Undo changes") { withAnimation(Motion.change) { fill(b) } }.buttonStyle(BrandLink()).font(.role(.callout))
                }
                Spacer()
            }
            HStack(spacing: 6) {
                Text("Nudge").font(.role(.caption, weight: .semibold)).foregroundStyle(ink.soft)
                NudgeChip(title: L("Epochs ×2"), symbol: "arrow.up.right") { epochs = min(epochs * 2, 1000) }
                NudgeChip(title: L("Learning rate ÷3"), symbol: "tortoise") {
                    let lr = Double(overrides["lr0"] ?? "") ?? 0.01
                    overrides["lr0"] = String(format: "%g", lr / 3)
                }
                NudgeChip(title: L("Bigger images"), symbol: "arrow.up.left.and.arrow.down.right") {
                    let steps = [320, 480, 640, 800, 960, 1280], now = Int(overrides["imgsz"] ?? "640") ?? 640
                    overrides["imgsz"] = String(steps.first { $0 > now } ?? now)
                }
                NudgeChip(title: L("Bigger model"), symbol: "plus.magnifyingglass") {
                    let order = ["n", "s", "m", "l", "x"]
                    if let i = order.firstIndex(of: size), i + 1 < order.count { size = order[i + 1] }
                }
            }
            if !baseData.isEmpty, let d = data?.path, !d.hasSuffix(baseData) && !baseData.hasSuffix(URL(fileURLWithPath: d).lastPathComponent) {
                Label("This data is not the data of the run you started from, so scores are not directly comparable.", systemImage: "exclamationmark.triangle.fill")
                    .font(.role(.caption)).foregroundStyle(.warn)
            }
        }
        .padding(10)
        .background(.good.opacity(0.07), in: .rect(cornerRadius: Radius.control))
        .animation(Motion.change, value: changedKeys)
    }

    func applyPreset(_ name: String, _ p: [String: String]) {
        var a = currentArgs()
        for (k, v) in p { a[k] = v }
        withAnimation(Motion.change) { fill(a); clearInherited() }
        baseName = name; baseData = ""
        baseline = currentArgs()
        Haptic.tick()
    }

    func applyRun(_ r: TableRun) {
        var a = r.args
        if let m = a["model"], let c = URL(fileURLWithPath: m).deletingPathExtension().lastPathComponent.split(separator: "-").first?.last,
           sizes.contains(where: { $0.0 == String(c) }) { a["size"] = String(c) }
        a.removeValue(forKey: "model"); a.removeValue(forKey: "data")          // 데이터는 지금 고른 것을 그대로(다르면 알린다)
        withAnimation(Motion.change) { fill(a); clearInherited() }
        baseName = r.display; baseData = r.args["data"] ?? ""
        baseline = currentArgs()
        Haptic.tick()
    }

    /// 값들을 양식에 넣는다(task·size·epochs는 칸, 나머지는 전문가 설정)
    func fill(_ a: [String: String]) {
        if let t = a["task"], tasks.contains(where: { $0.0 == t }) { task = t }
        if let s = a["size"], sizes.contains(where: { $0.0 == s }) { size = s }
        if let e = a["epochs"].flatMap(Double.init) { epochs = e }
        overrides = a.filter { !["task", "size", "epochs", "model", "data", "name", "device"].contains($0.key) }   // 나머지는 전문가 설정
    }

    /// 최근 학습 4개 + 데이터셋별 최고(겹치지 않게), 울트라리틱스 학습만(설정을 되살릴 수 있는 것)
    func loadStarts() async {
        struct P: Decodable { let label: String; let rows: [TableRun] }
        guard let p: P = try? await client.get("runs/table") else { return }
        let ok = p.rows.filter { $0.args["task"] != nil }.map { var r = $0; r.source = p.label; return r }
        let recent = ok.sorted { ($0.idle ?? .infinity) < ($1.idle ?? .infinity) }.prefix(4)
        var best: [TableRun] = []
        for (_, g) in Dictionary(grouping: ok, by: { $0.args["data"] ?? "" }) {
            if let b = g.max(by: { ($0.best ?? -1) < ($1.best ?? -1) }), !recent.contains(b) { best.append(b) }
        }
        withAnimation(Motion.change) { starts = Array(recent) + best.sorted { ($0.best ?? 0) > ($1.best ?? 0) }.prefix(3) }
    }
}

extension TrainView {
    /// "다시 학습"·재개 띠: 원래 설정 N개를 그대로 쓴다는 한 줄 + 펼쳐 보기 + 못 옮긴 키
    var inheritStrip: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Image(systemName: resumeParams == nil ? "arrow.clockwise.circle.fill" : "playpause.circle.fill").foregroundStyle(.brand)
                    .symbolEffect(.bounce, value: inheritedFrom)
                Text(resumeParams == nil ? L("Uses %d original settings from %@", inheritedKept, inheritedFrom)
                                         : L("Resumes %@ from last.pt in its own folder. Optimizer and epoch pick up where it stopped.", inheritedFrom))
                    .font(.role(.callout)).contentTransition(.numericText())
                Spacer()
                Button(resumeParams == nil ? L("Don't use") : L("Cancel resume")) { withAnimation(Motion.change) { clearInherited() } }
                    .buttonStyle(BrandLink()).font(.role(.callout))
            }
            if resumeParams == nil {
                DisclosureGroup(L("Show settings")) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(verbatim: "model: \(inheritedModel ?? L("(model size picker)"))")
                        ForEach(inherited.keys.sorted(), id: \.self) { k in Text(verbatim: "\(k): \(Self.show(inherited[k]))") }
                        if !inheritedDropped.isEmpty {
                            Text(L("Not carried over: %@", inheritedDropped.sorted { $0.key < $1.key }.map { "\($0.key) (\($0.value))" }.joined(separator: ", ")))
                                .foregroundStyle(ink.soft).padding(.top, 4)
                        }
                    }
                    .font(.ui(11, design: .monospaced)).textSelection(.enabled).padding(.top, 4)
                }
                .font(.role(.caption))
            }
        }
        .padding(10)
        .background(Color.brand.opacity(0.07), in: .rect(cornerRadius: Radius.control))
        .animation(Motion.change, value: inherited.count)
    }

    static func show(_ v: Any?) -> String {
        switch v {
        case nil, is NSNull: "null"
        case let n as NSNumber where CFGetTypeID(n) == CFBooleanGetTypeID(): n.boolValue ? "true" : "false"
        case let a as [Any]: "[" + a.map { show($0) }.joined(separator: ", ") + "]"
        default: "\(v!)"
        }
    }
}

/// 시작 카드: 제목·요약·점수. 올리면 떠오르고, 누르면 눌린다
struct StartCard: View {
    let title: String
    let detail: String
    let symbol: String
    let score: Double?
    let tint: Color
    let action: () -> Void
    @Environment(\.ink) private var ink

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Image(systemName: symbol).font(.role(.caption, weight: .semibold)).foregroundStyle(tint)
                    Text(verbatim: title).font(.role(.callout, weight: .semibold)).lineLimit(1).truncationMode(.middle)
                    if let s = score { Text(String(format: "%.3f", s)).font(.role(.caption, weight: .semibold)).monospacedDigit().foregroundStyle(tint) }
                }
                Text(verbatim: detail).font(.role(.caption)).foregroundStyle(ink.soft).lineLimit(1)
            }
            .frame(width: 190, alignment: .leading)
            .padding(10)
            .background(.quaternary.opacity(0.35), in: .rect(cornerRadius: Radius.control))
            .contentShape(.rect)
        }
        .buttonStyle(PressStyle())
        .hoverLift()
        .help(L("Fill the form with these settings. Nothing starts until you press Start."))
    }
}

/// 살짝 비틀기 알약
struct NudgeChip: View {
    let title: String
    let symbol: String
    let action: () -> Void
    @State private var hover = false
    @State private var bump = 0

    var body: some View {
        Button { withAnimation(Motion.change) { action() }; bump += 1; Haptic.tick() } label: {
            Label(title, systemImage: symbol).font(.role(.caption, weight: .medium))
                .padding(.horizontal, 8).padding(.vertical, 3)
                .foregroundStyle(.brand)
                .background(Color.brand.opacity(hover ? 0.18 : 0.1), in: Capsule())
                .symbolEffect(.bounce, value: bump)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
    }
}
