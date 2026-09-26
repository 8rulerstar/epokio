import Foundation
#if canImport(FoundationModels)
import FoundationModels
#endif

// 학습 해설을 맥 안의 Apple 모델(Foundation Models)로 짧게 다시 쓰기 (선택 기능).
// 기기 밖으로 아무것도 안 나간다. 입력은 규칙 문단과 jev_payload 같은 요약뿐, 경로·학습 이름은 넣지 않는다.
// ★사실은 입력 숫자만. 출력에 입력에 없는 숫자가 하나라도 있으면 버리고 다음 단계로 간다.
// 순서: 온디바이스(켜짐·가능) → Jev 고르기(켜짐) → 규칙 문장. 연결하는 쪽은 best(...) 하나만 부른다.

enum OnDeviceExplain {
    static let settingKey = "onDeviceExplain"

    /// 설정이 없으면 켬으로 본다(기기 밖으로 안 나가므로). 끄면 바로 다음 단계
    static var enabled: Bool {
        UserDefaults.standard.object(forKey: settingKey) as? Bool ?? true
    }

    /// text: 규칙 문단, sentences: 후보 문장, summary: jev_payload와 같은 dict, request: Jev 본문
    static func best(text: String, sentences: [String], summary: [String: Any]?,
                     request: [String: Any]?) async -> String {
        if enabled, let summary, let out = await generate(text: text, summary: summary) { return out }
        return await JevExplain.polish(text: text, sentences: sentences, request: request)
    }

    /// 모델이 없거나, 실패하거나, 숫자 검사에 걸리면 nil
    static func generate(text: String, summary: [String: Any]) async -> String? {
        #if canImport(FoundationModels)
        if #available(macOS 26.0, *) { return await Model.run(text: text, summary: summary) }
        #endif
        return nil
    }

    static func isAvailable() -> Bool {
        #if canImport(FoundationModels)
        if #available(macOS 26.0, *) { return Model.ready(lang: lang(nil)) }
        #endif
        return false
    }

    // MARK: 프롬프트 (모델과 무관하게 시험할 수 있게 밖에 둔다)

    static func lang(_ summary: [String: Any]?) -> String {
        (summary?["lang"] as? String) ?? (Locale.current.language.languageCode?.identifier == "ko" ? "ko" : "en")
    }

    /// 경로류 키는 한 번 더 걸러 낸다(explain.jev_payload가 이미 빼지만 방어)
    static let pathKeys: Set<String> = ["weights", "model", "data", "project", "name", "source"]

    static func facts(_ summary: [String: Any]) -> String {
        var lines: [String] = []
        for k in ["status", "kind"] { if let v = summary[k] { lines.append("\(k): \(v)") } }
        if let s = summary["score"] as? [String: Any] {
            lines.append("score: " + s.keys.sorted().map { "\($0)=\(s[$0]!)" }.joined(separator: ", "))
        }
        if let st = summary["settings"] as? [String: Any] {
            let kv = st.keys.sorted().filter { !pathKeys.contains($0) }.map { "\($0)=\(st[$0]!)" }
            if !kv.isEmpty { lines.append("next settings: " + kv.joined(separator: ", ")) }
        }
        return lines.joined(separator: "\n")
    }

    static func instructions(lang: String) -> String {
        let language = lang == "ko" ? "Korean (한국어)" : "English"
        return """
        You explain a finished machine learning training run to a beginner.
        Write in \(language). Be short and plain. Do not use dashes as punctuation.
        Use only facts and numbers given in the input. Never invent, round, or convert numbers.
        If a number is not in the input, do not write it.
        """
    }

    static func prompt(text: String, summary: [String: Any]) -> String {
        "Facts:\n\(facts(summary))\n\nRule-based explanation:\n\(text)\n\n"
            + "Rewrite this as a 2 to 3 sentence summary and one next step."
    }

    // MARK: 숫자 검사

    /// 글 속 숫자들. 1,000 → 1000, 0.50 → 0.5 로 맞춘다
    static func numbers(in s: String) -> Set<String> {
        let re = try! NSRegularExpression(pattern: #"\d[\d,]*(?:\.\d+)?"#)
        let ns = s as NSString
        var out = Set<String>()
        for m in re.matches(in: s, range: NSRange(location: 0, length: ns.length)) {
            var t = ns.substring(with: m.range).replacingOccurrences(of: ",", with: "")
            if t.contains(".") {
                while t.hasSuffix("0") { t.removeLast() }
                if t.hasSuffix(".") { t.removeLast() }
            }
            out.insert(t)
        }
        return out
    }

    /// 출력 숫자가 전부 입력(요약 + 규칙 문단)에 있어야 통과
    static func numbersOK(output: String, text: String, summary: [String: Any]) -> Bool {
        numbers(in: output).isSubset(of: numbers(in: text + "\n" + facts(summary)))
    }

    static func join(summary: String, nextStep: String) -> String {
        [summary, nextStep].map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }.joined(separator: " ")
    }
}

#if canImport(FoundationModels)
@available(macOS 26.0, *)
@Generable(description: "Short explanation of a finished training run")
struct OnDeviceExplanation {
    @Guide(description: "2 to 3 short sentences: the result and its main cause. Only numbers from the input.")
    var summary: String
    @Guide(description: "One sentence: the concrete next thing to try.")
    var nextStep: String
}

@available(macOS 26.0, *)
extension OnDeviceExplain {
    enum Model {
        static func ready(lang: String) -> Bool {
            let m = SystemLanguageModel.default
            guard case .available = m.availability else { return false }
            return m.supportsLocale(Locale(identifier: lang))
        }

        static func run(text: String, summary: [String: Any]) async -> String? {
            let lang = OnDeviceExplain.lang(summary)
            guard ready(lang: lang) else { return nil }
            let session = LanguageModelSession(instructions: OnDeviceExplain.instructions(lang: lang))
            let opts = GenerationOptions(temperature: 0.2, maximumResponseTokens: 300)
            guard let r = try? await session.respond(to: OnDeviceExplain.prompt(text: text, summary: summary),
                                                     generating: OnDeviceExplanation.self, options: opts)
            else { return nil }
            let out = OnDeviceExplain.join(summary: r.content.summary, nextStep: r.content.nextStep)
            guard !out.isEmpty, !out.contains("\u{2014}"),
                  OnDeviceExplain.numbersOK(output: out, text: text, summary: summary) else { return nil }
            return out
        }
    }
}
#endif
