import SwiftUI

// 설정 → 꾸미기: 사용자에게 맡길 수 있는 것을 한곳에. 움직임 속도·진동 · 강조색 · 왼쪽 막대 항목(숨기기·순서) · 홈 칸(숨기기·순서).
// 메뉴바 그림·빠르기는 "모양" 탭, 알림 종류·소리는 "알림" 탭에 있다.

/// 강조색(버튼·선택 표시). 기본은 브랜드 보라. "system"은 맥 시스템 강조색을 따라간다
enum Accent {
    /// 시스템 강조색. 사용자가 시스템 설정에서 바꾸면 따라간다(SystemPrefsWatcher가 화면을 다시 그린다)
    static let system = "system"
    static var presets: [(String, Color)] { [(system, Color(nsColor: .controlAccentColor)),
                                             ("brand", .brand), ("teal", .brand2), ("green", .good), ("blue", .info),
                                             ("orange", .warn), ("purple", .mixup), ("gold", .gold), ("red", .bad)] }
    /// 색 이름. 시스템만 번역해 보여 준다(나머지는 색 자체가 설명이다)
    static func label(_ raw: String) -> String { raw == system ? L("Match system") : raw }
    static func color(_ raw: String) -> Color {
        if let p = presets.first(where: { $0.0 == raw }) { return p.1 }
        if raw.hasPrefix("#"), raw.count == 7, let v = Int(raw.dropFirst(), radix: 16) {
            return Color(.sRGB, red: Double(v >> 16 & 255) / 255, green: Double(v >> 8 & 255) / 255, blue: Double(v & 255) / 255)
        }
        return .brand
    }
    static func hex(_ c: Color) -> String {
        guard let n = NSColor(c).usingColorSpace(.sRGB) else { return "brand" }
        return String(format: "#%02X%02X%02X", Int(n.redComponent * 255), Int(n.greenComponent * 255), Int(n.blueComponent * 255))
    }
}

struct AccentTint: ViewModifier {
    @AppStorage("accent") private var accent = "brand"
    @ObservedObject private var sys = SystemPrefsWatcher.shared      // 시스템 강조색·동작 줄이기가 바뀌면 다시 그린다

    func body(content: Content) -> some View {
        _ = sys.stamp                                                // 시스템 색이 바뀌면 여기가 다시 계산된다
        return content.tint(Accent.color(accent))
    }
}

/// 홈 칸
enum HomeTile: String, CaseIterable, Identifiable {
    case now, attention, recent, best, quick
    var id: String { rawValue }
    var title: String { switch self { case .now: L("Now"); case .attention: L("Needs attention"); case .recent: L("Recent results"); case .best: L("Best per dataset"); case .quick: L("Quick actions") } }
    var symbol: String { switch self { case .now: "bolt.fill"; case .attention: "exclamationmark.circle"; case .recent: "clock"; case .best: "trophy"; case .quick: "square.grid.2x2" } }
}

struct CustomizeTab: View {
    @AppStorage("motionScale") private var motion = 1.0
    @AppStorage("haptics") private var haptics = true
    @AppStorage("glass") private var glass = true
    @AppStorage("accent") private var accent = "brand"
    @AppStorage("railOrder") private var railOrder = ""
    @AppStorage("railHidden") private var railHidden = ""
    @AppStorage("homeOrder") private var homeOrder = ""
    @AppStorage("homeHidden") private var homeHidden = ""
    @State private var custom = Color.brand
    @State private var bump = 0
    @ObservedObject private var sys = SystemPrefsWatcher.shared

    var body: some View {
        Form {
            Section("Motion") {
                Picker("Animation speed", selection: $motion) {
                    Text("Off").tag(0.0); Text("Quick").tag(0.6); Text("Normal").tag(1.0); Text("Relaxed").tag(1.5)
                }
                .pickerStyle(.segmented)
                .disabled(sys.reduce)
                Toggle("Glass effect on floating panels", isOn: $glass).help("Liquid Glass on the tour card, banners and drag previews (macOS 26 and later)")
                Toggle("Trackpad feedback", isOn: $haptics).help("A light tap on the trackpad when something is saved or picked")
                Text(sys.reduce ? "macOS Reduce Motion is on." : "The menu bar icon has its own speed in Appearance.")
                    .font(.ui(11.5)).foregroundStyle(.secondary)
                TipsSettingsRow()
            }
            CustomizeViewSection()
            Section("Accent color") {
                HStack(spacing: 10) {
                    ForEach(Accent.presets, id: \.0) { p in
                        Button { withAnimation(Motion.celebrate) { accent = p.0 }; bump += 1; Haptic.tick() } label: {
                            Circle().fill(p.1).frame(width: 22, height: 22)
                                .overlay(Circle().strokeBorder(.primary.opacity(0.25), lineWidth: 1))
                                .overlay(Circle().strokeBorder(.primary.opacity(accent == p.0 ? 0.8 : 0), lineWidth: 2).padding(-4))
                                .scaleEffect(accent == p.0 ? 1.12 : 1)
                        }
                        .buttonStyle(PressStyle()).help(Accent.label(p.0)).accessibilityLabel(Accent.label(p.0))
                    }
                    ColorPicker("", selection: Binding(get: { custom }, set: { custom = $0; accent = Accent.hex($0) }), supportsOpacity: false)
                        .labelsHidden().help("Pick any color")
                }
                HStack {
                    Button("Sample button") {}.primaryButton()
                    Toggle("Sample", isOn: .constant(true)).toggleStyle(.switch).labelsHidden()
                    Image(systemName: "star.fill").foregroundStyle(.tint).symbolEffect(.bounce, value: bump)
                }
                .allowsHitTesting(false)
            }
            Section("Sidebar") {
                reorder(all: (Studio.Section.main + Studio.Section.more).filter { $0 != .trophies }, order: $railOrder, hidden: $railHidden,
                        id: \.rawValue, title: \.title, symbol: \.symbol, locked: [.home])
            }
            Section("Home") {
                reorder(all: HomeTile.allCases, order: $homeOrder, hidden: $homeHidden, id: \.rawValue, title: \.title, symbol: \.symbol, locked: [])
            }
            Section {
                Button("Reset Everything on This Tab") {
                    withAnimation(Motion.change) { motion = 1; haptics = true; glass = true; accent = "brand"; railOrder = ""; railHidden = ""; homeOrder = ""; homeHidden = ""
                        for k in [Tips.key, Fmt.scoreKey, Fmt.timeKey, ViewPrefs.curveWidthKey, ViewPrefs.densityKey, ViewPrefs.startKey] { UserDefaults.standard.removeObject(forKey: k) } }
                }
            }
        }
        .formStyle(.grouped)
        .onAppear { custom = Accent.color(accent) }
    }

    /// 켜기/끄기 + 위아래로 옮기기. locked는 숨길 수 없다
    private func reorder<T: Hashable>(all: [T], order: Binding<String>, hidden: Binding<String>, id: @escaping (T) -> String,
                                      title: @escaping (T) -> String, symbol: @escaping (T) -> String, locked: Set<T>) -> some View {
        let items = all.sorted { a, b in
            let o = order.wrappedValue.split(separator: ",").map(String.init)
            return (o.firstIndex(of: id(a)) ?? 999, all.firstIndex(of: a)!) < (o.firstIndex(of: id(b)) ?? 999, all.firstIndex(of: b)!)
        }
        let off = Set(hidden.wrappedValue.split(separator: ",").map(String.init))
        return ForEach(Array(items.enumerated()), id: \.element) { i, it in
            HStack {
                Toggle(isOn: Binding(get: { !off.contains(id(it)) }, set: { v in
                    var s = off; if v { s.remove(id(it)) } else { s.insert(id(it)) }
                    withAnimation(Motion.change) { hidden.wrappedValue = s.sorted().joined(separator: ",") }
                })) { Label(title(it), systemImage: symbol(it)) }
                .disabled(locked.contains(it))
                Spacer()
                IconButton(symbol: "chevron.up", help: "Move up") { move(items, i, -1, order, id) }.disabled(i == 0)
                IconButton(symbol: "chevron.down", help: "Move down") { move(items, i, 1, order, id) }.disabled(i == items.count - 1)
            }
        }
    }

    private func move<T>(_ items: [T], _ i: Int, _ d: Int, _ order: Binding<String>, _ id: (T) -> String) {
        var ids = items.map(id)
        ids.swapAt(i, i + d)
        withAnimation(Motion.change) { order.wrappedValue = ids.joined(separator: ",") }
        Haptic.tick()
    }
}
