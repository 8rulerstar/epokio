import SwiftUI
import AppKit
import ImageIO

// 메뉴바 캐릭터(런캣처럼 아이콘 안에서 계속 움직인다). 전부 코드로 그린 단색(template) 그림이라
// 라이트·다크 메뉴바 색을 OS가 칠한다. 한 바퀴 = 16프레임, 도는 속도 = 학습 속도(멎으면 멈춘 자세).
// 새 캐릭터: Runner에 case 하나 + draw 함수 하나. 프레임은 캐시하므로 그리기 비용은 첫 바퀴만 든다.

enum Runner: String, CaseIterable {
    case cat, runner, bird, rocket, neuron, blob, fish, dino, coffee, planet

    static let frames = 16

    /// phase: 0..<1 (한 바퀴 중 어디인가)
    @MainActor func image(_ phase: Double) -> NSImage {
        let i = ((Int(phase * Double(Self.frames)) % Self.frames) + Self.frames) % Self.frames
        let key = "\(rawValue)-\(i)"
        if let c = RunnerCache.images[key] { return c }
        let th = Double(i) / Double(Self.frames) * 2 * .pi
        let img = NSImage(size: NSSize(width: 24, height: 16), flipped: false) { _ in
            NSColor.black.setFill(); NSColor.black.setStroke()
            switch self {
            case .cat: drawCat(th)
            case .runner: drawRunner(th)
            case .bird: drawBird(th)
            case .rocket: drawRocket(th, Double(i) / Double(Self.frames))
            case .neuron: drawNeuron(Double(i) / Double(Self.frames))
            case .blob: drawBlob(th)
            case .fish: drawFish(th, Double(i) / Double(Self.frames))
            case .dino: drawDino(th)
            case .coffee: drawCoffee(th)
            case .planet: drawPlanet(th)
            }
            return true
        }
        img.isTemplate = true
        RunnerCache.images[key] = img
        return img
    }
}

@MainActor enum RunnerCache { static var images: [String: NSImage] = [:] }

// MARK: - 그리기 도구

private func pt(_ x: Double, _ y: Double) -> NSPoint { NSPoint(x: x, y: y) }
private func seg(_ a: NSPoint, _ b: NSPoint, _ w: CGFloat = 1.6) {
    let p = NSBezierPath(); p.move(to: a); p.line(to: b)
    p.lineWidth = w; p.lineCapStyle = .round; p.stroke()
}
private func poly(_ ps: [NSPoint]) {
    let p = NSBezierPath(); p.move(to: ps[0]); ps.dropFirst().forEach { p.line(to: $0) }; p.close(); p.fill()
}
private func dot(_ c: NSPoint, _ r: Double) { NSBezierPath(ovalIn: NSRect(x: c.x - r, y: c.y - r, width: r * 2, height: r * 2)).fill() }
private func ring(_ c: NSPoint, _ r: Double, _ w: CGFloat = 1) {
    let p = NSBezierPath(ovalIn: NSRect(x: c.x - r, y: c.y - r, width: r * 2, height: r * 2)); p.lineWidth = w; p.stroke()
}
/// 구멍 뚫기(눈·창문). template이라 투명 = 메뉴바 바탕색
private func punch(_ c: NSPoint, _ r: Double) {
    NSGraphicsContext.current?.compositingOperation = .clear
    dot(c, r)
    NSGraphicsContext.current?.compositingOperation = .sourceOver
}

// MARK: - 캐릭터

/// 달리는 고양이: 등이 오르내리고, 네 다리가 두 박자로 엇갈리며, 꼬리가 흔들린다
private func drawCat(_ th: Double) {
    let bob = sin(2 * th) * 0.6
    NSBezierPath(ovalIn: NSRect(x: 6, y: 5.2 + bob, width: 11.5, height: 5.2)).fill()          // 몸
    dot(pt(18.6, 9.6 + bob), 2.9)                                                              // 머리
    poly([pt(16.7, 11.4 + bob), pt(17.2, 15.2 + bob), pt(19.0, 12.3 + bob)])                   // 귀
    poly([pt(19.2, 12.3 + bob), pt(21.0, 15.0 + bob), pt(21.3, 10.8 + bob)])
    punch(pt(19.9, 10.0 + bob), 0.55)                                                          // 눈
    let tail = NSBezierPath()                                                                  // 꼬리
    tail.move(to: pt(6.6, 9.0 + bob))
    tail.curve(to: pt(1.6, 12.6 + sin(th) * 1.8), controlPoint1: pt(3.4, 9.2 + bob), controlPoint2: pt(1.4, 10.6 + sin(th) * 2.4))
    tail.lineWidth = 1.5; tail.lineCapStyle = .round; tail.stroke()
    for (x, off) in [(15.6, 0.0), (14.2, Double.pi), (8.6, Double.pi / 2), (7.2, 3 * Double.pi / 2)] {
        let a = th + off
        seg(pt(x, 6.4 + bob), pt(x + 2.6 * sin(a), 0.9 + max(0, cos(a)) * 1.6), 1.5)          // 다리
    }
}

/// 달리는 사람(막대 인형): 팔다리가 반대로 흔들리고 몸이 살짝 튄다
private func drawRunner(_ th: Double) {
    let bob = abs(sin(th)) * 0.9
    let hip = pt(11, 5.6 + bob), sh = pt(12.4, 10.4 + bob)
    dot(pt(13.3, 12.9 + bob), 1.8)
    seg(hip, sh, 1.8)
    for side in [0.0, Double.pi] {
        let a = sin(th + side) * 0.95
        let knee = pt(hip.x + 3.2 * sin(a), hip.y - 3.2 * cos(a))
        let b = a - 0.35 - 0.75 * (1 + cos(th + side)) / 2                                    // 뒤로 갈 때 무릎이 접힌다
        seg(hip, knee); seg(knee, pt(knee.x + 3.0 * sin(b), knee.y - 3.0 * cos(b)))
        let c = -a * 0.9
        let elbow = pt(sh.x + 2.6 * sin(c), sh.y - 2.6 * cos(c))
        seg(sh, elbow, 1.4); seg(elbow, pt(elbow.x + 2.2 * sin(c + 1.3), elbow.y - 2.2 * cos(c + 1.3)), 1.4)
    }
}

/// 나는 새: 날개가 오르내리고 몸은 반대로 까딱인다
private func drawBird(_ th: Double) {
    let bob = -sin(th) * 1.0
    NSBezierPath(ovalIn: NSRect(x: 7, y: 5.4 + bob, width: 9, height: 5)).fill()
    dot(pt(16.2, 9.4 + bob), 2.2)
    poly([pt(18.0, 10.0 + bob), pt(21.2, 9.2 + bob), pt(18.0, 8.4 + bob)])                     // 부리
    poly([pt(7.8, 8.6 + bob), pt(3.2, 10.8 + bob), pt(4.0, 6.8 + bob)])                        // 꼬리
    punch(pt(16.8, 9.9 + bob), 0.5)
    let tip = 8.2 + bob + 6.6 * sin(th)
    poly([pt(9.2, 8.8 + bob), pt(13.6, 8.8 + bob), pt(9.6, tip)])                             // 날개
}

/// 로켓: 불꽃이 깜빡이고, 속도선이 뒤로 흐른다
private func drawRocket(_ th: Double, _ ph: Double) {
    let bob = sin(th) * 0.5
    NSBezierPath(roundedRect: NSRect(x: 7.5, y: 6 + bob, width: 10, height: 4.4), xRadius: 1.6, yRadius: 1.6).fill()
    poly([pt(17, 6 + bob), pt(21.4, 8.2 + bob), pt(17, 10.4 + bob)])
    poly([pt(8.4, 10.2 + bob), pt(6.6, 13.2 + bob), pt(11, 10.2 + bob)])
    poly([pt(8.4, 6.2 + bob), pt(6.6, 3.2 + bob), pt(11, 6.2 + bob)])
    punch(pt(14.4, 8.2 + bob), 1.1)
    let flame = 3.0 + 1.6 * abs(sin(th * 3))
    poly([pt(7.4, 7.0 + bob), pt(7.4 - flame, 8.2 + bob), pt(7.4, 9.4 + bob)])
    NSColor.black.withAlphaComponent(0.5).setStroke()
    for (k, y) in [(0.0, 2.2), (0.35, 13.8), (0.7, 4.2)] {                                     // 속도선
        let x = 24 - (ph + k).truncatingRemainder(dividingBy: 1) * 26
        seg(pt(x, y), pt(x + 3.2, y), 1.1)
    }
    NSColor.black.setStroke()
}

/// 신경망: 신호가 입력 → 은닉 → 출력으로 흐르고, 지나간 마디가 켜진다
private func drawNeuron(_ ph: Double) {
    let L0 = [pt(3, 4.5), pt(3, 11.5)], L1 = [pt(12, 2.5), pt(12, 8), pt(12, 13.5)], L2 = [pt(21, 8)]
    NSColor.black.withAlphaComponent(0.35).setStroke()
    for a in L0 { for b in L1 { seg(a, b, 0.8) } }
    for a in L1 { for b in L2 { seg(a, b, 0.8) } }
    NSColor.black.setStroke()
    let cycle = Int(ph * 3) % 3                                                                // 세 갈래를 돌아가며
    let t = (ph * 3).truncatingRemainder(dividingBy: 1)
    let a = L0[cycle % 2], m = L1[cycle], z = L2[0]
    let lit0 = t < 0.5, lit1 = t >= 0.35, lit2 = t >= 0.85
    for n in L0 { n == a && lit0 ? dot(n, 1.9) : ring(n, 1.6, 1.1) }
    for n in L1 { n == m && lit1 ? dot(n, 1.9) : ring(n, 1.6, 1.1) }
    lit2 ? dot(z, 2.1) : ring(z, 1.8, 1.2)
    let p = t < 0.5 ? pt(a.x + (m.x - a.x) * t * 2, a.y + (m.y - a.y) * t * 2)
                    : pt(m.x + (z.x - m.x) * (t - 0.5) * 2, m.y + (z.y - m.y) * (t - 0.5) * 2)
    dot(p, 1.3)
}

/// 젤리: 통통 튀며 바닥에 닿을 때 납작해진다
private func drawBlob(_ th: Double) {
    let up = abs(sin(th))
    let sq = pow(1 - up, 3)
    let w = 9.5 * (1 + 0.3 * sq), h = 8.0 / (1 + 0.3 * sq)
    let y = 1.4 + up * 5.2
    let c = pt(12, y + h / 2)
    NSBezierPath(roundedRect: NSRect(x: c.x - w / 2, y: y, width: w, height: h), xRadius: w / 2.2, yRadius: h / 2.2).fill()
    punch(pt(c.x - 1.7, c.y + 0.8), 0.8); punch(pt(c.x + 1.7, c.y + 0.8), 0.8)
    NSColor.black.withAlphaComponent(0.4).setStroke()
    let sw = 7 - up * 3.5
    seg(pt(12 - sw / 2, 0.6), pt(12 + sw / 2, 0.6), 1)                                         // 그림자
    NSColor.black.setStroke()
}

/// 물고기: 꼬리를 흔들며 헤엄치고 거품이 올라간다
private func drawFish(_ th: Double, _ ph: Double) {
    let bob = sin(th) * 0.6
    NSBezierPath(ovalIn: NSRect(x: 7, y: 5 + bob, width: 11, height: 6.4)).fill()
    let flick = sin(th * 2) * 2.2                                                              // 꼬리
    poly([pt(8, 8.2 + bob), pt(3, 11.4 + bob + flick), pt(3.6, 8.2 + bob), pt(3, 5 + bob + flick)])
    punch(pt(15.4, 9.0 + bob), 0.7)
    NSColor.black.withAlphaComponent(0.55).setStroke()
    for k in [0.0, 0.5] {                                                                      // 거품
        let t = (ph + k).truncatingRemainder(dividingBy: 1)
        ring(pt(20 + sin(t * 6) * 0.6, 8 + t * 8), 0.7 + t * 0.6, 0.9)
    }
    NSColor.black.setStroke()
}

/// 작은 공룡: 뒤뚱뒤뚱 걷는다(다리 번갈아 · 꼬리 까딱)
private func drawDino(_ th: Double) {
    let bob = abs(sin(th)) * 0.7
    NSBezierPath(roundedRect: NSRect(x: 7, y: 5 + bob, width: 9, height: 5.4), xRadius: 2.4, yRadius: 2.4).fill()   // 몸
    NSBezierPath(roundedRect: NSRect(x: 13.4, y: 8.6 + bob, width: 6.4, height: 4.6), xRadius: 1.8, yRadius: 1.8).fill() // 머리
    punch(pt(17.6, 11.6 + bob), 0.6)
    poly([pt(7.6, 8.6 + bob), pt(2.2, 9.6 + bob + sin(th) * 1.2), pt(7.6, 6.2 + bob)])       // 꼬리
    for (x, off) in [(9.4, 0.0), (13.2, Double.pi)] {
        let lift = max(0, sin(th + off)) * 1.6
        NSBezierPath(roundedRect: NSRect(x: x - 0.9, y: 1 + lift, width: 1.8, height: 4.6 + bob - lift), xRadius: 0.8, yRadius: 0.8).fill()
    }
    seg(pt(14.6, 7.6 + bob), pt(16, 6.4 + bob + sin(th) * 0.5), 1.2)                           // 앞발
}

/// 커피: 김이 물결치며 피어오른다(학습 기다리는 동안)
private func drawCoffee(_ th: Double) {
    NSBezierPath(roundedRect: NSRect(x: 6, y: 1.5, width: 9.5, height: 7.5), xRadius: 1.8, yRadius: 1.8).fill()
    let handle = NSBezierPath(ovalIn: NSRect(x: 13.6, y: 3.4, width: 4.2, height: 4))
    handle.lineWidth = 1.5; handle.stroke()
    for (k, x) in [(0.0, 8.0), (2.1, 12.0)] {
        let p = NSBezierPath()
        p.move(to: pt(x, 10))
        for j in 1...6 {
            let y = 10 + Double(j)
            p.line(to: pt(x + sin(th + k + Double(j) * 0.9) * 0.7, y))
        }
        NSColor.black.withAlphaComponent(0.6).setStroke()
        p.lineWidth = 1.2; p.lineCapStyle = .round; p.stroke()
    }
    NSColor.black.setStroke()
}

/// 행성: 달이 궤도를 돌고, 뒤로 갈 때는 행성 뒤에 숨는다
private func drawPlanet(_ th: Double) {
    let c = pt(12, 8), mx = 12 + cos(th) * 9, my = 8 + sin(th) * 2.6
    let behind = sin(th) > 0
    let orbit = NSBezierPath(ovalIn: NSRect(x: 3, y: 5.4, width: 18, height: 5.2))
    NSColor.black.withAlphaComponent(0.3).setStroke(); orbit.lineWidth = 0.8; orbit.stroke()
    NSColor.black.setStroke()
    if behind { dot(pt(mx, my), 1.5) }
    dot(c, 4.6)
    punch(pt(10.4, 9.6), 0.9); punch(pt(13.4, 6.8), 0.6)                                      // 분화구
    if !behind { dot(pt(mx, my), 1.5) }
}

// MARK: - 사용자 애니메이션

/// 사용자가 올린 움직이는 아이콘. GIF 하나, 여러 장(이름순), 또는 가로로 이어 붙인 한 장(스프라이트)을 받는다.
/// 앱 지원 폴더 menubar-anim/에 16pt 높이 PNG로 풀어 둔다. 단색/원래 색은 "내 그림"과 같은 설정(barCustomMono)
enum CustomAnim {
    static var dir: URL {
        let d = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Epokio/menubar-anim")
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        return d
    }
    nonisolated(unsafe) private static var cache: (Date, Bool, [NSImage])?

    static func frames() -> [NSImage] {
        let when = (try? dir.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .distantPast
        let mono = UserDefaults.standard.object(forKey: "barCustomMono") as? Bool ?? true
        if let c = cache, c.0 == when, c.1 == mono { return c.2 }
        let files = ((try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? [])
            .filter { $0.pathExtension == "png" }.sorted { $0.lastPathComponent < $1.lastPathComponent }
        let imgs = files.compactMap { NSImage(contentsOf: $0) }.map { im -> NSImage in
            if let rep = im.representations.first, rep.pixelsHigh > 0 {                          // 2배 그림 → 16pt 높이로
                im.size = NSSize(width: CGFloat(rep.pixelsWide) * 16 / CGFloat(rep.pixelsHigh), height: 16)
            }
            im.isTemplate = mono; return im
        }
        cache = (when, mono, imgs)
        return imgs
    }

    static func image(_ phase: Double) -> NSImage? {
        let f = frames()
        guard !f.isEmpty else { return nil }
        return f[Int(phase * Double(f.count)) % f.count]
    }

    /// 고른 파일들 → 프레임 목록. 성공하면 프레임 수
    static func save(from urls: [URL]) -> Int {
        var src: [CGImage] = []
        let sorted = urls.sorted { $0.lastPathComponent < $1.lastPathComponent }
        for u in sorted {
            guard let s = CGImageSourceCreateWithURL(u as CFURL, nil) else { continue }
            let n = CGImageSourceGetCount(s)
            if n > 1 { src += (0..<n).compactMap { CGImageSourceCreateImageAtIndex(s, $0, nil) } }     // GIF·APNG
            else if let im = CGImageSourceCreateImageAtIndex(s, 0, nil) ?? NSImage(contentsOf: u)?.cgImage(forProposedRect: nil, context: nil, hints: nil) {
                src.append(im)
            }
        }
        if src.count == 1, let one = src.first, one.height > 0, one.width >= one.height * 2 {         // 스프라이트: 정사각 칸으로 자른다
            let n = one.width / one.height
            src = (0..<n).compactMap { one.cropping(to: CGRect(x: $0 * one.height, y: 0, width: one.height, height: one.height)) }
        }
        let frames = Array(src.prefix(60))
        guard !frames.isEmpty else { return 0 }
        clear()
        for (i, cg) in frames.enumerated() {
            // ★2배로 저장(레티나). 16px이면 흐렸다. 폭은 정사각~1.6배 사이: 아주 좁은 그림(10×200)이 1pt 실선이 됐다 → 가운데 둔다
            let h: CGFloat = 32, aspect = CGFloat(cg.width) / CGFloat(max(cg.height, 1))
            let canvasW = min(max(h * aspect, h), h * 1.6)
            let drawW = min(h * aspect, canvasW), drawH = min(h, drawW / max(aspect, 0.001))
            let im = NSImage(size: NSSize(width: canvasW, height: h), flipped: false) { r in
                NSGraphicsContext.current?.imageInterpolation = .high
                NSGraphicsContext.current?.cgContext.draw(cg, in: CGRect(x: (r.width - drawW) / 2, y: (r.height - drawH) / 2, width: drawW, height: drawH))
                return true
            }
            guard let tiff = im.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) else { continue }
            try? png.write(to: dir.appendingPathComponent(String(format: "frame_%03d.png", i)))
        }
        cache = nil
        return frames.count
    }

    static func clear() {
        for f in (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? [] { try? FileManager.default.removeItem(at: f) }
        cache = nil
    }
}
