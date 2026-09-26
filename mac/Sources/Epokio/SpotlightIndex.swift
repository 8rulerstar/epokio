@preconcurrency import CoreSpotlight
import UniformTypeIdentifiers

// Spotlight에서 학습 찾기(메모·메일처럼): ⌘스페이스로 "coco8"을 치면 그 학습이 나오고, 누르면 Studio에서 열린다.
// 목록이 실제로 바뀔 때만(이름·상태·최고 점수) 다시 올린다. 지운 학습은 빠진다.
@MainActor
enum SpotlightIndex {
    private static var last = ""
    static let domain = "io.github.8rulerstar.epokio.runs"

    static func update(_ runs: [Run]) {
        // ★도는 학습은 에폭마다 최고 점수가 바뀌어 에폭마다 전체를 다시 색인했다. 도는 동안은 점수를 빼고, 끝나면 한 번
        let key = runs.map { "\($0.id)|\($0.state)|\($0.isLive ? -1 : ($0.best ?? -1))|\($0.meta?.tags?.joined() ?? "")" }.sorted().joined(separator: ";")
        guard key != last else { return }
        last = key
        let items = runs.map { r -> CSSearchableItem in
            let a = CSSearchableItemAttributeSet(contentType: .content)
            a.title = r.displayName
            a.contentDescription = [r.stateText, r.best.map { L("best %@", String(format: "%.3f", $0)) },
                                    L("epoch %@", "\(r.epoch)/\(r.total.map(String.init) ?? "?")"), r.framework?.capitalized, r.source]
                .compactMap { $0 }.joined(separator: " · ")
            a.keywords = ["epokio", "training", r.name] + (r.meta?.tags ?? []) + [r.meta?.note ?? ""].filter { !$0.isEmpty }
            a.contentURL = URL(fileURLWithPath: r.path)
            return CSSearchableItem(uniqueIdentifier: r.id, domainIdentifier: domain, attributeSet: a)
        }
        let index = CSSearchableIndex.default()
        index.deleteSearchableItems(withDomainIdentifiers: [domain]) { _ in
            index.indexSearchableItems(items) { _ in }
        }
    }
}
