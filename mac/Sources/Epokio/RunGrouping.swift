import SwiftUI

// 학습 기록을 묶어 보는 방법. 학습이 수백 개가 되어도 찾을 수 있게, 파일 시스템처럼 접었다 펴는 나무로 보인다.
//  · 최근(지금·오늘·어제·이번 주·이전) · 날짜(연 › 월 › 일) · 폴더(디스크의 실제 폴더 구조) · 내 모음
//  · 작업(검출·분할…) · 데이터셋 · 모델 · 프레임워크 · 기계 · 태그

enum RunGroupBy: String, CaseIterable, Identifiable {
    case recent, date, folder, collection, task, dataset, model, framework, machine, tag
    var id: String { rawValue }
    var title: String {
        switch self {
        case .recent: L("Recent"); case .date: L("Date"); case .folder: L("Folders on disk"); case .collection: L("My collections")
        case .task: L("Task"); case .dataset: L("Dataset"); case .model: L("Model"); case .framework: L("Framework")
        case .machine: L("Machine"); case .tag: L("Tag")
        }
    }
    var symbol: String {
        switch self {
        case .recent: "clock"; case .date: "calendar"; case .folder: "folder"; case .collection: "rectangle.stack"
        case .task: "square.grid.2x2"; case .dataset: "cylinder"; case .model: "cube"; case .framework: "shippingbox"
        case .machine: "server.rack"; case .tag: "number"
        }
    }
}

/// 나무의 한 마디: 아래 마디들과 이 마디에 바로 든 학습
struct RunNode: Identifiable, Hashable {
    let id: String
    var title: String
    var symbol: String
    var children: [RunNode] = []
    var runs: [Run] = []
    var count: Int { runs.count + children.reduce(0) { $0 + $1.count } }

    /// 이 묶음에 든 학습 전부(자식 포함)
    var allRuns: [Run] { runs + children.flatMap(\.allRuns) }

    /// 이 묶음의 지표 방향. 지표가 섞여 있으면 nil = 견줄 수 없다
    var metricHigher: Bool? {
        let named = allRuns.filter { $0.best != nil }
        guard let first = named.first else { return nil }
        guard named.allSatisfy({ $0.metric_name == first.metric_name }) else { return nil }
        return first.metricHigher
    }

    /// 묶음의 최고. ★낮을수록 좋은 지표(loss·rmse)에서 max를 쓰면 제일 나쁜 값을 "최고"로 보였다.
    ///   지표가 섞인 묶음은 견줄 수 없으므로 아무것도 안 보인다
    var best: Double? {
        guard let higher = metricHigher else { return nil }
        let vs = allRuns.compactMap(\.best)
        return higher ? vs.max() : vs.min()
    }
}

enum RunTree {
    /// runs → 나무. args는 표 API의 설정(작업·데이터·모델 묶기에)
    static func build(_ runs: [Run], by: RunGroupBy, args: [String: [String: String]], recent: ([Run]) -> [(String, [Run])]) -> [RunNode] {
        let sorted = runs.sorted { ($0.isLive ? 0 : 1, $0.idle) < ($1.isLive ? 0 : 1, $1.idle) }
        switch by {
        case .recent:
            return recent(runs).map { RunNode(id: "r:" + $0.0, title: $0.0, symbol: "clock", runs: $0.1) }
        case .date:
            return dateTree(sorted)
        case .folder:
            return folderTree(sorted)
        case .collection:
            var groups: [String: [Run]] = [:]
            for r in sorted {
                let cs = r.meta?.collections ?? []
                for c in cs.isEmpty ? [""] : cs { groups[c, default: []].append(r) }
            }
            return groups.keys.sorted { ($0.isEmpty ? 1 : 0, $0) < ($1.isEmpty ? 1 : 0, $1) }.map { k in
                RunNode(id: "c:" + k, title: k.isEmpty ? L("Not in a collection") : k, symbol: k.isEmpty ? "tray" : "rectangle.stack", runs: groups[k]!)
            }
        case .tag:
            var groups: [String: [Run]] = [:]
            for r in sorted { for t in (r.meta?.tags ?? []).isEmpty ? [""] : r.meta!.tags! { groups[t, default: []].append(r) } }
            return groups.keys.sorted { ($0.isEmpty ? 1 : 0, $0) < ($1.isEmpty ? 1 : 0, $1) }.map { k in
                RunNode(id: "t:" + k, title: k.isEmpty ? L("No tag") : "#" + k, symbol: "number", runs: groups[k]!)
            }
        default:
            func key(_ r: Run) -> String {
                let a = args[r.path] ?? [:]
                switch by {
                case .task: return a["task"] ?? ""
                case .dataset: return a["data"] ?? ""
                case .model: return a["model"] ?? ""
                case .framework: return r.frameworkName
                case .machine: return r.source
                default: return ""
                }
            }
            let groups = Dictionary(grouping: sorted, by: key)
            return groups.keys.sorted { ($0.isEmpty ? 1 : 0, $0) < ($1.isEmpty ? 1 : 0, $1) }.map { k in
                RunNode(id: "\(by.rawValue):" + k, title: k.isEmpty ? L("Unknown") : k, symbol: by.symbol, runs: groups[k]!)
            }
        }
    }

    /// 연 › 월 › 일. 마지막으로 바뀐 날 기준(도는 학습은 오늘)
    static func dateTree(_ runs: [Run]) -> [RunNode] {
        let cal = Calendar.current, now = Date()
        let month = DateFormatter(); month.setLocalizedDateFormatFromTemplate("LLLL")
        let day = DateFormatter(); day.setLocalizedDateFormatFromTemplate("MMMdEEE")
        var years: [Int: [Int: [Int: [Run]]]] = [:]
        var dates: [Int: Date] = [:]
        for r in runs {
            let d = now.addingTimeInterval(-r.idle)
            let c = cal.dateComponents([.year, .month, .day], from: d)
            years[c.year!, default: [:]][c.month!, default: [:]][c.day!, default: []].append(r)
            dates[c.year! * 10_000 + c.month! * 100 + c.day!] = d
        }
        return years.keys.sorted(by: >).map { y in
            RunNode(id: "y:\(y)", title: String(y), symbol: "calendar", children: years[y]!.keys.sorted(by: >).map { m in
                let anyDay = dates.first { $0.key / 100 == y * 100 + m }!.value
                return RunNode(id: "m:\(y)-\(m)", title: month.string(from: anyDay), symbol: "calendar", children: years[y]![m]!.keys.sorted(by: >).map { d in
                    let date = dates[y * 10_000 + m * 100 + d]!
                    let title = cal.isDateInToday(date) ? L("Today") : cal.isDateInYesterday(date) ? L("Yesterday") : day.string(from: date)
                    return RunNode(id: "d:\(y)-\(m)-\(d)", title: title, symbol: "calendar.day.timeline.left", runs: years[y]![m]![d]!)
                })
            })
        }
    }

    /// 디스크의 폴더 구조. 모든 학습에 공통인 앞부분은 떼고, 가지가 하나뿐인 폴더는 이어 붙인다(a/b/c)
    static func folderTree(_ runs: [Run]) -> [RunNode] {
        let bySource = Dictionary(grouping: runs, by: \.source)
        var out: [RunNode] = []
        for (src, rs) in bySource.sorted(by: { $0.key < $1.key }) {
            let parts = rs.map { Array(URL(fileURLWithPath: $0.path).deletingLastPathComponent().pathComponents) }
            var common = parts.first ?? []
            for p in parts.dropFirst() { common = Array(zip(common, p).prefix { $0.0 == $0.1 }.map(\.0)) }
            if common.count == (parts.first?.count ?? 0), !common.isEmpty { common.removeLast() }   // 한 폴더에 다 있으면 그 폴더 이름은 남긴다
            final class Dir { var subs: [String: Dir] = [:]; var runs: [Run] = [] }
            let root = Dir()
            for (r, p) in zip(rs, parts) {
                var d = root
                for c in p.dropFirst(common.count) { d = d.subs[c] ?? { let n = Dir(); d.subs[c] = n; return n }() }
                d.runs.append(r)
            }
            func node(_ name: String, _ d: Dir, _ path: String) -> RunNode {
                var name = name, d = d, path = path
                while d.runs.isEmpty, d.subs.count == 1, let (k, v) = d.subs.first {       // 가지 하나뿐이면 이어 붙인다
                    name += "/" + k; path += "/" + k; d = v
                }
                return RunNode(id: "f:\(src):\(path)", title: name, symbol: "folder",
                               children: d.subs.keys.sorted().map { node($0, d.subs[$0]!, path + "/" + $0) }, runs: d.runs)
            }
            let top = node(bySource.count > 1 ? src : (common.last ?? "/"), root, common.joined(separator: "/"))
            out.append(contentsOf: bySource.count > 1 || !top.runs.isEmpty ? [top] : top.children)
        }
        return out
    }
}
