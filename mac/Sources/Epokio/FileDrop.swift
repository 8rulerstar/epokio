import SwiftUI

// Studio 창 어디에나 파일을 떨어뜨리면 알맞은 곳으로: 폴더 → 보는 폴더에 추가 · data.yaml → 학습 양식 · .pt → 모델 시험
enum FileDrop {
    @MainActor static func handle(_ urls: [URL], _ store: Store) -> Bool {
        guard let u = urls.first else { return false }
        var isDir: ObjCBool = false
        FileManager.default.fileExists(atPath: u.path, isDirectory: &isDir)
        Haptic.success()
        if isDir.boolValue {
            Task { for d in urls { await store.act(L("Watching %@", d.lastPathComponent)) { try await AgentClient.local.post("roots", ["path": d.path]) } } }
        } else if ["yaml", "yml"].contains(u.pathExtension.lowercased()) {
            store.pendingTrainArgs = ["data": u.path]; store.section = .train
            store.say(L("Data set: %@. Pick the rest and press Start.", u.lastPathComponent))
        } else if u.pathExtension.lowercased() == "pt" {
            UserDefaults.standard.set(u.path, forKey: "tryModel"); store.section = .tryit
        } else {
            store.say(L("Drop a folder, a data.yaml or a .pt model."), bad: true); return false
        }
        return true
    }
}

/// 끌고 있을 때 창 위에 뜨는 안내
struct FileDropHint: View {
    @Environment(\.ink) private var ink
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: Radius.sheet).strokeBorder(.tint, style: StrokeStyle(lineWidth: 2.5, dash: [8, 6]))
                .background(RoundedRectangle(cornerRadius: Radius.sheet).fill(.tint.opacity(0.05)))
            VStack(spacing: 10) {
                Image(systemName: "tray.and.arrow.down.fill").font(.ui(34, weight: .semibold)).foregroundStyle(.tint)
                    .symbolEffect(.bounce, options: .repeat(.continuous))
                Text("Drop to open").font(.role(.headline))
                Text("Folder: watch its runs  ·  data.yaml: new training  ·  .pt: try the model").font(.role(.caption)).foregroundStyle(ink.soft)
            }
            .padding(20).glass(RoundedRectangle(cornerRadius: Radius.card))
        }
        .padding(14)
        .allowsHitTesting(false)
    }
}
