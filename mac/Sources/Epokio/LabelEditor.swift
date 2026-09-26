import SwiftUI

// 검수 중 라벨 바로 고치기. 원본 라벨은 건드리지 않고 평가 폴더의 labels_fixed/ 에 저장한다(agent /review/fix).
// 조작: 박스 끌기 = 옮기기 · 모서리 끌기 = 크기 · 빈 곳 끌기 = 새 박스 · Delete = 지우기 · 클래스는 아래 목록에서

struct EditBox: Identifiable, Hashable {
    let id = UUID()
    var cls: Int
    var box: [Double]              // cx, cy, w, h (0~1)
    var rect: CGRect {
        get { CGRect(x: box[0] - box[2] / 2, y: box[1] - box[3] / 2, width: box[2], height: box[3]) }
        set {
            let r = newValue.standardized.intersection(CGRect(x: 0, y: 0, width: 1, height: 1))
            box = [r.midX, r.midY, max(r.width, 0.002), max(r.height, 0.002)]
        }
    }
}

struct LabelEditor: View {
    @Binding var boxes: [EditBox]
    @Binding var selected: EditBox.ID?
    let names: [String: String]?
    let newClass: Int

    @State private var drag: (id: EditBox.ID, start: CGRect, corner: Int?)?   // corner: nil=옮기기, 0~3=모서리
    @State private var drawing: CGRect?

    var body: some View {
        GeometryReader { geo in
            let S = geo.size
            ZStack(alignment: .topLeading) {
                Color.clear.contentShape(.rect)
                ForEach(boxes) { b in
                    let r = scaled(b.rect, S), on = b.id == selected
                    Rectangle()
                        .strokeBorder(on ? Color.brand : .good, lineWidth: on ? 3 : 2)
                        .background(on ? Color.brand.opacity(0.12) : .clear)
                        .frame(width: r.width, height: r.height)
                        .overlay(alignment: .topLeading) {
                            Text(verbatim: names?[String(b.cls)] ?? "\(b.cls)")
                                .font(.ui(11, weight: .bold)).foregroundStyle(.white)
                                .padding(.horizontal, 4).padding(.vertical, 1)
                                .background(on ? Color.brand : .good, in: .rect(cornerRadius: 3))
                                .offset(y: -18)
                        }
                        .overlay { if on { handles(r.size) } }
                        .position(x: r.midX, y: r.midY)
                        .animation(Motion.tap, value: on)
                }
                if let d = drawing {
                    let r = scaled(d, S)
                    Rectangle().strokeBorder(Color.brand, style: StrokeStyle(lineWidth: 2, dash: [5, 3]))
                        .frame(width: r.width, height: r.height).position(x: r.midX, y: r.midY)
                }
            }
            .gesture(DragGesture(minimumDistance: 0).onChanged { g in changed(g, S) }.onEnded { g in ended(g, S) })
        }
    }

    private func scaled(_ r: CGRect, _ s: CGSize) -> CGRect {
        CGRect(x: r.minX * s.width, y: r.minY * s.height, width: r.width * s.width, height: r.height * s.height)
    }

    /// 선택한 박스의 네 모서리 손잡이
    private func handles(_ s: CGSize) -> some View {
        ZStack {
            ForEach(0..<4, id: \.self) { i in
                Circle().fill(.white).overlay(Circle().stroke(Color.brand, lineWidth: 2)).frame(width: 10, height: 10)
                    .position(x: i % 2 == 0 ? 0 : s.width, y: i < 2 ? 0 : s.height)
            }
        }
        .transition(.scale.combined(with: .opacity))
    }

    private func changed(_ g: DragGesture.Value, _ S: CGSize) {
        let p = CGPoint(x: g.location.x / S.width, y: g.location.y / S.height)
        let p0 = CGPoint(x: g.startLocation.x / S.width, y: g.startLocation.y / S.height)
        if drag == nil && drawing == nil {
            // 선택한 박스의 모서리 → 크기, 박스 안 → 옮기기(위에 그려진 것 먼저), 빈 곳 → 새로 그리기
            let tol = 8 / min(S.width, S.height)
            if let sel = boxes.first(where: { $0.id == selected }) {
                let r = sel.rect
                let corners = [CGPoint(x: r.minX, y: r.minY), CGPoint(x: r.maxX, y: r.minY), CGPoint(x: r.minX, y: r.maxY), CGPoint(x: r.maxX, y: r.maxY)]
                if let c = corners.firstIndex(where: { abs($0.x - p0.x) < tol && abs($0.y - p0.y) < tol }) {
                    drag = (sel.id, r, c)
                }
            }
            // ★겹친 박스는 작은 것부터: 큰 박스가 나중에 그려졌다고 그 안의 작은 박스를 못 고르면 안 된다
            if drag == nil, let hit = boxes.filter({ $0.rect.insetBy(dx: -tol, dy: -tol).contains(p0) })
                .min(by: { $0.rect.width * $0.rect.height < $1.rect.width * $1.rect.height }) {
                selected = hit.id
                drag = (hit.id, hit.rect, nil)
            }
            if drag == nil { selected = nil; drawing = .zero }
        }
        if let d = drag, let i = boxes.firstIndex(where: { $0.id == d.id }) {
            let dx = p.x - p0.x, dy = p.y - p0.y
            var r = d.start
            switch d.corner {
            case nil: r = r.offsetBy(dx: dx, dy: dy)
            case 0?: r = CGRect(x: r.minX + dx, y: r.minY + dy, width: r.width - dx, height: r.height - dy)
            case 1?: r = CGRect(x: r.minX, y: r.minY + dy, width: r.width + dx, height: r.height - dy)
            case 2?: r = CGRect(x: r.minX + dx, y: r.minY, width: r.width - dx, height: r.height + dy)
            default: r = CGRect(x: r.minX, y: r.minY, width: r.width + dx, height: r.height + dy)
            }
            boxes[i].rect = r
        } else if drawing != nil {
            drawing = CGRect(x: min(p0.x, p.x), y: min(p0.y, p.y), width: abs(p.x - p0.x), height: abs(p.y - p0.y))
        }
    }

    private func ended(_ g: DragGesture.Value, _ S: CGSize) {
        if let d = drawing, d.width * S.width > 6, d.height * S.height > 6 {       // 너무 작으면 클릭으로 본다
            var b = EditBox(cls: newClass, box: [0, 0, 0, 0]); b.rect = d
            withAnimation(.snappy) { boxes.append(b); selected = b.id }
        }
        drag = nil; drawing = nil
    }
}

/// 편집 막대: 선택한 박스 클래스 · 지우기 · 모델 답에서 시작 · 되돌리기 · 저장
struct LabelEditBar: View {
    @Binding var boxes: [EditBox]
    @Binding var selected: EditBox.ID?
    @Binding var newClass: Int
    let names: [String: String]?
    let onFromModel: () -> Void
    let onReset: () -> Void
    let onSave: () -> Void
    let onCancel: () -> Void
    @Environment(\.ink) private var ink

    private var classes: [(Int, String)] {
        let known = (names ?? [:]).compactMap { k, v in Int(k).map { ($0, v) } }.sorted { $0.0 < $1.0 }
        let used = Set(boxes.map(\.cls)).subtracting(known.map(\.0)).map { ($0, "\($0)") }
        return known + used
    }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "pencil.and.outline").foregroundStyle(.tint).accessibilityHidden(true)
            Text("Drag to move · corners to resize · drag on empty space to add").font(.ui(11.5)).foregroundStyle(ink.soft)
            Spacer()
            Picker("Class", selection: Binding(
                get: { boxes.first { $0.id == selected }?.cls ?? newClass },
                set: { c in newClass = c; if let i = boxes.firstIndex(where: { $0.id == selected }) { boxes[i].cls = c } })) {
                ForEach(classes, id: \.0) { Text(verbatim: "\($0.0)  \($0.1)").tag($0.0) }
            }
            .frame(width: 180)
            Button { if let i = boxes.firstIndex(where: { $0.id == selected }) { withAnimation(.snappy) { _ = boxes.remove(at: i); selected = nil } } } label: {
                Label("Delete", systemImage: "trash")
            }
            .keyboardShortcut(.delete, modifiers: []).disabled(selected == nil)
            Menu {
                Button("Start from the Model's Boxes", action: onFromModel)
                Button("Undo All Changes", action: onReset)
            } label: { Image(systemName: "ellipsis.circle") }
            .menuIndicator(.hidden).fixedSize().accessibilityLabel("More")
            Button("Cancel", action: onCancel).keyboardShortcut(.cancelAction)
            Button { onSave() } label: { Label("Save Fix", systemImage: "checkmark") }
                .primaryButton().keyboardShortcut(.return, modifiers: .command)
                .help("Saved next to the check results (labels_fixed). Your original labels stay as they are.")
        }
    }
}

/// 분류의 라벨 고치기: 올바른 클래스를 고른다. 모델의 상위 답을 먼저 버튼으로 보여 준다
struct ClassFixBar: View {
    @Binding var cls: Int
    let names: [String: String]?
    let top: [[Double]]
    let onSave: () -> Void
    let onCancel: () -> Void
    @Environment(\.ink) private var ink

    private var all: [(Int, String)] { (names ?? [:]).compactMap { k, v in Int(k).map { ($0, v) } }.sorted { $0.0 < $1.0 } }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "tag").foregroundStyle(.tint).accessibilityHidden(true)
            Text("The right class is").font(.ui(12.5))
            ForEach(Array(top.prefix(3).enumerated()), id: \.offset) { _, t in
                let c = Int(t.first ?? -1)
                Button { withAnimation(.snappy) { cls = c } } label: {
                    Text(verbatim: "\(names?[String(c)] ?? "\(c)")  \(String(format: "%.2f", t.count > 1 ? t[1] : 0))")
                        .font(.ui(12, weight: cls == c ? .bold : .regular))
                }
                .secondaryButton().tint(cls == c ? .brand : nil)
            }
            Picker("Class", selection: $cls) {
                ForEach(all, id: \.0) { Text(verbatim: "\($0.0)  \($0.1)").tag($0.0) }
            }
            .labelsHidden().frame(width: 170)
            Spacer()
            Button("Cancel", action: onCancel).keyboardShortcut(.cancelAction)
            Button { onSave() } label: { Label("Save Fix", systemImage: "checkmark") }
                .primaryButton().keyboardShortcut(.return, modifiers: .command)
                .help("Saved next to the check results (labels_fixed). Your image folders stay as they are.")
        }
    }
}
