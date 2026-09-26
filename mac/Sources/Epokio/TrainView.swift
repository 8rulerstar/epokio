import SwiftUI
import UniformTypeIdentifiers

// 학습 시작 화면.
// 초보자: 데이터셋 끌어다 놓기 → 작업 종류 → 모델 크기 → 에폭 → 시작. 이 다섯 개면 끝.
// 전문가: "모든 설정 보기"를 켜면 ultralytics 설정표(88개)가 설명과 함께 전부 나온다.
struct TrainView: View {
    @Environment(\.ink) var ink
    @Environment(Store.self) var store
    @State var envs: [PyEnv] = []
    @State var env: PyEnv?
    @State var data: URL?
    @AppStorage("trainTask") var task = "detect"          // 마지막에 쓴 값을 기억해 다음 학습 기본값으로
    @AppStorage("trainSize") var size = "n"
    @AppStorage("trainEpochs") var epochs = 50.0
    @State var name = ""
    @State var expert = false
    @State var fields: [Field] = []
    @State var overrides: [String: String] = [:]
    @State var search = ""
    @State var status: String?
    @State var makeYaml = false
    // 어디서 학습하나: 이 Mac 또는 연결된 원격 기계(ClearML의 agent 큐처럼)
    @State var machine: URL = AgentLauncher.url
    @State var remotePath = ""                   // 원격이면 그 기계 기준 data.yaml 경로를 적는다
    var client: AgentClient { AgentClient(base: machine) }
    var remote: Bool { machine != AgentLauncher.url }
    // 무엇을 돌리나: YOLO(설정을 골라서) 또는 내 스크립트(Hugging Face·Lightning·Keras 등 아무 파이썬)
    @State var mode = "yolo"
    @State var script = ""
    @State var scriptArgs = ""
    @State var scriptFolder = ""
    @State var watchFolder = ""
    // 격자 스윕: 두 번째 설정
    @State var sweep2 = false
    @State var sweepKey2 = "imgsz"
    @State var sweepValues2 = "480, 640"
    // 스윕: 설정 하나를 여러 값으로 바꿔 가며 한꺼번에 대기열에
    @State var sweep = false
    @State var sweepKey = "lr0"
    @State var sweepValues = "0.01, 0.005, 0.001"
    // 무작위 탐색 · 조기 중단
    @State var sweepMode = "grid"                 // grid · random · smart
    @State var sweepMachines: [SweepMachinePick] = []   // 여러 기계에 나눠 돌리기(원격이 등록돼 있을 때)
    @State var extraSpace: [SpaceRow] = []              // 무작위·똑똑하게: 설정을 더(최대 4개)
    @State var secondGoal = ""                          // 두 목표: "" · size(작은 모델) · time(빠른 학습)
    // "무엇에서 시작할까요?": 최근·최고 학습, 프리셋에서 한 번에 채우기. 채운 뒤 바뀐 칸을 보인다(TrainStart.swift)
    @State var starts: [TableRun] = []
    @State var baseline: [String: String]?
    @State var baseName = ""
    @State var baseData = ""
    @State var randKey = "lr0"
    @State var randLow = "0.0001"
    @State var randHigh = "0.01"
    @State var randLog = true
    @State var randTrials = 8.0
    @State var prune = false
    @State var pruneAt = 0.3
    @State var busy = false
    @State var dropHover = false
    // "다시 학습": 원래 run의 설정 전체(타입 그대로)·원래 모델·못 옮긴 키. 재개면 resumeParams(TrainSubmit.swift)
    @State var inherited: [String: Any] = [:]
    @State var inheritedFrom = ""
    @State var inheritedKept = 0
    @State var inheritedModel: String?
    @State var inheritedDropped: [String: String] = [:]
    @State var resumeParams: [String: Any]?
    @State var moreOpen = false                         // "옵션 더 보기" 펼침(화면 표시만, 저장 안 함)
    @State var preflightErrors: [String] = []           // 출발 전 점검에 걸린 데이터 오류
    @State var loadError: String?                       // 파이썬 목록을 못 받은 이유(토큰·연결)

    let tasks: [(String, String, String)] = [
        ("detect", L("Detect"), "rectangle.dashed"), ("segment", L("Segment"), "scribble"),
        ("pose", L("Pose"), "figure.stand"), ("classify", L("Classify"), "square.grid.2x2")]
    let sizes: [(String, String)] = [("n", L("Nano")), ("s", L("Small")), ("m", L("Medium")), ("l", L("Large")), ("x", L("X-Large"))]

    /// 학습 상세의 "다시 학습": 그때 쓴 데이터·작업·크기·에폭을 채운다
    func takePending() {
        guard let a = store.pendingTrainArgs else { return }
        store.pendingTrainArgs = nil
        clearInherited()
        if let path = RetrainRequest.path {                  // 원래 run 경로를 알면 args.yaml 전체를 받아 온다
            let resume = RetrainRequest.resume
            RetrainRequest.path = nil; RetrainRequest.resume = false
            Task { await loadRetrain(path, resume: resume) }
        }
        if let d = a["data"], !d.isEmpty { data = d.hasSuffix(".yaml") && !d.contains("/") ? URL(string: d) : URL(fileURLWithPath: d) }
        if let t = a["task"], tasks.contains(where: { $0.0 == t }) { task = t }
        if let m = a["model"], let c = URL(fileURLWithPath: m).deletingPathExtension().lastPathComponent
            .split(separator: "-").first?.last, sizes.contains(where: { $0.0 == String(c) }) { size = String(c) }
        if let e = a["epochs"].flatMap(Double.init) { epochs = e }
        // ★lr0·imgsz 같은 설정은 받지 않아 "다음 학습 제안(학습률 ÷3)"을 눌러도 양식에 안 들어갔다. 전문가 설정으로 옮긴다
        for k in ["lr0", "lrf", "imgsz", "batch", "optimizer", "patience", "momentum", "weight_decay", "mosaic", "close_mosaic"] {
            if let v = a[k], !v.isEmpty { overrides[k] = v }
        }
        if let w = a["weights"], !w.isEmpty {                 // 그 best.pt에서 새로 파인튜닝(옵티마이저·에폭은 처음부터. 재개 아님)
            overrides["model"] = w
            status = L("Fine-tunes from %@ as a new run (epochs and optimizer start over). Change anything, then start.", URL(fileURLWithPath: w).deletingLastPathComponent().deletingLastPathComponent().lastPathComponent)
            return
        }
        status = L("Filled in from the previous run. Change anything, then start.")
    }

    // 본문 밖으로 뺐다. ★본문 안에 두면 Int·Double 변환과 min/max 때문에 컴파일러가 타입 검사를 포기했다
    var epochSlider: Binding<Double> {
        Binding(get: { Swift.min(epochs, 300.0) }, set: { (v: Double) in epochs = (v / 5).rounded() * 5 })
    }
    var epochField: Binding<Int> {
        Binding(get: { Int(epochs) }, set: { (v: Int) in epochs = Double(Swift.min(Swift.max(v, 1), 5000)) })
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                // 머리: 제목 · 무엇을 돌리나 · 어디서 · 레시피. 요약 먼저, 나머지는 아래 "옵션 더 보기"에 접는다
                HStack(spacing: 10) {
                    Text("New training").font(.role(.title))
                    Spacer()
                    Picker(selection: $mode.animation(.smooth)) {
                        Label("YOLO", systemImage: "square.dashed").tag("yolo")
                        Label("My script", systemImage: "terminal").tag("script")
                        Label("Practice", systemImage: "sparkles.tv").tag("practice")
                    } label: { EmptyView() }
                    .pickerStyle(.segmented).fixedSize()
                    .help("YOLO: pick settings here. My script: run any Python training script (Hugging Face, Lightning, Keras…)")
                    if store.agents.count > 1 {
                        Picker(selection: $machine) {
                            ForEach(store.agents, id: \.self) { u in
                                Text(verbatim: u == AgentLauncher.url ? L("This Mac") : store.label(for: u)).tag(u)
                            }
                        } label: { Image(systemName: "desktopcomputer") }
                        .fixedSize()
                        .help("Train on this Mac or on a connected machine")
                    }
                    RecipeMenu(task: $task, size: $size, epochs: $epochs, overrides: $overrides, data: $data, status: $status)
                }
                if mode == "practice" { PracticePanel().transition(.opacity) } else if mode == "script" { scriptPanel.transition(.opacity) } else {
                if remote {
                    VStack(alignment: .leading, spacing: 6) {
                        Label(L("Path to data.yaml on %@", store.label(for: machine)), systemImage: "doc.text").font(.ui(13, weight: .semibold))
                        TextField("D:\\datasets\\mydata\\data.yaml", text: $remotePath).textFieldStyle(.roundedBorder)
                            .onChange(of: remotePath) { _, v in data = v.isEmpty ? nil : URL(fileURLWithPath: v) }
                    }
                } else {
                datasetDrop
                }
                if let data, data.pathExtension != "" && data.path != "coco8.yaml" {
                    HealthCard(data: data, client: client, remotePath: remote ? remotePath : nil).id(machine).transition(.opacity.combined(with: .move(edge: .top)))
                }
                step("Task", "What should the model learn?", symbol: "square.grid.2x2") {
                    HStack(spacing: 8) {
                        ForEach(tasks, id: \.0) { t in
                            Choice(title: LocalizedStringKey(t.1), symbol: t.2, on: task == t.0) {
                                withAnimation(.snappy) { task = t.0 }
                            }
                        }
                    }
                }
                step("Model size", "Bigger is more accurate but slower.", symbol: "cube") {
                    Picker("", selection: $size) { ForEach(sizes, id: \.0) { Text($0.1).tag($0.0) } }
                        .pickerStyle(.segmented).labelsHidden()
                }
                step("Epochs", "How many times to go through the data.", symbol: "repeat") {
                    HStack {
                        // step을 주면 눈금이 수십 개 그려져 지저분했다. 값만 5 단위로 맞춘다
                        Slider(value: epochSlider, in: 5...300)
                        // 직접 입력도 된다(슬라이더 끝 300보다 크게도)
                        TextField("", value: epochField, format: .number)
                            .textFieldStyle(.roundedBorder)
                            .font(.ui(13, design: .monospaced))
                            .multilineTextAlignment(.trailing)
                            .frame(width: 64)
                    }
                }
                // 파이썬은 문제가 있을 때만 작게 알린다. 고르기는 "옵션 더 보기" 안에
                if envs.isEmpty || env?.ready == false {
                    Group {                           // ★if/else 뒤에 바로 수식어를 붙여 컴파일이 멈췄다
                        if let loadError {
                            // 목록을 못 받았다(토큰·연결). ★예전엔 조용히 '파이썬 설치' 카드를 보여 줘, 원인과 상관없는 설치를 권했다
                            Label(loadError, systemImage: "exclamationmark.triangle").font(.ui(12)).foregroundStyle(.warn)
                        } else {
                            PythonSetupCard(hasAnyReady: envs.contains(where: \.ready), client: client) { Task { await load() } }
                        }
                    }
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }
                if !preflightErrors.isEmpty {
                    PreflightCard(errors: preflightErrors) { Task { await start(anyway: true) } }
                        .transition(.opacity.combined(with: .move(edge: .bottom)))
                }
                }                                                            // YOLO 모드 끝
                if mode == "yolo" && (!inherited.isEmpty || resumeParams != nil) { inheritStrip.transition(.opacity.combined(with: .move(edge: .top))) }
                if mode != "practice" { startBar }
                if mode == "yolo" { moreOptions }
            }
            .padding(28)
            .frame(maxWidth: 720, alignment: .leading)
            .frame(maxWidth: .infinity)          // 가운데 두고 스크롤 영역은 창 끝까지
        }
        .task { await load() }
        .sheet(isPresented: $makeYaml) {
            DataYamlBuilder { url in withAnimation(.smooth) { data = url } }.withInk()
        }
        .onAppear(perform: takePending)
        .onChange(of: store.pendingTrainArgs) { takePending() }
        .onChange(of: env) { Task { await loadSchema() } }
        .onChange(of: data) { withAnimation(.smooth) { preflightErrors = [] } }
        // ★설정표·바꾼 값도 비운다. 안 그러면 앞 기계(다른 ultralytics 판)의 칸과 값이 새 기계로 넘어갔다
        .onChange(of: machine) { data = nil; remotePath = ""; env = nil; envs = []; fields = []; overrides = [:]; clearInherited(); Task { await load() } }   // ★다시 학습 설정이 남아 다른 기계에 옛 설정이 채워졌다
    }

    // ── 데이터셋 ──
    // 드롭존 하나. 샘플·data.yaml 만들기는 안쪽 작은 보조 버튼(긴 설명은 툴팁·우클릭)
    var sample: Bool { data?.absoluteString == "coco8.yaml" }
    func useSample() { withAnimation(.smooth) { data = URL(string: "coco8.yaml"); task = "detect"; size = "n"; epochs = 10 } }

    var datasetDrop: some View {
        VStack(spacing: 8) {
            Image(systemName: data == nil ? "tray.and.arrow.down" : "checkmark.circle.fill")
                .font(.ui(28, weight: .light))
                .foregroundStyle(data == nil ? AnyShapeStyle(dropHover ? AnyShapeStyle(.brand) : AnyShapeStyle(ink.faint)) : AnyShapeStyle(.good))
                .symbolEffect(.bounce, value: data)
                .scaleEffect(dropHover ? 1.12 : 1)
                .contentTransition(.symbolEffect(.replace))
            Text(sample ? L("Sample: COCO8") : (data?.lastPathComponent ?? L("Drop your data.yaml here")))
                .font(.ui(14, weight: .semibold)).foregroundStyle(.primary)
                .contentTransition(.opacity)
            if let data {
                Text(verbatim: sample ? L("8 images. For a first try.") : data.deletingLastPathComponent().path)
                    .font(.ui(11.5)).foregroundStyle(ink.soft).lineLimit(1).truncationMode(.middle)
                    .transition(.opacity)
            } else if !remote {
                HStack(spacing: 14) {
                    Button(action: useSample) { Label("Try sample", systemImage: "sparkles") }
                        .help("No dataset yet? Try with a tiny sample (8 images)")
                    Button { makeYaml = true } label: { Label("Make data.yaml", systemImage: "doc.badge.plus") }
                        .help("Have images but no data.yaml? Make one")
                }
                .buttonStyle(BrandLink()).font(.ui(12, weight: .medium))
                .transition(.opacity)
            }
        }
        .frame(maxWidth: .infinity).padding(.vertical, 22)
        // 떠 있는 표면이 아니라 읽는 자리라 유리 대신 옅은 면(Components 규칙). 점선은 뺐다
        .background(dropHover ? Color.brand.opacity(0.10) : .primary.opacity(0.035), in: .rect(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).strokeBorder(dropHover ? Color.brand.opacity(0.7) : .primary.opacity(0.08), lineWidth: dropHover ? 1.5 : 1))
        .scaleEffect(dropHover ? 1.01 : 1)
        .contentShape(.rect)
        .onTapGesture { pick() }
        // Tab 으로 옮겨 오고 Space·Return 으로도 열리게 한다.
        // 다른 두 드롭 영역과 달리 여기만 Button 으로 못 감싼다. 안에 작은 버튼 둘(샘플·data.yaml 만들기)이 있어
        // 감싸면 그 둘이 바깥 버튼에 먹혀 안 눌린다. 그래서 focusable 로 포커스만 받고 키는 직접 받는다
        .focusable()
        .onKeyPress(.space) { pick(); return .handled }
        .onKeyPress(.return) { pick(); return .handled }
        .help("Click to choose, or drop a data.yaml. It lists your images and classes.")
        .contextMenu {
            Button("Choose data.yaml…", systemImage: "folder") { pick() }
            Button("Try the Sample", systemImage: "sparkles") { useSample() }
            Button("Make data.yaml…", systemImage: "doc.badge.plus") { makeYaml = true }
            if data != nil { Divider(); Button("Clear", systemImage: "xmark.circle") { withAnimation(.smooth) { data = nil } } }
        }
        .accessibilityElement(children: .contain)
        .accessibilityAddTraits(.isButton)
        .onDrop(of: [.fileURL], isTargeted: $dropHover) { items in
            _ = items.first?.loadObject(ofClass: URL.self) { url, _ in
                if let url { Task { @MainActor in data = url } }
            }
            return true
        }
        .animation(.snappy, value: dropHover)
        .animation(.smooth, value: data)
    }

    // ── 접힌 옵션: 시작점 · 파이썬 · 모든 설정 · 스윕 ──
    var moreOptions: some View {
        DisclosureGroup(isExpanded: $moreOpen.animation(.smooth)) {
            VStack(alignment: .leading, spacing: 16) {
                startStrip
                step("Python", "Where to run. Needs ultralytics and torch.", symbol: "terminal") {
                    Picker("", selection: $env) {
                        ForEach(envs) { e in
                            Label("\(e.name)  ·  \(e.device)" + (e.ultralytics.map { "  ·  ultralytics \($0)" } ?? "  ·  no ultralytics"),
                                  systemImage: e.ready ? "checkmark.circle.fill" : "exclamationmark.circle")
                                .tag(Optional(e))
                        }
                    }.labelsHidden()
                }
                Toggle(isOn: $expert.animation(.smooth)) {
                    Label("Show all settings", systemImage: "slider.horizontal.3")
                }
                .toggleStyle(.switch)
                if expert { expertPanel.transition(.opacity.combined(with: .move(edge: .top))) }
                Toggle(isOn: $sweep.animation(.smooth)) {
                    Label("Try several values (sweep)", systemImage: "square.stack.3d.forward.dottedline")
                }
                .toggleStyle(.switch)
                if sweep { sweepPanel.transition(.opacity.combined(with: .move(edge: .top))) }
            }
            .padding(.top, 10)
        } label: {
            Label("More options", systemImage: "ellipsis.circle")
                .font(.ui(13, weight: .semibold)).foregroundStyle(ink.soft)
                .contentShape(.rect)
                .onTapGesture { withAnimation(.smooth) { moreOpen.toggle() } }
        }
        .help("Presets, Python, all settings, sweep")
    }

    var startBar: some View {
        HStack(spacing: 12) {
            TextField("Run name (optional)", text: $name).textFieldStyle(.roundedBorder).frame(width: 220)
            Spacer()
            if let status { Text(status).font(.ui(11.5)).foregroundStyle(ink.soft).transition(.opacity) }
            else if let why = blocked {                                    // 시작 버튼이 꺼진 이유. 꺼진 버튼도 도움말은 뜨지만, 여기선 다음 할 일이라 늘 보인다
                Label(why, systemImage: "info.circle").font(.role(.caption)).foregroundStyle(ink.soft).transition(.opacity)
            }
            Button {
                Task { if mode == "script" { await startScript() } else { await start() } }
            } label: {
                Label(busy ? "Adding…" : (sweep && sweepRuns > 1 ? "Queue Sweep" : "Start Training"),
                      systemImage: sweep ? "square.stack.3d.forward.dottedline" : "play.fill")
                    .font(.ui(14, weight: .semibold)).padding(.horizontal, 10).padding(.vertical, 4)
            }
            .primaryButton().controlSize(.large)
            .disabled((mode == "script" ? script.isEmpty : data == nil && resumeParams == nil) || env == nil || busy)
            .keyboardShortcut(.return, modifiers: .command)
        }
        .padding(.top, 6)
    }

    /// 시작 버튼이 꺼진 이유. 켜질 수 있으면 nil
    var blocked: LocalizedStringKey? {
        if busy { return nil }
        if mode == "script" { if script.isEmpty { return "Choose a script first" } }
        else if data == nil { return "Choose a data.yaml first" }
        return env == nil ? "Choose a Python first" : nil
    }

    func step<C: View>(_ title: LocalizedStringKey, _ hint: LocalizedStringKey, symbol: String = "circle",
                               @ViewBuilder _ content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 7) {
                Image(systemName: symbol).font(.ui(13, weight: .semibold)).foregroundStyle(.tint).frame(width: 18).accessibilityHidden(true)
                Text(title).font(.ui(14, weight: .semibold))
                Image(systemName: "info.circle").font(.ui(11)).foregroundStyle(ink.soft).help(hint).accessibilityLabel(hint)   // 설명은 올리면
            }
            content()
        }
    }

}
