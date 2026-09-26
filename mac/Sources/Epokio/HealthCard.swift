import SwiftUI

// 데이터셋 건강 검진 결과. data.yaml을 떨어뜨리면 학습 전에 문제를 짚는다.
struct HealthReport: Decodable {
    struct Split: Decodable { let images: Int; let missing_labels: Int; let empty_labels: Int; let bad_rows: Int }
    struct Warn: Decodable, Hashable { let level: String; let text: String }
    let ok: Bool
    let data: String?                  // 실제로 읽은 data.yaml (폴더를 주면 그 안에서 찾은 것)
    let score: String?
    let classes: [String]?
    let splits: [String: Split]?
    let warnings: [Warn]?
    let tips: [String]?
    let per_class: [String: Int]?
    let error: String?
}

struct HealthCard: View {
    @Environment(\.ink) private var ink
    let data: URL
    var client = AgentClient.local                       // 원격 기계에서 학습할 때는 그 기계가 검진한다
    var remotePath: String? = nil                        // 원격이면 사용자가 적은 그 기계 기준 경로 그대로(윈도우 D:\...)
    @State private var report: HealthReport?
    @State private var loading = true
    @State private var failed: String?                  // 검진 요청이 실패한 이유

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: icon).foregroundStyle(tint).font(.ui(16, weight: .semibold))
                    .symbolEffect(.bounce, value: report?.score)
                    .accessibilityHidden(true)
                Text(title).font(.ui(13, weight: .semibold))
                Spacer()
                if loading { ProgressView().controlSize(.small) }
            }
            if let r = report, r.ok {
                HStack(spacing: 18) {
                    stat(r.splits?["train"]?.images ?? 0, "train")
                    stat(r.splits?["val"]?.images ?? 0, "validation")
                    stat(r.classes?.count ?? 0, "classes")
                    stat(r.per_class?.values.reduce(0, +) ?? 0, "boxes")
                }
                ForEach(r.warnings ?? [], id: \.self) { w in
                    Label(w.text, systemImage: w.level == "error" ? "xmark.octagon.fill" : "exclamationmark.triangle.fill")
                        .foregroundStyle(w.level == "error" ? .bad : .warn)
                        .font(.ui(11.5)).fixedSize(horizontal: false, vertical: true)
                }
                ForEach(r.tips ?? [], id: \.self) { t in
                    Label(t, systemImage: "lightbulb").font(.ui(11.5)).foregroundStyle(ink.soft)
                        .fixedSize(horizontal: false, vertical: true)
                        .tip()
                }
            } else if let e = report?.error {
                Label(e, systemImage: "xmark.octagon").font(.ui(11.5)).foregroundStyle(.bad)
            }
            // ★실패하면 '검사하는 중…'에서 멈춘 채 아무 말도 없었다(원격 기계의 토큰이 틀리면 늘 그랬다)
            if let failed, !loading {
                HStack {
                    Label(failed, systemImage: "exclamationmark.triangle").font(.ui(11.5)).foregroundStyle(.warn)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    Button("Try Again") { Task { await load() } }.controlSize(.small)
                }
            }
        }
        .padding(14)
        .background(tint.opacity(0.07), in: .rect(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(tint.opacity(0.25)))
        .animation(.smooth, value: report?.score)
        .task(id: data) { await load() }
    }

    private var tint: Color {
        switch report?.score { case "good": .good; case "problems": .bad; case "check": .warn; default: .secondary }
    }
    private var icon: String {
        switch report?.score { case "good": "checkmark.seal.fill"; case "problems": "xmark.octagon.fill"; case "check": "exclamationmark.triangle.fill"; default: "stethoscope" }
    }
    private var title: LocalizedStringKey {
        switch report?.score {
        case "good": "Your dataset looks healthy"
        case "problems": "Fix these before training"
        case "check": "Worth a look before training"
        default: failed != nil && !loading ? "Could not check this dataset" : "Checking your dataset…"
        }
    }
    private func stat(_ n: Int, _ l: LocalizedStringKey) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("\(n)").font(.ui(15, weight: .bold, design: .rounded)).contentTransition(.numericText())
            Text(l).font(.ui(11)).foregroundStyle(ink.soft)
        }
        .accessibilityElement(children: .combine)
    }
    private func load() async {
        loading = true; defer { loading = false }
        do { report = try await client.get("health-check", ["data": remotePath ?? data.path]); failed = nil }
        catch { failed = (error as? AgentError ?? AgentError.bad).localizedDescription }
    }
}
