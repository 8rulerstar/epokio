import SwiftUI

// 글자 대비. 사용자가 고른다 (Soft / Standard / High).
// ★기본을 Soft로 뒀더니 "best 0.7000" 같은 글자가 흐려 안 읽혔다. 기본은 Standard.
// 맥 '대비 증가'가 켜져 있으면 무조건 High.
enum Contrast: String, CaseIterable, Identifiable {
    case soft, standard, high
    var id: String { rawValue }
    var title: LocalizedStringKey {
        switch self { case .soft: "Soft"; case .standard: "Standard"; case .high: "High" }
    }
}

struct Ink {
    let contrast: Contrast
    /// 보조 글자 (상태·에폭 줄)
    var soft: AnyShapeStyle {
        switch contrast {
        case .soft: AnyShapeStyle(.secondary)
        case .standard: AnyShapeStyle(.primary.opacity(0.72))
        case .high: AnyShapeStyle(.primary.opacity(0.9))
        }
    }
    /// 가장 옅은 글자 (best 값, 바닥 줄)
    var faint: AnyShapeStyle {
        switch contrast {
        case .soft: AnyShapeStyle(.tertiary)
        case .standard: AnyShapeStyle(.secondary)
        case .high: AnyShapeStyle(.primary.opacity(0.75))
        }
    }
}

private struct InkKey: EnvironmentKey { static let defaultValue = Ink(contrast: .standard) }
extension EnvironmentValues {
    var ink: Ink {
        get { self[InkKey.self] }
        set { self[InkKey.self] = newValue }
    }
}

// 설정값 + 시스템 대비를 합쳐 하위 뷰에 내려 준다
struct InkProvider: ViewModifier {
    @AppStorage("contrast") private var raw = Contrast.standard.rawValue
    @Environment(\.colorSchemeContrast) private var system

    func body(content: Content) -> some View {
        let chosen = Contrast(rawValue: raw) ?? .standard
        content.environment(\.ink, Ink(contrast: system == .increased ? .high : chosen))
    }
}

extension View {
    /// 글자 대비·스킨 + 브랜드 강조색(아이콘 보라, docs/DESIGN.md). 모든 창의 뿌리에 붙는다
    func withInk() -> some View { modifier(InkProvider()).modifier(SkinProvider()).modifier(AccentTint()) }      // 강조색은 설정 → 꾸미기
}
