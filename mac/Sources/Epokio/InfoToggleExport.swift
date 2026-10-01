import SwiftUI

// `Epokio --export-info-toggle <폴더> [--dark]` : README용. 메뉴바 "Show" 칩을 누르면 메뉴바 글자가 바뀌는 장면을 PNG 프레임으로.
// ★ImageRenderer는 정지 화면만 찍으므로 SwiftUI 애니메이션에 기대지 않고 프레임마다 값을 직접 계산한다.
//   실제 데이터는 안 쓴다(가짜 Run 하나). 글자는 진짜 barText, 캐릭터는 진짜 Runner.cat 프레임.
@MainActor
enum InfoToggleExport {
    static let fps = 20.0
    static let length = 7.0                                   // 초. 마지막 0.5초는 첫 장면으로 겹쳐 돌아간다(끊김 없는 반복)

    /// 탭 순서: (시각, 칩). 같은 칩을 다시 누르면 꺼진다
    static let taps: [(Double, BarInfo)] = [(1.3, .epoch), (2.7, .eta), (4.6, .pct)]
    static let tickAt = 3.6                                   // 에폭 하나 지남(37 → 38)
    static let start: [BarInfo] = [.pct]

    static func runIfRequested() {
        let a = CommandLine.arguments
        guard let i = a.firstIndex(of: "--export-info-toggle"), i + 1 < a.count else { return }
        let dir = URL(fileURLWithPath: a[i + 1])
        let dark = a.contains("--dark")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let n = Int(length * fps)
        for k in 0..<n {
            let t = Double(k) / fps
            let back = smooth01((t - (length - 0.5)) / 0.5)    // 끝에서 처음 장면으로
            let view = ZStack {
                InfoToggleScene(t: t).opacity(1 - back)
                if back > 0 { InfoToggleScene(t: 0).opacity(back) }
            }
            .frame(width: 440, height: 164)
            .background(dark ? Color(white: 0.13) : Color(white: 0.985))
            .environment(\.colorScheme, dark ? .dark : .light)
            let r = ImageRenderer(content: view)
            r.scale = 2
            if let img = r.nsImage, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
               let png = rep.representation(using: .png, properties: [:]) {
                try? png.write(to: dir.appendingPathComponent(String(format: "f_%03d.png", k)))
            }
        }
        print("info toggle frames:", n, dir.path); exit(0)
    }

    // MARK: 시간 함수

    static func smooth01(_ x: Double) -> Double { let c = min(max(x, 0), 1); return c * c * (3 - 2 * c) }
    /// 감쇠 스프링 0 → 1 (살짝 넘쳤다 돌아온다). Motion.appear(스프링 0.4초, 약한 튐)에 맞춘 값
    static func spring(_ p: Double) -> Double {
        guard p > 0 else { return 0 }
        let z = 9.0, w = 15.0
        return 1 - exp(-z * p) * (cos(w * p) + z / w * sin(w * p))
    }
    /// 칩 방울: 눌림(살짝 작아짐) 뒤 1.15까지 부풀었다 1로. Motion.celebrate(0.45초 튐) 길이
    static func bubble(_ p: Double) -> Double {
        guard p > 0, p < 0.9 else { return 1 }
        if p < 0.06 { return 1 - 0.08 * (p / 0.06) }
        let q = p - 0.06
        return 1 + 0.17 * exp(-6.5 * q) * sin(13 * q) - 0.08 * exp(-40 * q)
    }

    /// t 시각에 켜져 있는가 + 마지막으로 바뀐 뒤 지난 시간
    static func state(_ info: BarInfo, at t: Double) -> (on: Bool, since: Double) {
        var on = start.contains(info), since = 99.0
        for (tt, i) in taps where i == info && tt <= t { on.toggle(); since = t - tt }
        return (on, since)
    }

    /// 가짜 학습(진행 중). tick 전후로 에폭·남은 시간이 바뀐다
    static func run(at t: Double) -> Run {
        let ticked = t >= tickAt
        return Run(name: "coco8", path: "/sample", epoch: ticked ? 38 : 37, total: 50, elapsed: 2200,
                   eta: ticked ? 660 : 720, metric: 0.65, metric_name: "", best: 0.662, best_epoch: 36, state: "running", idle: 1)
    }

    /// 커서 위치: 칩 사이를 부드럽게 옮겨 다닌다(탭 0.7초 전에 출발)
    static func cursor(at t: Double, chips: [BarInfo: CGPoint]) -> (CGPoint, Double) {
        var pts: [(Double, CGPoint)] = [(0, CGPoint(x: 380, y: 160))]
        for (tt, i) in taps { if let c = chips[i] { pts.append((tt, CGPoint(x: c.x + 14, y: c.y + 6))) } }
        pts.append((length - 0.6, CGPoint(x: 380, y: 160)))
        var pos = pts[0].1
        for k in 1..<pts.count {
            let (t1, p1) = pts[k], begin = t1 - 0.75
            if t >= begin {
                let e = smooth01((t - begin) / 0.7)
                pos = CGPoint(x: pos.x + (p1.x - pos.x) * e, y: pos.y + (p1.y - pos.y) * e)
            }
        }
        let press = taps.map { t - $0.0 }.filter { $0 > -0.06 && $0 < 0.12 }.isEmpty ? 1.0 : 0.85
        return (pos, press)
    }
}

/// 한 프레임: 위는 메뉴바 띠, 아래는 설정의 "Show" 칩 줄
private struct InfoToggleScene: View {
    let t: Double
    @Environment(\.colorScheme) private var scheme
    // 칩 중심(장면 좌표). 두 줄 세 칸 고정 배치
    static let chipW: CGFloat = 112
    static func center(_ i: BarInfo) -> CGPoint {
        let k = BarInfo.allCases.firstIndex(of: i) ?? 0
        return CGPoint(x: 44 + CGFloat(k % 3) * (chipW + 10) + chipW / 2, y: 104 + CGFloat(k / 3) * 34)
    }

    var body: some View {
        let chips = Dictionary(uniqueKeysWithValues: BarInfo.allCases.map { ($0, Self.center($0)) })
        let (cur, press) = InfoToggleExport.cursor(at: t, chips: chips)
        ZStack(alignment: .topLeading) {
            menuBar.frame(width: 440, height: 30)
            Text("Show").font(.ui(13, weight: .semibold)).foregroundStyle(.secondary)
                .position(x: 44 + 18, y: 70)
            ForEach(BarInfo.allCases) { i in chip(i).position(Self.center(i)) }
            Pointer().scaleEffect(press, anchor: .topLeading)
                .frame(width: 16, height: 22).position(x: cur.x + 8, y: cur.y + 11)
        }
        .frame(width: 440, height: 164, alignment: .topLeading)
    }

    // MARK: 메뉴바

    private var ink: Color { scheme == .dark ? Color(white: 0.95) : Color(white: 0.08) }

    private var menuBar: some View {
        let r = InfoToggleExport.run(at: t)
        return HStack(spacing: 14) {
            Image(systemName: "apple.logo").font(.system(size: 13))
            Text("Finder").font(.ui(13, weight: .bold)).fixedSize()
            Text("File").font(.ui(13)).fixedSize()
            Spacer(minLength: 0)
            HStack(spacing: 4) {
                Image(nsImage: Runner.cat.image(t * 1.6)).renderingMode(.template)
                ForEach(BarInfo.allCases) { i in segment(i, r) }
            }
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(ink.opacity(0.07), in: RoundedRectangle(cornerRadius: 5))
            Image(systemName: "wifi").font(.system(size: 12.5))
            Image(systemName: "battery.75percent").font(.system(size: 13))
            Text("Thu 9:41").font(.ui(13)).fixedSize()
        }
        .foregroundStyle(ink)
        .padding(.horizontal, 12)
        .frame(maxHeight: .infinity)
        .background(scheme == .dark ? Color(white: 0.2) : Color(white: 0.93))
        .overlay(alignment: .bottom) { ink.opacity(0.08).frame(height: 1) }
    }

    /// 메뉴바 글자 한 조각. 켜질 때 폭이 스프링으로 벌어지며 아래에서 떠오르고, 꺼질 땐 반대로 접힌다
    @ViewBuilder private func segment(_ i: BarInfo, _ r: Run) -> some View {
        let s = InfoToggleExport.state(i, at: t)
        let g = InfoToggleExport.spring(s.since / 0.55)
        let w = max(0, s.on ? g : 1 - g)
        if w > 0.001 {
            let text = barText(r, [i], gpu: 62, scoreStyle: "3")
            let charW: CGFloat = 7.53                          // 12.5pt 고정폭 한 글자
            let tick = InfoToggleExport.spring((t - InfoToggleExport.tickAt) / 0.5)
            let changes = text != barText(InfoToggleExport.run(at: 0), [i], gpu: 62, scoreStyle: "3")
            ZStack {
                if changes && t >= InfoToggleExport.tickAt && tick < 1 {   // 숫자 넘김: 옛 값은 위로, 새 값은 아래에서
                    label(barText(InfoToggleExport.run(at: 0), [i], gpu: 62, scoreStyle: "3")).offset(y: -10 * tick).opacity(1 - tick)
                    label(text).offset(y: 10 * (1 - tick)).opacity(tick)
                } else { label(text) }
            }
            .frame(width: CGFloat(text.count) * charW * min(w, 1.08), alignment: .leading)
            .clipped()
            .offset(y: 6 * (1 - min(w, 1)))
            .opacity(min(1, w * 1.4))
            .blur(radius: 2 * (1 - min(w, 1)))
        }
    }

    private func label(_ s: String) -> some View {
        Text(s).font(.system(size: 12.5, design: .monospaced)).fixedSize()
    }

    // MARK: 칩 (SettingsAppearance의 캡슐과 같은 모양)

    private func chip(_ i: BarInfo) -> some View {
        let s = InfoToggleExport.state(i, at: t)
        let f = InfoToggleExport.smooth01(s.since / 0.2)       // 색 바뀜
        let on = s.on ? f : 1 - f
        let pop = InfoToggleExport.bubble(s.since)
        let ring = s.since < 0.6 ? s.since / 0.6 : 1
        return ZStack {
            Capsule().fill(.quaternary.opacity(0.6))
            Capsule().fill(Color.brand).opacity(on)
            HStack(spacing: 5) {
                Image(systemName: i.symbol)
                Text(i.title)
            }
            .font(.ui(11.5, weight: on > 0.5 ? .semibold : .regular))
            .foregroundStyle(on > 0.5 ? AnyShapeStyle(.white) : AnyShapeStyle(.primary))
        }
        .frame(width: Self.chipW - 8, height: 24)
        .background {                                          // 방울이 터지는 고리
            Capsule().stroke(Color.brand, lineWidth: 2.5 * (1 - ring))
                .scaleEffect(1 + 0.35 * ring).opacity(ring < 1 ? 0.7 * (1 - ring) : 0)
        }
        .scaleEffect(pop)
        .shadow(color: Color.brand.opacity(0.35 * on * max(0, pop - 1) * 6), radius: 6)
    }
}

/// 마우스 화살표(흰 테두리 + 검은 몸)
private struct Pointer: View {
    var body: some View {
        let p = Path { p in
            p.move(to: .zero); p.addLine(to: CGPoint(x: 0, y: 17)); p.addLine(to: CGPoint(x: 4.5, y: 13))
            p.addLine(to: CGPoint(x: 7.5, y: 20)); p.addLine(to: CGPoint(x: 10, y: 19)); p.addLine(to: CGPoint(x: 7, y: 12))
            p.addLine(to: CGPoint(x: 12.5, y: 12)); p.closeSubpath()
        }
        ZStack {
            p.fill(Color.black)
            p.stroke(Color.white, lineWidth: 1.3)
        }
        .shadow(color: .black.opacity(0.3), radius: 1.5, y: 1)
    }
}
