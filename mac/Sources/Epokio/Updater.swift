import SwiftUI
import Sparkle

// 자동 업데이트(Sparkle 2). 빌드에 공개키(SUPublicEDKey)가 들어 있을 때만 켠다: 서명 안 된 업데이트는 받지 않는다.
// 자동 확인 여부는 Sparkle이 두 번째 실행 때 사용자에게 묻고(동의 전엔 요청 안 함), 설정 → 일반에서 바꾼다.
// 확인 요청은 외부 전송이다(공개 저장소의 appcast.xml 하나를 읽는다. 보내는 것은 앱 버전·macOS 버전뿐).
@MainActor
final class Updater: ObservableObject {
    static let shared = Updater()
    let controller: SPUStandardUpdaterController?
    @Published var canCheck = false

    var available: Bool { controller != nil }

    private init() {
        let key = Bundle.main.object(forInfoDictionaryKey: "SUPublicEDKey") as? String ?? ""
        guard !key.isEmpty, Bundle.main.object(forInfoDictionaryKey: "SUFeedURL") != nil else { controller = nil; return }
        controller = SPUStandardUpdaterController(startingUpdater: true, updaterDelegate: nil, userDriverDelegate: nil)
        controller?.updater.publisher(for: \.canCheckForUpdates).assign(to: &$canCheck)
    }

    func check() { controller?.checkForUpdates(nil) }

    var automatic: Bool {
        get { controller?.updater.automaticallyChecksForUpdates ?? false }
        set { controller?.updater.automaticallyChecksForUpdates = newValue; objectWillChange.send() }
    }
}

struct UpdateCommands: Commands {
    @ObservedObject var updater = Updater.shared
    var body: some Commands {
        CommandGroup(after: .appInfo) {
            if updater.available {
                Button("Check for Updates…") { updater.check() }.disabled(!updater.canCheck)
            }
        }
    }
}

/// 설정 → 일반 한 줄
struct UpdateSettingsRow: View {
    @ObservedObject var updater = Updater.shared
    @State private var bump = 0
    var body: some View {
        if updater.available {
            HStack {
                Toggle("Check for updates automatically", isOn: Binding(get: { updater.automatic }, set: { updater.automatic = $0 }))
                    .help("Reads one small file from the project's GitHub releases. Sends only the app and macOS versions.")
                Spacer()
                Button { bump += 1; updater.check() } label: {
                    Label("Check Now", systemImage: "arrow.triangle.2.circlepath").symbolEffect(.rotate, value: bump)
                }
                .disabled(!updater.canCheck)
            }
        } else {
            Text("Updates: this build has no update key, so it does not check for updates. Download new versions from GitHub.")
                .font(.ui(11.5)).foregroundStyle(.secondary)
        }
    }
}
