import SwiftUI

// 검수 데이터: 평가 결과(agent /jobs/<id>/eval)의 모양 · 판정 · 정렬 · 혼동 행렬 칸 거르기.

struct EvalBox: Codable, Hashable {
    let cls: Int
    let box: [Double]
    let conf: Double?
    let kpts: [[Double]]
    var poly: [[Double]]?           // 분할: 다각형 (0~1)
}
struct EvalRow: Codable, Identifiable, Hashable {
    var id: String { image }
    let image: String
    let label: String
    let tp: Int, fp: Int, fn: Int
    let f1: Double
    let kpt: Double?
    let score: Double
    let gt: [EvalBox]
    let pred: [EvalBox]
    // 다시 채점(epokio.review)이 붙인 것. 옛 결과엔 없다
    var gt_status: [String]?        // tp · fn · cls(자리는 맞고 클래스 틀림)
    var pred_status: [String]?      // tp · fp · cls
    var top: [[Double]]?            // 분류: [[클래스, 신뢰도], …]
    var truth: Int?                 // 분류: 정답 클래스
}
struct EvalResult: Codable {
    var task: String?               // detect · pose · segment · classify
    var source: String?             // 예측 파일에서 가져온 결과면 그 파일 (라벨 파일이 없다)
    let metric: String
    let images: Int
    let mean: Double
    let rows: [EvalRow]
    var conf: Double?
    var conf_floor: Double?
    var overall: Counts?
    var per_class: [ClassCounts]?
    var confusion: Confusion?
    var curve: [CurvePoint]?
    var best_conf: Double?
    var names: [String: String]?
    var official: Official?         // 같은 예측을 Ultralytics 검증 규칙으로 (epokio.review.official)
    var trained: Trained?           // 모델 학습 폴더의 results.csv 값 (학습 검증셋)

    struct Official: Codable, Hashable { var precision: Double?; var recall: Double?; var map50: Double?; var conf: Double?; var top1: Double? }
    struct Trained: Codable, Hashable { var precision: Double?; var recall: Double?; var map50: Double?; var epoch: Int? }

    struct Counts: Codable, Hashable { let tp: Int; let fp: Int; let fn: Int; let precision: Double?; let recall: Double?; let f1: Double? }
    struct ClassCounts: Codable, Hashable, Identifiable {
        var id: Int { cls }
        let cls: Int; let name: String; let support: Int
        let tp: Int; let fp: Int; let fn: Int; let precision: Double?; let recall: Double?; let f1: Double?
    }
    struct Confusion: Codable, Hashable { let labels: [String]; let classes: [Int]; let matrix: [[Int]] }
    struct CurvePoint: Codable, Hashable { let conf: Double; let precision: Double?; let recall: Double?; let f1: Double? }

    func name(_ cls: Int) -> String { names?[String(cls)] ?? "\(cls)" }
    var deep: Bool { overall != nil }
    var isClassify: Bool { task == "classify" }
    var imported: Bool { source != nil }
    /// 라벨 고치기: 검출·자세는 박스 편집, 분류는 클래스 고르기. 분할(다각형)과 가져온 예측은 아직 안 된다
    var canFix: Bool { !imported && task != "segment" }
}

/// 혼동 행렬 칸 하나로 이미지 거르기: 정답 클래스 g, 예측 클래스 p (-1 = 배경)
struct ConfusionCell: Hashable { let g: Int; let p: Int }

extension EvalRow {
    func has(_ c: ConfusionCell) -> Bool {
        let gs = gt_status ?? [], ps = pred_status ?? []
        let gHit = { (want: String) in zip(gt, gs).contains { $0.cls == c.g && $1 == want } }
        let pHit = { (want: String) in zip(pred, ps).contains { $0.cls == c.p && $1 == want } }
        if c.p == -1 { return gHit("fn") }
        if c.g == -1 { return pHit("fp") }
        if c.g == c.p { return gHit("tp") }
        return gHit("cls") && pHit("cls")
    }
    func hasClass(_ cls: Int) -> Bool { gt.contains { $0.cls == cls } || pred.contains { $0.cls == cls } }
}

enum Verdict: String, CaseIterable {
    case model = "model_wrong", label = "label_wrong", unsure = "unsure", ok = "ok"
    var title: LocalizedStringKey {
        switch self { case .model: "Model is wrong"; case .label: "Label is wrong"; case .unsure: "Not sure"; case .ok: "Looks right" }
    }
    var titleResource: String.LocalizationValue {
        switch self { case .model: "Model is wrong"; case .label: "Label is wrong"; case .unsure: "Not sure"; case .ok: "Looks right" }
    }
    var key: Character { switch self { case .model: "1"; case .label: "2"; case .unsure: "3"; case .ok: "4" } }
    var color: Color { switch self { case .model: .bad; case .label: .warn; case .unsure: .gold; case .ok: .good } }
    var symbol: String { switch self { case .model: "cpu"; case .label: "tag"; case .unsure: "questionmark"; case .ok: "checkmark" } }
}

enum ReviewSort: CaseIterable {
    case lowest, highest, unreviewedFirst, reviewedFirst
    var title: LocalizedStringKey {
        switch self {
        case .lowest: "Lowest score first"; case .highest: "Highest score first"
        case .unreviewedFirst: "Not reviewed first"; case .reviewedFirst: "Reviewed first"
        }
    }
}

/// 필터 칩: 이름 + 개수. 켜지면 색이 찬다
