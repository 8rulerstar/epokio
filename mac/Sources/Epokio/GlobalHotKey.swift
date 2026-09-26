import AppKit
import Carbon.HIToolbox

// 어디서든 ⌥⌘E로 Epokio Studio를 앞으로(iStat Menus·Raycast처럼). Carbon 단축키라 손쉬운 사용 권한이 필요 없다.
// 설정 → 일반에서 끈다(globalHotKey). 누르면 .openStudio 알림 → StudioOpener가 창을 연다.
@MainActor final class GlobalHotKey {
    static let shared = GlobalHotKey()
    private var ref: EventHotKeyRef?
    private var handler: EventHandlerRef?

    func apply() {
        let on = UserDefaults.standard.object(forKey: "globalHotKey") as? Bool ?? true
        on ? register() : unregister()
    }

    private func register() {
        guard ref == nil else { return }
        if handler == nil {
            var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
            InstallEventHandler(GetApplicationEventTarget(), { _, _, _ in
                DispatchQueue.main.async {
                    NSApp.activate()
                    NotificationCenter.default.post(name: .openStudio, object: nil)
                }
                return noErr
            }, 1, &spec, nil, &handler)
        }
        let id = EventHotKeyID(signature: OSType(0x45504B4F), id: 1)          // 'EPKO'
        let st = RegisterEventHotKey(UInt32(kVK_ANSI_E), UInt32(cmdKey | optionKey), id, GetApplicationEventTarget(), 0, &ref)
        NSLog("Epokio hotkey ⌥⌘E register status %d", st)                  // 0 = 등록됨. 다른 앱이 이미 쓰면 -9878
    }

    private func unregister() {
        if let ref { UnregisterEventHotKey(ref) }
        ref = nil
    }
}
