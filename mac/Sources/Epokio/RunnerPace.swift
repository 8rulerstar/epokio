import Foundation

/// 메뉴바 캐릭터 속도를 어디서 받을지. 학습이 없는 날에도 캐릭터가 CPU·GPU 사용률로 달리게 한다(RunCat처럼).
/// UserDefaults 키 `barPaceSource`. 값: "train"(기본) · "idleCPU" · "cpu" · "idleGPU" · "aiUse"
enum PaceSource: String, CaseIterable, Identifiable {
    case train, idleCPU, cpu, idleGPU, aiUse
    var id: String { rawValue }
    static let key = "barPaceSource"
    static var current: PaceSource { PaceSource(rawValue: UserDefaults.standard.string(forKey: key) ?? "") ?? .train }

    /// 실제로 쓸 출처. 사용자가 설정에서 고른 적이 있으면(키가 저장돼 있으면) 그 값을 그대로 따른다.
    /// 고른 적이 없고 쉬는 모드(RestMode, 학습 기록 0개)면 idleCPU, 아니면 train.
    /// `stored`는 UserDefaults 원래 값(nil = 저장된 적 없음). @AppStorage는 기본값을 돌려주므로 구분이 안 된다
    static func effective(stored: String?, resting: Bool) -> PaceSource {
        if let stored, let chosen = PaceSource(rawValue: stored) { return chosen }
        return resting ? .idleCPU : .train
    }

    /// 지금 UserDefaults 기준의 실제 출처
    static func effectiveNow(resting: Bool) -> PaceSource {
        effective(stored: UserDefaults.standard.string(forKey: key), resting: resting)
    }

    /// 설정에 보일 이름. 영어 원문이 Localizable.strings의 키다(L()로 감싸야 키 추출기가 본다)
    var title: String {
        switch self {
        case .train: return L("Training progress")
        case .idleCPU: return L("CPU when nothing is training")
        case .cpu: return L("CPU always")
        case .idleGPU: return L("GPU when nothing is training")
        case .aiUse: return L("AI tool use")
        }
    }
}

enum RunnerPace {
    /// 이 사용률(%) 미만이면 멈춘다. 쉬는 맥의 잔잔한 1~3%에 캐릭터가 꼼지락대지 않게
    static let stopBelow = 5.0

    /// 사용률(0~100%) → 속도(0 = 멈춤, 1~6 = Run.speed와 같은 눈금).
    /// 5% 미만은 0. 5%에서 1, 100%에서 6. 제곱근 곡선이라 낮은 구간에서 변화가 잘 보이고 높은 구간은 완만하다.
    /// 연속 함수라 사용률이 조금 흔들려도 속도가 한 칸씩 튀지 않는다. 범위 밖·NaN은 잘라 낸다
    static func speed(utilization u: Double?) -> Double {
        guard let u, u.isFinite else { return 0 }
        let c = min(max(u, 0), 100)
        guard c >= stopBelow else { return 0 }
        return 1 + 5 * ((c - stopBelow) / (100 - stopBelow)).squareRoot()
    }

    /// 지금 캐릭터에 쓸 속도. training = 학습 속도(0이면 학습 없음), cpu·gpu·ai = 사용률(%)
    /// ai는 agent가 보내는 AI 도구 사용량(aiuse.py). 값이 없으면(nil) 멈춘다 = 끊긴 값으로 달리지 않는다
    static func pace(_ source: PaceSource, training: Double, cpu: Double?, gpu: Double?, ai: Double? = nil) -> Double {
        switch source {
        case .train: return training
        case .cpu: return speed(utilization: cpu)
        case .idleCPU: return training > 0 ? training : speed(utilization: cpu)
        case .idleGPU: return training > 0 ? training : speed(utilization: gpu)   // GPU 값이 없으면(nil) 멈춤
        case .aiUse: return training > 0 ? training : speed(utilization: ai)      // 학습이 우선, 없으면 AI 사용량
        }
    }

}
