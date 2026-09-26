import SwiftUI

/// 크게 보기 + 고치기.
/// 넘기기 ⌥←→ (고친 것은 저장하고 넘어간다) · E 고치기 · 숫자 클래스 · N 봤고 없음 · V 확인함 · ⌘S 저장 · ⌘Z 되돌리기
/// 확대축소: 휠·핀치 · 이동: 두 손가락·스페이스+끌기 · 맞춤: 0 (고치는 중에는 숫자가 클래스라 ⌘0)
///
/// ★클래스 10개 초과: 숫자키는 "지금 10칸 묶음"의 0~9이고 [ ] 로 묶음을 넘긴다. C를 누르면 이름으로 찾는다.
///   왜 이 방식인가: ①클래스가 10개 이하인 기존 데이터셋에서는 동작이 예전과 완전히 같다(손가락 기억을 안 깬다)
///   ②⌥·⌃ 조합으로 20~30개를 억지로 넣는 방식은 화살표 미세조정(⌥←→ 넘기기)과 부딪히고 외우기 어렵다
///   ③이름을 아는 사람에게는 묶음 번호보다 검색이 빠르다. 그래서 두 길을 같이 둔다
struct LabelingViewer: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.ink) private var ink
    @Environment(Store.self) private var store
    let ds: Dataset
    let progress: LabelProgress
    let items: [LabeledImage]
    @State var current: LabeledImage
    @State private var image: NSImage?
    @State private var editing = false
    @State private var boxes: [EditBox] = []
    @State private var sel: EditBox.ID?
    @State private var newClass = 0
    @State private var dirty = false
    @State private var savedTick = 0
    @State private var undo: [[EditBox]] = []          // ⌘Z: 박스를 바꾸기 직전 모습들(최근 30단계)
    @State private var zoom = 1.0
    @State private var pan = CGSize.zero
    @State private var spaceHeld = false
    @State private var classPage = 0
    @State private var showPalette = false
    @State private var autosave: Task<Void, Never>?
    @State private var saveFailed = false              // ★백업 실패 등으로 저장이 막히면 자동 저장을 멈춘다(같은 경고를 반복하지 않게)

    private var index: Int { items.firstIndex(of: current) ?? 0 }
    private var names: [String: String] { Dictionary(uniqueKeysWithValues: ds.classes.map { (String($0.key), $0.value) }) }
    private var classes: [(id: Int, name: String)] {
        let list = classList(names, used: boxes.map(\.cls))
        return list.isEmpty ? [(id: 0, name: "0")] : list
    }
    /// 포즈 키포인트가 든 라벨은 1차에선 고치지 않는다(박스만 저장하면 키포인트가 사라진다)
    private var hasKeypoints: Bool { ds.boxes(current).contains { !$0.kpts.isEmpty } }

    var body: some View {
        let st = progress.status(current, boxes: editing ? boxes.count : ds.boxes(current).count)
        VStack(spacing: 0) {
            topBar(st)
            Divider()
            LabelCanvas(image: image, zoom: $zoom, pan: $pan, spaceHeld: spaceHeld) {
                if editing {
                    LabelEditor(boxes: $boxes, selected: $sel, names: names, newClass: newClass).transition(.opacity)
                } else {
                    BoxOverlay(boxes: ds.boxes(current), classes: ds.classes)
                }
            }
            .overlay(alignment: .topTrailing) { originBadge(st) }
            .overlay(alignment: .bottomTrailing) { zoomControls }
            .onChange(of: boxes) { old, _ in
                guard editing else { return }
                dirty = true
                if undo.last != old { undo.append(old); if undo.count > 30 { undo.removeFirst() } }
                scheduleAutosave()
            }
            bottomBar(st)
        }
        .task(id: current) { image = await loadThumb(current.id, max: 2400) }
        .onDisappear { autosave?.cancel(); commit() }
        .onKeyPress(keys: [.leftArrow, .rightArrow, .upArrow, .downArrow], phases: .down) { k in arrow(k) }
        .onKeyPress(.space, phases: [.down, .up]) { k in
            withAnimation(Motion.tap) { spaceHeld = k.phase == .down }
            return .handled
        }
        .onKeyPress(characters: .decimalDigits) { k in digit(k) }
        .onKeyPress(characters: .init(charactersIn: "nN")) { _ in markEmpty(); return .handled }
        .onKeyPress(characters: .init(charactersIn: "vV")) { _ in toggleVerified(); return .handled }
        .onKeyPress(characters: .init(charactersIn: "cC")) { _ in
            guard editing else { return .ignored }
            showPalette = true; return .handled
        }
        .onKeyPress(characters: .init(charactersIn: "[]")) { k in
            guard editing, classes.count > 10 else { return .ignored }
            let pages = (classes.count + 9) / 10
            withAnimation(Motion.change) { classPage = min(max(classPage + (k.characters == "[" ? -1 : 1), 0), pages - 1) }
            return .handled
        }
        .background {
            Button("") { commit() }.keyboardShortcut("s", modifiers: .command).hidden()
            Button("") { undoOnce() }.keyboardShortcut("z", modifiers: .command).disabled(undo.isEmpty).hidden()
            Button("") { fitToWindow() }.keyboardShortcut("0", modifiers: .command).hidden()
        }
        .focusable()
        .focusEffectDisabled()
        .animation(Motion.change, value: editing)
    }

    // MARK: 화면 조각

    @ViewBuilder private func topBar(_ st: LabelStatus) -> some View {
        HStack(spacing: 10) {
            Image(systemName: st.symbol).foregroundStyle(st.tint).help(st.title).contentTransition(.symbolEffect(.replace))
            Text(current.name).font(.ui(13, weight: .semibold)).lineLimit(1).truncationMode(.middle)
            Spacer()
            Text("\(index + 1) / \(items.count)").font(.ui(13, design: .monospaced)).foregroundStyle(ink.soft)
            if !editing {
                Button { startEdit() } label: { Label("Edit", systemImage: "pencil") }
                    .keyboardShortcut("e", modifiers: []).disabled(hasKeypoints)
                    .help(hasKeypoints ? L("Keypoint labels can't be edited here yet") : L("Edit boxes (E)"))
            }
            Button("Done") { commit(); dismiss() }.keyboardShortcut(.cancelAction)
        }
        .padding(12)
    }

    /// 이 라벨을 누가 만들었나. 기계 라벨은 확인하기 전까지 눈에 띄게 둔다
    @ViewBuilder private func originBadge(_ st: LabelStatus) -> some View {
        let auto = LabelProgress.isAuto(current)
        if auto || progress.isVerified(current) {
            let checked = !auto || progress.isVerified(current)
            Label(checked ? L("Checked by you") : L("Model boxes"),
                  systemImage: checked ? "checkmark.seal.fill" : "wand.and.stars")
                .font(.ui(11.5, weight: .semibold))
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(.black.opacity(0.55), in: Capsule())
                .foregroundStyle(checked ? Color.good : .warn)
                .padding(10)
                .help(checked ? L("You looked at these boxes.") : L("A model made these boxes. Press V when you have checked them."))
                .transition(.opacity.combined(with: .move(edge: .top)))
                .animation(Motion.change, value: checked)
        }
    }

    private var zoomControls: some View {
        HStack(spacing: 4) {
            Text(verbatim: "\(Int(zoom * 100))%")
                .font(.ui(11, design: .monospaced)).foregroundStyle(.white).contentTransition(.numericText())
            IconButton(symbol: "minus.magnifyingglass", help: "Zoom out") { step(1 / 1.4) }
            IconButton(symbol: "plus.magnifyingglass", help: "Zoom in") { step(1.4) }
            IconButton(symbol: "arrow.up.left.and.down.right.magnifyingglass", help: "Fit to window (0)") { fitToWindow() }
        }
        .padding(.horizontal, 8).padding(.vertical, 5)
        .background(.black.opacity(0.5), in: Capsule())
        .padding(10)
        .contextMenu {                                  // 아이콘만 있는 버튼이라 메뉴로도 닿게 한다
            Button("Zoom In", systemImage: "plus.magnifyingglass") { step(1.4) }
            Button("Zoom Out", systemImage: "minus.magnifyingglass") { step(1 / 1.4) }
            Button("Fit to Window", systemImage: "arrow.up.left.and.down.right.magnifyingglass") { fitToWindow() }
        }
        .animation(Motion.change, value: zoom)
    }

    @ViewBuilder private func bottomBar(_ st: LabelStatus) -> some View {
        HStack(spacing: 10) {
            if editing {
                ClassPageBar(classes: classes, page: $classPage, pick: Binding(
                    get: { boxes.first { $0.id == sel }?.cls ?? newClass },
                    set: { setClass($0) })) { setClass($0) }
                Button { showPalette = true } label: { Image(systemName: "magnifyingglass") }
                    .help("Find a class by name (C)").accessibilityLabel(L("Find a class by name"))
                    .popover(isPresented: $showPalette) {
                        ClassSearchPalette(classes: classes) { setClass($0) }
                    }
                Button { deleteSelected() } label: { Label("Delete", systemImage: "trash") }
                    .keyboardShortcut(.delete, modifiers: []).disabled(sel == nil)
                Text(verbatim: L("%d boxes", boxes.count)).font(.ui(12)).foregroundStyle(ink.soft).contentTransition(.numericText())
                Button { undoOnce() } label: { Label("Undo", systemImage: "arrow.uturn.backward") }.disabled(undo.isEmpty)
                Spacer()
                saveNote
                Button("Stop Editing") { commit(); editing = false }
                Button { commit() } label: { Label(dirty ? "Save" : "Saved", systemImage: dirty ? "checkmark" : "checkmark.circle.fill")
                        .symbolEffect(.bounce, value: savedTick) }
                    .primaryButton().disabled(!dirty)
                    .help("Saves on its own a moment after you stop editing, and when you move to another image.")
            } else {
                Label(st.title, systemImage: st.symbol).foregroundStyle(st.tint).font(.ui(12.5))
                Spacer()
                if st == .auto {
                    Button { toggleVerified() } label: { Label("Mark Checked (V)", systemImage: "checkmark.seal") }
                } else if progress.isVerified(current) {
                    Button { toggleVerified() } label: { Label("Unmark Checked", systemImage: "seal") }
                }
                if st != .boxes, st != .auto {
                    Button { markEmpty() } label: { Label(st == .checkedEmpty ? "Unmark" : "Nothing to Label (N)", systemImage: "circle") }
                }
            }
        }
        .padding(12)
        .animation(Motion.change, value: dirty)
    }

    /// 기계가 만든 라벨을 고치는 중: 어디에 저장되는지 분명히
    @ViewBuilder private var saveNote: some View {
        if saveFailed {
            Label("Auto-save is off because saving failed. Use Save.", systemImage: "exclamationmark.triangle")
                .font(.ui(11.5)).foregroundStyle(.bad)
        } else if LabelProgress.isAuto(current) {
            Label(L("Saves to %@", LabelProgress.labelURL(for: current).lastPathComponent), systemImage: "arrow.down.doc")
                .font(.ui(11.5)).foregroundStyle(.warn)
                .help("This image shows boxes a model made (labels_auto). Your fix is saved as the real label.")
        }
    }

    // MARK: 키

    private func arrow(_ k: KeyPress) -> KeyPress.Result {
        // ★고치는 중에는 방향키가 박스를 1px씩 옮긴다(예전엔 다음 사진으로 넘어가 미세 조정을 할 수 없었다). 사진 넘기기는 ⌥←→
        let step = k.modifiers.contains(.shift) ? 0.01 : 0.002
        if editing, !k.modifiers.contains(.option), let i = boxes.firstIndex(where: { $0.id == sel }) {
            switch k.key {
            case .leftArrow: boxes[i].box[0] -= step
            case .rightArrow: boxes[i].box[0] += step
            case .upArrow: boxes[i].box[1] -= step
            default: boxes[i].box[1] += step
            }
            return .handled
        }
        if k.key == .leftArrow { move(-1); return .handled }
        if k.key == .rightArrow { move(1); return .handled }
        return .ignored
    }

    private func digit(_ k: KeyPress) -> KeyPress.Result {
        guard let d = Int(k.characters) else { return .ignored }
        guard editing else {                          // 볼 때는 0이 "창에 맞춤"
            if d == 0 { fitToWindow(); return .handled }
            return .ignored
        }
        let i = classPage * 10 + d
        guard i < classes.count else { return .handled }
        setClass(classes[i].id)
        return .handled
    }

    // MARK: 동작

    private func setClass(_ c: Int) {
        newClass = c
        if let i = boxes.firstIndex(where: { $0.id == sel }) { boxes[i].cls = c }
        if let p = classes.firstIndex(where: { $0.id == c }) { classPage = p / 10 }
        Haptic.tick()
    }

    private func deleteSelected() {
        guard let i = boxes.firstIndex(where: { $0.id == sel }) else { return }
        withAnimation(Motion.tap) { boxes.remove(at: i); sel = nil }
    }

    private func step(_ k: Double) {
        withAnimation(Motion.change) { zoom = min(max(zoom * k, ImageFit.minZoom), ImageFit.maxZoom) }
        if zoom == ImageFit.minZoom { pan = .zero }
    }

    private func fitToWindow() {
        withAnimation(Motion.change) { zoom = 1; pan = .zero }
        Haptic.tick()
    }

    private func undoOnce() {
        guard let last = undo.popLast() else { return }
        withAnimation(Motion.change) { boxes = last }
        sel = nil; Haptic.tick()
    }

    private func startEdit() {
        boxes = ds.boxes(current).map { EditBox(cls: $0.cls, box: [$0.cx, $0.cy, $0.w, $0.h]) }
        sel = nil; dirty = false; undo = []
        withAnimation(Motion.change) { editing = true }
    }

    /// 편집이 멈춘 뒤 잠깐 기다렸다가 저장한다. ★한 번 실패하면(백업 실패 등) 꺼 둔다: 조용히 반복해 봐야 같은 실패다
    private func scheduleAutosave() {
        guard !saveFailed else { return }
        autosave?.cancel()
        autosave = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(900))
            guard !Task.isCancelled else { return }
            commit()
        }
    }

    /// 고친 것이 있으면 저장. 실패하면 파일을 건드리지 않고 알린다(LabelProgress.save가 백업 전에 멈춘다)
    private func commit() {
        autosave?.cancel()
        guard editing, dirty else { return }
        do {
            let url = try LabelProgress.save(boxes, for: current)
            ds.replaceLabel(current, url: url)
            progress.setVerified(current, true)         // 사람이 손댄 라벨은 확인된 것이다
            if let i = items.firstIndex(of: current) { current = ds.items.first { $0.id == items[i].id } ?? current }
            dirty = false; savedTick += 1; saveFailed = false; Haptic.success()
        } catch {
            saveFailed = true
            store.say(error.localizedDescription, bad: true)
        }
    }

    private func markEmpty() {
        let n = editing ? boxes.count : ds.boxes(current).count
        guard n == 0 else { store.say(L("Remove the boxes first to mark it as nothing to label."), bad: true); return }
        progress.toggleChecked(current); Haptic.tick()
    }

    private func toggleVerified() {
        let n = editing ? boxes.count : ds.boxes(current).count
        guard n > 0 else { markEmpty(); return }
        withAnimation(Motion.change) { progress.setVerified(current, !progress.isVerified(current)) }
        Haptic.tick()
    }

    private func move(_ d: Int) {
        commit()
        let i = min(max(index + d, 0), items.count - 1)
        let next = ds.items.first { $0.id == items[i].id } ?? items[i]
        withAnimation(Motion.hover) { current = next }
        fitToWindow()
        if editing { startEdit() }
    }
}
