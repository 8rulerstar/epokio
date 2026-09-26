import SwiftUI

// 검수 화면 부품: 필터 칩, 이미지 카드, 정답·예측 겹쳐 그리기, 크게 보기.

struct FilterChip: View {
    let title: String
    var symbol: String = "circle"
    let count: Int
    let on: Bool
    let tint: Color
    let action: () -> Void
    @State private var hover = false
    var body: some View {
        Button(action: { withAnimation(.snappy) { action() } }) {
            HStack(spacing: 5) {
                Image(systemName: symbol).font(.ui(11.5, weight: .semibold)).foregroundStyle(on ? AnyShapeStyle(.white) : AnyShapeStyle(tint))
                if on { Text(verbatim: title).font(.ui(12, weight: .semibold)).transition(.opacity.combined(with: .move(edge: .leading))) }
                Text(verbatim: "\(count)").font(.ui(11, weight: .semibold, design: .rounded))
                    .padding(.horizontal, 5).padding(.vertical, 1)
                    .background((on ? Color.white.opacity(0.25) : tint.opacity(0.15)), in: Capsule())
                    .contentTransition(.numericText())
            }
            .padding(.horizontal, 10).padding(.vertical, 5)
            .foregroundStyle(on ? .white : .primary)
            .background(on ? tint : tint.opacity(hover ? 0.14 : 0.07), in: Capsule())
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(title)
        .accessibilityLabel("\(title) \(count)")
    }
}

struct ReviewCard: View {
    let row: EvalRow
    let verdict: Verdict?
    var names: [String: String]? = nil
    var classify = false
    var selected = false
    var focused = false             // 키보드 포커스(방향키)
    var onHover: (Bool) -> Void = { _ in }
    @State private var image: NSImage?
    @State private var hover = false

    /// 사진 앱처럼 틀 없이: 사진이 칸을 채우고, 점수·놓침/더함·판정만 작은 배지로 위에 얹는다
    var body: some View {
        Color.primary.opacity(0.05)
            .overlay {
                if let image {
                    Image(nsImage: image).resizable().scaledToFit()
                        .overlay { CompareOverlay(gt: row.gt, pred: row.pred, gtStatus: row.gt_status, predStatus: row.pred_status, names: names, compact: true, classify: classify) }
                        .transition(.opacity)
                }
            }
            .aspectRatio(4 / 3, contentMode: .fit)
            .clipShape(.rect(cornerRadius: 6))
            .overlay(alignment: .bottomLeading) {
                HStack(spacing: 3) {
                    Text(row.score, format: .number.precision(.fractionLength(2)))
                        .font(.ui(10, weight: .bold, design: .monospaced))
                        .foregroundStyle(row.score < 0.5 ? .bad : row.score < 0.8 ? .warn : .good)
                    if row.fn > 0 { mini("minus", row.fn, .warn, L("missed")) }
                    if row.fp > 0 { mini("plus", row.fp, .bad, L("extra, not in your labels")) }
                }
                .padding(.horizontal, 5).padding(.vertical, 2)
                .background(.thinMaterial, in: Capsule()).padding(5)
            }
            .overlay(alignment: .topTrailing) {
                if let verdict {
                    Image(systemName: verdict.symbol).font(.ui(9, weight: .bold)).foregroundStyle(.white)
                        .frame(width: 18, height: 18).background(verdict.color, in: Circle()).padding(5)
                        .transition(.scale.combined(with: .opacity))
                }
            }
            .overlay {
                if selected {
                    RoundedRectangle(cornerRadius: 6).strokeBorder(.tint, lineWidth: 3)
                        .overlay(alignment: .topLeading) {
                            Image(systemName: "checkmark.circle.fill").font(.ui(16)).foregroundStyle(.white, .tint).padding(5)
                        }
                        .transition(.scale(scale: 0.96).combined(with: .opacity))
                }
            }
            .overlay {
                if focused && !selected {
                    RoundedRectangle(cornerRadius: 6).strokeBorder(.tint.opacity(0.8), style: StrokeStyle(lineWidth: 2, dash: [4, 3]))
                        .transition(.opacity)
                }
            }
            .animation(Motion.hover, value: focused)
            .brightness(hover ? 0.03 : 0)
            .scaleEffect(hover ? 1.02 : 1)
            .contentShape(.rect)
            .onHover { h in withAnimation(Motion.hover) { hover = h }; onHover(h) }
            .animation(Motion.tap, value: selected)
            .animation(.snappy, value: verdict)
            .animation(Motion.appear, value: image != nil)
            .help("Green: found correctly · Red: found something that is not there · Orange: missed · Purple: right place, wrong class")
            .task { image = await loadThumb(URL(fileURLWithPath: row.image), max: 500) }
    }

    private func mini(_ symbol: String, _ n: Int, _ c: Color, _ help: String) -> some View {
        HStack(spacing: 1) {
            Image(systemName: symbol).font(.ui(8, weight: .bold))
            Text(verbatim: "\(n)").font(.ui(10, weight: .semibold, design: .rounded))
        }
        .foregroundStyle(c)
        .accessibilityLabel(L("%d %@", n, help))
    }
}

// 정답(실선)과 예측(점선)을 겹쳐 그린다. 다시 채점한 결과가 있으면 박스마다 상태 색:
//   초록 = 맞춤 · 주황 = 놓친 정답 · 빨강 = 없는 걸 찾음 · 보라 = 자리는 맞고 클래스 틀림
enum BoxStatus {
    static func color(_ s: String?, gt: Bool) -> Color {
        switch s {
        case "tp": .good
        case "fn": .warn
        case "fp": .bad
        case "cls": .mixup
        default: gt ? .good : .bad
        }
    }
}

struct CompareOverlay: View {
    let gt: [EvalBox]
    let pred: [EvalBox]
    var gtStatus: [String]? = nil
    var predStatus: [String]? = nil
    var names: [String: String]? = nil
    var compact = false
    var classify = false            // 분류: 박스 대신 "정답 → 모델 답" 한 줄

    var body: some View {
        canvas
            .accessibilityElement()
            .accessibilityLabel(L("%lld labels, %lld predictions", gt.count, pred.count))
    }

    private var canvas: some View {
        Canvas { ctx, size in
            if classify { caption(ctx, size); return }
            func rect(_ b: [Double]) -> CGRect {
                CGRect(x: (b[0] - b[2] / 2) * size.width, y: (b[1] - b[3] / 2) * size.height,
                       width: b[2] * size.width, height: b[3] * size.height)
            }
            func tag(_ text: String, _ r: CGRect, _ c: Color, top: Bool) {
                let t = ctx.resolve(Text(text).font(.ui(11, weight: .bold)).foregroundStyle(.white))
                let s = t.measure(in: size)
                let y = top ? r.minY - s.height - 4 : r.maxY + 2
                ctx.fill(Path(roundedRect: CGRect(x: top ? r.minX : r.maxX - s.width - 8, y: y, width: s.width + 8, height: s.height + 4), cornerRadius: 3), with: .color(c))
                ctx.draw(t, at: CGPoint(x: top ? r.minX + 4 : r.maxX - 4, y: y + 2), anchor: top ? .topLeading : .topTrailing)
            }
            let name = { (c: Int) in names?[String(c)] ?? "\(c)" }
            for (i, g) in gt.enumerated() {
                let st = gtStatus.flatMap { i < $0.count ? $0[i] : nil }
                let c = BoxStatus.color(st, gt: true)
                if let pl = g.poly, pl.count >= 3 {
                    let path = poly(pl, size)
                    ctx.fill(path, with: .color(c.opacity(0.18))); ctx.stroke(path, with: .color(c), lineWidth: compact ? 1.5 : 2.5)
                } else {
                    ctx.stroke(Path(rect(g.box)), with: .color(c), lineWidth: compact ? 1.5 : 2.5)
                }
                for k in g.kpts where k.count >= 2 && (k.count < 3 || k[2] > 0) {
                    let p = CGRect(x: k[0] * size.width - 3, y: k[1] * size.height - 3, width: 6, height: 6)
                    ctx.fill(Path(ellipseIn: p), with: .color(c))
                }
                if !compact { tag(name(g.cls), rect(g.box), c, top: true) }
            }
            for (i, q) in pred.enumerated() {
                let st = predStatus.flatMap { i < $0.count ? $0[i] : nil }
                if st == "tp" && compact { continue }            // 작은 카드: 맞춘 예측은 정답 박스와 겹치니 생략
                let c = BoxStatus.color(st, gt: false)
                let shape = q.poly.flatMap { $0.count >= 3 ? poly($0, size) : nil } ?? Path(rect(q.box))
                ctx.stroke(shape, with: .color(c.opacity(st == "tp" ? 0.7 : 1)), style: .init(lineWidth: compact ? 1.5 : 2.5, dash: [5, 3]))
                for k in q.kpts where k.count >= 2 {
                    let p = CGRect(x: k[0] * size.width - 2.5, y: k[1] * size.height - 2.5, width: 5, height: 5)
                    ctx.stroke(Path(ellipseIn: p), with: .color(c), lineWidth: 1.5)
                }
                if !compact, let cf = q.conf {
                    tag((st == "cls" || st == "fp" ? name(q.cls) + " " : "") + String(format: "%.2f", cf), rect(q.box), c, top: false)
                }
            }
        }
        .allowsHitTesting(false)
    }

    private func poly(_ pts: [[Double]], _ size: CGSize) -> Path {
        var p = Path()
        for (i, xy) in pts.enumerated() where xy.count >= 2 {
            let pt = CGPoint(x: xy[0] * size.width, y: xy[1] * size.height)
            i == 0 ? p.move(to: pt) : p.addLine(to: pt)
        }
        p.closeSubpath()
        return p
    }

    /// 분류: 왼쪽 위에 "정답 → 모델 답 신뢰도". 맞으면 초록, 틀리면 보라, 자신 없어 답이 없으면 주황
    private func caption(_ ctx: GraphicsContext, _ size: CGSize) {
        let name = { (c: Int) in names?[String(c)] ?? "\(c)" }
        let truth = gt.first.map { name($0.cls) } ?? "?"
        let st = gtStatus?.first
        let answer = pred.first.map { "\(name($0.cls)) \(String(format: "%.2f", $0.conf ?? 0))" } ?? L("not sure")
        let c = BoxStatus.color(st, gt: true)
        let text = st == "tp" ? "✓ \(truth)" : "\(truth) → \(answer)"
        let base: CGFloat = compact ? 11 : 14
        var t = ctx.resolve(Text(verbatim: text).font(.ui(base, weight: .bold)).foregroundStyle(.white))
        var m = t.measure(in: CGSize(width: 10_000, height: 100))
        if m.width > size.width - 20 {                                // 세로로 긴 그림: 폭에 맞춰 글자를 줄인다(잘리지 않게)
            let k = max(0.55, (size.width - 20) / m.width)
            t = ctx.resolve(Text(verbatim: text).font(.ui(base * k, weight: .bold)).foregroundStyle(.white))
            m = t.measure(in: CGSize(width: 10_000, height: 100))
        }
        let r = CGRect(x: 6, y: 6, width: m.width + 12, height: m.height + 6)
        ctx.fill(Path(roundedRect: r, cornerRadius: 5), with: .color(c.opacity(0.92)))
        ctx.draw(t, at: CGPoint(x: r.midX, y: r.midY))
    }
}

/// 맞춤·잘못 찾음·놓침. 0이면 흐리게, 있으면 색을 채운다
struct CountChips: View {
    let row: EvalRow
    var body: some View {
        HStack(spacing: 4) {
            chip("checkmark", row.tp, .good, L("found correctly"))
            chip("plus", row.fp, .bad, L("extra, not in your labels"))
            chip("minus", row.fn, .warn, L("missed"))
        }
    }
    private func chip(_ symbol: String, _ n: Int, _ c: Color, _ help: String) -> some View {
        HStack(spacing: 2) {
            Image(systemName: symbol).font(.ui(9, weight: .bold))
            Text(verbatim: "\(n)").font(.ui(11.5, weight: .semibold, design: .rounded))
        }
        .padding(.horizontal, 6).padding(.vertical, 2)
        .foregroundStyle(n == 0 ? AnyShapeStyle(.secondary) : AnyShapeStyle(c))
        .background(c.opacity(n == 0 ? 0.06 : 0.16), in: Capsule())
        .help(L("%d %@", n, help))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(L("%d %@", n, help))
    }
}
