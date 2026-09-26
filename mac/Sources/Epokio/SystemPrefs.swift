import SwiftUI
import AppKit

// 맥 시스템 설정을 앱이 따라가게 하는 한 곳.
// ① 손쉬운 사용 "동작 줄이기"  ② 시스템 강조색.
// 왜 여기 모았나: Motion 토큰은 static이라 SwiftUI Environment를 못 읽는다. 그래서
// NSWorkspace 값을 캐시해 두고, 시스템이 바뀔 때 알림으로만 갱신한다(애니메이션마다 API를 부르지 않는다).

/// 시스템 값 캐시. 읽기는 공짜, 갱신은 알림이 올 때만.
enum SystemPrefs {
    /// 진짜 시스템 값을 읽는 자리. 시험·미리보기에서 갈아 끼우려고 함수로 뒀다
    nonisolated(unsafe) static var reduceMotionSource: () -> Bool = { NSWorkspace.shared.accessibilityDisplayShouldReduceMotion }
    nonisolated(unsafe) private static var cached = reduceMotionSource()

    /// 손쉬운 사용 → 동작 줄이기. 켜져 있으면 앱의 "움직임 속도" 설정과 무관하게 움직이지 않는다
    static var reduceMotion: Bool { cached }

    /// 알림을 받았을 때(또는 시험에서 source를 바꾼 뒤) 캐시를 다시 읽는다
    @discardableResult static func refresh() -> Bool { cached = reduceMotionSource(); return cached }
}

/// 시스템 설정이 바뀌면 화면을 다시 그리게 하는 감시자. `withInk()`가 뿌리에 하나 붙인다
@MainActor final class SystemPrefsWatcher: ObservableObject {
    static let shared = SystemPrefsWatcher()

    /// 값이 바뀔 때마다 하나씩 오른다(뷰를 다시 그리게 하는 용도)
    @Published private(set) var stamp = 0

    /// 시스템 동작 줄이기. 화면에서 이걸 읽으면 바뀔 때 알아서 다시 그려진다
    var reduce: Bool { _ = stamp; return SystemPrefs.reduceMotion }

    private init() {
        let bump: @Sendable (Notification) -> Void = { _ in
            Task { @MainActor in SystemPrefsWatcher.shared.changed() }
        }
        // 동작 줄이기·대비 증가 등 손쉬운 사용 표시 설정
        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: nil, queue: .main, using: bump)
        // 시스템 강조색 (설정 → 모양새에서 고르는 색)
        NotificationCenter.default.addObserver(
            forName: NSColor.systemColorsDidChangeNotification, object: nil, queue: .main, using: bump)
        DistributedNotificationCenter.default.addObserver(
            forName: Notification.Name("AppleColorPreferencesChangedNotification"), object: nil, queue: .main, using: bump)
    }

    private func changed() {
        SystemPrefs.refresh()
        stamp &+= 1
    }
}
