import SwiftUI

// 학습 상세의 "에폭별 예측": 같은 검증 이미지 4장을 몇 에폭마다 예측한 사진. 슬라이더로 넘긴다.

struct RunSnapshots: Codable, Hashable {
    let epochs: [Int]
    let files: [String: [String]]
}

struct SnapshotsSection: View {
    @Environment(\.ink) private var ink
    @Environment(\.accessibilityReduceMotion) private var reduce
    let snaps: RunSnapshots
    let url: (String) -> URL?
    let open: (String) -> Void
    @State private var k: Double = -1

    var body: some View {
        let i = Int(k < 0 ? Double(snaps.epochs.count - 1) : k)
        let ep = snaps.epochs[min(max(i, 0), snaps.epochs.count - 1)]
        VStack(alignment: .leading, spacing: 8) {
            SectionTitle("Predictions by epoch", hint: L("The same validation images, predicted as training went on. Drag to compare."))
            HStack {
                Slider(value: Binding(get: { Double(i) }, set: { v in withAnimation(reduce ? nil : Motion.change) { k = v.rounded() } }),
                       in: 0...Double(max(snaps.epochs.count - 1, 1)), step: 1)
                    .disabled(snaps.epochs.count < 2)
                Text(verbatim: L("epoch %@", "\(ep)")).font(.ui(12, weight: .semibold, design: .monospaced))
                    .contentTransition(.numericText(value: Double(ep))).frame(minWidth: 70, alignment: .trailing)
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 160), spacing: 8)], spacing: 8) {
                ForEach(snaps.files[String(ep)] ?? [], id: \.self) { name in
                    Button { open("epokio_snapshots/" + name) } label: {
                        AsyncImage(url: url("epokio_snapshots/" + name)) { img in img.resizable().scaledToFit() }
                            placeholder: { Rectangle().fill(.quaternary.opacity(0.4)) }
                            .frame(height: 130).frame(maxWidth: .infinity)
                            .clipShape(.rect(cornerRadius: 8))
                    }
                    .buttonStyle(PressStyle())
                    .transition(.opacity)
                }
            }
            .id(ep)
        }
    }
}
