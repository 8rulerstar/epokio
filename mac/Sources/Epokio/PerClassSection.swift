import SwiftUI

// 학습 상세의 클래스별 성능. 계산은 agent(classes.py). 없으면 "클래스별 점수 계산"이 best.pt 검증을 대기열에 넣는다.

struct RunClasses: Codable, Hashable {
    let source: String?             // train(학습 끝에 저장) · val(best.pt로 따로 검증)
    let heads: [Head]
    struct Head: Codable, Hashable {
        let head: String            // box · pose · mask · obb
        let main: String            // mAP50-95 (없으면 mAP50)
        let mean: Double?
        let rows: [Row]
    }
    struct Row: Codable, Hashable {
        let name: String
        let instances: Int?
        let precision: Double?
        let recall: Double?
        let mAP50: Double?
        let map5095: Double?
        let weak: Bool
        let few: Bool
        enum CodingKeys: String, CodingKey { case name, instances, precision, recall, mAP50, map5095 = "mAP50-95", weak, few }
        func main(_ key: String) -> Double? { key == "mAP50" ? mAP50 : map5095 }
    }
}

struct PerClassSection: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @Environment(\.accessibilityReduceMotion) private var reduce
    let run: Run
    let classes: RunClasses?
    @State private var shown = false
    @State private var queued = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let c = classes {
                SectionTitle("Per class", hint: (c.source == "val" ? L("From a validation pass with best.pt.") : L("From the last validation of this run."))
                             + " " + L("Weakest first. Highlighted: well below the class average."))
                ForEach(c.heads, id: \.head) { h in
                    if c.heads.count > 1 { Text(verbatim: h.head.capitalized).font(.ui(12, weight: .semibold)).padding(.top, 2) }
                    VStack(spacing: 2) {
                        ForEach(Array(h.rows.enumerated()), id: \.element.name) { i, r in
                            ClassRow(row: r, main: h.main)
                                .opacity(shown ? 1 : 0).offset(y: shown ? 0 : 6)
                                .animation(reduce ? nil : Motion.appear.delay(Double(min(i, 12)) * 0.03), value: shown)
                        }
                    }
                    if let m = h.mean {
                        Text(verbatim: L("Class average") + ": " + String(format: "%.3f", m)).font(.ui(11.5)).foregroundStyle(ink.soft)
                    }
                }
            } else {
                SectionTitle("Per class", hint: L("Which classes pull the score down. Runs Epokio starts save this at the end; for this one it takes one validation pass with best.pt."))
                Button(queued ? L("Added to the queue. The table appears here when it finishes.") : L("Work out per-class scores")) {
                    Task {
                        await store.act(L("Added to the queue. The table appears here when it finishes.")) {
                            _ = try await store.client(for: run).post("classes", ["path": run.path])
                        }
                        withAnimation(reduce ? nil : Motion.change) { queued = true }
                    }
                }
                .disabled(queued)
            }
        }
        .onAppear { shown = true }
    }
}

private struct ClassRow: View {
    @Environment(\.ink) private var ink
    @Environment(\.accessibilityReduceMotion) private var reduce
    let row: RunClasses.Row
    let main: String
    @State private var hover = false

    var body: some View {
        let v = row.main(main)
        HStack(spacing: 10) {
            HStack(spacing: 5) {
                Text(verbatim: row.name).font(.ui(12.5, weight: row.weak ? .semibold : .regular)).lineLimit(1)
                if row.few {
                    Text("few").font(.ui(10, weight: .semibold)).padding(.horizontal, 5).padding(.vertical, 1)
                        .background(Color.warn.opacity(0.15), in: .capsule).foregroundStyle(.warn)
                        .help(L("Few examples: the score is shaky"))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text(verbatim: row.instances.map(String.init) ?? "–").font(.ui(11.5, design: .monospaced)).foregroundStyle(ink.soft)
                .frame(width: 44, alignment: .trailing).help(L("Examples"))
            ProgressView(value: min(max(v ?? 0, 0), 1)).tint(row.weak ? Color.warn : Color.brand).frame(width: 90)
            Text(verbatim: v.map { String(format: "%.3f", $0) } ?? "–").font(.ui(12, weight: .semibold, design: .monospaced))
                .foregroundStyle(row.weak ? Color.warn : Color.primary).frame(width: 46, alignment: .trailing)
        }
        .padding(.vertical, 4).padding(.horizontal, 8)
        .background(Color.primary.opacity(hover ? 0.06 : 0), in: .rect(cornerRadius: 6))
        .onHover { h in withAnimation(reduce ? nil : Motion.hover) { hover = h } }
        .help([("Precision", row.precision), ("Recall", row.recall), ("mAP50", row.mAP50)]
            .map { L($0.0) + " " + ($0.1.map { String(format: "%.3f", $0) } ?? "–") }.joined(separator: " · "))
        .accessibilityElement(children: .combine)
    }
}
