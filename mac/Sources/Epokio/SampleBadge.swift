import SwiftUI

// 첫 실행 30초: 학습이 하나도 없을 때 샘플 한 번 누르기, 샘플이 있으면 작은 표시와 지우기.
// 샘플 데이터는 agent /demo(Samples)를 그대로 쓴다. 여기서 새로 만들지 않는다.

extension Store {
    /// 샘플 run이 목록에 있는가(파일 검사 대신 목록으로 봐서 화면이 바로 따라온다)
    var hasSamples: Bool { runs.contains { $0.path.contains("/.epokio/demo/") } }
    /// 진짜 학습 기록이 하나도 없다(샘플만 있거나 비었다)
    var noRealRuns: Bool { runs.allSatisfy { $0.path.contains("/.epokio/demo/") } }
}

/// 샘플로 둘러보기 버튼. 누르는 동안 돌고, 끝나면 샘플 표시로 바뀐다.
struct TrySamplesButton: View {
    @Environment(Store.self) private var store
    @State private var busy = false

    var body: some View {
        Button {
            busy = true
            Task { await Samples.add(store); busy = false }
        } label: {
            HStack(spacing: 6) {
                if busy { ProgressView().controlSize(.small) } else { Image(systemName: "sparkles").symbolEffect(.bounce, value: busy) }
                Text("Try with Samples")
            }
            .padding(.horizontal, 6)
        }
        .primaryButton().controlSize(.large)
        .disabled(busy)
        .hoverLift()
        .help("Adds three example runs so you can look around. Nothing trains. Remove them any time.")
    }
}

/// "샘플" 작은 캡슐 + 지우기. 샘플이 있을 때만 보인다.
struct SampleBadge: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var hover = false

    var body: some View {
        if store.hasSamples {
            HStack(spacing: 6) {
                Label("Samples", systemImage: "sparkles").font(.ui(11.5, weight: .semibold)).foregroundStyle(.tint)
                Button { Task { await Samples.remove(store) } } label: {
                    Image(systemName: "xmark.circle.fill").font(.ui(12)).foregroundStyle(hover ? AnyShapeStyle(.tint) : AnyShapeStyle(ink.faint))
                }
                .buttonStyle(PressStyle())
                .onHover { h in withAnimation(Motion.hover) { hover = h } }
                .help("Remove sample runs")
                .accessibilityLabel(Text("Remove sample runs"))
            }
            .padding(.horizontal, 9).padding(.vertical, 4)
            .background(Capsule().fill(.tint.opacity(0.12)))
            .transition(.opacity.combined(with: .scale(scale: 0.9)))
            .help("These are example runs, not your training.")
        }
    }
}
