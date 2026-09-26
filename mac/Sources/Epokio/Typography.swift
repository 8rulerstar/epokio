import SwiftUI

// 글씨 규칙. 화면의 모든 글꼴은 Font.ui를 거친다(메뉴바 글씨만 예외: 시스템 메뉴바 크기를 따른다).
//
//   22  화면 제목          15  카드·섹션 제목      13  본문·목록 이름
//   12.5 보조 설명         11.5 가장 작은 읽는 글씨 (이보다 작게 쓰지 않는다)
//   10  숫자 뱃지 같은 장식만
//
// ★읽는 글씨에 ink.faint(가장 흐린 색)를 쓰지 않는다. 흐린 색은 화살표·구분점 같은 장식용.
// 설정 → 모양 → 글씨 크기(작게·보통·크게)가 전체에 곱해진다.
enum TextSize: String, CaseIterable, Identifiable {
    case small, standard, large
    var id: String { rawValue }
    var scale: CGFloat { switch self { case .small: 0.92; case .standard: 1; case .large: 1.15 } }
    var title: LocalizedStringKey { switch self { case .small: "Smaller"; case .standard: "Standard"; case .large: "Larger" } }
    static var current: TextSize { TextSize(rawValue: UserDefaults.standard.string(forKey: "textSize") ?? "") ?? .standard }
}

extension Font {
    /// 읽는 글씨는 11.5pt 아래로 내려가지 않는다. 10pt 이하는 뱃지 같은 장식으로 보고 그대로 둔다.
    /// ★크기는 역할 사다리(DesignTokens.typeLadder)의 가장 가까운 칸으로 맞춘다. 흩어진 20여 가지 크기가 8칸으로 모인다.
    ///   10보다 작은 것(점·장식 기호)만 그대로 둔다. 둥근 서체는 숫자 폭을 고정한다(값이 바뀌어도 안 흔들림)
    static func ui(_ size: CGFloat, weight: Font.Weight = .regular, design: Font.Design = .default) -> Font {
        let base = size < 10 ? size : typeLadder.min { abs($0 - size) < abs($1 - size) } ?? size
        let f = Font.system(size: (base * TextSize.current.scale).rounded(toPlaces: 1), weight: weight, design: design)
        return design == .rounded ? f.monospacedDigit() : f
    }
}

private extension CGFloat {
    func rounded(toPlaces p: Int) -> CGFloat { let m = pow(10, CGFloat(p)); return (self * m).rounded() / m }
}

/// 글씨 크기를 바꾸면 화면을 새로 그린다(Font.ui는 값을 한 번 읽으므로).
struct TextSizeRefresh: ViewModifier {
    @AppStorage("textSize") private var size = TextSize.standard.rawValue
    func body(content: Content) -> some View { content.id(size) }
}
extension View { func followsTextSize() -> some View { modifier(TextSizeRefresh()) } }
