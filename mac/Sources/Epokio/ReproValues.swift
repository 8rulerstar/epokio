import Foundation

/// 재현 기록(epokio_repro.json)의 seed·system·packages 처럼 값이 문자열이 아닐 수도 있는 사전.
/// 숫자·참거짓은 글자로, 목록·사전은 읽을 수 있게 펼친다. 화면은 예전처럼 `값["키"]` 로 읽는다.
/// ★[String: String] 으로 읽었더니 값 하나(seed_default: true, seed: 42, NVIDIA 기계의 gpus 목록)에
///   학습 상세 전체가 안 열렸다. 이 앱의 학습 버튼으로 seed 없이 시작한 학습이 전부 그랬다
struct LooseStrings: Codable, Hashable {
    var values: [String: String]

    subscript(key: String) -> String? { values[key] }

    init(_ values: [String: String] = [:]) { self.values = values }

    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: AnyKey.self)
        var out: [String: String] = [:]
        for k in c.allKeys {
            // 한 칸을 못 읽어도 나머지는 살린다(앱보다 새 agent 가 모르는 모양을 보낼 수 있다)
            if let v = try? c.decode(LooseValue.self, forKey: k), !v.text.isEmpty { out[k.stringValue] = v.text }
        }
        values = out
    }

    func encode(to e: Encoder) throws { try values.encode(to: e) }
}

/// 아무 JSON 값이나 받아 한 줄 글자로
private indirect enum LooseValue: Decodable {
    case text(String), list([LooseValue]), object([String: LooseValue]), none

    init(from d: Decoder) throws {
        let c = try d.singleValueContainer()
        if c.decodeNil() { self = .none }
        else if let b = try? c.decode(Bool.self) { self = .text(b ? "true" : "false") }
        else if let n = try? c.decode(Double.self) {
            self = .text(n == n.rounded() && abs(n) < 1e15 ? String(Int64(n)) : String(n))
        }
        else if let s = try? c.decode(String.self) { self = .text(s) }
        else if let a = try? c.decode([LooseValue].self) { self = .list(a) }
        else if let o = try? c.decode([String: LooseValue].self) { self = .object(o) }
        else { self = .none }
    }

    var text: String {
        switch self {
        case .text(let s): return s
        case .none: return ""
        case .list(let a): return a.map(\.text).filter { !$0.isEmpty }.joined(separator: ", ")
        case .object(let o):
            // GPU 한 장({name, driver})처럼 이름이 있으면 이름을 앞에
            if let name = o["name"]?.text, !name.isEmpty {
                let rest = o.filter { $0.key != "name" }.sorted { $0.key < $1.key }
                    .map { "\($0.key) \($0.value.text)" }.filter { !$0.hasSuffix(" ") }
                return rest.isEmpty ? name : name + " (" + rest.joined(separator: ", ") + ")"
            }
            return o.sorted { $0.key < $1.key }.map { "\($0.key) \($0.value.text)" }.joined(separator: ", ")
        }
    }
}

private struct AnyKey: CodingKey {
    var stringValue: String
    var intValue: Int? { nil }
    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { nil }
}
