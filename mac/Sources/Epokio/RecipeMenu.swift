import SwiftUI

// 학습 레시피: 자주 쓰는 설정에 이름을 붙여 두고 한 번에 채운다(단축어 모음처럼). 저장은 agent(~/.epokio/recipes.json)라 웹과 같은 목록.
struct Recipe: Decodable, Hashable { let name: String; let params: [String: SweepSummary.Value] }

struct RecipeMenu: View {
    @Binding var task: String
    @Binding var size: String
    @Binding var epochs: Double
    @Binding var overrides: [String: String]
    @Binding var data: URL?
    @Binding var status: String?
    @Environment(Store.self) private var store
    @State private var recipes: [Recipe] = []
    @State private var naming = false
    @State private var newName = ""
    @State private var bump = 0

    var body: some View {
        Menu {
            if recipes.isEmpty { Text("No recipes yet") }
            ForEach(recipes, id: \.name) { r in
                Button { apply(r) } label: { Label(r.name, systemImage: "wand.and.rays") }
            }
            Divider()
            Button { newName = ""; naming = true } label: { Label("Save Current Settings as Recipe…", systemImage: "plus") }
            if !recipes.isEmpty {
                Menu("Delete Recipe") {
                    ForEach(recipes, id: \.name) { r in Button(r.name, role: .destructive) { Task { await delete(r.name) } } }
                }
            }
        } label: { Label("Recipes", systemImage: "book.closed").symbolEffect(.bounce, value: bump) }
        .fixedSize()
        .help("Save the settings you use often and fill them in with one click")
        .task { await load() }
        .alert("Save as recipe", isPresented: $naming) {
            TextField("Name, e.g. Fast check", text: $newName)
            Button("Save") { Task { await save() } }
            Button("Cancel", role: .cancel) {}
        } message: { Text("Task, model size, epochs, changed settings and the data file are saved.") }
    }

    private func load() async {
        struct R: Decodable { let recipes: [Recipe] }
        if let r: R = try? await AgentClient.local.get("recipes") { recipes = r.recipes }
    }

    private func save() async {
        let name = newName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        var p: [String: Any] = ["task": task, "size": size, "epochs": Int(epochs)]
        if let data { p["data"] = data.isFileURL ? data.path : data.absoluteString }
        for (k, v) in overrides { p["set." + k] = v }
        nonisolated(unsafe) let body: [String: Any] = ["name": name, "params": p]
        await store.act(L("Saved recipe %@", name)) { _ = try await AgentClient.local.post("recipes", body) }
        bump += 1; Haptic.success()
        await load()
    }

    private func delete(_ name: String) async {
        await store.act { _ = try await AgentClient.local.post("recipes/delete", ["name": name]) }
        await load()
    }

    /// 레시피 값을 화면 칸에 채운다. "set.xxx"는 전문가 설정
    private func apply(_ r: Recipe) {
        withAnimation(Motion.change) {
            for (k, v) in r.params {
                switch k {
                case "task": task = v.description
                case "size": size = v.description
                case "epochs": epochs = Double(v.description) ?? epochs
                case "data": data = v.description.hasSuffix(".yaml") && !v.description.contains("/") ? URL(string: v.description) : URL(fileURLWithPath: v.description)
                default: if k.hasPrefix("set.") { overrides[String(k.dropFirst(4))] = v.description }
                }
            }
            status = L("Filled in from the recipe %@.", r.name)
        }
        bump += 1
    }
}
