import AppIntents

// ④ 학습이 끝날 때까지 기다리기(macOS 27+). 에폭마다 진행률을 보고한다. 단축어에서 "끝나면 다음 동작"에 쓴다
@available(macOS 27.0, *)
struct WaitForRunIntent: LongRunningIntent, CancellableIntent {
    static let title: LocalizedStringResource = "Wait Until Training Ends"
    static let description = IntentDescription("Waits for a run to finish and reports progress.")

    @Parameter(title: "Training run") var run: RunEntity

    static var parameterSummary: some ParameterSummary { Summary("Wait for \(\.$run)") }

    func perform() async throws -> some IntentResult & ProvidesDialog & ReturnsValue<RunEntity> {
        let id = run.id
        let done: Run = try await performBackgroundTask {
            while true {
                guard let r = try await IntentAgent.runs().first(where: { $0.id == id }) else { throw AgentError.bad }
                progress.totalUnitCount = Int64(r.total ?? 0)
                progress.completedUnitCount = Int64(r.epoch)
                if !r.isLive { return r }
                try await Task.sleep(for: .seconds(15))
            }
        } onCancel: { _ in }
        return .result(value: RunEntity(done), dialog: "\(done.displayName): \(IntentText.line(done)).")
    }
}
