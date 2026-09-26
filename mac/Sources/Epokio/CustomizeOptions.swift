import SwiftUI

// 설정 → 꾸미기의 "보기" 칸: 점수 형식 · 시각 형식 · 곡선 두께 · 목록 밀도 · 처음 열 화면.
// 키·기본값·포맷 함수를 여기 모은다. 화면들은 Fmt.* 나 키를 읽기만 한다.

enum Fmt {
    /// "2" "3" "4" 소수 자릿수, "pct" 백분율. 기본 "3"
    static let scoreKey = "scoreStyle", timeKey = "clockStyle"
    static func score(_ v: Double, style: String? = nil) -> String {
        switch style ?? UserDefaults.standard.string(forKey: scoreKey) ?? "3" {
        case "2": String(format: "%.2f", v)
        case "4": String(format: "%.4f", v)
        case "pct": String(format: "%.1f%%", v * 100)
        default: String(format: "%.3f", v)
        }
    }
    /// 낮을수록 좋은 지표(손실 등)는 백분율·자릿수 설정을 따르지 않는다
    static func metric(_ v: Double, higher: Bool, style: String? = nil, raw: String = "%.4f") -> String {
        higher ? score(v, style: style) : String(format: raw, v)
    }
    /// "system" "12" "24". 기본 system
    static func time(_ d: Date, style: String? = nil) -> String {
        switch style ?? UserDefaults.standard.string(forKey: timeKey) ?? "system" {
        case "12": let f = DateFormatter(); f.dateFormat = "h:mm a"; return f.string(from: d)
        case "24": let f = DateFormatter(); f.dateFormat = "HH:mm"; return f.string(from: d)
        default: return d.formatted(date: .omitted, time: .shortened)
        }
    }
}

enum ViewPrefs {
    static let curveWidthKey = "curveWidth", densityKey = "rowDensity", startKey = "startScreen"
    /// 목록 한 줄 위아래 여백. compact / regular / roomy
    static func rowPadding(_ raw: String) -> CGFloat { raw == "compact" ? 1 : raw == "roomy" ? 7 : 3 }
    static let starts: [Studio.Section] = [.home, .runs, .train, .review]
    @MainActor private static var applied = false
    /// Studio를 처음 열 때 한 번만. 다른 곳(알림·명령)이 이미 화면을 골랐으면 건드리지 않는다
    @MainActor static func applyStart(_ store: Store) {
        guard !applied else { return }
        applied = true
        let raw = UserDefaults.standard.string(forKey: startKey) ?? "Home"
        if store.section == .home, let s = Studio.Section(rawValue: raw), s != .home { store.section = s }
    }
}

/// 설정 Section. 각 줄 = 짧은 이름 + 컨트롤 + 작은 미리보기
struct CustomizeViewSection: View {
    @AppStorage(Fmt.scoreKey) private var score = "3"
    @AppStorage(Fmt.timeKey) private var clock = "system"
    @AppStorage(ViewPrefs.curveWidthKey) private var width = 2.0
    @AppStorage(ViewPrefs.densityKey) private var density = "regular"
    @AppStorage(ViewPrefs.startKey) private var start = "Home"
    @Environment(\.accessibilityReduceMotion) private var reduce
    private let sample = 0.71234, when = Calendar.current.date(bySettingHour: 15, minute: 45, second: 0, of: .now) ?? .now

    private var anim: Animation? { reduce ? nil : Motion.change }

    var body: some View {
        Section("View") {
            row("Score") {
                Picker("", selection: $score.animation(anim)) {
                    ForEach(["2", "3", "4", "pct"], id: \.self) { Text(verbatim: Fmt.score(sample, style: $0)).tag($0) }
                }
            } preview: { Text(verbatim: Fmt.score(sample, style: score)).monospacedDigit().contentTransition(.numericText()) }

            row("Time") {
                Picker("", selection: $clock.animation(anim)) {
                    Text("System").tag("system")
                    Text(verbatim: Fmt.time(when, style: "12")).tag("12")
                    Text(verbatim: Fmt.time(when, style: "24")).tag("24")
                }
            } preview: { Text(verbatim: Fmt.time(when, style: clock)).monospacedDigit().contentTransition(.numericText()) }

            row("Curve") {
                Picker("", selection: $width.animation(anim)) { Text("Thin").tag(1.2); Text("Normal").tag(2.0); Text("Bold").tag(3.0) }
                    .pickerStyle(.segmented)
            } preview: { CurvePreview(width: width).stroke(.brand, style: StrokeStyle(lineWidth: width, lineCap: .round)).frame(width: 54, height: 18) }

            row("List") {
                Picker("", selection: $density.animation(anim)) { Text("Compact").tag("compact"); Text("Regular").tag("regular"); Text("Roomy").tag("roomy") }
                    .pickerStyle(.segmented)
            } preview: {
                VStack(spacing: ViewPrefs.rowPadding(density)) {
                    ForEach(0..<3, id: \.self) { _ in Capsule().fill(.secondary.opacity(0.45)).frame(width: 54, height: 3) }
                }
                .frame(height: 30)
            }

            row("Open to") {
                Picker("", selection: $start) {
                    ForEach(ViewPrefs.starts) { s in Label(s.title, systemImage: s.symbol).tag(s.rawValue) }
                }
            } preview: {
                Image(systemName: (Studio.Section(rawValue: start) ?? .home).symbol).foregroundStyle(.tint)
                    .contentTransition(.symbolEffect(.replace))
            }
        }
    }

    private func row<C: View, P: View>(_ title: LocalizedStringKey, @ViewBuilder control: () -> C, @ViewBuilder preview: () -> P) -> some View {
        LabeledContent(title) {
            HStack(spacing: 12) {
                control().labelsHidden().fixedSize()
                PreviewChip { preview() }
            }
        }
    }
}

/// 미리보기 칸: 올리면 옅은 배경, 값이 바뀌면 부드럽게
private struct PreviewChip<Content: View>: View {
    @ViewBuilder var content: Content
    @State private var hover = false
    var body: some View {
        content.font(.ui(12, design: .monospaced)).frame(minWidth: 62, minHeight: 26)
            .background(RoundedRectangle(cornerRadius: Radius.control).fill(.quaternary.opacity(hover ? 0.6 : 0.3)))
            .onHover { h in withAnimation(Motion.hover) { hover = h } }
            .accessibilityHidden(true)
    }
}

/// 곡선 두께 미리보기용 작은 오르막
private struct CurvePreview: Shape {
    var width: Double
    var animatableData: Double { get { width } set { width = newValue } }
    func path(in r: CGRect) -> Path {
        Path { p in
            p.move(to: CGPoint(x: r.minX, y: r.maxY - 2))
            p.addCurve(to: CGPoint(x: r.maxX, y: r.minY + 2), control1: CGPoint(x: r.midX, y: r.maxY), control2: CGPoint(x: r.midX, y: r.minY))
        }
    }
}
