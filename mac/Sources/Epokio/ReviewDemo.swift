import SwiftUI

// 검수 화면 스냅샷용 내장 데모(`--review-demo`). agent를 부르지 않고, 사용자 폴더·설정도 읽지 않는다.
// 사진 대신 도형을 그린 합성 이미지를 임시 폴더에 만든다. 실제 데이터가 스냅샷에 찍히지 않게 하려는 것.
enum ReviewDemo {
    static var enabled: Bool { CommandLine.arguments.contains("--review-demo") }

    @MainActor static func result() -> EvalResult {
        let dir = FileManager.default.temporaryDirectory.appending(path: "epokio-review-demo")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let names = ["0": "circle", "1": "square", "2": "triangle"]
        var rows: [EvalRow] = []
        var rng = SystemRandomNumberGenerator()
        for i in 0..<18 {
            let url = dir.appending(path: String(format: "shapes_%02d.png", i))
            let n = 1 + i % 3
            let gt = (0..<n).map { k in
                EvalBox(cls: (i + k) % 3, box: [0.22 + 0.28 * Double(k), 0.5 + 0.1 * Double(k % 2), 0.2, 0.26], conf: nil, kpts: [])
            }
            let fn = i % 4 == 0 ? 1 : 0, fp = i % 5 == 1 ? 1 : 0, cls = i % 7 == 3
            var pred = Array(gt.dropLast(fn)).map { EvalBox(cls: $0.cls, box: $0.box, conf: 0.9, kpts: []) }
            if fp == 1 { pred.append(EvalBox(cls: 1, box: [0.8, 0.2, 0.14, 0.16], conf: 0.41, kpts: [])) }
            let tp = n - fn
            let f1 = Double(2 * tp) / Double(2 * tp + fp + fn)
            var row = EvalRow(image: url.path, label: "", tp: tp, fp: fp, fn: fn, f1: f1, kpt: nil,
                              score: max(0, f1 - (cls ? 0.2 : 0) - Double.random(in: 0...0.05, using: &rng)), gt: gt, pred: pred)
            row.gt_status = gt.indices.map { $0 >= n - fn ? "fn" : (cls && $0 == 0 ? "cls" : "tp") }
            row.pred_status = pred.indices.map { $0 >= tp ? "fp" : (cls && $0 == 0 ? "cls" : "tp") }
            rows.append(row)
            if !FileManager.default.fileExists(atPath: url.path) { draw(url, gt: gt, seed: i) }
        }
        let mean = rows.map(\.score).reduce(0, +) / Double(rows.count)
        let curve = stride(from: 0.05, through: 0.95, by: 0.05).map { c in
            EvalResult.CurvePoint(conf: c, precision: 0.6 + 0.35 * c, recall: 0.95 - 0.5 * c * c, f1: 0.62 + 0.25 * sin(c * .pi))
        }
        func cc(_ k: Int, _ n: String, _ s: Int, _ tp: Int, _ fp: Int, _ fn: Int) -> EvalResult.ClassCounts {
            let p = Double(tp) / Double(tp + fp), r = Double(tp) / Double(tp + fn)
            return .init(cls: k, name: n, support: s, tp: tp, fp: fp, fn: fn, precision: p, recall: r, f1: 2 * p * r / (p + r))
        }
        return EvalResult(task: "detect", source: nil, metric: "f1", images: rows.count, mean: mean, rows: rows,
                          conf: 0.25, conf_floor: 0.05,
                          overall: .init(tp: 30, fp: 4, fn: 5, precision: 0.882, recall: 0.857, f1: 0.869),
                          per_class: [cc(0, "circle", 12, 11, 1, 1), cc(1, "square", 12, 9, 3, 3), cc(2, "triangle", 11, 10, 0, 1)],
                          confusion: .init(labels: ["circle", "square", "triangle", "Background"], classes: [0, 1, 2, -1],
                                           matrix: [[11, 0, 0, 1], [1, 9, 0, 2], [0, 0, 10, 1], [0, 3, 0, 0]]),
                          curve: curve, best_conf: 0.45, names: names,
                          official: .init(precision: 0.874, recall: 0.842, map50: 0.901, conf: 0.4, top1: nil), trained: nil)
    }

    /// 파스텔 배경에 도형 몇 개. 사진이 아니다
    private static func draw(_ url: URL, gt: [EvalBox], seed: Int) {
        let size = NSSize(width: 480, height: 360)
        let hues: [Double] = [0.08, 0.55, 0.3, 0.75, 0.95, 0.15]
        let img = NSImage(size: size, flipped: true) { r in
            NSColor(hue: hues[seed % hues.count], saturation: 0.18, brightness: 0.93, alpha: 1).setFill(); r.fill()
            for g in gt {
                let b = g.box
                let rect = NSRect(x: (b[0] - b[2] / 2) * r.width, y: (b[1] - b[3] / 2) * r.height, width: b[2] * r.width, height: b[3] * r.height)
                NSColor(hue: Double(g.cls) / 3, saturation: 0.55, brightness: 0.75, alpha: 1).setFill()
                switch g.cls {
                case 0: NSBezierPath(ovalIn: rect).fill()
                case 1: NSBezierPath(rect: rect.insetBy(dx: 4, dy: 4)).fill()
                default:
                    let p = NSBezierPath(); p.move(to: NSPoint(x: rect.midX, y: rect.minY))
                    p.line(to: NSPoint(x: rect.maxX, y: rect.maxY)); p.line(to: NSPoint(x: rect.minX, y: rect.maxY)); p.close(); p.fill()
                }
            }
            return true
        }
        if let t = img.tiffRepresentation, let png = NSBitmapImageRep(data: t)?.representation(using: .png, properties: [:]) { try? png.write(to: url) }
    }
}
