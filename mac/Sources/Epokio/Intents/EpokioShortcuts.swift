import AppIntents

// Siri·Spotlight 문구. 문구마다 앱 이름이 들어가야 한다(시스템 규칙)
struct EpokioShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: TrainingStatusIntent(), phrases: [
            "How is my training going in \(.applicationName)",
            "\(.applicationName) training status",
            "\(.applicationName) 학습 어때",
            "\(.applicationName) 학습 상태",
        ], shortTitle: "Training Status", systemImageName: "chart.line.uptrend.xyaxis")
        AppShortcut(intent: OpenRunIntent(), phrases: [
            "Open \(\.$run) in \(.applicationName)",
            "\(.applicationName)에서 \(\.$run) 열기",
        ], shortTitle: "Open Run", systemImageName: "chart.xyaxis.line")
        AppShortcut(intent: RetrainIntent(), phrases: [
            "Train \(\.$run) again in \(.applicationName)",
            "\(.applicationName)에서 \(\.$run) 다시 학습",
        ], shortTitle: "Train Again", systemImageName: "arrow.clockwise")
    }
}
