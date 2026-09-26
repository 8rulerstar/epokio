import SwiftUI
import AppKit

// 라벨 화면의 줌·팬. ★화면 좌표 ↔ 그림 좌표 변환은 여기 한 곳(`ImageFit`)에만 있다.
// 박스 그리기·끌기·꼭짓점은 LabelEditor가 "그려진 그림 칸" 안의 0~1 좌표로만 일하므로,
// 그 칸의 크기와 자리를 여기서 정확히 잡아 주면 확대 상태에서도 좌표가 저절로 맞는다.
//
// 조작(맥 기본 관습을 따른다):
//   마우스 휠 = 확대축소(커서 자리 고정) · 트랙패드 두 손가락 = 이동 · 핀치 = 확대축소
//   스페이스 + 끌기 = 이동 · 0 = 맞춤으로 복귀

/// 뷰포트 안에 그림이 실제로 그려지는 칸. zoom 1 = 창에 맞춤
struct ImageFit {
    var viewport: CGSize
    var image: CGSize
    var zoom: Double
    var pan: CGSize

    static let minZoom = 1.0
    static let maxZoom = 16.0

    /// 맞춤 배율(창에 다 들어가는 크기)
    var fitScale: Double {
        guard image.width > 0, image.height > 0 else { return 1 }
        return min(viewport.width / image.width, viewport.height / image.height)
    }

    /// 그려지는 크기
    var displaySize: CGSize {
        CGSize(width: image.width * fitScale * zoom, height: image.height * fitScale * zoom)
    }

    /// 그려지는 칸의 한가운데(뷰포트 좌표)
    var center: CGPoint { CGPoint(x: viewport.width / 2 + pan.width, y: viewport.height / 2 + pan.height) }

    /// 그림이 화면 밖으로 완전히 달아나지 않게 묶는다(가장자리에 늘 60pt는 남는다)
    func clamped(_ p: CGSize) -> CGSize {
        let d = displaySize
        let mx = max(0, (d.width - viewport.width) / 2) + max(0, viewport.width / 2 - 60)
        let my = max(0, (d.height - viewport.height) / 2) + max(0, viewport.height / 2 - 60)
        return CGSize(width: min(max(p.width, -mx), mx), height: min(max(p.height, -my), my))
    }

    /// 커서 자리를 고정한 채 배율만 바꾼다
    func zoomed(to z: Double, at cursor: CGPoint) -> (Double, CGSize) {
        let nz = min(max(z, Self.minZoom), Self.maxZoom)
        guard zoom > 0 else { return (nz, pan) }
        let k = nz / zoom
        let dx = (cursor.x - viewport.width / 2) - ((cursor.x - center.x) * k)
        let dy = (cursor.y - viewport.height / 2) - ((cursor.y - center.y) * k)
        var next = ImageFit(viewport: viewport, image: image, zoom: nz, pan: CGSize(width: dx, height: dy))
        next.pan = next.clamped(next.pan)
        return (nz, next.pan)
    }
}

/// 그림 + 그 위에 얹는 것(박스 보기·고치기)을 같은 칸에 그린다
struct LabelCanvas<Content: View>: View {
    let image: NSImage?
    @Binding var zoom: Double
    @Binding var pan: CGSize
    let spaceHeld: Bool
    @ViewBuilder var content: () -> Content

    @State private var panStart: CGSize?

    var body: some View {
        GeometryReader { geo in
            let fit = ImageFit(viewport: geo.size, image: image?.size ?? .zero, zoom: zoom, pan: pan)
            let d = fit.displaySize
            ZStack {
                Color.black.opacity(0.92)
                if let image {
                    Image(nsImage: image).resizable().interpolation(zoom > 2 ? .none : .high)
                        .frame(width: d.width, height: d.height)
                        .overlay { content() }
                        .position(x: fit.center.x, y: fit.center.y)
                        .transition(.opacity)
                }
            }
            .clipped()
            .contentShape(.rect)
            .overlay {
                // 스페이스를 누른 동안에만 위를 덮어 이동으로 쓴다(평소엔 박스 조작이 그대로 통한다)
                if spaceHeld {
                    Color.clear.contentShape(.rect)
                        .gesture(DragGesture(minimumDistance: 0)
                            .onChanged { g in
                                let s = panStart ?? pan
                                if panStart == nil { panStart = pan }
                                pan = fit.clamped(CGSize(width: s.width + g.translation.width, height: s.height + g.translation.height))
                            }
                            .onEnded { _ in panStart = nil })
                }
            }
            .overlay { ScrollZoom(onScroll: { pt, delta, precise in
                if precise {                                   // 트랙패드 두 손가락 = 이동
                    pan = fit.clamped(CGSize(width: pan.width + delta.width, height: pan.height + delta.height))
                } else {                                       // 마우스 휠 = 확대축소
                    let (z, p) = fit.zoomed(to: zoom * (1 + delta.height / 120), at: pt)
                    zoom = z; pan = p
                }
            }, onMagnify: { pt, m in
                let (z, p) = fit.zoomed(to: zoom * (1 + m), at: pt)
                zoom = z; pan = p
            })
            .allowsHitTesting(false) }
        }
    }
}

/// 휠·핀치를 받는다. SwiftUI에 스크롤 제스처가 없어 AppKit 이벤트를 직접 본다.
/// ★박스 조작을 가로채면 안 되므로 뷰를 덮지 않고(hitTesting 끔) 로컬 모니터로 본다.
struct ScrollZoom: NSViewRepresentable {
    var onScroll: (CGPoint, CGSize, Bool) -> Void
    var onMagnify: (CGPoint, CGFloat) -> Void

    func makeNSView(context: Context) -> ScrollZoomView { ScrollZoomView() }

    func updateNSView(_ v: ScrollZoomView, context: Context) {
        v.onScroll = onScroll
        v.onMagnify = onMagnify
    }
}

final class ScrollZoomView: NSView {
    var onScroll: ((CGPoint, CGSize, Bool) -> Void)?
    var onMagnify: ((CGPoint, CGFloat) -> Void)?
    private var monitor: Any?
    override var isFlipped: Bool { true }          // SwiftUI와 같은 좌표(왼쪽 위가 0)

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        if window == nil { stop() } else { start() }
    }

    private func start() {
        guard monitor == nil else { return }
        monitor = NSEvent.addLocalMonitorForEvents(matching: [.scrollWheel, .magnify]) { [weak self] e in
            guard let self, let w = self.window, e.window === w else { return e }
            let p = self.convert(e.locationInWindow, from: nil)
            guard self.bounds.contains(p) else { return e }
            if e.type == .magnify {
                self.onMagnify?(p, e.magnification)
            } else {
                self.onScroll?(p, CGSize(width: e.scrollingDeltaX, height: e.scrollingDeltaY), e.hasPreciseScrollingDeltas)
            }
            return nil
        }
    }

    func stop() {
        if let m = monitor { NSEvent.removeMonitor(m) }
        monitor = nil
    }
}
