import SwiftUI

// 끝난 학습의 해설 한 문단(agent explain.py): 왜 이 점수인지 + 다음에 무엇을 바꿀지.
// Jev를 켰으면 후보 문장 중 필요한 것만 골라 짧게(JevExplain). 보내는 것: 상태·종류·점수·바꿀 설정 숫자·언어·후보 문장(경로·이름 없음)
struct ExplainCard: View {
    let run: Run
    let explain: RunExplain
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var text: String?
    @State private var polished = false
    @State private var shown = false

    private var tint: Color { explain.status == "failed" ? .bad : explain.status == "stalled" ? .warn : .good }
    private var symbol: String { explain.status == "failed" ? "xmark.octagon.fill" : explain.status == "stalled" ? "pause.circle.fill" : "text.bubble.fill" }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: symbol).font(.ui(16, weight: .semibold)).foregroundStyle(tint)
                .symbolEffect(.bounce, value: shown)
            VStack(alignment: .leading, spacing: 4) {
                Text(verbatim: text ?? explain.text).font(.role(.callout)).fixedSize(horizontal: false, vertical: true)
                    .contentTransition(.opacity)
                if polished {
                    Label(OnDeviceExplain.enabled ? "Rewritten on this Mac" : "Shortened by Jev", systemImage: "sparkles").font(.role(.caption)).foregroundStyle(ink.soft)
                        .help("Sent: status, task, scores, setting numbers, language and these sentences. No paths or names.")
                        .transition(.opacity)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(tint.opacity(0.08), in: RoundedRectangle(cornerRadius: Radius.card))
        .overlay(RoundedRectangle(cornerRadius: Radius.card).strokeBorder(tint.opacity(0.25)))
        .opacity(shown ? 1 : 0).offset(y: shown ? 0 : 6)
        .onAppear { withAnimation(Motion.appear) { shown = true } }
        .animation(Motion.change, value: text)
        .contextMenu { Button("Copy") { copyText(text ?? explain.text, store, what: L("Explanation")) } }
        .task(id: run.id) { await polish() }
    }

    /// Jev를 켰을 때만: 상세를 원본 JSON으로 다시 받아 요청 본문을 꺼내 보낸다
    private func polish() async {
        guard OnDeviceExplain.enabled || Jev.enabled else { return }
        guard let out = await Self.rewrite(client: store.client(for: run), path: run.path, explain: explain) else { return }
        if out != explain.text { withAnimation(Motion.change) { text = out; polished = true } }
    }

    /// 상세를 원본 JSON으로 다시 받아(요청 본문은 Codable 모델에 없다) 이 맥 모델 → Jev → 규칙 순으로 다듬는다
    nonisolated private static func rewrite(client c: AgentClient, path: String, explain: RunExplain) async -> String? {
        var comps = URLComponents(url: c.base.appending(path: "run"), resolvingAgainstBaseURL: false)!
        comps.queryItems = [URLQueryItem(name: "path", value: path)]
        var req = URLRequest(url: comps.url!); c.authorize(&req)
        guard let (data, _) = try? await URLSession.shared.data(for: req),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let ex = obj["explain"] as? [String: Any] else { return nil }
        let request = ex["jev_request"] as? [String: Any]
        let summary = (request?["state"] as? [String: Any])?["summary"] as? [String: Any]
            ?? ["status": explain.status ?? "finished", "kind": explain.kind ?? ""]
        return await OnDeviceExplain.best(text: explain.text, sentences: explain.sentences ?? [], summary: summary, request: request)
    }
}
