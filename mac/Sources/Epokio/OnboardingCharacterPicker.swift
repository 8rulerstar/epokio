import SwiftUI

// 첫 실행 안내 ②: 메뉴바 캐릭터 고르기. 설정 → 모양의 갤러리 칸(StyleTile)을 그대로 가져다 쓴다.
// 고르면 바로 `barStyle`에 저장돼 진짜 메뉴바도 즉시 바뀐다. 칸에 올리면 위 미리보기가 잠깐 그 모양.
// 잠긴(업적) 캐릭터는 여기 싣지 않는다: 첫 화면에서 자물쇠부터 보이면 김이 샌다.

struct OnboardCharacterPicker: View {
    @AppStorage("barStyle") private var raw = BarStyle.mark.rawValue
    @State private var hovered: BarStyle?

    private var choices: [BarStyle] { [.mark] + BarStyle.characters.filter { !$0.locked } }
    private var selected: BarStyle { BarStyle.from(raw) }

    var body: some View {
        VStack(spacing: 18) {
            OnboardBarStage(style: hovered ?? selected).appearRise(0)
            OnboardHeader(title: "Pick a menu bar buddy",
                          line: "It runs while you train. Change it any time in Settings.")
            LazyVGrid(columns: Array(repeating: GridItem(.fixed(78), spacing: 8), count: min(choices.count, 6)), spacing: 8) {
                ForEach(Array(choices.enumerated()), id: \.element) { i, s in
                    StyleTile(style: s, on: selected == s, locked: false) {
                        Haptic.tick()
                        withAnimation(Motion.celebrate) { raw = s.rawValue }
                    }
                    .appearRise(3 + i)
                }
            }
            .environment(\.styleHover) { s, h in
                if h { hovered = s } else if hovered == s { hovered = nil }
            }
            PaceToggle()
                .frame(width: 260)
                .onboardGlass(RoundedRectangle(cornerRadius: Radius.control, style: .continuous))
                .opacity(selected.runner != nil ? 1 : 0.4)
                .disabled(selected.runner == nil)
                .animation(Motion.change, value: selected)
        }
        .padding(.horizontal, 28).padding(.vertical, 20)
    }
}
