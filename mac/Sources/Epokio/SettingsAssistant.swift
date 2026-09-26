import SwiftUI

/// 자연어 명령(TypeSafe Jev). 기본 꺼짐. 무엇이 밖으로 나가는지 먼저 알린다
struct AssistantTab: View {
    @AppStorage("jevEnabled") private var on = false
    @State private var key = Keychain.get(Jev.keychainKey) ?? ""
    @State private var saved = false
    var body: some View {
        Form {
            Section {
                Toggle("Type commands in the menu bar", isOn: $on)
                Text("For example \"retrain coco8 for 100 epochs\" or \"compare the last two runs\". Epokio shows what it understood and waits for you to confirm.")
                    .font(.ui(12)).foregroundStyle(.secondary)
            }
            Section("TypeSafe API key") {
                SecureField("Key", text: $key)
                HStack {
                    Link("Get a key at typesafe.ai", destination: URL(string: "https://typesafe.ai")!)
                    Spacer()
                    if saved { Label("Saved", systemImage: "checkmark").foregroundStyle(.good).transition(.opacity) }
                    Button("Save") {
                        Keychain.set(key.trimmingCharacters(in: .whitespacesAndNewlines), for: Jev.keychainKey)
                        withAnimation { saved = true }
                    }
                }
            }
            Section("Sent to TypeSafe") {
                // ★기능마다 보내는 것이 다르다(2026-09-22 결정). 문구가 실제 동작과 어긋나면 안 된다
                Label("Commands: the sentence you type and run names.", systemImage: "text.bubble")
                Label("Explanations: status, task, scores, setting numbers, language and the draft sentences.", systemImage: "sparkles")
                Label("Never sent: images, training data, file paths.", systemImage: "lock.shield")
                Label("Explanations on this Mac (macOS 26+) send nothing.", systemImage: "desktopcomputer")
            }
        }
        .formStyle(.grouped)
    }
}
