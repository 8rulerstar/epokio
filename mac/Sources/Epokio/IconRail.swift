import SwiftUI

// 아이폰 듀오(iOS 27)에서 가져온 것: 컨트롤은 가장자리의 세로 아이콘 줄로 모으고, 내용을 넓게 쓴다.
// "아이콘은 세로로, 글자는 가로로." 상태는 원 하나로 합친다(듀오의 상태 원).

extension Studio.Section {
    /// 레일 밑 짧은 이름
    var short: String {
        switch self {
        case .home: L("Home"); case .runs: L("Runs"); case .train: L("Train"); case .review: L("Review"); case .data: L("Labels")
        case .tryit: L("Try it"); case .label: L("Auto-label"); case .queue: L("Queue"); case .trophies: L("Awards"); default: title
        }
    }
    static let main: [Studio.Section] = [.home, .runs, .train, .review, .data]
    static let more: [Studio.Section] = [.tryit, .label, .queue, .trophies]
}

struct IconRail: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @Namespace private var pill                          // 선택 표시가 다음 칸으로 미끄러져 옮겨 간다
    @AppStorage("railOrder") private var railOrder = ""      // 설정 → 꾸미기: 순서·숨김
    @AppStorage("railHidden") private var railHidden = ""
    @AppStorage("achievements") private var achievements = false
    private func shown(_ list: [Studio.Section]) -> [Studio.Section] {
        let off = Set(railHidden.split(separator: ",").map(String.init)), o = railOrder.split(separator: ",").map(String.init)
        return list.filter { $0 == .home || !off.contains($0.rawValue) }.filter { $0 != .trophies || achievements }
            .sorted { (o.firstIndex(of: $0.rawValue) ?? 999, list.firstIndex(of: $0)!) < (o.firstIndex(of: $1.rawValue) ?? 999, list.firstIndex(of: $1)!) }
    }

    var body: some View {
        VStack(spacing: 6) {
            ForEach(shown(Studio.Section.main)) { s in RailItem(section: s, big: true, ns: pill) }
            Divider().frame(width: 34).padding(.vertical, 6)
            ForEach(shown(Studio.Section.more)) { s in RailItem(section: s, big: false, ns: pill) }
            Spacer(minLength: 12)
            StatusRing()
                .padding(.bottom, 12)
        }
        .padding(.top, 12)
        .frame(width: 72)
        .frame(maxHeight: .infinity)
        .glass(Rectangle())
    }
}

struct RailItem: View {
    let section: Studio.Section
    let big: Bool
    let ns: Namespace.ID
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var hover = false

    private var on: Bool { (store.section ?? .home) == section }

    var body: some View {
        Button { withAnimation(Motion.change) { store.section = section }; Haptic.tick() } label: {
            VStack(spacing: 3) {
                Image(systemName: section.symbol)
                    .font(.ui(big ? 17 : 14, weight: on ? .semibold : .regular))
                    .symbolVariant(on ? .fill : .none)
                    .symbolEffect(.bounce, value: on)
                    .frame(width: big ? 44 : 36, height: big ? 34 : 28)
                    .background {
                        if on {
                            RoundedRectangle(cornerRadius: Radius.control).fill(.tint.opacity(0.18))
                                .matchedGeometryEffect(id: "rail", in: ns)
                        } else {
                            RoundedRectangle(cornerRadius: Radius.control).fill(.primary.opacity(hover ? 0.07 : 0))
                        }
                    }
                    .foregroundStyle(on ? AnyShapeStyle(.tint) : AnyShapeStyle(.primary))
                Text(verbatim: section.short)
                    .font(.ui(big ? 10.5 : 10, weight: on ? .semibold : .regular))
                    .foregroundStyle(on ? AnyShapeStyle(.tint) : ink.soft)
                    .lineLimit(1).minimumScaleFactor(0.8)
            }
            .frame(width: 64)
            .contentShape(.rect)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(section.title)
        .accessibilityLabel(section.title)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

/// 상태 원: 테두리 = 지금 학습 진행률, 가운데 = 퍼센트(쉴 때는 달). 올리면 GPU·CPU·메모리, 누르면 그 학습으로
struct StatusRing: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var show = false
    @Environment(\.accessibilityReduceMotion) private var reduce

    var body: some View {
        let lead = store.lead
        let p = lead?.progress ?? 0
        Button { if let lead { store.open(run: lead.id) } else { show.toggle() } } label: {
            ZStack {
                Circle().stroke(.quaternary, lineWidth: 4)
                Circle().trim(from: 0, to: lead == nil ? 0 : max(p, 0.02))
                    .stroke(lead?.tint ?? .brand, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .animation(Motion.progress, value: p)
                if let lead {
                    Text(verbatim: "\(Int(((lead.progress ?? 0) * 100).rounded()))")
                        .font(.ui(12, weight: .bold, design: .rounded)).contentTransition(.numericText())
                } else {
                    Image(systemName: "moon.zzz").font(.ui(13)).foregroundStyle(ink.soft)
                }
            }
            .frame(width: 42, height: 42)
            .scaleEffect(lead != nil && !reduce && show ? 1.06 : 1)
            .contentShape(Circle())
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(.snappy) { show = h } }
        .popover(isPresented: $show, arrowEdge: .trailing) { detail.padding(14).withInk() }
        .accessibilityLabel(lead.map { L("%@ training, %@", $0.displayName, $0.pct4.trimmingCharacters(in: .whitespaces)) } ?? L("Nothing is training right now"))
    }

    private var detail: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let r = store.lead {
                Text(verbatim: r.displayName).font(.ui(13, weight: .semibold))
                Text(verbatim: L("epoch %@", "\(r.epoch)/\(r.total.map(String.init) ?? "?")") + "  ·  " + L("%@ left", duration(r.eta)))
                    .font(.ui(12)).foregroundStyle(ink.soft)
            } else {
                Text("Nothing is training right now").font(.ui(13, weight: .semibold))
            }
            if let (name, s) = store.system.sorted(by: { $0.key < $1.key }).first.flatMap({ k, v in v.now.map { (k, $0) } }) {
                Divider()
                HStack(spacing: 14) {
                    stat("GPU", s.gpus.first?.util)
                    stat("CPU", s.cpu)
                    stat("MEM", s.mem_total.flatMap { t in s.mem_used.map { $0 / t * 100 } })
                }
                Text(verbatim: name).font(.ui(11.5)).foregroundStyle(ink.soft)
            }
        }
        .frame(minWidth: 180, alignment: .leading)
    }

    private func stat(_ n: String, _ v: Double?) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(v.map { "\(Int($0))%" } ?? "–").font(.ui(14, weight: .semibold, design: .rounded))
            Text(verbatim: n).font(.ui(10)).foregroundStyle(ink.soft)
        }
    }
}
