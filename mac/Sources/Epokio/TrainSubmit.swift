import SwiftUI
import UniformTypeIdentifiers

// 학습 화면의 동작: 값 해석 · 파일 고르기 · 파이썬·설정표 불러오기 · 대기열에 넣기(한 번 또는 스윕).

/// "다시 학습"을 누른 run의 경로. 채워져 있으면 양식이 args.yaml 전체를 받아 온다(없으면 예전처럼 args 몇 개만)
/// ★RunActions의 "다시 학습" 버튼이 pendingTrainArgs보다 먼저 채운다. resume이면 진짜 재개(last.pt)
@MainActor enum RetrainRequest {
    static var path: String?
    static var resume = false
}

/// 다시 학습·재개 요청 본문(agent POST /retrain/args, retrain_args.py). 양식과 Siri(RetrainIntent)가 같이 쓴다
enum RetrainBody {
    static func fetch(_ client: AgentClient, path: String, resume: Bool = false) async throws -> [String: Any] {
        try await client.post("retrain/args", ["path": path, "mode": resume ? "resume" : "same"])
    }
}

/// 입력칸 글자를 JSON 값으로. ★"None"이 문자열로 넘어가 device="None" 같은 값이 됐다 → null. 리스트도 리스트로
func typedValue(_ v: String) -> Any {
    let t = v.trimmingCharacters(in: .whitespaces)
    if ["None", "none", "null", "~"].contains(t) { return NSNull() }
    if t == "true" || t == "True" { return true }
    if t == "false" || t == "False" { return false }
    if let i = Int(t) { return i }
    if let d = Double(t) { return d }
    if t.hasPrefix("["), let d = t.data(using: .utf8), let a = try? JSONSerialization.jsonObject(with: d) as? [Any] { return a }
    return v
}

extension TrainView {
    func typed(_ v: String) -> Any { typedValue(v) }

    func clearInherited() {
        inherited = [:]; inheritedFrom = ""; inheritedKept = 0; inheritedModel = nil; inheritedDropped = [:]; resumeParams = nil
    }

    /// 원래 run의 설정 전체를 받아 둔다. 양식 칸(데이터·작업·에폭·모델)은 양식 값이 이긴다
    func loadRetrain(_ path: String, resume: Bool) async {
        let from = URL(fileURLWithPath: path).lastPathComponent
        do {
            let r = try await RetrainBody.fetch(client, path: path, resume: resume)
            withAnimation(Motion.change) {
                inheritedFrom = from
                if resume { resumeParams = r["params"] as? [String: Any]; status = nil; return }
                var p = r["params"] as? [String: Any] ?? [:]
                for k in ["data", "task", "epochs", "model"] { p[k] = nil }
                inherited = p
                inheritedKept = (r["kept"] as? [String])?.count ?? p.count
                inheritedDropped = r["dropped"] as? [String: String] ?? [:]
                if r["model_ok"] as? Bool == true { inheritedModel = r["model"] as? String }
                status = inheritedModel == nil
                    ? L("The original model %@ is not on this Mac. Pick a model size, then start.", r["model"] as? String ?? "?")
                    : nil
            }
        } catch {
            withAnimation { status = error.localizedDescription }
        }
    }

    func pick() {
        let p = NSOpenPanel()
        p.allowedContentTypes = [UTType(filenameExtension: "yaml")!, UTType(filenameExtension: "yml")!]
        p.message = String(localized: "Choose your dataset's data.yaml")
        if p.runModal() == .OK { data = p.url }
    }

    func load() async {
        struct R: Decodable { let envs: [PyEnv] }
        do {
            let r: R = try await client.get("pythons")
            envs = r.envs
            env = r.envs.first(where: \.ready) ?? r.envs.first
            loadError = nil
        } catch {
            loadError = error.localizedDescription           // ★조용히 '파이썬 설치' 카드를 보여 원인과 상관없는 설치를 권했다
        }
    }

    func loadSchema() async {
        guard let env else { return }
        if let s: SchemaPayload = try? await client.get("schema", ["python": env.path, "mode": "train"]) {
            withAnimation { fields = s.fields ?? [] }
        }
    }

    func start(anyway: Bool = false) async {
        guard let env else { return }
        if let rp = resumeParams {                         // 진짜 재개: 원래 폴더·옵티마이저·에폭에서 이어서
            busy = true; defer { busy = false }
            nonisolated(unsafe) let body: [String: Any] = ["kind": "train", "name": inheritedFrom + "_resume", "python": env.path, "params": rp]
            do { try await client.post("jobs", body); withAnimation { status = L("Added to queue") } }
            catch { withAnimation { status = error.localizedDescription } }
            return
        }
        guard let data else { return }
        busy = true; defer { busy = false }
        // ★원격이면 적은 글자 그대로 보낸다. URL(fileURLWithPath: "D:\\...")는 맥에서 현재 폴더 기준 경로가 되어
        //   윈도우 agent가 데이터를 못 찾았다
        var dataArg = remote ? remotePath : (data.absoluteString == "coco8.yaml" ? "coco8.yaml" : data.path)
        // 출발 전 점검: 데이터에 진짜 오류가 있으면 대기열에 넣기 전에 막는다. coco8.yaml 같은 내장 이름은 경로만 본다
        if !anyway && dataArg.contains(where: { $0 == "/" || $0 == "\\" }) {
            withAnimation { status = L("Checking the data first…") }
            let (errs, found) = await preflight(dataArg)
            withAnimation(.smooth) { preflightErrors = errs; status = nil }
            if !errs.isEmpty { return }
            if let found, !found.isEmpty { dataArg = found }        // 폴더를 적었으면 그 안에서 찾은 data.yaml로
        }
        withAnimation(.smooth) { preflightErrors = [] }
        var params: [String: Any] = inherited               // 다시 학습이면 원래 설정 전체(증강·freeze·device…)
        let picked = "yolo11\(size)\(task == "detect" ? "" : "-" + (task == "segment" ? "seg" : task == "classify" ? "cls" : "pose")).pt"
        params["data"] = dataArg; params["model"] = inheritedModel ?? picked; params["epochs"] = Int(epochs); params["task"] = task
        for (k, v) in overrides { params[k] = typed(v) }
        if snapshots { params["epokio_snapshots"] = 5 }        // 학습 틀이 빼서 쓴다(ultralytics에는 안 넘어간다)
        // 기본 이름 = 데이터 폴더 이름. 윈도우 경로의 \ 도 나눈다(맥 URL은 \ 를 글자로 본다)
        let parts = dataArg.split(whereSeparator: { $0 == "/" || $0 == "\\" }).map(String.init)
        let base = name.isEmpty ? (dataArg == "coco8.yaml" ? "sample" : (parts.count >= 2 ? parts[parts.count - 2] : "train")) : name
        // 스윕이면 값마다 하나씩. 이름에 바꾼 값을 붙여 비교할 때 알아보게 한다
        func apply(_ p: inout [String: Any], _ key: String, _ v: String) {
            if key == "model" { p["model"] = picked.replacingOccurrences(of: "yolo11\(size)", with: "yolo11\(v)") }
            else { p[key] = typed(v) }
        }
        // 스윕은 agent가 펼치고 묶는다(POST /sweeps). 결과는 대기열 화면의 스윕 칸에서 비교한다
        if sweep {
            var space: [[String: Any]] = []
            if sweepMode != "grid" {                      // 무작위·똑똑하게: 범위 하나
                guard let lo = Double(randLow), let hi = Double(randHigh), lo < hi else {
                    withAnimation { status = L("Give a range where the low value is smaller than the high value.") }; return
                }
                space = [["key": randKey, "low": lo, "high": hi, "log": randLog, "int": ["imgsz", "batch", "epochs"].contains(randKey)]]
                for r in extraSpace where r.key != randKey {       // 더 넣은 설정(범위·목록 섞기)
                    let (sp, why) = r.space()
                    guard let sp else { withAnimation { status = "\(r.key): " + (why ?? "") }; return }
                    space.append(sp)
                }
            } else {
                space = [["key": sweepKey, "values": sweepValueList]]
                if sweep2 && !sweepValueList2.isEmpty && sweepKey2 != sweepKey { space.append(["key": sweepKey2, "values": sweepValueList2]) }
            }
            var sweepBody: [String: Any] = ["name": base, "python": env.path, "base": params, "space": space, "mode": sweepMode,
                                            "trials": Int(randTrials), "prune": prune, "prune_at": pruneAt]
            if !secondGoal.isEmpty { sweepBody["second"] = secondGoal }
            let others = sweepMachines.filter { $0.on && !$0.python.isEmpty }
            if !others.isEmpty {                               // 여러 기계: 이 맥 + 고른 원격들. 토큰은 먼저 agent 메모리로
                sweepBody["machines"] = [["url": "local", "python": env.path, "data": params["data"] ?? ""]]
                    + others.map { ["url": $0.url.hasSuffix("/") ? String($0.url.dropLast()) : $0.url, "python": $0.python, "data": $0.data] }
                store.pushRemoteTokens(force: true)
                try? await Task.sleep(for: .milliseconds(300))
            }
            nonisolated(unsafe) let body = sweepBody
            do {
                let r = try await client.post("sweeps", body)
                Trophies.shared.bump("sweep"); if sweepMode == "smart" { Trophies.shared.bump("smart_sweep") }
                withAnimation { status = L("%d runs added to queue", r["runs"] as? Int ?? 0) }
                store.say(L("Sweep queued. Compare the results in Queue."))
            } catch { withAnimation { status = error.localizedDescription } }
            return
        }
        // 한 설정이면 값마다, 두 설정이면 모든 조합(격자)
        var variants: [(String, [String: Any])] = [(base, params)]
        if sweep && !sweepValueList.isEmpty {
            variants = sweepValueList.map { v in var p = params; apply(&p, sweepKey, v); return ("\(base)_\(sweepKey)=\(v)", p) }
            if sweep2 && !sweepValueList2.isEmpty && sweepKey2 != sweepKey {
                variants = variants.flatMap { n, p in
                    sweepValueList2.map { v in var q = p; apply(&q, sweepKey2, v); return ("\(n)_\(sweepKey2)=\(v)", q) }
                }
            }
        }
        do {
            for (n, p) in variants {
                nonisolated(unsafe) let body: [String: Any] = ["kind": "train", "name": n, "python": env.path, "params": p]
                try await client.post("jobs", body)
            }
            withAnimation { status = variants.count > 1 ? L("%d runs added to queue", variants.count) : L("Added to queue") }
        } catch {
            withAnimation { status = error.localizedDescription }
        }
    }
}
