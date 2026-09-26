import SwiftUI

// 스킨 = 팝오버 생김새 값 묶음. 그리는 코드는 숫자를 직접 갖지 않고 여기서 읽는다.
// 새 스킨은 all 배열에 하나 더하면 끝 (파이썬판과 같은 구조).
struct Skin: Identifiable, Hashable, @unchecked Sendable {   // 값만 담은 불변 구조라 공유해도 안전
    let id: String
    let name: LocalizedStringKey
    let note: LocalizedStringKey
    var radius: CGFloat = 12
    var cardOpacity: Double = 0.45
    var barHeight: CGFloat = 7
    var spacing: CGFloat = 12
    var showBadge = true
    var sideStripe = false
    var gradientBar = true
    var monoTitle = false
    var palette: [String: Color] = [:]

    func tint(_ state: String, fallback: Color) -> Color { palette[state] ?? fallback }

    static func == (a: Skin, b: Skin) -> Bool { a.id == b.id }
    func hash(into h: inout Hasher) { h.combine(id) }

    static let apple = Skin(id: "apple", name: "Apple", note: "Follows system colors")
    static let minimal = Skin(id: "minimal", name: "Minimal", note: "Flat and compact",
                              radius: 8, cardOpacity: 0, barHeight: 4, spacing: 6,
                              showBadge: false, sideStripe: true, gradientBar: false)
    static let terminal = Skin(id: "terminal", name: "Terminal", note: "High contrast, monospaced",
                               radius: 4, cardOpacity: 0.7, barHeight: 10, spacing: 8,
                               showBadge: false, sideStripe: true, gradientBar: false, monoTitle: true,
                               palette: ["running": Color(red: 0, green: 1, blue: 0.5), "done": Color(red: 0, green: 0.78, blue: 1),
                                         "failed": Color(red: 1, green: 0.24, blue: 0.24), "stalled": Color(red: 1, green: 0.78, blue: 0)])
    static let soft = Skin(id: "soft", name: "Soft", note: "Pastel, wide spacing",
                           radius: 18, cardOpacity: 0.5, barHeight: 8, spacing: 16,
                           palette: ["running": Color(red: 0.47, green: 0.84, blue: 0.63), "done": Color(red: 0.51, green: 0.71, blue: 0.94),
                                     "failed": Color(red: 0.94, green: 0.55, blue: 0.55), "stalled": Color(red: 0.96, green: 0.75, blue: 0.47),
                                     "starting": Color(red: 0.73, green: 0.67, blue: 0.94)])
    static let all = [apple, minimal, terminal, soft]
    static func named(_ id: String) -> Skin { all.first { $0.id == id } ?? apple }
}

private struct SkinKey: EnvironmentKey { static let defaultValue = Skin.apple }
extension EnvironmentValues {
    var skin: Skin { get { self[SkinKey.self] } set { self[SkinKey.self] = newValue } }
}

struct SkinProvider: ViewModifier {
    @AppStorage("skin") private var id = "apple"
    func body(content: Content) -> some View { content.environment(\.skin, Skin.named(id)) }
}
