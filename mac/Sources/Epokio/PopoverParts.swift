import SwiftUI

// 팝오버 카드가 같이 쓰는 작은 부품: 지표 짧은 이름, 얇은 진행 막대.

enum MetricLabel {
    /// agent의 metric_name을 숫자 옆에 붙일 짧은 표기로. "metrics/mAP50-95(B)" → "mAP50-95", "eval_accuracy" → "accuracy"
    static func short(_ name: String) -> String {
        var s = name
        if let slash = s.lastIndex(of: "/") { s = String(s[s.index(after: slash)...]) }
        if s.hasSuffix(")"), let open = s.lastIndex(of: "(") { s = String(s[..<open]) }       // (B)·(M) 같은 과제 표시
        for p in ["eval_", "val_", "test_"] where s.hasPrefix(p) { s = String(s.dropFirst(p.count)) }
        s = s.trimmingCharacters(in: .whitespaces)
        return s.count > 12 ? String(s.prefix(11)) + "…" : s
    }
}

/// 얇은 진행 막대(제어 센터 슬라이더 느낌). 트랙은 중립색, 채움만 색
struct ThinProgress: View {
    let value: Double
    let tint: Color
    var height: CGFloat = 4

    var body: some View {
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(.primary.opacity(0.08))
                Capsule().fill(tint)
                    .frame(width: max(g.size.width * min(max(value, 0), 1), height))
                    .animation(Motion.progress, value: value)
            }
        }
        .frame(height: height)
        .accessibilityElement()
        .accessibilityValue(Text(verbatim: "\(Int((value * 100).rounded()))%"))
    }
}
