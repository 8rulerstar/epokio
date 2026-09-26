import SwiftUI

// ⌘K 명령 팔레트(Raycast·Linear처럼). 학습 이름·화면 이름·작업을 입력해서 바로 간다.
// ↑↓로 고르고 Enter, Esc로 닫는다. 인터넷을 쓰지 않는다(자연어 명령과 별개).

struct PaletteItem: Identifiable {
    let id: String
    let title: String
    let subtitle: String
    let symbol: String
    let tint: Color
    let run: () -> Void
}

struct CommandPalette: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var index = 0
    @FocusState private var focused: Bool

    private var items: [PaletteItem] {
        var out: [PaletteItem] = []
        func go(_ s: Studio.Section) -> () -> Void { { store.section = s } }
        out += [
            PaletteItem(id: "new", title: L("New training"), subtitle: L("Action"), symbol: "play.fill", tint: .brand, run: go(.train)),
            PaletteItem(id: "try", title: L("Try it"), subtitle: L("Action"), symbol: "eye", tint: .mixup, run: go(.tryit)),
            PaletteItem(id: "label", title: L("Auto-label"), subtitle: L("Action"), symbol: "wand.and.stars", tint: .warn, run: go(.label)),
            PaletteItem(id: "review", title: L("Review"), subtitle: L("Action"), symbol: "checkmark.rectangle.stack", tint: .good, run: go(.review)),
            PaletteItem(id: "queue", title: L("Queue"), subtitle: L("Go to"), symbol: "list.number", tint: .teal, run: go(.queue)),
            PaletteItem(id: "labels", title: L("Label Viewer"), subtitle: L("Go to"), symbol: "photo.stack", tint: .pink, run: go(.data)),
            PaletteItem(id: "inbox", title: L("Notifications"), subtitle: L("Go to"), symbol: "bell", tint: .bad, run: { store.showInbox = true }),
        ]
        if let r = store.selected {                        // 고른 학습에 하는 일(학습 메뉴와 같은 것)
            let sub = r.displayName
            out += [
                PaletteItem(id: "a-star", title: L("Star or Unstar"), subtitle: sub, symbol: "star", tint: .gold, run: { Task { await store.starSelected() } }),
                PaletteItem(id: "a-again", title: L("Train Again with These Settings"), subtitle: sub, symbol: "arrow.clockwise", tint: .brand, run: { Task { await store.trainAgainSelected() } }),
                PaletteItem(id: "a-try", title: L("Try This Model"), subtitle: sub, symbol: "eye", tint: .mixup, run: { store.trySelected() }),
                PaletteItem(id: "a-review", title: L("Check Mistakes in Review"), subtitle: sub, symbol: "checkmark.rectangle.stack", tint: .good, run: { store.reviewSelected() }),
            ]
        }
        out.append(PaletteItem(id: "keys", title: L("Keyboard Shortcuts"), subtitle: L("Help"), symbol: "keyboard", tint: .info, run: { store.showShortcuts = true }))
        let starred = store.runs.filter { $0.meta?.star == true }.map(\.id)
        if starred.count >= 2 {
            out.append(PaletteItem(id: "cmp", title: L("Compare starred runs"), subtitle: L("Action"), symbol: "square.stack.3d.up",
                                   tint: .gold, run: { store.pendingCompare = starred; store.section = .runs }))
        }
        out += store.runs.map { r in
            PaletteItem(id: r.id, title: r.displayName,
                        subtitle: [r.stateText, r.best.map { String(format: "%.3f", $0) } ?? "", r.source].filter { !$0.isEmpty }.joined(separator: " · "),
                        symbol: r.meta?.star == true ? "star.fill" : r.symbol, tint: r.tint, run: { store.open(run: r.id) })
        }
        guard !query.isEmpty else { return Array(out.prefix(14)) }
        // 글자가 순서대로 들어 있으면 맞다(느슨한 검색). 앞에서 맞을수록 위로
        let q = query.lowercased()
        func score(_ t: String) -> Int? {
            let s = t.lowercased()
            if let r = s.range(of: q) { return s.distance(from: s.startIndex, to: r.lowerBound) }    // 붙어 있으면 앞일수록 위
            var i = s.startIndex                                                                    // 떨어져 있어도 순서대로면 맞다
            for ch in q {
                guard let f = s[i...].firstIndex(of: ch) else { return nil }
                i = s.index(after: f)
            }
            return 100
        }
        return out.compactMap { i in score(i.title + " " + i.subtitle).map { (i, $0) } }.sorted { $0.1 < $1.1 }.map(\.0).prefix(20).map { $0 }
    }

    var body: some View {
        let list = items
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass").foregroundStyle(ink.soft)
                TextField("Go to a run or screen, or run an action", text: $query)
                    .textFieldStyle(.plain).font(.ui(16)).focused($focused)
                    .onSubmit { pick(list) }
                    .onChange(of: query) { index = 0 }
                Text(verbatim: "esc").font(.ui(11, design: .monospaced)).foregroundStyle(ink.soft)
                    .padding(.horizontal, 5).background(.quaternary, in: .rect(cornerRadius: 4))
            }
            .padding(14)
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 2) {
                        ForEach(Array(list.enumerated()), id: \.element.id) { i, item in
                            row(item, on: i == index)
                                .id(i)
                                .onTapGesture { index = i; pick(list) }
                                .onHover { if $0 { index = i } }
                        }
                        if list.isEmpty {
                            Text("Nothing matches").font(.ui(13)).foregroundStyle(ink.soft).padding(30)
                        }
                    }
                    .padding(6)
                }
                .onChange(of: index) { _, i in withAnimation(Motion.tap) { proxy.scrollTo(i) } }
            }
            .frame(maxHeight: 380)
        }
        .frame(width: 560)
        .onAppear { focused = true }
        .onKeyPress(.downArrow) { index = min(index + 1, max(list.count - 1, 0)); return .handled }
        .onKeyPress(.upArrow) { index = max(index - 1, 0); return .handled }
        .onKeyPress(.escape) { dismiss(); return .handled }
    }

    private func row(_ item: PaletteItem, on: Bool) -> some View {
        HStack(spacing: 10) {
            Image(systemName: item.symbol).font(.ui(13, weight: .semibold)).foregroundStyle(item.tint)
                .frame(width: 28, height: 28).background(item.tint.opacity(0.14), in: .rect(cornerRadius: 7))
            VStack(alignment: .leading, spacing: 1) {
                Text(verbatim: item.title).font(.ui(13.5, weight: .medium)).lineLimit(1)
                Text(verbatim: item.subtitle).font(.ui(11.5)).foregroundStyle(ink.soft).lineLimit(1)
            }
            Spacer()
            if on { Image(systemName: "return").font(.ui(11)).foregroundStyle(ink.soft).transition(.opacity) }
        }
        .padding(.horizontal, 8).padding(.vertical, 6)
        .background(on ? AnyShapeStyle(.tint.opacity(0.14)) : AnyShapeStyle(.clear), in: .rect(cornerRadius: 8))
        .contentShape(.rect)
        .animation(Motion.tap, value: on)
    }

    private func pick(_ list: [PaletteItem]) {
        guard list.indices.contains(index) else { return }
        list[index].run()
        dismiss()
    }
}
