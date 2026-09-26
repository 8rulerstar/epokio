// ★자동 생성: design/tokens.json → tools/design_tokens.py. 손으로 고치지 말 것 (규칙: docs/DESIGN.md)
import SwiftUI
import AppKit

/// 라이트·다크에서 다른 색 (시스템이 모드를 바꾸면 따라간다)
private func dyn(_ l: (Double, Double, Double), _ d: (Double, Double, Double)) -> Color {
    Color(nsColor: NSColor(name: nil) { a in
        let c = a.bestMatch(from: [.darkAqua, .vibrantDark]) != nil ? d : l
        return NSColor(srgbRed: c.0, green: c.1, blue: c.2, alpha: 1)
    })
}

/// 색 역할. `.foregroundStyle(.good)`처럼 쓴다. 시스템 색(.green 등)을 직접 쓰지 않는다(test_house_rules)
extension ShapeStyle where Self == Color {
    /// 강조색: 버튼·선택·링크·진행률 (아이콘 보라)
    static var brand: Color { dyn((0.427, 0.357, 0.961), (0.549, 0.490, 1.000)) }
    /// 포인트 짝색: 그라데이션 끝·끝점 (아이콘 청록)
    static var brand2: Color { dyn((0.055, 0.647, 0.753), (0.133, 0.827, 0.933)) }
    /// 좋음·도는 중·맞춤·완료
    static var good: Color { dyn((0.122, 0.616, 0.341), (0.204, 0.780, 0.482)) }
    /// 주의·멈춤·놓침
    static var warn: Color { dyn((0.851, 0.478, 0.071), (1.000, 0.663, 0.302)) }
    /// 나쁨·실패·헛검출·지우기
    static var bad: Color { dyn((0.878, 0.251, 0.247), (1.000, 0.388, 0.412)) }
    /// 클래스 착각·시작 중
    static var mixup: Color { dyn((0.608, 0.302, 0.878), (0.753, 0.518, 0.988)) }
    /// 최고·1등·별표·목표
    static var gold: Color { dyn((0.788, 0.580, 0.000), (0.961, 0.773, 0.259)) }
    /// 정보·링크가 아닌 안내
    static var info: Color { dyn((0.184, 0.486, 0.965), (0.353, 0.635, 1.000)) }
}

extension LinearGradient {
    static var brand: LinearGradient { LinearGradient(colors: [.brand, .brand2], startPoint: .leading, endPoint: .trailing) }
}

/// 글꼴 역할. `.font(.role(.headline))`. 글씨 크기 설정(작게·보통·크게)을 따른다
enum TypeRole: CaseIterable {
    case hero, display, title, headline, body, callout, caption, badge
    var size: CGFloat { switch self { case .hero: 44; case .display: 28; case .title: 22; case .headline: 15; case .body: 13; case .callout: 12.5; case .caption: 11.5; case .badge: 10 } }
    var weight: Font.Weight { switch self { case .hero: .bold; case .display: .bold; case .title: .bold; case .headline: .semibold; case .body: .regular; case .callout: .regular; case .caption: .regular; case .badge: .semibold } }
    var design: Font.Design { switch self { case .hero: .rounded; case .display: .rounded; case .title: .default; case .headline: .default; case .body: .default; case .callout: .default; case .caption: .default; case .badge: .rounded } }
}

extension Font {
    static func role(_ r: TypeRole, weight: Font.Weight? = nil) -> Font { .ui(r.size, weight: weight ?? r.weight, design: r.design) }
}

/// 역할 크기 사다리. Font.ui(크기)는 가장 가까운 칸으로 맞춘다(흩어진 크기를 모은다)
let typeLadder: [CGFloat] = [10, 11.5, 12.5, 13, 15, 22, 28, 44]

enum Space { static let xs: CGFloat = 4; static let s: CGFloat = 8; static let m: CGFloat = 12; static let l: CGFloat = 16; static let xl: CGFloat = 24 }
enum Radius { static let chip: CGFloat = 6; static let control: CGFloat = 10; static let card: CGFloat = 14; static let sheet: CGFloat = 20 }

/// 움직임 역할. `withAnimation(Motion.change) { … }`
/// 길이는 설정 → 모양 "움직임 속도"(motionScale: 0.5 빠르게 ~ 2 느리게, 0 끄기)를 곱한다
/// 시스템 손쉬운 사용의 "동작 줄이기"가 켜져 있으면 앱 설정과 무관하게 멈춘다 (SystemPrefs.swift)
enum Motion {
    static var scale: Double {
        if SystemPrefs.reduceMotion { return 0.001 }
        let v = UserDefaults.standard.object(forKey: "motionScale") as? Double ?? 1
        return v <= 0 ? 0.001 : v
    }
    /// 누름
    static var tap: Animation { .snappy(duration: 0.12 * scale) }
    /// 마우스 올림
    static var hover: Animation { .snappy(duration: 0.15 * scale) }
    /// 값·배치 변화, 펼침
    static var change: Animation { .smooth(duration: 0.3 * scale) }
    /// 진행률 고리·막대가 새 값으로 차오를 때
    static var progress: Animation { .smooth(duration: 0.6 * scale) }
    /// 나타남(목록은 차례로, 12개까지)
    static var appear: Animation { .spring(duration: 0.4 * scale, bounce: 0.15) }
    /// 목표 달성·저장 성공 (+ 트랙패드 진동)
    static var celebrate: Animation { .bouncy(duration: 0.45 * scale) }
    static var stagger: Double { 0.025 * scale }
}
