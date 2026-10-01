import SwiftUI
import AppKit

// 메뉴바에 보일 모양. 펫은 없앴다(움직이는 데스크톱 펫은 나중에 따로). 모든 모양이 학습 속도로 움직인다.
// 규칙 (파이썬판에서 겪은 것)
//  1. 프레임마다 폭이 같아야 한다. 글자는 점자·블록만, 숫자는 고정폭. 원·반원 글자는 폭이 달라 떨렸다
//  2. 쉴 때는 아이콘 하나. '⠿ ✓' 같은 글자는 엉성했다
//  3. 막대는 글자가 아니라 그림(캡슐). 글자 막대는 빈 칸이 공백이라 끊겨 보였다
//  4. 움직임 속도 = 학습 속도. 멎으면 멈춘다
enum BarStyle: String, CaseIterable, Identifiable {
    case mark, bar, dots, orbit, wave, gauge, percent, cat, runner, bird, rocket, neuron, blob, fish, dino, coffee, planet, custom, customAnim
    var id: String { rawValue }

    var title: LocalizedStringKey { LocalizedStringKey(nameKey) }
    var name: String { L(nameKey) }
    private var nameKey: String {
        switch self {
        case .mark: "Epokio mark"; case .bar: "Bar"; case .dots: "Dots"; case .orbit: "Orbit"
        case .wave: "Wave"; case .gauge: "Gauge"; case .percent: "Percent only"; case .custom: "My image"
        case .cat: "Running cat"; case .runner: "Runner"; case .bird: "Bird"; case .rocket: "Rocket"
        case .neuron: "Neural net"; case .blob: "Jelly"; case .customAnim: "My animation"
        case .fish: "Fish"; case .dino: "Dino"; case .coffee: "Coffee"; case .planet: "Planet"
        }
    }
    /// 아이콘 안에서 계속 움직이는 캐릭터(런캣처럼)
    var runner: Runner? { Runner(rawValue: rawValue) }
    /// 설정 목록 묶음
    static let still: [BarStyle] = [.mark, .bar, .gauge, .dots, .orbit, .wave, .percent]
    static let characters: [BarStyle] = [.cat, .runner, .bird, .rocket, .neuron, .blob, .fish, .dino, .coffee, .planet]
    static let mine: [BarStyle] = [.custom, .customAnim]
    /// 예전에 저장된 값(펫: cat, robot…)은 기본 모양으로
    static func from(_ raw: String) -> BarStyle { BarStyle(rawValue: raw) ?? .mark }

    static let spin = Array("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
    static let orbitF = Array("⠈⠐⠠⢀⡀⠄⠂⠁")
    static let waveF = Array("▁▂▃▄▅▆▇█▇▆▅▄▃▂")
}

extension Run {
    /// 1(느림) ~ 6(빠름). 멎으면 0
    var speed: Int {
        if state == "starting" { return 2 }
        guard state == "running", epoch > 0, elapsed > 0 else { return 0 }
        let per = elapsed / Double(epoch)
        return per < 20 ? 6 : per < 60 ? 4 : per < 180 ? 3 : per < 600 ? 2 : 1
    }
    var pct4: String { progress.map { String(format: "%3d%%", Int(($0 * 100).rounded())) } ?? "   ?" }
}

/// 메뉴바 움직임 빠르기(설정 → 모양 → 메뉴바). 사용자가 정한다
enum BarTempo {
    /// 배율. 기본 0.6(예전 1.0은 너무 빠르다는 의견, 2026-09-22)
    static var scale: Double { UserDefaults.standard.object(forKey: "barTempo") as? Double ?? 0.6 }
    /// 켜면 빠른 학습일수록 빨리 달린다(RunCat처럼). 끄면 늘 같은 빠르기
    static var follow: Bool { UserDefaults.standard.object(forKey: "barFollowSpeed") as? Bool ?? true }
    /// 초당 다시 그리는 최대 횟수(CPU). 4·8·12
    static var maxFPS: Double { UserDefaults.standard.object(forKey: "barMaxFPS") as? Double ?? 8 }
    static func speed(_ s: Double) -> Double { s == 0 ? 0 : follow ? s : 3 }
}

// 메뉴바 라벨. 시간으로 프레임을 고른다 (타이머 주기와 무관하게 속도 일정)
/// 메뉴바에 무엇을 보일지(설정 → 모양 → 메뉴바). 사용자가 입맛대로 고른다
enum BarInfo: String, CaseIterable, Identifiable {
    case pct, eta, clock, epoch, best, gpu
    var id: String { rawValue }
    var title: LocalizedStringKey {
        switch self {
        case .pct: "Progress %"; case .eta: "Time left"; case .clock: "Finish time"
        case .epoch: "Epoch"; case .best: "Best score"; case .gpu: "GPU %"
        }
    }
    var symbol: String {
        switch self {
        case .pct: "percent"; case .eta: "hourglass"; case .clock: "flag.checkered"
        case .epoch: "repeat"; case .best: "star"; case .gpu: "cpu"
        }
    }
    static func parse(_ s: String) -> [BarInfo] { s.split(separator: ",").compactMap { BarInfo(rawValue: String($0)) } }
}

/// 메뉴바 글자: 고른 정보를 고정폭으로 이어 붙인다(★폭이 흔들리지 않게 숫자는 고정폭)
@MainActor func barText(_ r: Run, _ infos: [BarInfo], gpu: Double?, scoreStyle: String? = nil) -> String {
    infos.compactMap { i -> String? in
        switch i {
        case .pct: return r.pct4.trimmingCharacters(in: .whitespaces)
        case .eta: return r.state == "running" ? r.eta.map { shortDuration($0) } : nil
        case .clock: return r.state == "running" ? r.eta.map { Date().addingTimeInterval($0).formatted(date: .omitted, time: .shortened) } : nil
        case .epoch: return r.countText
        case .best: return r.best.map { Fmt.metric($0, higher: r.metricHigher, style: scoreStyle) }
        case .gpu: return gpu.map { "G\(Int($0))%" }
        }
    }.joined(separator: " ")
}

/// 메뉴바용 짧은 시간: 42s · 12m · 1h05 · 2d
func shortDuration(_ s: Double) -> String {
    let t = Int(s)
    if t < 60 { return "\(t)s" }
    if t < 3600 { return "\(t / 60)m" }
    if t < 86_400 { return String(format: "%dh%02d", t / 3600, t % 3600 / 60) }
    return "\(t / 86_400)d"
}

struct MenuBarLabel: View {
    @Environment(Store.self) private var store
    @AppStorage("barStyle") private var raw = BarStyle.mark.rawValue
    @AppStorage("barShow") private var show = "pct"            // 보일 정보(쉼표로)
    @AppStorage("barRun") private var which = "live"           // live · star · cycle
    @AppStorage("barIdle") private var idle = "icon"           // icon · score
    @AppStorage(PaceSource.key) private var paceRaw = PaceSource.train.rawValue   // 캐릭터 속도 출처(RunnerPace.swift)
    @AppStorage("animations") private var animations = true
    @AppStorage(Fmt.scoreKey) private var scoreStyle = "3"   // 바꾸면 바로 다시 그린다
    @Environment(\.accessibilityReduceMotion) private var reduce
    var sample: Run? = nil                                     // 설정 미리보기: 도는 학습이 없을 때 이걸 보인다
    var styleOverride: BarStyle? = nil                         // 설정 미리보기: 올린 타일의 모양을 잠깐 보인다
    var frozen = false                                         // 설정 미리보기: 안 보일 때·움직임 끔일 때 멈춘다

    @State private var t: Double = 0
    @State private var cheer: String?                          // 방금 끝남·실패: 몇 초 동안 아이콘이 알려 준다

    // TimelineView를 메뉴바 라벨에 쓰면 macOS 27에서 상태 항목 갱신이 끝없이 돌아 앱 실행이 끝나지 않는다(아이콘 안 뜸).
    // 움직일 게 있을 때만 타이머로 t를 올린다. 모든 모양이 움직인다(퍼센트만 제외), 속도 = 학습 속도
    var body: some View {
        let style = styleOverride ?? BarStyle.from(raw)
        let moves = style.runner != nil || style == .customAnim
        let animating = !frozen && ((store.lead != nil || sample != nil) && (style != .percent || which == "cycle")
            || (moves && pace(0) > 0))                             // 학습 없어도 CPU·GPU로 달린다
        Group {
            if let c = cheer {                                     // 끝나는 순간을 놓치지 않게: 체크(또는 실패 표시)가 튄다
                Image(systemName: c == "finished" ? "checkmark.seal.fill" : "exclamationmark.octagon.fill")
                    .symbolEffect(.bounce, options: .repeat(2), value: c)
                    .transition(.scale.combined(with: .opacity))
            } else {
                content(style, t: t)
            }
        }
            .onChange(of: store.justFinished?.id) { _, id in
                guard id != nil, let j = store.justFinished, -j.date.timeIntervalSinceNow < 30 else { return }
                cheer = j.kind
                Task { try? await Task.sleep(for: .seconds(5)); cheer = nil }
            }
            .accessibilityLabel(store.lead.map { L("Epokio, %@ training, %@", $0.displayName, $0.pct4.trimmingCharacters(in: .whitespaces)) } ?? "Epokio")
            .task(id: "\(animating)\(style.rawValue)") {
                var last = -1
                while animating && !Task.isCancelled {
                    try? await Task.sleep(for: .milliseconds(style.runner != nil || style == .customAnim ? 50 : 100))
                    let now = Date.timeIntervalSinceReferenceDate
                    let k = frameKey(style, now)
                    if k != last { last = k; t = now }           // ★보이는 칸이 바뀔 때만 다시 그린다(매 틱 그리니 CPU 17~20%였다)
                }
            }
    }

    /// 캐릭터 걸음. 빠를수록 한 바퀴가 빨라지되, 메뉴바는 초당 12번까지만 다시 그린다.
    /// ★초당 37칸을 그리면 CPU +7%. 그냥 12번으로 자르면 3·3·3·4칸씩 불규칙하게 건너뛰어 떨려 보여서, 빠를 땐 2·3칸씩 고르게 건너뛴다
    private func runnerStep(_ speed: Double, _ t: Double) -> (tick: Int, phase: Double) {
        let rate = (0.5 + BarTempo.speed(speed) * 0.3) * Double(Runner.frames) * BarTempo.scale     // 초당 칸
        let k = max(1, (rate / BarTempo.maxFPS).rounded(.up))              // 한 번에 건너뛸 칸
        let tick = Int(t * rate / k)
        return (tick, Double(tick) * k / Double(Runner.frames))
    }

    /// 지금 보일 그림 칸을 하나의 수로. 같으면 메뉴바를 다시 그릴 필요가 없다(상태 항목 배치 계산이 비싸다)
    private func frameKey(_ style: BarStyle, _ t: Double) -> Int {
        let speed = pace(t)
        if speed == 0 { return Int(t / 5) }                                            // 멎음: 번갈아 보이기(5초)만
        let cycle = Int(t / 5) * 10_000
        if style.runner != nil || style == .customAnim {
            return cycle + runnerStep(speed, t).tick                                    // 캐릭터 한 걸음
        }
        return cycle + Int(t * min((0.6 + BarTempo.speed(speed) * 0.35) * 24 * BarTempo.scale, BarTempo.maxFPS))   // 맥박·빛줄기도 상한
    }

    /// 어느 학습을 보일지: 진행 중 첫 번째 · 별표 단 것(없으면 첫 번째) · 여러 개면 5초마다 번갈아
    private func chosen(_ t: Double) -> Run? {
        let live = store.runs.filter(\.isLive)
        guard !live.isEmpty else { return sample }
        switch which {
        case "star": return live.first { $0.meta?.star == true } ?? live[0]
        case "cycle": return live[Int(t / 5) % live.count]
        default: return live[0]
        }
    }

    private var gpuNow: Double? { store.system.values.first?.now?.gpus.first?.util }
    private var aiNow: Double? { store.system.values.first?.now?.ai }

    /// 캐릭터 속도: 학습 속도 또는 CPU·GPU 사용률(설정 `barPaceSource`). 움직임을 끄면 예전처럼 학습 속도만
    private func pace(_ t: Double) -> Double {
        let training = Double(chosen(t)?.speed ?? 0)
        _ = paceRaw                                   // 설정이 바뀌면 다시 그리게(값은 effectiveNow가 읽는다)
        let src = animations && !reduce ? PaceSource.effectiveNow(resting: store.gotRuns && RestMode.isResting(runs: store.runs)) : .train
        let fresh = Date().timeIntervalSince(store.systemAt) < 30              // ★30초 넘은 값은 버린다(팝오버를 닫으면 안 받던 때 마지막 값으로 계속 달렸다)
        return RunnerPace.pace(src, training: training, cpu: fresh ? store.system.values.first?.now?.cpu : nil,
                               gpu: fresh ? gpuNow : nil, ai: fresh ? aiNow : nil)
    }

    @ViewBuilder
    private func content(_ style: BarStyle, t: Double) -> some View {
        let lead = chosen(t)
        let warn = store.runs.contains { $0.state == "stalled" || $0.state == "failed" }
        let speed = pace(t)
        let fps = (2.0 + BarTempo.speed(speed) * 1.5) * BarTempo.scale
        let frame = speed == 0 ? 0 : Int(t * fps)
        let phase = speed == 0 ? 0 : t * (0.6 + BarTempo.speed(speed) * 0.35) * BarTempo.scale          // 맥박 주기(초당)
        let stride = speed == 0 ? 0 : runnerStep(speed, t).phase         // 캐릭터: 빠른 학습일수록 빨리 달린다

        if let r = lead {
            HStack(spacing: 4) {
                switch style {
                case .mark: Image(nsImage: markImage(r.progress ?? 0, pulse: phase))
                case .bar: Image(nsImage: barImage(r.progress ?? 0, sheen: phase))
                case .gauge: Image(nsImage: gaugeImage(r.progress ?? 0, wobble: phase))
                case .dots: Text(String(BarStyle.spin[frame % BarStyle.spin.count])).font(.system(size: 12.5, design: .monospaced))
                case .orbit: Text(String(BarStyle.orbitF[frame % BarStyle.orbitF.count])).font(.system(size: 12.5, design: .monospaced))
                case .wave:
                    Text(String((0..<3).map { BarStyle.waveF[(frame + $0 * 3) % BarStyle.waveF.count] }))
                        .font(.system(size: 12.5, design: .monospaced))
                case .percent: EmptyView()
                case .custom: Image(nsImage: CustomMark.image() ?? markImage(r.progress ?? 0, pulse: phase))
                case .cat, .runner, .bird, .rocket, .neuron, .blob, .fish, .dino, .coffee, .planet: Image(nsImage: style.runner!.image(stride))
                case .customAnim: Image(nsImage: CustomAnim.image(stride) ?? markImage(r.progress ?? 0, pulse: phase))
                }
                let text = barText(r, BarInfo.parse(show), gpu: gpuNow, scoreStyle: scoreStyle)
                if !text.isEmpty {
                    Text(text).font(.system(size: 12.5, design: .monospaced))   // 고정폭: 숫자가 안 떨린다
                        .contentTransition(.numericText())
                }
            }
        } else if warn {
            Image(systemName: "exclamationmark.triangle.fill")
        } else if idle == "score", let last = store.runs.min(by: { $0.idle < $1.idle }), let b = last.best {
            HStack(spacing: 4) {                                               // 쉴 때: 마지막 학습 점수
                idleIcon(style)
                Text(Fmt.metric(b, higher: last.metricHigher, style: scoreStyle)).font(.system(size: 12.5, design: .monospaced))
            }
        } else if stride > 0, let run = style.runner {
            Image(nsImage: run.image(stride))                                 // 학습 없음: CPU·GPU 사용률로 달린다
        } else if stride > 0, style == .customAnim, let img = CustomAnim.image(stride) {
            Image(nsImage: img)
        } else {
            idleIcon(style)                                                   // 쉴 때: 로고(또는 내 그림) 하나
        }
    }
}

extension MenuBarLabel {
    /// 쉴 때: 캐릭터는 멈춘 자세, 내 그림·내 애니메이션은 첫 장, 나머지는 로고
    func idleIcon(_ style: BarStyle) -> Image {
        if let r = style.runner { return Image(nsImage: r.image(0)) }
        switch style {
        case .custom: return Image(nsImage: CustomMark.image() ?? markImage(1, pulse: 0))
        case .customAnim: return Image(nsImage: CustomAnim.image(0) ?? markImage(1, pulse: 0))
        default: return Image(nsImage: markImage(1, pulse: 0))
        }
    }
}

/// 사용자가 고른 그림(설정 → 모양 → 메뉴바 → 내 그림). 앱 지원 폴더에 복사해 두고 16pt 높이로 줄여 쓴다.
/// 기본은 메뉴바 색을 따르는 단색(template). 원래 색을 쓰려면 "원래 색 그대로"
enum CustomMark {
    static var url: URL {
        let d = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Epokio")
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        return d.appendingPathComponent("menubar-icon.png")
    }
    nonisolated(unsafe) private static var cache: (Date, Bool, NSImage)?

    static func image(size: CGFloat = 16) -> NSImage? {
        guard let when = (try? url.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate else { return nil }
        let mono = UserDefaults.standard.object(forKey: "barCustomMono") as? Bool ?? true
        if let c = cache, c.0 == when, c.1 == mono { return c.2 }
        guard let src = NSImage(contentsOf: url), src.size.height > 0 else { return nil }
        let aspect = src.size.width / src.size.height
        let w = min(size * aspect, size * 1.6)                                    // 너무 넓은 그림은 잘라 쓰지 않고 줄인다
        let h = w / aspect
        let canvas = max(w, size)                                                 // ★아주 좁은 그림이 1pt 실선이 됐다: 정사각 칸 가운데
        let img = NSImage(size: NSSize(width: canvas, height: size), flipped: false) { r in
            src.draw(in: NSRect(x: (canvas - w) / 2, y: (r.height - h) / 2, width: w, height: h)); return true
        }
        img.isTemplate = mono
        cache = (when, mono, img)
        return img
    }

    /// 고른 파일을 PNG로 바꿔 저장한다(SVG·PDF·HEIC도 NSImage가 읽으면 된다)
    static func save(from src: URL) -> Bool {
        guard let im = NSImage(contentsOf: src), let tiff = im.tiffRepresentation,
              let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) else { return false }
        return (try? png.write(to: url)) != nil
    }
    static func remove() { try? FileManager.default.removeItem(at: url); cache = nil }
}

/// 앱 아이콘의 한 획 e. 가로획에서 시작해 원을 도는 한 획이 진행률만큼 진하게 그려지고,
/// 끝점이 학습 속도에 맞춰 맥박 친다. 쉴 때(p = 1)는 완성된 e.
/// ★앱 아이콘을 그대로 줄이면 16pt에서 가는 선이 사라진다(2026-09-22 사용자 지적). 메뉴바용은 굵게, 옅은 쪽도 35%로.
func markImage(_ p: Double, pulse: Double, size: CGFloat = 16) -> NSImage {
    let img = NSImage(size: NSSize(width: size + 2, height: size), flipped: false) { _ in
        let s = size / 16
        let c = NSPoint(x: (size + 2) / 2, y: size / 2), R = 5.9 * s, w = 1.95 * s
        let sweep: CGFloat = 320
        let bar = 2 * R - w / 2, arcLen = sweep / 180 * .pi * R
        let q = CGFloat(min(max(p, 0.03), 1))
        func stroke(_ upto: CGFloat, _ color: NSColor) -> NSPoint {            // 한 획을 길이 upto까지
            let path = NSBezierPath()
            path.move(to: NSPoint(x: c.x - R + w / 2, y: c.y))
            var end = NSPoint(x: c.x - R + w / 2 + min(upto, bar), y: c.y)
            path.line(to: end)
            if upto > bar {
                let deg = (upto - bar) / R * 180 / .pi
                path.appendArc(withCenter: c, radius: R, startAngle: 0, endAngle: deg, clockwise: false)
                end = NSPoint(x: c.x + R * cos(deg * .pi / 180), y: c.y + R * sin(deg * .pi / 180))
            }
            path.lineWidth = w; path.lineCapStyle = .round; path.lineJoinStyle = .round
            color.setStroke(); path.stroke()
            return end
        }
        _ = stroke(bar + arcLen, NSColor.black.withAlphaComponent(q >= 1 ? 1 : 0.35))
        let e = stroke((bar + arcLen) * q, .black)
        let r = (1.75 + 0.45 * CGFloat(sin(pulse * 2 * .pi))) * s             // 맥박
        NSColor.black.setFill()
        NSBezierPath(ovalIn: NSRect(x: e.x - r, y: e.y - r, width: r * 2, height: r * 2)).fill()
        return true
    }
    img.isTemplate = true
    return img
}

/// 반원 게이지. 바늘이 진행률 쪽으로 가고, 도는 동안 살짝 떨린다
func gaugeImage(_ p: Double, wobble: Double, size: CGFloat = 16) -> NSImage {
    let img = NSImage(size: NSSize(width: size + 2, height: size), flipped: false) { _ in
        let c = NSPoint(x: (size + 2) / 2, y: 4), r = size / 2 - 0.5
        let arc = NSBezierPath(); arc.appendArc(withCenter: c, radius: r, startAngle: 180, endAngle: 0, clockwise: true)
        arc.lineWidth = 1.8; arc.lineCapStyle = .round
        NSColor.black.withAlphaComponent(0.3).setStroke(); arc.stroke()
        let filled = NSBezierPath(); filled.appendArc(withCenter: c, radius: r, startAngle: 180, endAngle: 180 - 180 * CGFloat(min(max(p, 0), 1)), clockwise: true)
        filled.lineWidth = 1.8; filled.lineCapStyle = .round
        NSColor.black.setStroke(); filled.stroke()
        let ang = (180 - 180 * min(max(p, 0), 1) + 4 * sin(wobble * 2 * .pi)) * .pi / 180
        let needle = NSBezierPath(); needle.move(to: c)
        needle.line(to: NSPoint(x: c.x + (r - 3) * cos(ang), y: c.y + (r - 3) * sin(ang)))
        needle.lineWidth = 1.6; needle.lineCapStyle = .round; needle.stroke()
        NSBezierPath(ovalIn: NSRect(x: c.x - 1.6, y: c.y - 1.6, width: 3.2, height: 3.2)).fill()
        return true
    }
    img.isTemplate = true
    return img
}

/// 메뉴바 캡슐 막대. template이라 메뉴바 색(라이트·다크)을 OS가 칠한다
func barImage(_ p: Double, sheen: Double = 0, w: CGFloat = 44, h: CGFloat = 7) -> NSImage {
    let img = NSImage(size: NSSize(width: w, height: 16), flipped: false) { _ in
        let y = (16 - h) / 2
        NSColor.black.withAlphaComponent(0.28).setFill()
        NSBezierPath(roundedRect: NSRect(x: 0.5, y: y, width: w - 1, height: h), xRadius: h / 2, yRadius: h / 2).fill()
        if p > 0 {
            NSColor.black.setFill()
            let fw = max((w - 1) * min(p, 1), h)
            NSBezierPath(roundedRect: NSRect(x: 0.5, y: y, width: fw, height: h), xRadius: h / 2, yRadius: h / 2).fill()
            if sheen > 0 {                                  // 도는 중: 채워진 부분 위로 틈이 지나간다(학습 속도로)
                let x = 0.5 + (fw - 3) * CGFloat(sheen.truncatingRemainder(dividingBy: 1))
                NSGraphicsContext.current?.compositingOperation = .clear
                NSBezierPath(rect: NSRect(x: x, y: y, width: 2, height: h)).fill()
                NSGraphicsContext.current?.compositingOperation = .sourceOver
            }
        }
        return true
    }
    img.isTemplate = true
    return img
}
