import AppIntents
import SwiftUI

// ① 학습 어때: 도는 학습의 에폭·남은 시간·점수를 한 문장으로
struct TrainingStatusIntent: AppIntent {
    static let title: LocalizedStringResource = "Training Status"
    static let description = IntentDescription("Tells you how your training is going.")

    func perform() async throws -> some IntentResult & ProvidesDialog & ShowsSnippetView {
        let runs = try await IntentAgent.runs()
        let live = runs.first(where: \.isLive)
        return .result(dialog: "\(IntentText.status(runs))", view: RunSnippet(run: live ?? runs.first))
    }
}

// ② 특정 학습 열기: Studio에서 그 학습을 보인다(알림을 눌렀을 때와 같은 길)
struct OpenRunIntent: AppIntent {
    static let title: LocalizedStringResource = "Open Training Run"
    static let description = IntentDescription("Shows a run in Epokio Studio.")
    static let openAppWhenRun = true

    @Parameter(title: "Training run") var run: RunEntity

    static var parameterSummary: some ParameterSummary { Summary("Open \(\.$run)") }

    @MainActor
    func perform() async throws -> some IntentResult {
        NotificationCenter.default.post(name: .openRun, object: run.id)
        return .result()
    }
}

// ③ 같은 설정으로 다시 학습: 대기열에 넣기 전에 반드시 묻는다
struct RetrainIntent: AppIntent {
    static let title: LocalizedStringResource = "Train Again with Same Settings"
    static let description = IntentDescription("Adds a new run with the same settings to the queue.")

    @Parameter(title: "Training run") var run: RunEntity

    static var parameterSummary: some ParameterSummary { Summary("Train \(\.$run) again") }

    func perform() async throws -> some IntentResult & ProvidesDialog {
        try await requestConfirmation(actionName: .add, dialog: "Add \(run.name) to the queue with the same settings?")
        let name = try await IntentAgent.retrain(run.run)
        return .result(dialog: "Added \(name) to the queue.")
    }
}

/// 결과 스니펫. 작게: 이름, 진행 막대, 한 줄
struct RunSnippet: View {
    let run: Run?
    var body: some View {
        if let run {
            VStack(alignment: .leading, spacing: 6) {
                Text(run.displayName).font(.headline).lineLimit(1)
                if let p = run.progress { ProgressView(value: p) }
                Text(IntentText.line(run)).font(.caption).foregroundStyle(.secondary)
            }
            .padding(12)
        }
    }
}
