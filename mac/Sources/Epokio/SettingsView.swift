import SwiftUI
import ServiceManagement
import Security

// 설정 창 (⌘,). 디자인·알림·기계를 전부 사용자가 켜고 끈다.
struct SettingsView: View {
    var body: some View {
        TabView {
            GeneralTab().tabItem { Label("General", systemImage: "gearshape") }
            AppearanceTab().tabItem { Label("Appearance", systemImage: "paintbrush") }
            CustomizeTab().tabItem { Label("Customize", systemImage: "slider.horizontal.3") }
            NotificationsTab().tabItem { Label("Notifications", systemImage: "bell.badge") }
            MachinesTab().tabItem { Label("Machines", systemImage: "desktopcomputer") }
            AssistantTab().tabItem { Label("Assistant", systemImage: "sparkles") }
        }
        .frame(width: 560, height: 440)
        .withInk()
    }
}
