import SwiftUI

// 무작위·똑똑한 스윕에 설정을 더 넣는 줄(최대 3줄 더 = 모두 4개). 줄마다 범위(낮음~높음, 로그) 또는 값 목록(optimizer 같은 것).
// agent의 sweep.expand·tpe.suggest가 섞인 공간을 그대로 받는다.

struct SpaceRow: Identifiable, Hashable {
    let id = UUID()
    var key = "batch"
    var range = true
    var low = "8"
    var high = "32"
    var log = false
    var values = "SGD, AdamW"

    static let intKeys: Set<String> = ["imgsz", "batch", "epochs"]
    static let listOnly: Set<String> = ["optimizer", "model"]

    /// agent로 보낼 모양. 틀리면 nil과 이유
    func space() -> ([String: Any]?, String?) {
        if range && !Self.listOnly.contains(key) {
            guard let lo = Double(low), let hi = Double(high), lo < hi else { return (nil, L("Give a range where the low value is smaller than the high value.")) }
            if log && lo <= 0 { return (nil, L("A log scale needs a low value above 0.")) }
            return (["key": key, "low": lo, "high": hi, "log": log, "int": Self.intKeys.contains(key)], nil)
        }
        let vs = values.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        return vs.isEmpty ? (nil, L("Give at least one value.")) : (["key": key, "values": vs], nil)
    }
}

struct SpaceRowsEditor: View {
    @Binding var rows: [SpaceRow]
    let taken: Set<String>                         // 이미 첫 줄에서 쓴 설정
    @Environment(\.ink) private var ink

    private var free: [(String, LocalizedStringKey)] { TrainView.sweepKeys.filter { !taken.contains($0.0) } }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach($rows) { $r in
                HStack(spacing: 8) {
                    Picker("Setting", selection: $r.key) {
                        ForEach(free.filter { k in k.0 == r.key || !rows.contains { $0.key == k.0 } }, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    .labelsHidden().frame(width: 200)
                    .onChange(of: r.key) { _, k in if SpaceRow.listOnly.contains(k) { r.range = false } }
                    if !SpaceRow.listOnly.contains(r.key) {
                        Picker("", selection: $r.range.animation(Motion.change)) { Text("Range").tag(true); Text("Values").tag(false) }
                            .pickerStyle(.segmented).labelsHidden().frame(width: 130)
                    }
                    if r.range && !SpaceRow.listOnly.contains(r.key) {
                        TextField("From", text: $r.low).textFieldStyle(.roundedBorder).frame(width: 80)
                        Image(systemName: "arrow.right").foregroundStyle(ink.faint)
                        TextField("To", text: $r.high).textFieldStyle(.roundedBorder).frame(width: 80)
                        Toggle("Log", isOn: $r.log).toggleStyle(.checkbox)
                    } else {
                        TextField("Values, separated by commas", text: $r.values).textFieldStyle(.roundedBorder)
                    }
                    IconButton(symbol: "minus.circle", help: "Remove this setting") {
                        withAnimation(Motion.change) { rows.removeAll { $0.id == r.id } }
                    }
                }
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
            if rows.count < 3, let next = free.first(where: { k in !rows.contains { $0.key == k.0 } }) {
                Button {
                    withAnimation(Motion.change) {
                        var r = SpaceRow(key: next.0)
                        if SpaceRow.listOnly.contains(next.0) { r.range = false; r.values = next.0 == "model" ? "n, s" : "SGD, AdamW" }
                        rows.append(r)
                    }
                } label: { Label("Add a setting", systemImage: "plus.circle") }
                .buttonStyle(BrandLink())
                .help("Search several settings at once (up to 4). Smart search learns how they work together.")
            }
        }
    }
}
