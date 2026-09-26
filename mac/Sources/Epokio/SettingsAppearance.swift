import SwiftUI

struct AppearanceTab: View {
    @AppStorage("barStyle") private var bar = BarStyle.mark.rawValue
    @AppStorage("skin") private var skin = "apple"
    @AppStorage("contrast") private var contrast = Contrast.standard.rawValue
    @AppStorage("showSystem") private var showSystem = true
    @AppStorage("showSparkline") private var showSparkline = true
    @AppStorage("animations") private var animations = true
    @AppStorage("textSize") private var textSize = TextSize.standard.rawValue
    @AppStorage("barShow") private var barShow = "pct"
    @AppStorage("barRun") private var barRun = "live"
    @AppStorage("barIdle") private var barIdle = "icon"
    @AppStorage("barTempo") private var barTempo = 0.6
    @AppStorage("barFollowSpeed") private var barFollow = true
    @AppStorage("barMaxFPS") private var barMaxFPS = 8.0
    @AppStorage("popJustFinished") private var popJustFinished = true
    @AppStorage("popQuick") private var popQuick = true
    @AppStorage("popRecent") private var popRecent = 3
    @AppStorage("popWidth") private var popWidth = "regular"
    @Environment(Store.self) private var store
    @State private var hovered: BarStyle?                       // 올린 타일(미리보기 띠가 잠깐 그 모양으로)

    private func toggleInfo(_ i: BarInfo) {
        var cur = BarInfo.parse(barShow)
        if let k = cur.firstIndex(of: i) { cur.remove(at: k) } else { cur.append(i) }
        barShow = BarInfo.allCases.filter { cur.contains($0) }.map(\.rawValue).joined(separator: ",")
    }

    var body: some View {
        ScrollViewReader { proxy in
        Form {
            Section("Menu bar") {
                IconGallery(selected: Binding(get: { BarStyle.from(bar) }, set: { s in bar = s.rawValue }))     // 전부 펼친 갤러리(IconGallery.swift)
                if BarStyle.from(bar) == .custom { CustomMarkRow().transition(.move(edge: .top).combined(with: .opacity)) }
                if BarStyle.from(bar) == .customAnim { CustomAnimRow().transition(.move(edge: .top).combined(with: .opacity)) }
                VStack(alignment: .leading, spacing: 6) {
                    Text("Show").font(.ui(13))
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 118), spacing: 6, alignment: .leading)], alignment: .leading, spacing: 6) {
                        ForEach(BarInfo.allCases) { i in
                            let on = BarInfo.parse(barShow).contains(i)
                            Button { withAnimation(.snappy) { toggleInfo(i) } } label: {
                                Label(i.title, systemImage: i.symbol).font(.ui(11.5, weight: on ? .semibold : .regular))
                                    .padding(.horizontal, 8).padding(.vertical, 4)
                                    .foregroundStyle(on ? AnyShapeStyle(.white) : AnyShapeStyle(.primary))
                                    .background(on ? AnyShapeStyle(.tint) : AnyShapeStyle(.quaternary.opacity(0.6)), in: Capsule())
                            }
                            .buttonStyle(PressStyle())
                        }
                    }
                }
                LabeledContent("Animation speed") {
                    HStack(spacing: 8) {
                        Image(systemName: "tortoise").foregroundStyle(.secondary)
                        Slider(value: $barTempo, in: 0.2...2, step: 0.1).frame(width: 180)
                        Image(systemName: "hare").foregroundStyle(.secondary)
                        Text(verbatim: String(format: "%.1f×", barTempo)).font(.ui(12, design: .monospaced)).frame(width: 40, alignment: .trailing)
                            .contentTransition(.numericText()).animation(Motion.change, value: barTempo)
                    }
                }
                Toggle("Run faster when training is faster", isOn: $barFollow)
                    .help("Like RunCat: quick epochs make the character run faster. Off: always the same pace.")
                Picker("Smoothness", selection: $barMaxFPS) {
                    Text("Light (4 frames/s)").tag(4.0); Text("Normal (8)").tag(8.0); Text("Smooth (12)").tag(12.0)
                }
                .help("More frames look smoother but use a little more CPU")
                Picker("Which run", selection: $barRun) {
                    Text("The newest running one").tag("live")
                    Text("The starred one").tag("star")
                    Text("Take turns every 5 seconds").tag("cycle")
                }
                PaceSourceRow()
                Picker("When nothing is training", selection: $barIdle) {
                    Text("Icon only").tag("icon")
                    Text("Last run's score").tag("score")
                }
            }
            Section("Skin") {
                Picker("Skin", selection: $skin) {
                    ForEach(Skin.all) { s in
                        VStack(alignment: .leading) { Text(s.name); Text(s.note).font(.ui(11.5)).foregroundStyle(.secondary) }.tag(s.id)
                    }
                }
                .pickerStyle(.radioGroup)
            }
            .id("skin")
            Section("Popover") {
                Toggle("Show \"Just finished\"", isOn: $popJustFinished)
                Toggle("Show GPU, CPU and memory", isOn: $showSystem)
                Toggle("Show quick actions", isOn: $popQuick)
                Stepper(value: $popRecent, in: 0...6) { Text(L("Recent runs: %d", popRecent)) }
                Picker("Width", selection: $popWidth) { Text("Compact").tag("compact"); Text("Regular").tag("regular") }
                    .pickerStyle(.segmented)
                Toggle("Show score trend on each run", isOn: $showSparkline)
                Toggle("Animations", isOn: $animations)
                Text("Animations also stop when Reduce Motion is on in System Settings.")
                    .font(.ui(11.5)).foregroundStyle(.secondary)
            }
            Section("Text") {
                Picker("Text size", selection: $textSize) {
                    ForEach(TextSize.allCases) { Text($0.title).tag($0.rawValue) }
                }
                .pickerStyle(.segmented)
                Picker("Contrast", selection: $contrast) {
                    ForEach(Contrast.allCases) { Text($0.title).tag($0.rawValue) }
                }
                .pickerStyle(.segmented)
                Text("High is used automatically when Increase Contrast is on in System Settings.")
                    .font(.ui(11.5)).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .safeAreaInset(edge: .top, spacing: 0) { MenuBarPreview(hovered: hovered) }   // 고정 띠: 내용은 유리 밑으로 지나간다
        .environment(\.styleHover) { s, h in
            if h { hovered = s } else if hovered == s { hovered = nil }
        }
        .onAppear {                                              // 스냅샷용: -snapScroll mid
            if UserDefaults.standard.string(forKey: "snapScroll") == "mid" {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { proxy.scrollTo("skin", anchor: .center) }
            }
        }
        }
    }
}

/// 메뉴바 "내 그림": 파일 고르기 · 단색/원래 색 · 지우기
struct CustomMarkRow: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @AppStorage("barCustomMono") private var mono = true
    @State private var version = 0
    @State private var hover = false

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 8).fill(.black.opacity(0.75)).frame(width: 52, height: 34)
                if let img = CustomMark.image(size: 18) {
                    Image(nsImage: img).foregroundStyle(.white)
                        .id(version).transition(.scale(scale: 0.6).combined(with: .opacity))
                } else {
                    Image(systemName: "photo.badge.plus").foregroundStyle(.white.opacity(0.7))
                        .symbolEffect(.bounce, value: hover)
                }
            }
            .scaleEffect(hover ? 1.05 : 1)
            .onHover { h in withAnimation(Motion.hover) { hover = h } }
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Button { choose() } label: { Label("Choose Image…", systemImage: "photo.on.rectangle") }
                    if CustomMark.image() != nil {
                        Button(role: .destructive) { withAnimation(.snappy) { CustomMark.remove(); version += 1 } } label: {
                            Label("Remove", systemImage: "trash")
                        }
                    }
                }
                Toggle("Match the menu bar color", isOn: $mono)
                    .onChange(of: mono) { withAnimation(.snappy) { version += 1 } }
                Text("PNG, SVG, or PDF. A simple shape on a transparent background looks best.")
                    .font(.ui(11.5)).foregroundStyle(ink.soft)
            }
        }
        .padding(.vertical, 2)
    }

    private func choose() {
        let p = NSOpenPanel(); p.allowedContentTypes = [.png, .jpeg, .svg, .pdf, .heic, .tiff]; p.allowsMultipleSelection = false
        guard p.runModal() == .OK, let u = p.url else { return }
        if CustomMark.save(from: u) {
            withAnimation(Motion.celebrate) { version += 1 }
            store.say(L("Menu bar image updated"))
        } else {
            store.say(L("Could not read that image"), bad: true)
        }
    }
}

/// 캐릭터 고르기: 전부 제자리에서 움직이는 작은 타일. 누르면 그걸로 바뀐다
struct CharacterStrip: View {
    @Binding var selected: BarStyle

    var body: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 5), spacing: 6) {   // 10개: 5칸 두 줄
            ForEach(BarStyle.characters) { s in
                CharacterTile(style: s, on: selected == s) { selected = s }
            }
        }
    }
}

struct CharacterTile: View {
    let style: BarStyle
    let on: Bool
    let pick: () -> Void
    @State private var hover = false
    @Environment(\.accessibilityReduceMotion) private var reduce
    @AppStorage("animations") private var animations = true

    var body: some View {
        Button(action: pick) {
            VStack(spacing: 3) {                                                        // 아이콘엔 이름을 같이(DESIGN.md 원칙)
                // ★올린 칸·고른 칸만 12fps로 다시 그린다(예전: 탭이 보이는 내내 모든 칸 20fps)
                TimelineView(.animation(minimumInterval: 1 / 12, paused: reduce || !animations || !(hover || on))) { tl in
                    Image(nsImage: style.runner!.image(hover || on ? tl.date.timeIntervalSinceReferenceDate * 1.1 : 0)).renderingMode(.template)
                        .resizable().interpolation(.high).frame(width: 36, height: 24)
                }
                Text(style.title).font(.role(.badge, weight: on ? .semibold : .regular)).lineLimit(1).minimumScaleFactor(0.8)
            }
                .foregroundStyle(on ? AnyShapeStyle(.white) : AnyShapeStyle(.primary))
                .frame(maxWidth: .infinity).padding(.vertical, 6)
                .background(on ? AnyShapeStyle(LinearGradient.brand) : AnyShapeStyle(.quaternary.opacity(hover ? 0.9 : 0.5)),
                            in: .rect(cornerRadius: Radius.control))
                .scaleEffect(hover && !on ? 1.04 : 1)
                .contentShape(.rect)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(Text(style.title))
        .accessibilityLabel(Text(style.title))
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

/// 메뉴바 "내 애니메이션": GIF · 여러 장 · 가로 스프라이트 한 장
struct CustomAnimRow: View {
    @Environment(Store.self) private var store
    @Environment(\.accessibilityReduceMotion) private var reduce
    @Environment(\.ink) private var ink
    @AppStorage("barCustomMono") private var mono = true
    @AppStorage("animations") private var animations = true
    @State private var version = 0
    @State private var hover = false

    var body: some View {
        HStack(spacing: 12) {
            // ★Reduce Motion·애니메이션 끔·한 장뿐이면 멈춘다(예전엔 정지 그림도 12fps로 다시 그렸다)
            TimelineView(.animation(minimumInterval: 1 / 12, paused: reduce || !animations || CustomAnim.frames().count < 2)) { tl in
                ZStack {
                    RoundedRectangle(cornerRadius: 8).fill(.black.opacity(0.75)).frame(width: 52, height: 34)
                    if let img = CustomAnim.image(tl.date.timeIntervalSinceReferenceDate * 0.8) {
                        Image(nsImage: img).foregroundStyle(.white)
                    } else {
                        Image(systemName: "film.stack").foregroundStyle(.white.opacity(0.7)).symbolEffect(.bounce, value: hover)
                    }
                }
            }
            .id(version)
            .scaleEffect(hover ? 1.05 : 1)
            .onHover { h in withAnimation(Motion.hover) { hover = h } }
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Button { choose() } label: { Label("Choose Frames…", systemImage: "film.stack") }
                    if !CustomAnim.frames().isEmpty {
                        Button(role: .destructive) { withAnimation(Motion.change) { CustomAnim.clear(); version += 1 } } label: {
                            Label("Remove", systemImage: "trash")
                        }
                    }
                }
                Toggle("Match the menu bar color", isOn: $mono)
                    .onChange(of: mono) { withAnimation(Motion.change) { version += 1 } }
                Text("A GIF, several images (played in name order), or one wide strip of square frames. It plays faster when training is faster.")
                    .font(.role(.caption)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, 2)
    }

    private func choose() {
        let p = NSOpenPanel(); p.allowedContentTypes = [.gif, .png, .jpeg, .svg, .pdf, .heic, .tiff]; p.allowsMultipleSelection = true
        guard p.runModal() == .OK, !p.urls.isEmpty else { return }
        let n = CustomAnim.save(from: p.urls)
        if n > 0 {
            withAnimation(Motion.celebrate) { version += 1 }; Haptic.success()
            store.say(L("Menu bar animation updated (%d frames)", n))
        } else {
            store.say(L("Could not read that image"), bad: true)
        }
    }
}
