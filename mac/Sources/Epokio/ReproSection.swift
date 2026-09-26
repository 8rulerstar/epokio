import SwiftUI

// 학습 상세 "어떻게 돌렸나": 코드 버전·파이썬과 주요 패키지·시드·데이터 지문. 재현 기록(epokio_repro.json)이 있을 때만.
// 대기열로 돌린 학습은 시작할 때 기록되고(jobs.py), 밖에서 돌린 학습은 지금 상태로 대충 채운 것이라 "일부"로 표시한다.
struct ReproSection: View {
    let repro: RunRepro
    @Environment(\.ink) private var ink
    @Environment(Store.self) private var store
    @State private var open = false

    private var rows: [(String, String, String)] {           // (아이콘, 이름, 값)
        var out: [(String, String, String)] = []
        if let c = repro.code, let sha = c.commit {
            let dirty = c.dirty == true ? "  " + L("uncommitted changes") : ""
            out.append(("chevron.left.forwardslash.chevron.right", L("Code"), String(sha.prefix(7)) + (c.branch.map { "  (\($0))" } ?? "") + dirty))
        }
        if let p = repro.python, let v = p.version {
            let key = ["torch", "ultralytics"].compactMap { k in (p.packages?[k]).map { "\(k) \($0)" } }.joined(separator: "  ·  ")
            out.append(("terminal", L("Python"), v + (key.isEmpty ? "" : "  ·  " + key)))
        }
        if let s = repro.seed?["seed"] { out.append(("dice", L("Seed"), s)) }
        if let d = repro.data, let n = d.images {
            out.append(("cylinder", L("Data"), L("%d images", n) + (d.listing_sha256.map { "  ·  " + String($0.prefix(8)) } ?? "")))
        }
        if let chip = repro.system?["chip"] ?? repro.system?["machine"] { out.append(("cpu", L("Machine"), chip)) }
        if let gpus = repro.system?["gpus"] {                              // NVIDIA 기계: 이름(드라이버)·CUDA 판
            out.append(("rectangle.3.group", "GPU", gpus + (repro.system?["cuda"].map { "  ·  CUDA " + $0 } ?? "")))
        }
        return out
    }

    var body: some View {
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    Label("How it was run", systemImage: "shippingbox.and.arrow.backward").font(.role(.headline))
                    if repro.partial == true {
                        Text("partly").font(.role(.badge)).foregroundStyle(.warn)
                            .padding(.horizontal, 6).padding(.vertical, 1).background(.warn.opacity(0.14), in: Capsule())
                            .help("Filled in after the run, so code and packages are how they are now, not how they were then")
                    }
                    Spacer()
                    Button { copyText(text, store, what: L("Run setup")) } label: { Image(systemName: "doc.on.doc") }
                        .buttonStyle(.plain).foregroundStyle(ink.soft).help("Copy so you can paste it in a paper or an issue")
                }
                ForEach(Array(rows.enumerated()), id: \.offset) { i, r in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Image(systemName: r.0).font(.ui(11)).foregroundStyle(ink.faint).frame(width: 16)
                        Text(verbatim: r.1).font(.ui(12)).foregroundStyle(ink.soft).frame(width: 70, alignment: .leading)
                        Text(verbatim: r.2).font(.ui(12, design: .monospaced)).textSelection(.enabled).lineLimit(2)
                    }
                    .appearRise(i)
                }
            }
            .padding(12)
            .background(.quaternary.opacity(0.25), in: RoundedRectangle(cornerRadius: Radius.card))
        }
    }

    private var text: String { rows.map { "\($0.1): \($0.2)" }.joined(separator: "\n") }
}
