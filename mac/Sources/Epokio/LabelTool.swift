import SwiftUI
import CryptoKit

// 라벨링 툴 1차(박스). 라벨 보기(DatasetView)에서 그림을 열고 E로 고친다. 화면은 LabelViewer.swift
// 진행 상태 넷: ✓ 사람이 본 박스 · 지팡이 기계가 만든 박스(아직 확인 안 함) · ○ 봤고 없음(N키) · · 아직 안 봄.
// ★빈 .txt만으로는 "봤는데 없다"와 "그냥 넘겼다"를 구분 못 한다(실제 검수에서 빈 파일 291장이 전부 완료로 보였다). 그래서 N 표시를 따로 둔다.
// ★자동 라벨(labels_auto)도 같은 문제다. 박스가 있다고 사람이 확인한 것은 아니다. 그래서 확인(V) 표시를 따로 둔다.
// 진행 상태는 ~/.epokio/label_state/ 에만 쓴다. 데이터 폴더에는 라벨 .txt 말고 아무것도 쓰지 않는다.
// 처음 고치는 라벨 파일은 ~/.epokio/label_backup/ 에 원본을 한 번 복사해 둔다.

enum LabelStatus { case boxes, auto, checkedEmpty, unseen
    var symbol: String {
        switch self {
        case .boxes: "checkmark.circle.fill"
        case .auto: "wand.and.stars"
        case .checkedEmpty: "circle"
        case .unseen: "circle.dotted"
        }
    }
    var tint: Color { switch self { case .boxes: .good; case .auto: .warn; case .checkedEmpty: .info; case .unseen: .secondary } }
    var title: String {
        switch self {
        case .boxes: L("Has boxes")
        case .auto: L("Boxes from a model, not checked yet")
        case .checkedEmpty: L("Checked, nothing to label")
        case .unseen: L("Not checked yet")
        }
    }
}

/// 디스크에 남는 진행 상태. ★예전 판은 Set 하나만 적었다: 그 파일도 그대로 읽는다
private struct LabelStateFile: Codable {
    var checked: Set<String> = []
    var verified: Set<String> = []
}

@MainActor @Observable
final class LabelProgress {
    private(set) var checked: Set<String> = []          // 봤고 박스 없음(N). 키는 폴더 포함 상대 경로(NFC)
    private(set) var verified: Set<String> = []         // 기계가 만든 박스를 사람이 확인함(V)
    private var file: URL?
    private var root: URL?
    private static let home = FileManager.default.homeDirectoryForCurrentUser.appending(path: ".epokio")

    func open(_ root: URL) {
        self.root = root
        let key = SHA256.hash(data: Data(root.path.utf8)).prefix(8).map { String(format: "%02x", $0) }.joined()
        file = Self.home.appending(path: "label_state/\(key).json")
        let data = (try? Data(contentsOf: file!)) ?? Data()
        if let s = try? JSONDecoder().decode(LabelStateFile.self, from: data) {
            checked = s.checked; verified = s.verified
        } else {                                        // 옛 파일: Set 하나뿐
            checked = (try? JSONDecoder().decode(Set<String>.self, from: data)) ?? []
            verified = []
        }
    }

    /// ★파일 이름만 쓰면 train/0001.jpg와 val/0001.jpg가 같은 것이 된다(둘 다 한 번에 ○로 바뀜)
    func key(_ it: LabeledImage) -> String {
        let base = root?.path ?? ""
        let p = it.id.path
        return Dataset.nfc(p.hasPrefix(base) ? String(p.dropFirst(base.count)) : p)
    }

    func status(_ it: LabeledImage, boxes: Int) -> LabelStatus {
        guard boxes > 0 else { return checked.contains(key(it)) ? .checkedEmpty : .unseen }
        return LabelProgress.isAuto(it) && !verified.contains(key(it)) ? .auto : .boxes
    }

    func isVerified(_ it: LabeledImage) -> Bool { verified.contains(key(it)) }

    func toggleChecked(_ it: LabeledImage) {
        let k = key(it)
        if checked.contains(k) { checked.remove(k) } else { checked.insert(k) }
        write()
    }

    func setVerified(_ it: LabeledImage, _ on: Bool) {
        let k = key(it)
        if on { verified.insert(k) } else { verified.remove(k) }
        write()
    }

    private func write() {
        guard let file else { return }
        try? FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? JSONEncoder().encode(LabelStateFile(checked: checked, verified: verified)).write(to: file, options: .atomic)
    }

    /// 사람이 고친 라벨을 쓸 자리.
    /// ★기계가 만든 라벨(labels_auto)을 고칠 때 그 폴더에 쓰면, 학습이 읽는 진짜 라벨은 그대로 남아 하루치 작업이 헛일이 된다.
    ///   그래서 auto 라벨을 고치면 images/ ↔ labels/ 짝(사람 라벨 자리)에 쓴다
    static func labelURL(for it: LabeledImage) -> URL {
        if let l = it.label, !l.path.contains("/labels_auto/") { return l }
        var parts = it.id.deletingPathExtension().pathComponents
        if let k = parts.lastIndex(of: "images") { parts[k] = "labels" }
        return URL(fileURLWithPath: NSString.path(withComponents: parts)).appendingPathExtension("txt")
    }

    /// 지금 보고 있는 라벨을 누가 만들었나
    static func isAuto(_ it: LabeledImage) -> Bool { it.label?.path.contains("/labels_auto/") ?? false }

    /// YOLO 한 줄씩 저장. 처음이면 원본을 백업. 쓴 파일 주소
    static func save(_ boxes: [EditBox], for it: LabeledImage) throws -> URL {
        let url = labelURL(for: it)
        let fm = FileManager.default
        if fm.fileExists(atPath: url.path) {
            let key = SHA256.hash(data: Data(url.path.utf8)).prefix(8).map { String(format: "%02x", $0) }.joined()
            let bak = home.appending(path: "label_backup/\(key)_\(url.lastPathComponent)")
            if !fm.fileExists(atPath: bak.path) {                 // ★백업이 실패했는데 덮어쓰면 원본이 사라진다: 여기서 멈춘다
                try fm.createDirectory(at: bak.deletingLastPathComponent(), withIntermediateDirectories: true)
                try fm.copyItem(at: url, to: bak)
            }
        }
        try fm.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let text = boxes.map { b in "\(b.cls) " + b.box.map { String(format: "%.6f", $0) }.joined(separator: " ") }.joined(separator: "\n")
        try (text.isEmpty ? "" : text + "\n").write(to: url, atomically: true, encoding: .utf8)
        return url
    }
}

extension Dataset {
    /// 저장한 뒤: 그 그림의 라벨 주소와 캐시를 새로
    func replaceLabel(_ it: LabeledImage, url: URL) {
        cache[url] = nil
        if let i = items.firstIndex(where: { $0.id == it.id }) { items[i] = LabeledImage(id: it.id, label: url) }
    }
}
