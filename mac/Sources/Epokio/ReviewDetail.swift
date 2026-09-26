import SwiftUI

// 검수 크게 보기: 이미지 + 정답·예측 겹침, 1~4 판정, ←→ 넘기기, 스페이스 닫기, ⌘Z 되돌리기, 확대·이동, 라벨·클래스 고치기.

struct ReviewDetail: View {
    @Environment(\.ink) private var ink
    let row: EvalRow
    @Binding var verdict: Verdict?
    let rows: [EvalRow]
    @Binding var open: EvalRow?
    @Binding var verdicts: [String: Verdict]
    let onSave: () -> Void
    var onMark: ([String], Verdict?) -> Void = { _, _ in }
    var onUndo: () -> Void = {}
    var job: String? = nil
    var names: [String: String]? = nil
    var onFixed: (String) -> Void = { _ in }
    var classify = false
    var canFix = true
    @State private var image: NSImage?
    @Environment(Store.self) private var store
    // 라벨 고치기
    @State private var editing = false
    @State private var boxes: [EditBox] = []
    @State private var sel: EditBox.ID?
    @State private var newClass = 0
    @State private var stamp: Verdict?                   // 방금 누른 판정: 그림 위에 잠깐 찍고 다음 장으로
    @State private var pressed = 0

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(URL(fileURLWithPath: row.image).lastPathComponent).font(.ui(13, weight: .semibold)).lineLimit(1).truncationMode(.middle)
                Spacer()
                if !editing {
                    Label("Label", systemImage: "square").foregroundStyle(.good).font(.ui(11.5))
                    Label("Model", systemImage: "square.dashed").foregroundStyle(.bad).font(.ui(11.5))
                    if job != nil && canFix {
                        Button { startEdit() } label: { Label(classify ? "Fix Class" : "Fix Label", systemImage: "pencil") }
                            .keyboardShortcut("e", modifiers: [])
                            .help("Correct the boxes of this image (E). Your original label file is not changed.")
                    }
                }
                Button("Done") { open = nil }.keyboardShortcut(.cancelAction)
            }
            .padding(12)
            ZStack {
                Color.black.opacity(0.92)
                if let v = stamp {                               // ★누르면 바로 다음 장으로 넘어가 눌렸는지 알 수 없었다
                    Label { Text(v.title) } icon: { Image(systemName: v.symbol) }
                        .font(.role(.title, weight: .bold)).foregroundStyle(.white)
                        .padding(.horizontal, 22).padding(.vertical, 12)
                        .background(v.color.opacity(0.92), in: Capsule())
                        .shadow(color: v.color.opacity(0.5), radius: 16)
                        .transition(.scale(scale: 0.6).combined(with: .opacity))
                        .zIndex(2)
                }
                if let image {
                    ZoomPan(enabled: !(editing && !classify), reset: row.id) {         // 확대·이동(미리보기·사진처럼). 라벨 편집 중엔 끈다
                        Image(nsImage: image).resizable().scaledToFit()
                            .overlay {
                                if editing && !classify {
                                    LabelEditor(boxes: $boxes, selected: $sel, names: names, newClass: newClass)
                                        .transition(.opacity)
                                } else {
                                    CompareOverlay(gt: row.gt, pred: row.pred, gtStatus: row.gt_status, predStatus: row.pred_status, names: names, classify: classify)
                                        .transition(.opacity)
                                }
                            }
                    }
                }
            }
            if editing && classify {
                ClassFixBar(cls: $newClass, names: names, top: row.top ?? [],
                            onSave: { boxes = [EditBox(cls: newClass, box: [0.5, 0.5, 1, 1])]; Task { await saveFix() } },
                            onCancel: { withAnimation(.snappy) { editing = false } })
                    .padding(12)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            } else if editing {
                LabelEditBar(boxes: $boxes, selected: $sel, newClass: $newClass, names: names,
                             onFromModel: { withAnimation(.snappy) { boxes = row.pred.map { EditBox(cls: $0.cls, box: $0.box) }; sel = nil } },
                             onReset: { withAnimation(.snappy) { boxes = row.gt.map { EditBox(cls: $0.cls, box: $0.box) }; sel = nil } },
                             onSave: { Task { await saveFix() } },
                             onCancel: { withAnimation(.snappy) { editing = false } })
                    .padding(12)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            } else {
            HStack(spacing: 10) {
                Text(verbatim: L("Score %@", String(format: "%.2f", row.score)))
                    .font(.ui(13, weight: .semibold, design: .rounded))
                    .foregroundStyle(row.score < 0.5 ? .bad : row.score < 0.8 ? .warn : .good)
                CountChips(row: row)
                Spacer()
                ForEach(Verdict.allCases, id: \.self) { v in
                    Button {
                        set(v)
                    } label: {
                        Label { Text(v.title) } icon: { Image(systemName: v.symbol).symbolEffect(.bounce, value: stamp == v ? pressed : 0) }
                            .padding(.horizontal, 6)
                    }
                    .secondaryButton()
                    .tint(verdict == v ? v.color : nil)
                    .keyboardShortcut(KeyEquivalent(v.key), modifiers: [])
                    .help("Press \(String(v.key))")
                }
            }
            .padding(12)
            }
        }
        .animation(Motion.change, value: editing)
        .onChange(of: row) { editing = false }
        .task(id: row) { image = await loadThumb(URL(fileURLWithPath: row.image), max: 2400) }
        .onKeyPress(.leftArrow) { go(-1); return .handled }
        .onKeyPress(.rightArrow) { go(1); return .handled }
        .onKeyPress(.space) { if editing { return .ignored }; open = nil; return .handled }     // 훑어보기: 스페이스로 닫기
        .background { Button("") { onUndo() }.keyboardShortcut("z", modifiers: .command).hidden() }
        .focusable()
        .focusEffectDisabled()          // ★키보드 조작용 포커스라 파란 테두리는 숨긴다(창 위아래에 어색한 선으로 보였다)
    }

    private func startEdit() {
        boxes = row.gt.map { EditBox(cls: $0.cls, box: $0.box) }
        newClass = classify ? (row.pred.first?.cls ?? row.truth ?? 0) : (row.gt.first?.cls ?? 0)   // 분류: 모델 답을 먼저 제안
        sel = nil
        Task {                                         // 전에 고친 게 있으면 거기서 이어서
            if let job, let d = try? await AgentClient.local.post("review/fixed", ["job": job]),
               let f = d["fixed"] as? [String: [[String: Any]]], let mine = f[stem] {
                boxes = mine.compactMap { b in (b["cls"] as? Int).flatMap { c in (b["box"] as? [Double]).map { EditBox(cls: c, box: $0) } } }
                if classify, let c = boxes.first?.cls { newClass = c }
            }
            withAnimation(.snappy) { editing = true }
        }
    }

    private var stem: String { let n = URL(fileURLWithPath: row.image).lastPathComponent; return String(n[..<(n.lastIndex(of: ".") ?? n.endIndex)]) }

    private func saveFix() async {
        guard let job else { return }
        let body: [[String: Any]] = boxes.map { ["cls": $0.cls, "box": $0.box] }
        await store.act(L("Fixed label saved")) {
            _ = try await AgentClient.local.post("review/fix", ["job": job, "image": row.image, "boxes": body])
        }
        onFixed(stem); Haptic.success(); Trophies.shared.bump("fix")
        withAnimation(Motion.change) { editing = false }
        if verdict == nil || verdict == .ok { onMark([row.id], .label) }                // 고쳤으면 "라벨 틀림"
    }

    private func set(_ v: Verdict) {
        onMark([row.id], v)
        pressed += 1
        withAnimation(Motion.celebrate) { stamp = v }
        let here = row.id
        Task {                                            // 도장을 잠깐 보인 뒤 다음 장으로(키 하나로 쭉 넘기는 흐름은 그대로)
            try? await Task.sleep(for: .milliseconds(330))
            guard row.id == here else { return }
            withAnimation(Motion.change) { stamp = nil }
            go(1)
        }
    }
    private func go(_ d: Int) {
        guard let i = rows.firstIndex(of: row) else { return }
        let j = i + d
        if rows.indices.contains(j) { open = rows[j] }
    }
}

/// 확대·이동: 트랙패드 두 손가락 벌리기·스크롤로 확대, 끌어서 이동, 두 번 누르면 원래대로/2.5배.
/// 다음 이미지로 넘어가면(reset이 바뀌면) 원래 크기로
struct ZoomPan<Content: View>: View {
    var enabled = true
    var reset: String = ""
    @ViewBuilder var content: () -> Content
    @State private var scale: CGFloat = 1
    @State private var base: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var start: CGSize = .zero

    var body: some View {
        content()
            .scaleEffect(scale)
            .offset(offset)
            .gesture(enabled ? MagnifyGesture()
                .onChanged { v in scale = min(max(base * v.magnification, 1), 8) }
                .onEnded { _ in base = scale; if scale == 1 { withAnimation(Motion.change) { offset = .zero } } } : nil)
            .simultaneousGesture(enabled && scale > 1 ? DragGesture()
                .onChanged { v in offset = CGSize(width: start.width + v.translation.width, height: start.height + v.translation.height) }
                .onEnded { _ in start = offset } : nil)
            .onTapGesture(count: 2) {
                guard enabled else { return }
                withAnimation(Motion.change) {
                    if scale > 1 { scale = 1; offset = .zero } else { scale = 2.5 }
                    base = scale; start = offset
                }
            }
            .onChange(of: reset) { scale = 1; base = 1; offset = .zero; start = .zero }
            .overlay(alignment: .bottomTrailing) {
                if scale > 1.01 {
                    Text(verbatim: String(format: "%.1f×", scale)).font(.role(.badge)).foregroundStyle(.white)
                        .padding(.horizontal, 7).padding(.vertical, 3).background(.black.opacity(0.55), in: Capsule())
                        .padding(8).transition(.opacity)
                }
            }
            .clipped()
            .help("Pinch or double-click to zoom, drag to move")
    }
}
