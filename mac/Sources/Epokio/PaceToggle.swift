import SwiftUI

// 팝오버의 작은 켜기·끄기 줄: "학습 없을 때 CPU 사용률로 달리기".
// 켜면 barPaceSource = idleCPU, 끄면 train. cpu·idleGPU·aiUse(설정 → 모양새 → 메뉴바에서 고르는 값)는
// 켜진 것으로 보이고, 끌 때만 train으로 간다.
// 메뉴바가 캐릭터 모양일 때만 보인다. 값만 바꾼다(CPU 값 수신은 Store 몫).
struct PaceToggle: View {
    @Environment(\.ink) private var ink
    @Environment(\.accessibilityReduceMotion) private var reduce
    @AppStorage(PaceSource.key) private var raw = PaceSource.train.rawValue
    @State private var hover = false
    @State private var shown = false

    @Environment(Store.self) private var store
    /// 쉬는 모드(학습 0개)에서는 고른 값이 없어도 CPU로 달린다: 그때 "꺼짐"으로 보이지 않게
    private var on: Bool { PaceSource.effectiveNow(resting: store.gotRuns && RestMode.isResting(runs: store.runs)) != .train }

    var body: some View {
        Button {
            let turningOn = !on
            withAnimation(Motion.change) { raw = on ? PaceSource.train.rawValue : PaceSource.idleCPU.rawValue }
            // ★켤 때는 바로 한 번 받아 온다. CPU 값은 /system에서 오는데 그걸 받을지는 refresh()가 자기 차례에
            //   판단하므로(Store.swift), 신호를 안 보내면 다음 타이머까지(보는 화면 있으면 2초, 없으면 10초)
            //   캐릭터가 멈춰 있다가 뒤늦게 달리기 시작했다
            if turningOn { store.refresh() }
        } label: {
            HStack(spacing: Space.s) {
                icon
                Text("Run on CPU when idle").font(.ui(11)).foregroundStyle(on ? AnyShapeStyle(.primary) : AnyShapeStyle(ink.soft))
                Spacer(minLength: 0)
                knob
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(.primary.opacity(hover ? 0.06 : 0), in: .rect(cornerRadius: Radius.control))
            .contentShape(.rect)
        }
        .buttonStyle(PressStyle())
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
        .help("When nothing is training, the menu bar character runs at your CPU usage")
        .accessibilityLabel("Run on CPU when idle")
        .accessibilityValue(on ? Text("On") : Text("Off"))
        .opacity(shown ? 1 : 0).offset(y: shown ? 0 : 4)
        .onAppear { withAnimation(reduce ? nil : Motion.appear) { shown = true } }
    }

    private var tint: AnyShapeStyle { on ? AnyShapeStyle(.tint) : AnyShapeStyle(ink.soft) }

    private var icon: some View {
        Image(systemName: on ? "figure.run" : "figure.stand")
            .font(.ui(12, weight: .medium))
            .foregroundStyle(tint)
            .frame(width: 16)
            .contentTransition(.symbolEffect(.replace))
            .symbolEffect(.bounce, options: .nonRepeating, value: reduce ? false : on)
    }

    private var knob: some View {
        Capsule().fill(on ? AnyShapeStyle(.tint) : AnyShapeStyle(.quaternary))
            .frame(width: 22, height: 12)
            .overlay(alignment: on ? .trailing : .leading) {
                Circle().fill(.white).frame(width: 9, height: 9).padding(1.5)
            }
    }
}
