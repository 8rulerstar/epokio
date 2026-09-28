import Foundation

// agent의 JSON과 1:1. 필드 이름은 파이썬 Run.to_dict()와 같게 유지한다.
struct Run: Codable, Identifiable, Hashable {
    var id: String { "\(source)|\(path)" }
    let name: String
    let path: String
    let epoch: Int
    let total: Int?
    let elapsed: Double
    let eta: Double?
    let metric: Double?
    let metric_name: String
    let best: Double?
    let best_epoch: Int?
    let state: String
    let idle: Double
    var history: [Double] = []
    var source: String = "local"
    var framework: String?                          // ultralytics · huggingface · lightning · keras
    var display: String?                            // agent가 정한 보일 이름(defect_det/train). 옛 agent엔 없다
    var lower: Bool?                                // best가 낮을수록 좋은 점수인가(사람이 대표 점수를 골랐을 때). 옛 agent엔 없다
    var meta: RunMeta?                              // 사람이 붙인 별표·태그·메모·목표
    var ssh: SSHOrigin?                             // SSH 가벼운 모드로 비춰 온 학습(보기 전용)
    var format_warnings: [String]?                  // 못 알아본 열·버전. 목록에 작은 배지
    var metric_higher: Bool?                        // 대표 점수 방향(agent의 schema.py). 옛 agent는 안 보낸다
    struct SSHOrigin: Codable, Hashable { let host: String; let path: String }
    /// 대표 점수가 높을수록 좋은가. 옛 agent(필드 없음)면 열 이름으로 어림한다 (RunDetail.higher와 같은 규칙)
    var metricHigher: Bool { metric_higher ?? !metric_name.lowercased().contains("loss") }
    var frameworkName: String {
        switch framework { case "huggingface": "Hugging Face"; case "lightning": "Lightning"; case "keras": "Keras"; case "tensorboard": "TensorBoard"; case "epokio": "epokio.log"; case "custom": L("Your code"); default: "Ultralytics" }   // custom: epokio.start()로 기록한 직접 짠 학습
    }

    var progress: Double? {
        guard let t = total, t > 0 else { return nil }
        return min(Double(epoch) / Double(t), 1.0)
    }
    var isLive: Bool { state == "running" || state == "starting" }
    /// 끝까지 간 학습인가. ★진행률이 아니라 상태로 판단한다: 실패·중단은 마지막 에폭이 total에 닿아도 완료가 아니다
    var isComplete: Bool { state == "done" }
}

struct RunsPayload: Codable {
    let label: String
    let runs: [Run]
    var roots: [String]? = nil               // 이 기계가 지켜보는 폴더. 옛 agent는 안 보낸다
    var slow_roots: [String]? = nil          // 제때 못 읽은 폴더(권한 대기·끊긴 드라이브). 옛 agent는 안 보낸다
    var scan_mode: String? = nil             // auto · saver · manual(누를 때만, 알림 없음). 옛 agent는 안 보낸다
}

struct GPUInfo: Codable, Hashable {
    let name: String
    let util: Double?
    let mem_used: Double?
    let mem_total: Double?
    let temp: Double?
}

struct Snapshot: Codable {
    let host: String
    let cpu: Double?
    let mem_used: Double?
    let mem_total: Double?
    let gpus: [GPUInfo]
    var cpu_temp: Double? = nil      // °C, 애플 실리콘 맥만. 없으면 칸을 숨긴다
    var fan: Double? = nil           // % 가장 빠른 팬의 최대 대비. 팬 있는 애플 실리콘 맥만(macfan.py)
    var fan_rpm: Int? = nil
    var disk_free: Double? = nil     // GB (sysinfo). 쉬는 모드 카드가 쓴다
    var net_up: Double? = nil        // B/s
    var net_down: Double? = nil
    var battery: Double? = nil       // %
    var charging: Bool? = nil
    var ai: Double? = nil            // % AI 도구 사용량 (aiuse.py). 캐릭터 속도에만 쓴다
}

struct SystemPayload: Codable {
    let label: String
    let now: Snapshot?
    let history: [Double?]
}

/// agent `/run` 응답. 학습 상세 화면과 비교 화면이 쓴다.
struct RunExplain: Codable, Hashable {
    let text: String
    let kind: String?
    let status: String?
    let sentences: [String]?
}

/// 재현 기록(epokio_repro.json): 어떤 코드·환경·데이터로 돌렸나
struct RunRepro: Codable, Hashable {
    var partial: Bool?
    var code: Code?
    var python: PythonInfo?
    var seed: LooseStrings?                 // 숫자·참거짓이 올 수 있다(ReproValues.swift)
    var data: DataFingerprint?
    var system: LooseStrings?               // NVIDIA 기계는 gpus 가 목록이다
    struct Code: Codable, Hashable { var commit: String?; var branch: String?; var dirty: Bool?; var repo: String? }
    struct PythonInfo: Codable, Hashable { var version: String?; var path: String?; var packages: LooseStrings? }
    struct DataFingerprint: Codable, Hashable { var path: String?; var images: Int?; var listing_sha256: String? }
}

struct RunDetail: Codable, Hashable {
    var explain: RunExplain?
    var repro: RunRepro?
    var format_warnings: [String]?
    let path: String
    let name: String
    let columns: [String: [Double?]]
    let heads: [Head]
    let notes: [Note]
    let images: [String]
    let args: [String: String]
    var all_args: [String: String]?                 // args.yaml의 한 줄짜리 값 전부("다시 학습"·비교). 옛 agent엔 없다
    let weights: String?
    var last: String?                               // weights/last.pt(이어 하기). 옛 agent엔 없다
    var versions: Versions?
    var lineage: Lineage?
    var stage: String?              // candidate · production · archived (runmeta)
    var classes: RunClasses?        // 클래스별 성능(classes.py). 없으면 계산 버튼. 옛 agent엔 없다
    var snapshots: RunSnapshots?    // 에폭별 예측 사진(켠 학습만)
    var system: RunSystem?          // 학습하는 동안의 기계(sysrec.py). 옛 학습·옛 agent엔 없다
    var framework: String?

    /// 계보: 시작 가중치를 준 학습(부모)·조상 사슬·이 학습에서 시작한 학습들
    struct Lineage: Codable, Hashable {
        let weights: String?
        let parent: Link?
        let ancestors: [Link]
        let children: [Link]
        let pretrained: Bool
        struct Link: Codable, Hashable { let path: String; let name: String; var data: String? }
    }

    /// 열마다 종류·이름·머리·방향. agent의 schema.py가 만든다(앱은 열 이름을 해석하지 않는다)
    var column_info: [String: ColumnInfo]?

    struct ColumnInfo: Codable, Hashable {
        let kind: String            // loss | score | lr | other
        let name: String
        let head: String?           // Box | Pose | Mask
        let side: String?           // train | val (손실만)
        let higher: Bool
    }

    /// 화면에 쓸 열 이름. 옛 agent(column_info 없음)면 예전 규칙으로
    func label(_ k: String) -> String {
        guard let i = column_info?[k] else { return prettyColumn(k) }
        let s = i.side.map { "\($0) \(i.name)" } ?? i.name
        return i.head.map { s + " · " + L($0) } ?? s
    }
    func higher(_ k: String) -> Bool { column_info?[k]?.higher ?? !k.hasSuffix("loss") }

    /// 다시 학습·비교가 쓰는 설정. 새 agent면 전부, 옛 agent면 주요 설정만
    var trainArgs: [String: String] { (all_args?.isEmpty == false ? all_args : nil) ?? args }

    /// 가벼운 버전: 데이터·모델 지문(짧은 해시)과 같은 데이터로 학습한 다른 학습
    struct Versions: Codable, Hashable {
        let data: String?
        let model: String?
        let same_data: [Other]?
        var data_version: DataVersion?          // 같은 data.yaml의 몇 번째 버전(lineage.data_version)
        var data_now: String?                   // 학습 뒤 데이터가 바뀌었으면 지금 지문
        struct Other: Codable, Hashable { let path: String; let name: String }
        struct DataVersion: Codable, Hashable { let n: Int; let of: Int }
        var dataLabel: String? {
            guard let d = data else { return nil }
            return data_version.map { L("Data v%d of %d", $0.n, $0.of) } ?? L("Data %@", d)
        }
    }

    struct Head: Codable, Hashable {
        let head: String
        let best_epoch: Int
        let precision: Double?
        let recall: Double?
        let f1: Double?
        let map50: Double?
        let map5095: Double?
        var title: String { switch head { case "B": L("Box"); case "P": L("Pose"); case "M": L("Mask"); default: head } }
    }
    struct Note: Codable, Hashable {
        let observation: String; let `try`: String
        var next: [String: SweepSummary.Value]? = nil          // 해 볼 다음 학습(바꿀 설정). agent의 analysis.next_run
    }

    var epochs: [Double] { (columns["epoch"] ?? []).map { $0 ?? 0 } }
    /// 손실 곡선(train/·val/ …loss)과 점수 곡선(metrics/…)
    var lossKeys: [String] { columns.keys.filter { column_info?[$0].map { $0.kind == "loss" } ?? $0.hasSuffix("loss") }.sorted() }
    var scoreKeys: [String] { columns.keys.filter { column_info?[$0].map { $0.kind == "score" } ?? $0.hasPrefix("metrics/") }.sorted() }
}

/// 학습마다 다를 수밖에 없는 설정(폴더·이름·이어하기). 다시 학습에 옮기지 않고 비교에서도 뺀다(웹 AGAIN_SKIP·DIFF_SKIP와 같다)
let perRunArgs: Set<String> = ["project", "name", "exist_ok", "resume", "save_dir", "mode"]

/// 알림함 한 줄. agent 사건을 받아 맥에 쌓아 둔다(~/.epokio/inbox.json).
struct InboxItem: Codable, Identifiable, Hashable {
    let id: String            // 기계|사건번호
    let kind: String
    let runID: String         // Run.id
    let runName: String
    let machine: String
    let best: Double?
    let epoch: Int
    let total: Int?
    let date: Date
    var read = false

    var title: String {
        switch kind {
        case "finished": L("Training finished")
        case "failed": L("Training failed")
        case "stalled": L("Training may have stopped")
        case "stopped_early": L("Stopped before the last epoch")
        case "started": L("Training started")
        case "job_done": L("Job finished")
        case "job_failed": L("Job failed")
        case "goal": L("Goal reached")
        case "disk_low": L("Disk almost full")
        case "gpu_hot": L("GPU is very hot")
        case "gpu_mem": L("GPU memory is full")
        case "fan_max": L("Fans at full speed")
        default: L("Training resumed")
        }
    }
    var symbol: String {
        switch kind {
        case "finished", "job_done": "checkmark.circle.fill"
        case "failed", "job_failed": "xmark.octagon.fill"
        case "stalled": "pause.circle.fill"
        case "stopped_early": "stop.circle.fill"
        case "started": "play.circle.fill"
        case "goal": "target"
        case "disk_low": "externaldrive.badge.exclamationmark"
        case "gpu_hot": "thermometer.high"
        case "gpu_mem": "memorychip"
        case "fan_max": "fan.fill"
        default: "arrow.clockwise.circle.fill"
        }
    }
    var isMachine: Bool { ["disk_low", "gpu_hot", "gpu_mem", "fan_max"].contains(kind) }
    var isResult: Bool { ["finished", "failed", "stopped_early", "goal"].contains(kind) }
}

/// agent `runmeta` 와 같은 모양
struct RunMeta: Codable, Hashable {
    var star: Bool?
    var tags: [String]?
    var note: String?
    var goal: Double?
    var goal_hit: Bool?
    var stage: String?             // candidate · production · archived
    var collections: [String]?     // 내가 만든 모음(폴더처럼)
}
