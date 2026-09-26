import SwiftUI

// 카드 한 장. 레이아웃은 스택이 계산한다 (파이썬판처럼 좌표를 박지 않는다 → 겹침이 없다).
struct RunCard: View {
    private var tint: Color { skin.tint(run.state, fallback: run.tint) }
    @Environment(\.ink) private var ink
    let run: Run
    @Environment(Store.self) private var store
    @State private var hover = false
    @Environment(\.skin) private var skin
    @AppStorage("showSparkline") private var showSparkline = true
    @AppStorage("animations") private var animations = true
    @State private var shown = false
    @State private var glow = false                                  // 최고 점수가 오른 순간 금빛으로 한 번
    @Environment(\.accessibilityReduceMotion) private var reduce
    /// 끝까지 간 학습은 100%와 꽉 찬 막대가 정보가 아니다: 최고 점수를 크게, 막대는 뺀다
    /// ★상태로 본다. 예전엔 진행률만 봐서 실패·중단도 마지막 에폭이 total에 닿으면 "100% 완료"로 그려졌다
    private var complete: Bool { run.isComplete }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                if skin.showBadge {
                Image(systemName: run.symbol)
                    .font(.ui(13, weight: .semibold))
                    .foregroundStyle(tint)
                    .symbolEffect(.pulse, isActive: run.state == "running" && !reduce)
                    .frame(width: 26, height: 26)
                    .background(tint.opacity(0.16), in: Circle())
                    .alignmentGuide(.firstTextBaseline) { $0[VerticalAlignment.center] + 4 }
                    .help(run.stateText)                         // 아이콘만으로는 상태를 모른다
                }
                Text(run.displayName)
                    .font(.ui(13.5, weight: .semibold, design: skin.monoTitle ? .monospaced : .default))
                    .lineLimit(1).truncationMode(.middle)
                    .layoutPriority(1)                           // 이름이 스파크라인보다 먼저 자리를 받는다
                    .help(store.isLocal(run) ? run.displayName : run.displayName + " · " + run.source)
                Spacer(minLength: 8)
                if showSparkline && run.history.count >= 3 {
                    Sparkline(values: run.history, tint: tint)
                        .frame(width: 56, height: 16)
                }
                Group {
                    if complete, let b = run.best {
                        Text(Fmt.metric(b, higher: run.metricHigher)).foregroundStyle(tint)
                    } else {
                        Text(run.progress.map { "\(Int(($0 * 100).rounded()))%" } ?? "–")
                    }
                }
                .font(.ui(15, weight: .semibold, design: .rounded)).monospacedDigit()
                .contentTransition(.numericText())           // 숫자가 굴러가며 바뀐다
            }
            // 글자 대신 아이콘: ↻ 에폭 · ⏳ 남은 시간(또는 🕑 지난 시간) · ★ 최고 점수
            HStack(spacing: 10) {
                if run.state != "done" {                         // 이름 다음은 상태: 끝난 것은 아이콘으로 충분하다
                    Text(verbatim: run.stateText).foregroundStyle(tint).fontWeight(.medium)
                        .contentTransition(.opacity)
                }
                if !store.isLocal(run) {                       // 다른 기계의 학습: 별칭(label)을 잘리지 않게
                    Label(run.source, systemImage: "desktopcomputer").lineLimit(1).truncationMode(.middle)
                        .help(run.source)
                }
                Label("\(run.epoch)/\(run.total.map(String.init) ?? "?")", systemImage: "repeat").help(L("epoch %@", ""))
                if run.state == "running" {
                    Label(duration(run.eta), systemImage: "hourglass").help("Time left")
                } else {
                    Label(duration(run.idle), systemImage: "clock").help("Last update")
                }
                Spacer()
                if let b = run.best, !complete {
                    Label(String(format: "%.4f", b), systemImage: "star.fill")
                        .font(.ui(11.5, design: .monospaced))
                        .foregroundStyle(ink.soft).help("Best score")
                }
            }
            .labelStyle(TightLabel())
            .font(.ui(11))
            .foregroundStyle(ink.soft)
            .padding(.leading, skin.showBadge ? 36 : 0)

            if !complete, run.progress != nil {               // ★총 에폭을 모르면(100/?) 빈 막대가 0%처럼 보였다
                CapsuleBar(value: run.progress ?? 0, tint: tint, height: skin.barHeight,
                           shimmer: run.state == "running" && animations, gradient: skin.gradientBar)
                    .padding(.leading, skin.showBadge ? 36 : 0)
                    .transition(.opacity)
            }
        }
        .padding(skin.spacing)
        .padding(.leading, skin.sideStripe ? 6 : 0)          // ★띠가 있으면 글자를 띠에서 띄운다
        .overlay(alignment: .leading) {
            if skin.sideStripe { Capsule().fill(tint).frame(width: 3).padding(.vertical, 10) }
        }
        .background(.quaternary.opacity(hover ? max(skin.cardOpacity, 0.5) + 0.3 : skin.cardOpacity),
                    in: .rect(cornerRadius: skin.radius))
        .overlay(RoundedRectangle(cornerRadius: skin.radius).strokeBorder(tint.opacity(hover ? 0.45 : 0), lineWidth: 1))
        .overlay(RoundedRectangle(cornerRadius: skin.radius).strokeBorder(Color.gold.opacity(glow ? 0.9 : 0), lineWidth: 2)
                    .shadow(color: .gold.opacity(glow ? 0.5 : 0), radius: 6))
        .onChange(of: run.best) { old, new in
            guard let o = old, let n = new, !reduce, n != o, run.isLive else { return }       // 도는 학습의 새 최고점만
            withAnimation(Motion.celebrate) { glow = true }
            Task { try? await Task.sleep(for: .seconds(1.2)); withAnimation(Motion.change) { glow = false } }
        }
        .scaleEffect(hover ? 1.01 : 1)
        .opacity(shown ? 1 : 0)
        .offset(y: shown ? 0 : 6)
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .onAppear {
            if animations && !reduce { withAnimation(Motion.appear) { shown = true } } else { shown = true }
        }
        .animation(Motion.change, value: run.state)                  // 상태가 바뀌면 색이 번진다
    }
}

struct Sparkline: View {
    let values: [Double]
    let tint: Color
    @State private var reveal: CGFloat = 0

    var body: some View {
        GeometryReader { g in
            let v = Array(values.suffix(40))
            let lo = v.min() ?? 0, hi = v.max() ?? 1, span = max(hi - lo, 1e-9)
            let pts = v.enumerated().map { i, x in
                CGPoint(x: g.size.width * CGFloat(i) / CGFloat(max(v.count - 1, 1)),
                        y: g.size.height * (1 - CGFloat((x - lo) / span)))
            }
            Path { p in p.addLines(pts) }
                .trim(from: 0, to: reveal)                     // 왼쪽에서 그려 나간다
                .stroke(tint.opacity(0.9), style: .init(lineWidth: 1.6, lineCap: .round, lineJoin: .round))
        }
        .onAppear { withAnimation(Motion.appear) { reveal = 1 } }
    }
}

/// 아이콘과 글자를 붙여 쓰는 작은 라벨(카드 한 줄 정보용)
struct TightLabel: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 3) { configuration.icon.font(.ui(9.5, weight: .semibold)).opacity(0.8); configuration.title }
    }
}
