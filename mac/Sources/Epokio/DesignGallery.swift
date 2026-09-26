import SwiftUI

// 디자인 갤러리: 토큰(색·글꼴·간격·움직임)과 공통 컴포넌트를 한 화면에. 피그마의 컴포넌트 페이지 역할.
// 보기: Epokio --snapshot-window design out.png [--dark]  → docs/images/design-light.png · design-dark.png
// 새 컴포넌트를 만들면 여기에도 한 칸 넣는다(docs/DESIGN.md).

struct DesignGallery: View {
    @Environment(\.ink) private var ink
    @State private var chip = true
    @State private var progress = 0.62
    @State private var character = BarStyle.cat

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.xl) {
                HStack(spacing: 10) {
                    Image(nsImage: NSApp.applicationIconImage).resizable().frame(width: 36, height: 36)
                    VStack(alignment: .leading, spacing: 0) {
                        Text("Epokio design system").font(.role(.title))
                        Text(verbatim: "design/tokens.json → DesignTokens.swift · web/tokens.css").font(.role(.caption)).foregroundStyle(ink.soft)
                    }
                }
                section("Color roles") {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 128), spacing: Space.s)], spacing: Space.s) {
                        swatch("brand", .brand, "accent · selection"); swatch("brand2", .brand2, "gradient end")
                        swatch("good", .good, "running · right"); swatch("warn", .warn, "stalled · missed")
                        swatch("bad", .bad, "failed · wrong"); swatch("mixup", .mixup, "wrong class")
                        swatch("gold", .gold, "best · star"); swatch("info", .info, "notice")
                    }
                    RoundedRectangle(cornerRadius: Radius.control).fill(LinearGradient.brand).frame(height: 22)
                        .overlay(Text(verbatim: "gradient.brand").font(.role(.badge)).foregroundStyle(.white))
                }
                section("Type roles") {
                    ForEach(TypeRole.allCases, id: \.self) { r in
                        HStack(alignment: .firstTextBaseline, spacing: Space.m) {
                            Text(verbatim: "\(r)").font(.role(.caption)).foregroundStyle(ink.soft).frame(width: 70, alignment: .leading)
                            Text(verbatim: r.design == .rounded ? "0.6421" : "Training finished").font(.role(r)).lineLimit(1)
                            Text(verbatim: "\(r.size.formatted())pt").font(.role(.badge)).foregroundStyle(ink.faint)
                        }
                    }
                }
                section("Components") {
                    HStack(spacing: Space.s) {
                        Button("Primary") {}.primaryButton()
                        Button("Secondary") {}.secondaryButton()
                        Button("Delete", role: .destructive) {}
                        IconButton(symbol: "gearshape", help: "Icon button") {}
                    }
                    HStack(spacing: Space.s) {
                        FilterChip(title: "Missed", symbol: "minus.circle", count: 3, on: chip, tint: .warn) { chip.toggle() }
                        FilterChip(title: "Wrong class", symbol: "arrow.left.arrow.right.circle", count: 2, on: false, tint: .mixup) {}
                        StageBadge(stage: .production); StageBadge(stage: .candidate)
                    }
                    HStack(spacing: Space.s) {
                        MetricTile(name: "Precision", value: 0.812, hint: "")
                        MetricTile(name: "F1", value: 0.768, hint: "", strong: true)
                        MetricTile(name: "Best epoch", value: 41, hint: "", integer: true)
                    }
                    CapsuleBar(value: progress, tint: .brand, shimmer: true).frame(height: 8)
                        .onTapGesture { withAnimation(Motion.change) { progress = progress > 0.9 ? 0.2 : progress + 0.2 } }
                    GlassGroup { HStack(spacing: Space.m) {
                        Label("Fixed label saved", systemImage: "checkmark.circle.fill").font(.role(.callout, weight: .medium)).foregroundStyle(.good)
                            .padding(.horizontal, 14).padding(.vertical, 9).glass(Capsule())
                        Label("Could not read that image", systemImage: "exclamationmark.triangle.fill").font(.role(.callout, weight: .medium)).foregroundStyle(.warn)
                            .padding(.horizontal, 14).padding(.vertical, 9).glass(Capsule())
                    } }
                }
                section("Menu bar characters") {
                    CharacterStrip(selected: $character)
                    SlowRootsNote(paths: ["/Users/me/Desktop/runs"])
                }
                section("Radius · space") {
                    HStack(spacing: Space.m) {
                        ForEach([("chip", Radius.chip), ("control", Radius.control), ("card", Radius.card), ("sheet", Radius.sheet)], id: \.0) { n, r in
                            RoundedRectangle(cornerRadius: r).fill(.quaternary).frame(width: 64, height: 44)
                                .overlay(Text(verbatim: "\(n) \(Int(r))").font(.role(.badge)))
                        }
                    }
                }
                section("Motion") {
                    Text(verbatim: "tap 0.12 · hover 0.15 · change 0.30 · progress 0.60 · appear spring 0.40 (+25ms stagger) · celebrate bouncy 0.45 + haptic")
                        .font(.role(.callout)).foregroundStyle(ink.soft)
                }
            }
            .padding(Space.xl)
            .frame(maxWidth: 720, alignment: .leading)
        }
    }

    private func section<C: View>(_ title: String, @ViewBuilder _ c: () -> C) -> some View {
        VStack(alignment: .leading, spacing: Space.m) {
            Text(verbatim: title).font(.role(.headline))
            c()
        }
        .padding(Space.l)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.25), in: .rect(cornerRadius: Radius.card))
    }

    private func swatch(_ name: String, _ c: Color, _ use: String) -> some View {
        HStack(spacing: Space.s) {
            RoundedRectangle(cornerRadius: Radius.chip).fill(c).frame(width: 28, height: 28)
            VStack(alignment: .leading, spacing: 0) {
                Text(verbatim: name).font(.role(.callout, weight: .semibold))
                Text(verbatim: use).font(.role(.badge)).foregroundStyle(ink.soft)
            }
        }
        .hoverLift()
    }
}
