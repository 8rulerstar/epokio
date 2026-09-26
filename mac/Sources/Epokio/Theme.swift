import SwiftUI

extension Run {
    /// 'train', 'exp', 'train2' 같은 흔한 이름은 상위 폴더를 붙인다.
    /// ★ultralytics 기본 이름이라 세 개가 전부 'train'으로 떠서 구분이 안 됐다.
    var displayName: String {
        if let display, !display.isEmpty { return display }     // agent가 정한 이름(모든 화면이 같게)
        return runDisplayName(name, path)
    }
}

/// 학습 이름을 보일 때 한 곳(목록·표·팝오버). 흔한 이름이면 상위 폴더를 붙인다
func runDisplayName(_ name: String, _ path: String) -> String {
    let generic = name.range(of: #"^(train|exp|val|predict|run|detect|segment|pose|classify)\d*$"#,
                             options: .regularExpression) != nil
    guard generic else { return name }
    let parts = path.split(whereSeparator: { $0 == "/" || $0 == "\\" }).map(String.init)   // ★윈도우 경로를 못 나눴다
    let parent = parts.dropLast().last { !["runs", "detect", "segment", "pose", "classify", "obb"].contains($0) }
    return parent.map { "\($0)/\(name)" } ?? name
}

// 상태 색은 디자인 토큰의 색 역할(good·warn·bad·mixup, docs/DESIGN.md). 라이트·다크는 토큰이 맞춘다.
extension Run {
    var tint: Color {
        switch state {
        case "running": .good
        case "starting": .mixup
        case "stalled": .warn
        case "failed": .bad
        case "done": .brand
        default: .gray
        }
    }
    var symbol: String {
        switch state {
        case "running": "bolt.fill"
        case "starting": "hourglass"
        case "stalled": "pause.circle.fill"
        case "failed": "exclamationmark.triangle.fill"
        case "done": "checkmark.circle.fill"
        default: "stop.circle.fill"
        }
    }
    var stateText: String {
        switch state {
        case "running": L("Training"); case "starting": L("Starting"); case "stalled": L("Stalled")
        case "failed": L("Failed"); case "done": L("Done"); default: L("Stopped")
        }
    }
}

// 하루 넘으면 일 단위. "1156시간"을 만들지 않는다 (파이썬판에서 겪은 실수).
func duration(_ s: Double?) -> String {
    guard let s else { return "–" }
    let f = DateComponentsFormatter()
    f.unitsStyle = .abbreviated
    // 1분 넘으면 초는 잡음이다 ("38m 5s" 금지). 하루 넘으면 일 단위만.
    switch s {
    case ..<60: f.allowedUnits = [.second]
    case ..<3_600: f.allowedUnits = [.minute]
    case ..<86_400: f.allowedUnits = [.hour, .minute]
    default: f.allowedUnits = [.day]
    }
    return f.string(from: s) ?? "–"
}

// 진행 막대. ProgressView 대신 직접 그린다 (그라데이션 + 스냅샷에서도 보인다).
struct CapsuleBar: View {
    let value: Double
    let tint: Color
    var height: CGFloat = 7
    var shimmer = false
    var gradient = true
    @State private var phase: CGFloat = -1
    @Environment(\.accessibilityReduceMotion) private var reduce

    var body: some View {
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(.primary.opacity(0.08))
                Capsule()
                    .fill(LinearGradient(colors: [tint.opacity(gradient ? 0.7 : 1), tint], startPoint: .leading, endPoint: .trailing))
                    .frame(width: max(g.size.width * value, value > 0 ? height : 0))
                    .overlay {
                        if shimmer {       // 도는 중에는 빛이 스쳐 지나간다
                            LinearGradient(colors: [.clear, .white.opacity(0.35), .clear],
                                           startPoint: .leading, endPoint: .trailing)
                                .frame(width: 40).offset(x: phase * g.size.width)
                                .mask(Capsule())
                                .animation(.linear(duration: 1.8).repeatForever(autoreverses: false), value: phase)   // 빛줄기에만
                        }
                    }
                    .clipShape(Capsule())
            }
        }
        .frame(height: height)
        .animation(Motion.progress, value: value)
        .onAppear {
            guard shimmer, !reduce else { return }      // 동작 줄이기면 빛이 안 스친다
            // ★withAnimation(repeatForever)을 여기서 쓰면 같은 갱신의 모든 변화(부모 화면이 나타나는 전환·배치)까지 영원히 반복돼
            //   도는 학습을 고르면 상세 화면이 줄어든 채 멈춰 보였다(2026-09-22). 반복은 위 빛줄기 한 겹에만 건다
            phase = 1
        }
    }
}

/// 아이콘 버튼의 얼굴(26pt, 올리면 옅은 바탕). 메뉴·설정 버튼처럼 Button이 아닌 곳의 라벨로도 쓴다
struct IconFace: View {
    let symbol: String
    var hover: Bool? = nil                     // nil이면 스스로 올림을 잰다(메뉴 라벨 등)
    @State private var own = false
    var body: some View {
        let on = hover ?? own
        Image(systemName: symbol)
            .font(.ui(13, weight: .medium))
            .frame(width: 26, height: 26)
            .background(.primary.opacity(on ? 0.08 : 0), in: .rect(cornerRadius: 7))
            .scaleEffect(on ? 1.06 : 1)
            .contentShape(.rect)
            .onHover { h in if hover == nil { withAnimation(Motion.hover) { own = h } } }
    }
}

// 아이콘 버튼. 시스템 버튼 대신, 누를 때 살짝 눌리고, 올리면 배경이 생긴다.
struct IconButton: View {
    let symbol: String
    let help: LocalizedStringKey
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) { IconFace(symbol: symbol, hover: hover) }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(help)
        .accessibilityLabel(help)                  // 아이콘만 있는 버튼: 화면 낭독기가 이름을 읽는다
    }
}

// 누름. 가장자리가 "언제나 같은 pt만큼" 들어온다.
// ★비율 축소(scaleEffect 0.9)를 쓰지 않는 이유: 축소량이 크기에 비례해,
//   26pt 아이콘 버튼은 1.3pt만 줄지만 팝오버 폭을 다 쓰는 줄(368pt)은 좌우로 18pt씩 밀려
//   줄이 통째로 출렁인다. 눌림이 아니라 고장으로 보인다.
//   (헛다리 주의: 이 비율 축소가 눌림을 취소시킨다는 가설은 틀렸다. SwiftUI는
//    축소 전 원래 틀로 취소 여부를 따지므로 가장자리를 눌러도 동작은 그대로 났다.
//    2026-09-23 프로세스 안에서 마우스 사건을 직접 넣어 45/45 동작 확인.)
struct PressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { Face(configuration: configuration) }

    private struct Face: View {
        let configuration: Configuration
        /// 눌릴 때 각 변이 들어오는 양(pt). 버튼 크기와 무관하게 늘 같다
        private static let inset: CGFloat = 1.5
        @State private var size: CGSize = .zero

        /// 들어올 양을 배율로 바꾼다. 아주 작은 버튼이 찌그러지지 않게 0.88에서 멈춘다
        private func shrink(_ side: CGFloat) -> CGFloat {
            side > 0 ? max(0.88, (side - 2 * Self.inset) / side) : 0.97
        }

        var body: some View {
            let p = configuration.isPressed
            // 손쉬운 사용 "동작 줄이기"에서는 움직이지 않고 밝기만 바뀐다
            let still = SystemPrefs.reduceMotion
            configuration.label
                .onGeometryChange(for: CGSize.self) { $0.size } action: { size = $0 }
                .scaleEffect(x: p && !still ? shrink(size.width) : 1,
                             y: p && !still ? shrink(size.height) : 1)
                .opacity(p ? 0.62 : 1)          // 축소가 작아진 만큼 밝기로 더 확실히 알린다
                .animation(Motion.tap, value: p)
        }
    }
}
