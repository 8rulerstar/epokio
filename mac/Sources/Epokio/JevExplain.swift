import Foundation

// 학습 해설 다듬기 (선택 기능, 기본 꺼짐). Jev는 글을 쓰지 않고 고르기만 한다.
// agent의 explain 결과에 든 요청 본문(jev_request: 요약 payload + 후보 문장 + 문장별 noul)을 그대로 보내고,
// 필요한 문장만 원래 순서로 남긴다. 규칙은 src/epokio/explain.py의 jev_apply와 같다(바꾸면 둘 다).
// ★키는 키체인(typesafe.api)에서 메모리로만 읽는다. 꺼짐·키 없음·실패·답 모자람이면 규칙 문장 그대로.
// ★보내는 것: 상태·종류·점수(지표·최고값·최고 에폭·전체 에폭)·바꿀 설정 숫자·언어·후보 문장. 경로·이미지·데이터·학습 이름 없음.

enum JevExplain {
    static let maxSentences = 3          // UI에 글 너무 많지 않게
    static let keepP = 0.5

    /// text: 규칙 문장, sentences: 후보, request: agent가 만든 본문(nil이면 줄일 게 없음)
    static func polish(text: String, sentences: [String], request: [String: Any]?) async -> String {
        guard Jev.enabled, let key = Jev.key, let request else { return text }
        guard let answers = try? await Jev.post(request, key: key) else { return text }
        return apply(text: text, sentences: sentences, answers: answers)
    }

    static func apply(text: String, sentences: [String], answers: [String: [String: Any]]) -> String {
        var probs: [Double] = []
        for i in sentences.indices {
            guard let p = answers["s\(i)"]?["noul"] as? Double else { return text }
            probs.append(p)
        }
        let top = sentences.indices.sorted { probs[$0] > probs[$1] }.prefix(maxSentences)
        let keep = top.sorted().filter { probs[$0] >= keepP }
        return keep.count < 2 ? text : keep.map { sentences[$0] }.joined(separator: " ")
    }
}
