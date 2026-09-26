import SwiftUI

// 결과 화면(상세·비교)이 같이 쓰는 부품과 이름 풀이.

struct SectionTitle: View {
    let title: LocalizedStringKey
    let hint: String?
    @Environment(\.ink) private var ink
    init(_ title: LocalizedStringKey, hint: String?) { self.title = title; self.hint = hint }
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.ui(14, weight: .semibold))
            if let hint { Text(verbatim: hint).font(.ui(11.5)).foregroundStyle(ink.soft) }
        }
    }
}

struct MetricTile: View {
    let name: String
    let value: Double?
    let hint: String
    var strong = false
    var integer = false
    @AppStorage(Fmt.scoreKey) private var scoreStyle = "3"   // 바꾸면 바로 다시 그린다
    @Environment(\.ink) private var ink
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value.map { integer ? "\(Int($0))" : Fmt.score($0, style: scoreStyle) } ?? "–")
                .font(.ui(17, weight: strong ? .bold : .semibold, design: .rounded))
                .lineLimit(1).minimumScaleFactor(0.7)
                .foregroundStyle(strong ? AnyShapeStyle(.tint) : AnyShapeStyle(.primary))
                .contentTransition(.numericText())
            Text(verbatim: name).font(.ui(11)).foregroundStyle(ink.soft).lineLimit(1).minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 10).padding(.vertical, 8)
        .background(.quaternary.opacity(strong ? 0.55 : 0.3), in: .rect(cornerRadius: Radius.control))
        .hoverLift(1.03)
        .help(hint)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(verbatim: name))
        .accessibilityValue(Text(verbatim: value.map { integer ? "\(Int($0))" : Fmt.score($0, style: scoreStyle) } ?? L("No value")))
        .accessibilityHint(Text(verbatim: hint))
    }
}

/// 열 이름을 사람 말로. ★agent의 column_info가 없을 때(옛 agent·여러 학습 비교)만 쓰는 예비 규칙. 기본은 RunDetail.label
func prettyColumn(_ k: String) -> String {
    var s = k.replacingOccurrences(of: "metrics/", with: "")
    // "train/box_loss" → "train box"(울트라리틱스). ★"val_loss"·"eval_loss"(케라스·HF)까지 잘라 "val"·"eval"이 됐다
    s = s.contains("/") ? s.replacingOccurrences(of: "_loss", with: "") : s.replacingOccurrences(of: "_", with: " ")
    for (code, name) in [("(B)", L("Box")), ("(P)", L("Pose")), ("(M)", L("Mask"))] {
        s = s.replacingOccurrences(of: code, with: " · " + name)
    }
    return s.replacingOccurrences(of: "/", with: " ")
}

/// 그림 파일 이름을 사람 말로
func imageTitle(_ name: String) -> String {
    let known: [String: String] = [
        "results.png": L("All curves"), "confusion_matrix_normalized.png": L("Confusion matrix (normalized)"),
        "confusion_matrix.png": L("Confusion matrix"), "labels.jpg": L("Label statistics"),
        "BoxPR_curve.png": L("Precision–recall (Box)"), "BoxF1_curve.png": L("F1 by confidence (Box)"),
        "BoxP_curve.png": L("Precision by confidence (Box)"), "BoxR_curve.png": L("Recall by confidence (Box)"),
        "PosePR_curve.png": L("Precision–recall (Pose)"), "PoseF1_curve.png": L("F1 by confidence (Pose)"),
        "MaskPR_curve.png": L("Precision–recall (Mask)"), "MaskF1_curve.png": L("F1 by confidence (Mask)"),
    ]
    if let k = known[name] { return k }
    if name.hasPrefix("val_batch") { return name.contains("_pred") ? L("Validation: model predictions") : L("Validation: your labels") }
    if name.hasPrefix("train_batch") { return L("Training batch sample") }
    if name.hasPrefix("epokio_media/") {                   // epokio.image()로 남긴 그림: "predictions · epoch 3"
        let base = String(name.dropFirst("epokio_media/".count).dropLast(4))
        if let r = base.range(of: #"_e(\d{4})$"#, options: .regularExpression), let e = Int(base[r].dropFirst(2)) {
            return base[..<r.lowerBound].replacingOccurrences(of: "_", with: " ") + " · " + L("epoch %@", String(e))
        }
        return base.replacingOccurrences(of: "_", with: " ")
    }
    return name
}

// ── 비교 ─────────────────────────────────────────────

/// 잠깐 뜨는 알림 띠. 실패는 주황, 완료는 초록. 위에서 내려오고 저절로 사라진다
/// 접근성: 뜰 때 VoiceOver가 읽는다(사라지기 전에). 실패는 색 말고 "실패:" 글자로도 구분한다
struct ToastView: View {
    @Environment(Store.self) private var store
    private func spoken(_ t: Store.Toast) -> String {
        var s = t.bad ? L("Failed: %@", t.text) : t.text
        if let a = t.actionTitle, t.action != nil { s += ". " + L("%@ with Command-Z", a) }
        return s
    }
    var body: some View {
        VStack {
            if let t = store.toast {
                HStack(spacing: 10) {
                    Label(t.bad ? L("Failed: %@", t.text) : t.text, systemImage: t.bad ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                        .font(.role(.callout, weight: .medium))
                        .foregroundStyle(t.bad ? .warn : .good)
                        .lineLimit(3)
                    if let title = t.actionTitle, let act = t.action {
                        Button(title) { act(); store.toast = nil }
                            .buttonStyle(.borderless).font(.role(.callout, weight: .semibold))
                            .keyboardShortcut("z", modifiers: .command)
                    }
                }
                    .padding(.horizontal, 14).padding(.vertical, 9)
                    .glass(Capsule(), tint: t.bad ? .bad.opacity(0.25) : .good.opacity(0.2))
                    .overlay(Capsule().strokeBorder((t.bad ? Color.warn : .good).opacity(0.35), lineWidth: 1))
                    .shadow(color: .black.opacity(0.12), radius: 8, y: 3)
                    .onTapGesture { store.toast = nil }
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .id(t.id)
            }
            Spacer()
        }
        .padding(.top, 10)
        .animation(Motion.celebrate, value: store.toast)
        .onChange(of: store.toast) { _, t in
            if let t { AccessibilityNotification.Announcement(spoken(t)).post() }
        }
        .allowsHitTesting(store.toast != nil)
    }
}
