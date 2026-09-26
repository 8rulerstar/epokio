import SwiftUI

// 클래스가 10개를 넘을 때. 숫자키는 0~9뿐이라 그대로는 11번째부터 못 고른다.
// 고른 방법 두 가지(하나만 고르지 않은 이유는 LabelViewer 주석에):
//   ① 10칸 묶음(페이지): 숫자키는 늘 "지금 묶음의 0~9". [ ] 로 묶음을 넘긴다. 클래스가 10개 이하면 예전과 똑같이 동작한다
//   ② 이름으로 찾기(C): 검색창 + 목록. 이름을 아는 쪽이 빠른 사람을 위해

/// 클래스 번호와 이름 짝. 라벨에만 있고 이름표에 없는 번호도 빠뜨리지 않는다
func classList(_ names: [String: String], used: [Int]) -> [(id: Int, name: String)] {
    let known = names.compactMap { k, v in Int(k).map { (id: $0, name: v) } }
    let extra = Set(used).subtracting(known.map(\.id)).map { (id: $0, name: "\($0)") }
    return (known + extra).sorted { $0.id < $1.id }
}

/// 지금 묶음(10개)을 숫자키 힌트와 같이 보여 준다
struct ClassPageBar: View {
    let classes: [(id: Int, name: String)]
    @Binding var page: Int
    @Binding var pick: Int
    let onPick: (Int) -> Void
    @Environment(\.ink) private var ink

    var pages: Int { max(1, (classes.count + 9) / 10) }
    private var slice: [(id: Int, name: String)] {
        let start = min(page, pages - 1) * 10
        return Array(classes[start..<min(start + 10, classes.count)])
    }

    var body: some View {
        HStack(spacing: 6) {
            if pages > 1 {
                IconButton(symbol: "chevron.left", help: "Previous 10 classes ([)") { step(-1) }
                    .disabled(page <= 0)
            }
            ForEach(Array(slice.enumerated()), id: \.element.id) { i, c in
                ClassChip(digit: i, cls: c, on: pick == c.id) { onPick(c.id) }
            }
            if pages > 1 {
                IconButton(symbol: "chevron.right", help: "Next 10 classes (])") { step(1) }
                    .disabled(page >= pages - 1)
                Text(verbatim: "\(min(page, pages - 1) + 1)/\(pages)")
                    .font(.ui(11, design: .monospaced)).foregroundStyle(ink.soft)
                    .contentTransition(.numericText())
                    .accessibilityLabel(L("Class page %lld of %lld", page + 1, pages))
            }
        }
        .animation(Motion.change, value: page)
    }

    private func step(_ d: Int) {
        withAnimation(Motion.change) { page = min(max(page + d, 0), pages - 1) }
        Haptic.tick()
    }
}

/// 숫자키 힌트가 붙은 클래스 한 칸
private struct ClassChip: View {
    let digit: Int
    let cls: (id: Int, name: String)
    let on: Bool
    let action: () -> Void
    @State private var hover = false
    @Environment(\.ink) private var ink

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Text(verbatim: "\(digit)")
                    .font(.ui(10, weight: .bold, design: .monospaced))
                    .foregroundStyle(on ? AnyShapeStyle(.white) : ink.soft)
                Text(verbatim: cls.name).font(.ui(11.5, weight: on ? .semibold : .regular)).lineLimit(1)
            }
            .padding(.horizontal, 7).padding(.vertical, 3)
            .background(on ? AnyShapeStyle(Color.brand) : AnyShapeStyle(hover ? .quaternary : .quinary),
                        in: .rect(cornerRadius: 6))
            .foregroundStyle(on ? AnyShapeStyle(.white) : AnyShapeStyle(.primary))
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(L("%lld  %@ (press %lld)", cls.id, cls.name, digit))
        .animation(Motion.tap, value: on)
    }
}

/// 이름으로 찾아 고르기. 클래스가 많을 때 숫자·묶음을 외우지 않아도 된다
struct ClassSearchPalette: View {
    let classes: [(id: Int, name: String)]
    let onPick: (Int) -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.ink) private var ink
    @State private var query = ""
    @FocusState private var focused: Bool

    private var hits: [(id: Int, name: String)] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        guard !q.isEmpty else { return classes }
        return classes.filter { $0.name.lowercased().contains(q) || "\($0.id)" == q }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass").foregroundStyle(ink.soft).accessibilityHidden(true)
                TextField("Find a class", text: $query)
                    .textFieldStyle(.plain).font(.ui(13)).focused($focused)
                    .onSubmit { if let f = hits.first { pick(f.id) } }
            }
            .padding(10)
            Divider()
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 1) {
                    ForEach(Array(hits.enumerated()), id: \.element.id) { i, c in
                        PaletteRow(cls: c) { pick(c.id) }
                            .appearRise(min(i, 11))
                    }
                    if hits.isEmpty {
                        Text("No class matches.").font(.ui(12)).foregroundStyle(ink.soft).padding(10)
                    }
                }
                .padding(6)
                .animation(Motion.change, value: hits.map(\.id))
            }
            .frame(height: 220)
        }
        .frame(width: 260)
        .onAppear { focused = true }
    }

    private func pick(_ id: Int) { onPick(id); Haptic.tick(); dismiss() }
}

private struct PaletteRow: View {
    let cls: (id: Int, name: String)
    let action: () -> Void
    @State private var hover = false
    @Environment(\.ink) private var ink

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Text(verbatim: "\(cls.id)")
                    .font(.ui(11, design: .monospaced)).foregroundStyle(ink.soft).frame(width: 22, alignment: .trailing)
                Text(verbatim: cls.name).font(.ui(12.5)).lineLimit(1)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 6).padding(.vertical, 5)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(hover ? AnyShapeStyle(.quaternary) : AnyShapeStyle(.clear), in: .rect(cornerRadius: 5))
            .contentShape(.rect)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
    }
}
