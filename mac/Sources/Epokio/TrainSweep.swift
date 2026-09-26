import SwiftUI

// 학습 화면의 고급 칸: 스윕(한 설정·격자), 모든 설정(ultralytics 설정표).

extension TrainView {
    // ── 시작 ──
    static let sweepKeys: [(String, LocalizedStringKey)] = [("lr0", "Learning rate (lr0)"), ("imgsz", "Image size (imgsz)"),
        ("batch", "Batch size"), ("epochs", "Epochs"), ("model", "Model size (n, s, m, l, x)"), ("optimizer", "Optimizer")]

    var sweepValueList2: [String] {
        sweepValues2.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    var sweepValueList: [String] {
        sweepValues.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    var sweepRuns: Int {
        sweepMode != "grid" ? Int(randTrials) : max(sweepValueList.count, 1) * (sweep2 ? max(sweepValueList2.count, 1) : 1)
    }

    var sweepPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            SweepMachinesPicker(picks: $sweepMachines, localData: data?.path ?? "")
            Picker(selection: $sweepMode.animation(.smooth)) {
                Label("Values I choose", systemImage: "list.bullet").tag("grid")
                Label("Random in a range", systemImage: "dice").tag("random")
                Label("Smart", systemImage: "sparkle.magnifyingglass").tag("smart")
            } label: { EmptyView() }
            .pickerStyle(.segmented).frame(maxWidth: 480)
            if sweepMode == "grid" {
                Text("One run per value (or per combination), with everything else the same.")
                    .font(.ui(12)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 10) {
                    Picker("Setting", selection: $sweepKey) {
                        ForEach(Self.sweepKeys, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    .frame(width: 260)
                    TextField("Values, separated by commas", text: $sweepValues).textFieldStyle(.roundedBorder)
                }
                Toggle(isOn: $sweep2.animation(.smooth)) { Label("Combine with a second setting (grid)", systemImage: "square.grid.3x3") }
                    .toggleStyle(.checkbox)
                if sweep2 {
                    HStack(spacing: 10) {
                        Picker("Setting", selection: $sweepKey2) {
                            ForEach(Self.sweepKeys.filter { $0.0 != sweepKey }, id: \.0) { Text($0.1).tag($0.0) }
                        }
                        .frame(width: 260)
                        TextField("Values, separated by commas", text: $sweepValues2).textFieldStyle(.roundedBorder)
                    }
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }
            } else {
                Text(sweepMode == "smart"
                     ? "Tries a few values at random, then picks each next value near the best scores so far (the TPE method Optuna uses). Runs one after another so each result guides the next."
                     : "Picks values at random between two limits. Often finds a good learning rate faster than a fixed list.")
                    .font(.ui(12)).foregroundStyle(ink.soft).fixedSize(horizontal: false, vertical: true)
                    .contentTransition(.opacity).animation(Motion.change, value: sweepMode)
                    .transition(.opacity)
                HStack(spacing: 10) {
                    Picker("Setting", selection: $randKey) {
                        ForEach(Self.sweepKeys.filter { ["lr0", "imgsz", "batch", "epochs"].contains($0.0) }, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    .frame(width: 220)
                    TextField("From", text: $randLow).textFieldStyle(.roundedBorder).frame(width: 90)
                    Image(systemName: "arrow.right").foregroundStyle(ink.faint)
                    TextField("To", text: $randHigh).textFieldStyle(.roundedBorder).frame(width: 90)
                    Toggle("Log scale", isOn: $randLog).toggleStyle(.checkbox)
                        .help("Spread picks evenly across 0.0001, 0.001, 0.01… Good for learning rates.")
                }
                SpaceRowsEditor(rows: $extraSpace, taken: [randKey])
                HStack {
                    Text("Runs").font(.ui(12.5))
                    Slider(value: $randTrials, in: 2...24, step: 1).frame(width: 180)
                    TextField("", value: Binding(get: { Int(randTrials) }, set: { randTrials = Double(min(max($0, 2), 24)) }), format: .number)
                        .textFieldStyle(.roundedBorder).frame(width: 50).multilineTextAlignment(.trailing)
                }
            }
            HStack(spacing: 8) {
                Label("Also aim for", systemImage: "target").font(.role(.body))
                Picker("Also aim for", selection: $secondGoal.animation(Motion.change)) {
                    Text("Nothing else").tag(""); Text("A smaller model").tag("size"); Text("Faster training").tag("time")
                }
                .labelsHidden().frame(width: 180)
                if !secondGoal.isEmpty {
                    Text("Results show the runs no other run beats on both.").font(.role(.caption)).foregroundStyle(ink.soft)
                        .transition(.opacity)
                }
            }
            Divider()
            Toggle(isOn: $prune.animation(.smooth)) {
                Label("Stop runs that fall behind", systemImage: "scissors")
            }
            .toggleStyle(.checkbox)
            .help("When a run reaches the check point, it stops if it scores below the middle of the runs that already finished. Saves time on bad settings.")
            if prune {
                HStack(spacing: 8) {
                    Text("Check at").font(.ui(12))
                    Picker("Check at", selection: $pruneAt) {
                        Text("20% of epochs").tag(0.2); Text("30% of epochs").tag(0.3); Text("50% of epochs").tag(0.5)
                    }
                    .labelsHidden().frame(width: 150)
                    Text("Needs two finished runs to compare, so the first runs always go to the end.")
                        .font(.ui(11)).foregroundStyle(ink.soft)
                }
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
            Text(L("%d runs will be queued", sweepRuns))
                .font(.ui(12, weight: .medium)).foregroundStyle(.tint).contentTransition(.numericText())
        }
        .padding(12)
        .background(.tint.opacity(0.05), in: .rect(cornerRadius: 10))
        .animation(.snappy, value: sweepRuns)
    }

    // ── 전문가 설정 ──
    var expertPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                TextField("Search settings", text: $search).textFieldStyle(.roundedBorder)
                if !overrides.isEmpty {
                    Button("Reset \(overrides.count) changed") { withAnimation { overrides = [:] } }
                }
            }
            let shown = fields.filter { f in
                !["model", "data", "epochs", "task", "mode", "name", "project"].contains(f.key)
                    && (search.isEmpty || f.key.localizedCaseInsensitiveContains(search)
                        || f.help.localizedCaseInsensitiveContains(search))
            }
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(shown) { f in FieldRow(field: f, value: binding(f)).padding(.vertical, 6); Divider() }
            }
            .padding(.horizontal, 12)
            .background(.quaternary.opacity(0.35), in: .rect(cornerRadius: 12))
            if fields.isEmpty {
                Text("Choose a Python with ultralytics to see its settings.").font(.ui(11.5)).foregroundStyle(ink.soft)
            }
        }
    }

    func binding(_ f: Field) -> Binding<String> {
        Binding(get: { overrides[f.key] ?? f.default?.text ?? "" },
                set: { v in overrides[f.key] = (v == (f.default?.text ?? "")) ? nil : v })
    }
}
