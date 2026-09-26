import AppKit
import SwiftUI

// 메뉴바 아이콘 우클릭 메뉴(배터리·Wi-Fi 아이콘처럼): 창을 열지 않고 바로 하는 일.
// MenuBarExtra(.window)는 우클릭을 따로 주지 않아, 앱 안의 우클릭 중 메뉴바 창에서 온 것만 가로챈다.
@MainActor
enum MenuBarRightClick {
    private static var monitor: Any?
    private static let handler = Handler()

    static func install() {
        guard monitor == nil else { return }
        monitor = NSEvent.addLocalMonitorForEvents(matching: [.rightMouseDown]) { e in
            guard let w = e.window, String(describing: type(of: w)).contains("StatusBar"), let v = w.contentView else { return e }
            NSMenu.popUpContextMenu(menu(), with: e, for: v)
            return nil
        }
    }

    private static func menu() -> NSMenu {
        let m = NSMenu()
        let store = Store.current
        if let lead = store?.lead {
            let head = NSMenuItem(title: "\(lead.displayName)  ·  \(lead.pct4.trimmingCharacters(in: .whitespaces))  ·  " + L("%@ left", duration(lead.eta)), action: nil, keyEquivalent: "")
            head.isEnabled = false
            m.addItem(head)
        } else {
            let head = NSMenuItem(title: L("Nothing is training right now"), action: nil, keyEquivalent: "")
            head.isEnabled = false
            m.addItem(head)
        }
        m.addItem(.separator())
        m.addItem(item(L("Open Epokio Studio"), "macwindow", #selector(Handler.studio), "o"))
        if let job = store?.runningJob {
            m.addItem(item(L("Stop %@", job.name), "stop.circle", #selector(Handler.stop)))
        }
        if let until = Notifier.pausedUntil {
            let f = DateFormatter(); f.timeStyle = .short
            m.addItem(item(L("Resume Notifications (paused until %@)", f.string(from: until)), "bell", #selector(Handler.resume)))
        } else {
            m.addItem(item(L("Pause Notifications for 1 Hour"), "bell.slash", #selector(Handler.pause)))
        }
        m.addItem(.separator())
        m.addItem(item(L("Settings…"), "gearshape", #selector(Handler.settings), ","))
        m.addItem(item(L("Quit Epokio"), "power", #selector(Handler.quit), "q"))
        return m
    }

    private static func item(_ title: String, _ symbol: String, _ sel: Selector, _ key: String = "") -> NSMenuItem {
        let i = NSMenuItem(title: title, action: sel, keyEquivalent: key)
        i.target = handler
        i.image = NSImage(systemSymbolName: symbol, accessibilityDescription: nil)
        return i
    }

    private final class Handler: NSObject {
        @objc func studio() { NotificationCenter.default.post(name: .openStudio, object: nil); NSApp.activate() }
        @objc func stop() { NotificationCenter.default.post(name: .stopRun, object: nil) }
        @objc func pause() { MainActor.assumeIsolated { Notifier.pausedUntil = .now.addingTimeInterval(3600); Store.current?.say(L("Notifications paused for 1 hour")) } }
        @objc func resume() { MainActor.assumeIsolated { Notifier.pausedUntil = nil; Store.current?.say(L("Notifications are back on")) } }
        @objc func settings() { NSApp.activate(); NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil) }
        @objc func quit() { NSApp.terminate(nil) }
    }
}
