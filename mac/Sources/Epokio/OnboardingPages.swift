import SwiftUI

// 첫 실행 안내의 장들(①무엇인지 ③학습 폴더 ④완료). ②캐릭터는 OnboardingCharacterPicker.swift.
// 글은 한 장에 제목 한 줄 + 설명 한 줄. 아이콘만 있는 것은 올리면 툴팁.

/// 진짜 메뉴바 라벨(MenuBarLabel)을 가짜 학습 하나로 크게 그린 유리 띠. 메뉴바처럼 한 색으로 칠한다
struct OnboardBarStage: View {
    var style: BarStyle? = nil
    var scale: CGFloat = 2.2
    @AppStorage("animations") private var animations = true
    @Environment(\.accessibilityReduceMotion) private var reduce
    @State private var visible = false

    var body: some View {
        let still = reduce || !animations || !visible
        HStack(spacing: 18) {
            Image(systemName: "apple.logo").font(.ui(15)).opacity(0.5)
            Spacer(minLength: 0)
            MenuBarLabel(sample: MenuBarPreview.sample, styleOverride: style, frozen: true).hidden()
                .overlay {
                    Rectangle().fill(Color(nsColor: .labelColor))    // 유리가 글자색을 뒤집지 않게 창 글자색으로
                        .mask { MenuBarLabel(sample: MenuBarPreview.sample, styleOverride: style, frozen: still).fixedSize() }
                }
                .scaleEffect(scale)
                .frame(minWidth: 90, minHeight: 34)
                .id(style)
                .transition(reduce ? .opacity : .opacity.combined(with: .scale(scale: 0.7)))
            Spacer(minLength: 0)
            Group { Image(systemName: "wifi"); Image(systemName: "battery.75percent"); Text(verbatim: "9:41") }
                .font(.ui(13)).opacity(0.35).accessibilityHidden(true)
        }
        .padding(.horizontal, 20)
        .frame(width: 420, height: 64)
        .onboardGlass(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .animation(reduce ? nil : Motion.celebrate, value: style)
        .onAppear { visible = true }
        .onDisappear { visible = false }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Menu bar preview")
    }
}

/// 장 머리: 제목 + 설명 한 줄. 나타날 때 차례로 떠오른다
struct OnboardHeader: View {
    let title: LocalizedStringKey
    let line: LocalizedStringKey
    var tip: LocalizedStringKey? = nil                 // 있으면 설명 옆 ? 아이콘에 툴팁으로(글을 늘리지 않고 도움말)
    @Environment(\.ink) private var ink
    var body: some View {
        VStack(spacing: 6) {
            Text(title).font(.ui(26, weight: .bold)).multilineTextAlignment(.center).appearRise(1)
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(line).font(.ui(14)).foregroundStyle(ink.soft).multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                if let tip {
                    Image(systemName: "questionmark.circle").font(.ui(13)).foregroundStyle(ink.faint)
                        .help(tip).accessibilityLabel(Text(tip))
                }
            }
            .frame(maxWidth: 460).appearRise(2)
        }
    }
}

// MARK: ① 무엇인지

struct OnboardWelcome: View {
    var body: some View {
        VStack(spacing: 22) {
            OnboardBarStage().appearRise(0)
            OnboardHeader(title: "Know when training is done",
                          line: "Epokio is a menu bar monitor for AI model training. It watches runs and tells you when they finish or fail.")
            HStack(spacing: 14) {
                OnboardIcon(symbol: "chart.line.uptrend.xyaxis", tip: "Progress: epochs, time left, best score")
                OnboardIcon(symbol: "bell.badge", tip: "Alerts: finished, failed, stalled")
                OnboardIcon(symbol: "sparkle.magnifyingglass", tip: "Results: scores, curves, mistakes")
                OnboardIcon(symbol: "lock.shield", tip: "No code changes, no account. Data stays on this Mac.")
            }
            .appearRise(3)
        }
        .padding(28)
    }
}

/// 아이콘만 있는 유리 동그라미. 올리면 떠오르고 툴팁
struct OnboardIcon: View {
    let symbol: String
    let tip: LocalizedStringKey
    @State private var hover = false
    var body: some View {
        Image(systemName: symbol)
            .font(.ui(17, weight: .semibold)).foregroundStyle(.tint)
            .symbolEffect(.bounce, value: hover)
            .frame(width: 44, height: 44)
            .onboardGlass(Circle(), interactive: true)
            .scaleEffect(hover ? 1.08 : 1)
            .onHover { h in withAnimation(Motion.hover) { hover = h } }
            .help(tip)
            .accessibilityLabel(Text(tip))
    }
}

// MARK: ③ 학습 폴더 또는 샘플

struct OnboardConnect: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink

    var body: some View {
        VStack(spacing: 22) {
            Image(systemName: "folder.badge.gearshape")
                .font(.ui(46, weight: .light)).foregroundStyle(LinearGradient.brand)
                .symbolEffect(.bounce, value: store.runs.count)
                .appearRise(0)
            OnboardHeader(title: "Where are your runs?",
                          line: "Epokio already looked on this Mac. Add a folder it missed, or look around with samples.")
            Text(store.runs.isEmpty ? L("No runs found yet.") : L("Found %d runs.", store.runs.count))
                .font(.ui(13, weight: .semibold))
                .foregroundStyle(store.runs.isEmpty ? AnyShapeStyle(ink.soft) : AnyShapeStyle(.good))
                .contentTransition(.numericText())
                .animation(Motion.change, value: store.runs.count)
            GlassGroup(spacing: 14) {
                HStack(spacing: 14) {
                    OnboardChoice(symbol: "folder.badge.plus", title: "Add a Folder…",
                                  tip: "Pick a folder with training results, such as a project's runs folder") { addFolder() }
                    if store.runs.isEmpty || store.noRealRuns {
                        OnboardChoice(symbol: "sparkles", title: "Try with Samples",
                                      tip: "Adds three example runs so you can look around. Nothing trains. Remove them any time.",
                                      busy: busy, done: store.hasSamples) {
                            busy = true
                            Task { await Samples.add(store); busy = false }
                        }
                    }
                }
            }
            .appearRise(3)
            SampleBadge().animation(Motion.change, value: store.hasSamples)
        }
        .padding(28)
    }

    @State private var busy = false

    private func addFolder() {
        let p = NSOpenPanel(); p.canChooseDirectories = true; p.canChooseFiles = false; p.allowsMultipleSelection = true
        guard p.runModal() == .OK else { return }
        Task { for u in p.urls { await store.act(L("Watching %@", u.lastPathComponent)) { try await AgentClient.local.post("roots", ["path": u.path]) } } }
    }
}

/// 큰 유리 선택 칸: 아이콘 + 한 줄. 올리면 떠오르고, 누르면 눌린다
struct OnboardChoice: View {
    let symbol: String
    let title: LocalizedStringKey
    let tip: LocalizedStringKey
    var busy = false
    var done = false
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            VStack(spacing: 10) {
                ZStack {
                    if busy { ProgressView().controlSize(.small) }
                    else {
                        Image(systemName: done ? "checkmark.circle.fill" : symbol)
                            .font(.ui(24, weight: .medium))
                            .foregroundStyle(done ? AnyShapeStyle(.good) : AnyShapeStyle(.tint))
                            .contentTransition(.symbolEffect(.replace))
                            .symbolEffect(.bounce, value: hover)
                    }
                }
                .frame(height: 30)
                Text(title).font(.ui(13, weight: .semibold)).foregroundStyle(Color(nsColor: .labelColor))
            }
            .frame(width: 170, height: 96)
            .onboardGlass(RoundedRectangle(cornerRadius: 16, style: .continuous), interactive: true)
            .scaleEffect(hover ? 1.03 : 1)
            .contentShape(.rect)
        }
        .buttonStyle(PressStyle())
        .disabled(busy)
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help(tip)
    }
}

// MARK: ④ 완료

struct OnboardDone: View {
    let finish: () -> Void
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink

    var body: some View {
        VStack(spacing: 22) {
            OnboardBarStage(scale: 1.8).appearRise(0)
            OnboardHeader(title: "You're set", line: "Epokio lives in the menu bar, top right.",
                          tip: "Not there? The notch may hide it. Allow Epokio in System Settings, Menu Bar, or close a few other menu bar apps.")
            GlassGroup(spacing: 14) {
                HStack(spacing: 14) {
                    OnboardChoice(symbol: "play.fill", title: "Start a First Training",
                                  tip: "Open Train and start a run on this Mac") { store.section = .train; finish() }
                    OnboardChoice(symbol: "eye", title: "Look Around",
                                  tip: "Open your runs") { store.section = .runs; finish() }
                    OnboardChoice(symbol: "graduationcap", title: "Take the Tour",
                                  tip: "New to training? A 3-minute tour") { store.section = .home; store.tourStep = 0; finish() }
                }
            }
            .appearRise(3)
            Text("Press ⌘K anywhere to jump to a run or a screen.").font(.ui(12)).foregroundStyle(ink.faint).appearRise(4)
        }
        .padding(28)
    }
}

extension View {
    /// 유리 + 아주 옅은 바탕·테두리. 유리가 비치는 것이 없는 창(또는 구형 macOS)에서도 칸의 윤곽이 남는다
    func onboardGlass<S: Shape>(_ shape: S, interactive: Bool = false) -> some View {
        background(.primary.opacity(0.04), in: shape)
            .overlay(shape.stroke(.primary.opacity(0.08), lineWidth: 0.5))
            .glass(shape, interactive: interactive)
    }
}
