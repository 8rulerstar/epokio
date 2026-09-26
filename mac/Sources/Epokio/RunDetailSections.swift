import SwiftUI

// 학습 상세의 "자세히" 칸들: 성적, 해설, 결과 이미지, 사용한 설정과 버전.

extension RunDetailView {
    // 종류별 성적
    func scores(_ d: RunDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Scores", hint: L("At the best epoch. Higher is better."))
            ForEach(d.heads, id: \.head) { h in
                if d.heads.count > 1 { Text(verbatim: h.title).font(.ui(12, weight: .semibold)).padding(.top, 2) }
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 96), spacing: 8)], spacing: 8) {
                    MetricTile(name: L("Precision"), value: h.precision, hint: L("Of what it found, how much was right"))
                    MetricTile(name: L("Recall"), value: h.recall, hint: L("Of what was there, how much it found"))
                    MetricTile(name: "F1", value: h.f1, hint: L("Balance of precision and recall"), strong: true)
                    MetricTile(name: "mAP50", value: h.map50, hint: L("Box overlap 50% or more counts as a hit"))
                    MetricTile(name: "mAP50-95", value: h.map5095, hint: L("Stricter: averaged over 50 to 95% overlap"))
                    MetricTile(name: L("Best epoch"), value: Double(h.best_epoch), hint: "", integer: true)
                }
            }
        }
    }

    /// YOLO가 아닌 프레임워크: 점수 열마다 최고값과 그 에폭
    func genericScores(_ d: RunDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Scores", hint: L("Best value of each score and the epoch it came at."))
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), spacing: 8)], spacing: 8) {
                ForEach(d.scoreKeys, id: \.self) { k in
                    let vals = Array(zip(d.epochs, d.columns[k] ?? []))
                    let best = vals.compactMap { e, v in v.map { (e, $0) } }.max { d.higher(k) ? $0.1 < $1.1 : $0.1 > $1.1 }
                    MetricTile(name: d.label(k) + (best.map { "  ·  " + L("epoch %@", "\(Int($0.0))") } ?? ""),
                               value: best?.1, hint: k, strong: k == run.metric_name)
                }
            }
        }
    }

    func notes(_ d: RunDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("What stands out", hint: nil)
            ForEach(d.notes.dropFirst(), id: \.self) { n in
                VStack(alignment: .leading, spacing: 4) {
                    Label(n.observation, systemImage: "lightbulb.fill").foregroundStyle(.primary)
                        .symbolRenderingMode(.multicolor)
                    Text(verbatim: "→ " + n.try).font(.ui(12.5)).foregroundStyle(ink.soft).padding(.leading, 26)
                    if let c = n.next, !c.isEmpty { NextRunButton(change: c, detail: d, run: run).padding(.leading, 26) }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
                .background(.gold.opacity(0.08), in: .rect(cornerRadius: 10))
                .tip()
            }
        }
    }

    func gallery(_ d: RunDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Result images", hint: L("Charts and predictions saved by the framework. Click to enlarge."))
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 10)], spacing: 10) {
                ForEach(d.images, id: \.self) { name in
                    Button { bigImage = name } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            AsyncImage(url: imageURL(name)) { img in img.resizable().scaledToFit() }
                                placeholder: { Rectangle().fill(.quaternary.opacity(0.4)).overlay(ProgressView().controlSize(.small)) }
                                .frame(height: 130).frame(maxWidth: .infinity)
                                .clipShape(.rect(cornerRadius: 8))
                            Text(verbatim: imageTitle(name)).font(.ui(11.5)).foregroundStyle(ink.soft).lineLimit(1)
                        }
                        .padding(6)
                        .background(.quaternary.opacity(0.3), in: .rect(cornerRadius: 10))
                    }
                    .buttonStyle(PressStyle())
                }
            }
        }
    }

    func settings(_ d: RunDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Settings used", hint: nil)
            if let v = d.versions, v.data != nil || v.model != nil {
                HStack(spacing: 16) {
                    if let fp = v.data { Label(L("Data %@", fp), systemImage: "tray.full").help("Data version: changes when any image or label changes") }
                    if let fp = v.model { Label(L("Model %@", fp), systemImage: "cube").help("Model version (best.pt)") }
                }
                .font(.ui(12, design: .monospaced)).foregroundStyle(ink.soft)
                if let same = v.same_data, !same.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Label(L("Same data as %d other runs", same.count), systemImage: "equal.circle").font(.ui(12, weight: .medium))
                        ForEach(same.prefix(6), id: \.path) { o in
                            Button { store.selectedRun = "\(run.source)|\(o.path)" } label: {
                                Text(verbatim: URL(fileURLWithPath: o.path).deletingLastPathComponent().lastPathComponent + "/" + o.name)
                                    .font(.ui(12)).lineLimit(1)
                            }
                            .buttonStyle(BrandLink())
                        }
                    }
                }
            }
            // ★Grid는 긴 경로 값의 원래 폭만큼 늘어나 상세 화면이 창보다 넓어졌다(왼쪽이 잘림). 줄마다 폭을 맞춘다
            VStack(alignment: .leading, spacing: 4) {
                ForEach(d.args.sorted(by: { $0.key < $1.key }), id: \.key) { k, v in
                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                        Text(verbatim: k).font(.ui(11.5, design: .monospaced)).foregroundStyle(ink.soft)
                            .lineLimit(1).fixedSize()
                            .frame(minWidth: 110, alignment: .leading)
                        Text(verbatim: v).font(.ui(11.5, design: .monospaced)).textSelection(.enabled)
                            .lineLimit(1).truncationMode(.middle)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.quaternary.opacity(0.3), in: .rect(cornerRadius: 10))
        }
    }
}

struct ImageRef: Identifiable { let name: String; var id: String { name } }

struct BigImage: View {
    let url: URL?
    let name: String
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(spacing: 10) {
            HStack {
                Text(verbatim: imageTitle(name)).font(.ui(13, weight: .semibold))
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            AsyncImage(url: url) { $0.resizable().scaledToFit() } placeholder: { ProgressView() }
                .frame(minWidth: 640, minHeight: 440)
        }
        .padding(16)
        .frame(minWidth: 720, idealWidth: 960, minHeight: 540, idealHeight: 720)
    }
}

/// 해설 아래 "다음 학습" 버튼: 바꿀 설정을 보여 주고, 누르면 이 학습 설정 + 그 변화로 새 학습 양식을 채운다
/// (Ultralytics Platform의 "다음 학습 제안"을 규칙으로, 인터넷 없이. 규칙은 agent의 analysis.next_run)
struct NextRunButton: View {
    let change: [String: SweepSummary.Value]
    let detail: RunDetail
    let run: Run
    @Environment(Store.self) private var store
    @State private var hover = false

    private var summary: String {
        change.keys.sorted().map { k -> String in
            let new = change[k]!.description
            if k == "weights" { return L("from %@", URL(fileURLWithPath: new).lastPathComponent) }
            if let old = detail.args[k], old != new { return "\(k) \(old) → \(new)" }
            return "\(k) \(new)"
        }.joined(separator: " · ")
    }

    var body: some View {
        Button {
            var a = detail.args
            for (k, v) in change { a[k] = v.description }
            store.pendingTrainArgs = a
            withAnimation(Motion.change) { store.section = .train }
            Haptic.tick()
        } label: {
            Label(L("Try: %@", summary), systemImage: "play.circle.fill")
                .font(.role(.caption, weight: .semibold)).lineLimit(1).truncationMode(.middle)
                .padding(.horizontal, 10).padding(.vertical, 5)
                .foregroundStyle(hover ? AnyShapeStyle(.white) : AnyShapeStyle(.brand))
                .background(hover ? AnyShapeStyle(LinearGradient.brand) : AnyShapeStyle(Color.brand.opacity(0.12)), in: Capsule())
                .scaleEffect(hover ? 1.03 : 1)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .disabled(!store.isLocal(run))
        .help(store.isLocal(run) ? L("Opens New Training with this run's settings and this change. Nothing starts until you press Start.")
                                  : L("Only on the machine that has this run"))
        .transition(.scale(scale: 0.9).combined(with: .opacity))
    }
}
