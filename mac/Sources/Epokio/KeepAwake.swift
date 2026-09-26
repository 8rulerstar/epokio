import Foundation
import IOKit.pwr_mgt

/// 학습 중 잠자기 방지. 이 Mac에서 학습이 도는 동안만 시스템 잠자기를 막는다(화면은 꺼져도 된다).
/// 학습이 끝나거나 멈추면 바로 푼다. 설정 → 일반 "학습 중에는 Mac을 깨워 두기"(기본 켬).
@MainActor
final class KeepAwake {
    static let shared = KeepAwake()
    private var id: IOPMAssertionID = 0
    private(set) var active = false

    func update(training: Bool) {
        let want = training && (UserDefaults.standard.object(forKey: "keepAwake") as? Bool ?? true)
        guard want != active else { return }
        if want {
            let r = IOPMAssertionCreateWithName(kIOPMAssertionTypePreventUserIdleSystemSleep as CFString,
                                                IOPMAssertionLevel(kIOPMAssertionLevelOn),
                                                "Epokio: training is running" as CFString, &id)
            active = r == kIOReturnSuccess
        } else {
            IOPMAssertionRelease(id)
            active = false
        }
    }
}
