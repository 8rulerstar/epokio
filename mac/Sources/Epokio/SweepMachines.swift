import SwiftUI

// 스윕을 여러 기계에 나눠 돌릴 때 기계 고르기. 원격은 설정 → 기계에 등록한 것만(토큰은 키체인).
// 기계마다 파이썬과 data.yaml 경로가 다르다: 원격 파이썬 목록은 그 기계의 /pythons에서 읽는다(토큰 필요 없음).

struct SweepMachinePick: Identifiable, Hashable {
    var id: String { url }
    let url: String
    var on = false
    var python = ""
    var data = ""
    var envs: [PyEnv] = []
    var reachable: Bool? = nil
}

struct SweepMachinesPicker: View {
    @Binding var picks: [SweepMachinePick]
    let localData: String
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink

    private var remotes: [URL] { store.agents.filter { !($0.host == "127.0.0.1" || $0.host == "localhost") } }

    var body: some View {
        if !remotes.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Label("Also run on", systemImage: "server.rack").font(.role(.body, weight: .semibold))
                Text("Each machine takes the next run when it is free. Paths are on that machine.")
                    .font(.role(.caption)).foregroundStyle(ink.soft)
                ForEach($picks) { $p in row($p) }
            }
            .padding(12)
            .background(.quaternary.opacity(0.25), in: .rect(cornerRadius: Radius.card))
            .task(id: remotes) { await load() }
        }
    }

    private func row(_ p: Binding<SweepMachinePick>) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Toggle(isOn: p.on.animation(Motion.change)) {
                    Text(verbatim: URL(string: p.wrappedValue.url)?.host() ?? p.wrappedValue.url).font(.role(.body, weight: .medium))
                }
                .toggleStyle(.checkbox)
                .disabled(p.wrappedValue.reachable == false)
                if p.wrappedValue.reachable == false {
                    Label("Not reachable", systemImage: "wifi.exclamationmark").font(.role(.caption)).foregroundStyle(.warn)
                } else if p.wrappedValue.reachable == nil {
                    ProgressView().controlSize(.mini)
                }
            }
            if p.wrappedValue.on {
                HStack(spacing: 8) {
                    Picker("Python", selection: p.python) {
                        ForEach(p.wrappedValue.envs) { e in Text(verbatim: e.name).tag(e.path) }
                    }
                    .frame(width: 220)
                    TextField("data.yaml on that machine", text: p.data).textFieldStyle(.roundedBorder)
                }
                .padding(.leading, 22)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
    }

    /// 등록된 원격마다 파이썬 목록을 읽는다. 못 닿으면 고를 수 없게
    private func load() async {
        struct P: Decodable { let envs: [PyEnv] }
        var out: [SweepMachinePick] = []
        for u in remotes {
            var p = picks.first { $0.url == u.absoluteString } ?? SweepMachinePick(url: u.absoluteString, data: localData)
            if let got: P = try? await AgentClient(base: u).get("pythons") {
                p.envs = got.envs.filter { $0.ultralytics != nil }
                if p.python.isEmpty { p.python = p.envs.first?.path ?? "" }
                p.reachable = true
            } else {
                p.reachable = false; p.on = false
            }
            out.append(p)
        }
        withAnimation(Motion.change) { picks = out }
    }
}
