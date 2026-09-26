import SwiftUI

// 검수 화면 위쪽: 떠 있는 유리 툴바 한 줄(결과 고르기 · 지표 · 진행 · 동작)과 필터 줄(세그먼트 4개 + 나머지는 메뉴).
// 필터 값(filter 문자열)과 저장 키는 예전 칩과 같다. 표시만 묶었다.

/// 세그먼트로 늘 보이는 필터. 나머지(클래스 틀림·라벨 고침·검수함·판정 4종)는 "더 보기" 메뉴
enum ReviewSegment: String, CaseIterable {
    case all, missed, extra, todo
    var title: LocalizedStringKey { switch self { case .all: "All"; case .missed: "Missed something"; case .extra: "Extra detections"; case .todo: "Not reviewed" } }
    var symbol: String { switch self { case .all: "square.grid.2x2"; case .missed: "minus.circle"; case .extra: "plus.circle"; case .todo: "circle.dashed" } }
}

extension ReviewView {
    var header: some View {
        HStack(spacing: 12) {
            Picker("Results from", selection: $jobID) {
                Text("New check…").tag(String?.none)
                ForEach(jobs.filter { $0.kind == "evaluate" && $0.state == "done" }.reversed()) { j in
                    Text(j.name).tag(Optional(j.id))
                }
            }
            .labelsHidden().frame(minWidth: 90, maxWidth: 180)
            .help("Results from")
            .onChange(of: jobID) { result = nil; classFilter = nil; cell = nil; Task { await loadResult() } }
            if let r = result, r.deep {
                ThresholdBar(result: r, conf: $conf).transition(.opacity)
            }
            Spacer(minLength: 4)
            if let r = result {
                progress(r)
                batchMenu
                Button { Task { await buildRetrain() } } label: {
                    Label("Retrain Set", systemImage: building ? "hourglass" : "arrow.triangle.2.circlepath")
                        .contentTransition(.symbolEffect(.replace))
                }
                .labelStyle(.iconOnly).buttonStyle(.borderless)
                .disabled(building || (verdicts.values.allSatisfy { $0 == .ok } && fixed.isEmpty))
                .help("Make a dataset from the images you marked and the labels you fixed, then open Train with it")
                Button { exportCSV() } label: { Label("Export", systemImage: "square.and.arrow.up") }
                    .labelStyle(.iconOnly).buttonStyle(.borderless)
                    .help("Save scores and your verdicts as a CSV file")
                Button { withAnimation(Motion.change) { inspectorOpen.toggle() } } label: {
                    Label("Classes", systemImage: "sidebar.right").symbolEffect(.bounce, value: inspectorOpen)
                }
                .labelStyle(.iconOnly).buttonStyle(.borderless)
                .foregroundStyle(inspectorOpen ? AnyShapeStyle(.tint) : AnyShapeStyle(ink.soft))
                .help("Per-class scores and which classes get mixed up")
            }
        }
        .controlSize(.small)
        .padding(.horizontal, 12).padding(.vertical, 8)
        .glass(radius: Radius.card)
        .padding(.horizontal, 10).padding(.top, 10).padding(.bottom, 6)
    }

    /// 몇 장 검수했나: 작은 원 하나(툴팁에 숫자)
    func progress(_ r: EvalResult) -> some View {
        let t = L("%d of %d reviewed", verdicts.count, r.rows.count)
        return ZStack {
            Circle().stroke(Color.good.opacity(0.18), lineWidth: 3)
            Circle().trim(from: 0, to: Double(verdicts.count) / Double(max(r.rows.count, 1)))
                .stroke(Color.good, style: StrokeStyle(lineWidth: 3, lineCap: .round)).rotationEffect(.degrees(-90))
        }
        .frame(width: 16, height: 16)
        .animation(Motion.change, value: verdicts.count)
        .help(t).accessibilityElement().accessibilityLabel(t)
    }

    func count(_ f: String, _ r: EvalResult) -> Int { r.rows.filter { matches($0, f) }.count }

    /// 필터 줄: 세그먼트 · 더 보기 메뉴 · 켜진 클래스/칸 거르기 · 검색 · 정렬·개수 메뉴
    func filterBar(_ r: EvalResult) -> some View {
        HStack(spacing: 8) {
            HStack(spacing: 2) {
                ForEach(ReviewSegment.allCases, id: \.self) { s in
                    SegmentButton(title: s.title, symbol: s.symbol, count: count(s.rawValue, r), on: filter == s.rawValue) { filter = s.rawValue }
                }
            }
            .padding(2).background(.primary.opacity(0.05), in: Capsule())
            .fixedSize().layoutPriority(1)
            moreMenu(r)
            if let c = classFilter {
                FilterChip(title: L("Class: %@", r.name(c)), symbol: "xmark.circle.fill", count: r.rows.filter { $0.hasClass(c) }.count, on: true, tint: .brand) { classFilter = nil }
                    .transition(.scale.combined(with: .opacity))
            }
            if cell != nil {
                FilterChip(title: L("Mix-up cell"), symbol: "xmark.circle.fill", count: shown.count, on: true, tint: .brand) { cell = nil }
                    .transition(.scale.combined(with: .opacity))
            }
            Spacer(minLength: 4)
            HStack(spacing: 4) {
                Image(systemName: "magnifyingglass").foregroundStyle(ink.soft).accessibilityHidden(true)
                TextField("Search file names", text: $search).textFieldStyle(.plain).frame(minWidth: 60, maxWidth: 150)
            }
            .padding(.horizontal, 8).padding(.vertical, 4).background(.primary.opacity(0.05), in: Capsule())
            Menu {
                Picker("Sort", selection: $sort) { ForEach(ReviewSort.allCases, id: \.self) { Text($0.title).tag($0) } }
                Picker("Show", selection: $limit) {
                    Text("24 images").tag(24); Text("48 images").tag(48); Text("96 images").tag(96); Text("All").tag(0)
                }
            } label: { Label("Sort", systemImage: "arrow.up.arrow.down") }
            .menuStyle(.borderlessButton).labelStyle(.iconOnly).fixedSize()
            .help("Sort")
        }
        .controlSize(.small)
        .padding(.horizontal, 12).padding(.bottom, 8)
        .animation(.smooth, value: filter)
        .animation(Motion.change, value: classFilter)
        .animation(Motion.change, value: cell)
    }

    /// 세그먼트에 없는 필터. 켜져 있으면 메뉴 단추에 그 이름이 뜬다
    func moreMenu(_ r: EvalResult) -> some View {
        let seg = ReviewSegment(rawValue: filter) != nil
        return Menu {
            if r.deep { Toggle(L("Wrong class") + "  \(count("wrongclass", r))", isOn: pick("wrongclass")) }
            if !fixed.isEmpty { Toggle(L("Label fixed") + "  \(count("fixed", r))", isOn: pick("fixed")) }
            Toggle(L("Reviewed") + "  \(verdicts.count)", isOn: pick("done"))
            Divider()
            ForEach(Verdict.allCases, id: \.self) { v in
                Toggle(isOn: pick(v.rawValue)) {
                    Label(String(localized: v.titleResource) + "  \(verdicts.values.filter { $0 == v }.count)", systemImage: v.symbol)
                }
            }
        } label: {
            Label(seg ? L("More") : moreTitle(r), systemImage: "line.3.horizontal.decrease.circle")
        }
        .menuStyle(.borderlessButton).fixedSize()
        .foregroundStyle(seg ? AnyShapeStyle(ink.soft) : AnyShapeStyle(.tint))
        .help("More filters")
    }

    private func pick(_ f: String) -> Binding<Bool> {
        Binding(get: { filter == f }, set: { on in withAnimation(.snappy) { filter = on ? f : "all" } })
    }

    private func moreTitle(_ r: EvalResult) -> String {
        switch filter {
        case "wrongclass": L("Wrong class")
        case "fixed": L("Label fixed")
        case "done": L("Reviewed")
        default: Verdict(rawValue: filter).map { String(localized: $0.titleResource) } ?? L("More")
        }
    }
}

/// 세그먼트 한 칸: 아이콘 + 이름 + 개수. 켜지면 강조색이 찬다
struct SegmentButton: View {
    let title: LocalizedStringKey
    let symbol: String
    let count: Int
    let on: Bool
    let action: () -> Void
    @State private var hover = false
    var body: some View {
        Button(action: { withAnimation(.snappy) { action() } }) {
            HStack(spacing: 4) {
                Image(systemName: symbol).font(.ui(11, weight: .semibold))
                if on { Text(title).font(.ui(12, weight: .semibold)).lineLimit(1).fixedSize().transition(.opacity.combined(with: .move(edge: .leading))) }
                Text(verbatim: "\(count)").font(.ui(11, weight: .semibold, design: .rounded)).opacity(0.75)
                    .contentTransition(.numericText())
            }
            .padding(.horizontal, 9).padding(.vertical, 4)
            .foregroundStyle(on ? AnyShapeStyle(.white) : AnyShapeStyle(.primary))
            .background(on ? AnyShapeStyle(Color.brand) : AnyShapeStyle(.primary.opacity(hover ? 0.07 : 0)), in: Capsule())
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(Text(title))
        .accessibilityLabel(Text(title))
        .accessibilityValue(Text(verbatim: "\(count)"))
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

/// VoiceOver 동작: 카드마다 판정 4가지(키 1~4와 같은 것)
struct VerdictActions: ViewModifier {
    let mark: (Verdict) -> Void
    func body(content: Content) -> some View {
        content
            .accessibilityAction(named: Text(Verdict.model.title)) { mark(.model) }
            .accessibilityAction(named: Text(Verdict.label.title)) { mark(.label) }
            .accessibilityAction(named: Text(Verdict.unsure.title)) { mark(.unsure) }
            .accessibilityAction(named: Text(Verdict.ok.title)) { mark(.ok) }
    }
}
