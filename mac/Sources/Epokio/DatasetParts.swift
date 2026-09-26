import SwiftUI
import ImageIO

// 라벨 보기 부품: 썸네일, 박스 겹쳐 그리기, 크게 보기.

struct Thumb: View {
    let item: LabeledImage
    let boxes: [YoloBox]
    let classes: [Int: String]
    let side: Double
    @State private var image: NSImage?
    @State private var hover = false

    var body: some View {
        Group {
            if let image {
                Image(nsImage: image).resizable().scaledToFit()
                    .overlay { BoxOverlay(boxes: boxes, classes: classes, labels: false) }
                    .overlay(alignment: .bottomLeading) { badge }        // ★배지는 사진 위에 (칸 모서리에 두면 허공에 떴다)
                    .clipShape(.rect(cornerRadius: 8))
            } else {
                RoundedRectangle(cornerRadius: 8).fill(.quaternary).overlay(ProgressView().controlSize(.small))
            }
        }
        .frame(width: side, height: side * 0.75)
        .scaleEffect(hover ? 1.03 : 1)
        .shadow(color: .black.opacity(hover ? 0.18 : 0), radius: 8, y: 3)
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(item.name)
        .task(id: item.id) { image = await loadThumb(item.id, max: side * 2) }
    }
}

/// 썸네일 기억. ★검수·라벨 보기에서 스크롤할 때마다 같은 이미지를 디스크에서 다시 읽고 줄였다
nonisolated(unsafe) let thumbCache: NSCache<NSString, NSImage> = { let c = NSCache<NSString, NSImage>(); c.countLimit = 600; return c }()

func loadThumb(_ url: URL, max: Double) async -> NSImage? {
    let key = "\(url.path)#\(Int(max))" as NSString
    if let hit = thumbCache.object(forKey: key) { return hit }
    let img = await decodeThumb(url, max: max)
    if let img { thumbCache.setObject(img, forKey: key) }
    return img
}

private func decodeThumb(_ url: URL, max: Double) async -> NSImage? {
    await Task.detached(priority: .utility) {
        guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
        let opts: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true,
                                     kCGImageSourceThumbnailMaxPixelSize: Int(max),
                                     kCGImageSourceCreateThumbnailWithTransform: true]
        guard let cg = CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary) else { return nil }
        return NSImage(cgImage: cg, size: .zero)
    }.value
}

// 박스 그리기. 좌표는 0~1 비율이라 어떤 크기에도 맞는다

struct BoxOverlay: View {
    let boxes: [YoloBox]
    let classes: [Int: String]
    var labels = true

    var body: some View {
        canvas
            .accessibilityElement()
            .accessibilityLabel(L("%lld boxes", boxes.count))
    }

    private var canvas: some View {
        Canvas { ctx, size in
            for b in boxes {
                let r = CGRect(x: (b.cx - b.w / 2) * size.width, y: (b.cy - b.h / 2) * size.height,
                               width: b.w * size.width, height: b.h * size.height)
                let c = classColor(b.cls)
                ctx.fill(Path(r), with: .color(c.opacity(0.12)))
                ctx.stroke(Path(roundedRect: r, cornerRadius: 2), with: .color(c), lineWidth: labels ? 2 : 1.2)
                for (x, y, v) in b.kpts where v > 0 {
                    let p = CGRect(x: x * size.width - 3, y: y * size.height - 3, width: 6, height: 6)
                    ctx.fill(Path(ellipseIn: p), with: .color(.white))
                    ctx.fill(Path(ellipseIn: p.insetBy(dx: 1.2, dy: 1.2)), with: .color(c))
                }
                if labels {
                    var t = classes[b.cls] ?? "\(b.cls)"
                    if let cf = b.conf { t += String(format: " %.2f", cf) }
                    let text = Text(t).font(.ui(11, weight: .semibold)).foregroundStyle(.white)
                    let resolved = ctx.resolve(text)
                    let sz = resolved.measure(in: size)
                    let tag = CGRect(x: r.minX, y: max(r.minY - sz.height - 4, 0), width: sz.width + 8, height: sz.height + 4)
                    ctx.fill(Path(roundedRect: tag, cornerRadius: 3), with: .color(c))
                    ctx.draw(resolved, at: CGPoint(x: tag.minX + 4, y: tag.minY + 2), anchor: .topLeading)
                }
            }
        }
        .allowsHitTesting(false)
    }
}

// 크게 보기. ← → 로 넘긴다

struct Viewer: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.ink) private var ink
    let ds: Dataset
    let items: [LabeledImage]
    @State var current: LabeledImage
    @State private var image: NSImage?

    var index: Int { items.firstIndex(of: current) ?? 0 }

    var body: some View {
        let boxes = ds.boxes(current)
        VStack(spacing: 0) {
            HStack {
                Text(current.name).font(.ui(13, weight: .semibold)).lineLimit(1).truncationMode(.middle)
                Spacer()
                Text("\(index + 1) / \(items.count)").font(.ui(13, design: .monospaced)).foregroundStyle(ink.soft)
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            .padding(12)
            Divider()
            ZStack {
                Color.black.opacity(0.92)
                if let image {
                    Image(nsImage: image).resizable().scaledToFit()
                        .overlay { BoxOverlay(boxes: boxes, classes: ds.classes) }
                        .transition(.opacity)
                }
            }
            HStack(spacing: 14) {
                if current.label == nil {
                    Label("No label file for this image", systemImage: "questionmark.circle").foregroundStyle(.warn)
                } else if boxes.isEmpty {
                    Label("Label file is empty", systemImage: "circle.dashed").foregroundStyle(ink.soft)
                } else {
                    let counts = Dictionary(grouping: boxes, by: \.cls).mapValues(\.count)
                    ForEach(counts.keys.sorted(), id: \.self) { k in
                        Label("\(ds.classes[k] ?? "\(k)") \(counts[k]!)", systemImage: "square.fill")
                            .foregroundStyle(classColor(k)).font(.ui(12.5))
                    }
                }
                Spacer()
                if let l = current.label {
                    Button("Show label file") { NSWorkspace.shared.activateFileViewerSelecting([l]) }.buttonStyle(BrandLink())
                }
            }
            .padding(12)
        }
        .task(id: current) { image = await loadThumb(current.id, max: 2400) }
        .onKeyPress(.leftArrow) { move(-1); return .handled }
        .onKeyPress(.rightArrow) { move(1); return .handled }
        .focusable()
        .focusEffectDisabled()          // ★키보드 조작용 포커스라 파란 테두리는 숨긴다(창 위아래에 어색한 선으로 보였다)
    }

    private func move(_ d: Int) {
        let i = min(max(index + d, 0), items.count - 1)
        withAnimation(Motion.hover) { current = items[i] }
    }
}
