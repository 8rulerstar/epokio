import SwiftUI
import ImageIO
import UniformTypeIdentifiers

// 라벨 보기. 이미지 위에 YOLO 박스(와 포즈 키포인트)를 겹쳐 본다.
// 초보자가 라벨을 확인하려고 별도 툴을 켜던 일을 없앤다.
//
// 짝짓기: images/ ↔ labels/, 같은 폴더의 .txt, 오토라벨링 결과 labels_auto/*/labels/
// ★파일명은 NFC로 맞춰 비교한다. 맥 폴더는 NFD일 수 있어 그냥 비교하면 조용히 전부 어긋난다

struct YoloBox: Hashable {
    let cls: Int
    let cx, cy, w, h: Double
    let conf: Double?
    let kpts: [(Double, Double, Double)]
    static func == (a: YoloBox, b: YoloBox) -> Bool { a.cls == b.cls && a.cx == b.cx && a.cy == b.cy }
    func hash(into h: inout Hasher) { h.combine(cls); h.combine(cx); h.combine(cy) }
}

struct LabeledImage: Identifiable, Hashable {
    let id: URL
    let label: URL?
    var name: String { id.lastPathComponent }
}

@MainActor @Observable
final class Dataset {
    var root: URL?
    var items: [LabeledImage] = []
    var classes: [Int: String] = [:]
    var cache: [URL: [YoloBox]] = [:]
    var loading = false

    nonisolated static let imageExts: Set<String> = ["jpg", "jpeg", "png", "bmp", "webp", "tif", "tiff"]

    func open(_ url: URL) async {
        root = url; loading = true; defer { loading = false }
        let (items, classes) = await Task.detached { Dataset.scan(url) }.value
        self.items = items; self.classes = classes; cache = [:]
    }

    func boxes(_ it: LabeledImage) -> [YoloBox] {
        guard let l = it.label else { return [] }
        if let c = cache[l] { return c }
        let b = Dataset.parse(l)
        cache[l] = b
        return b
    }

    nonisolated static func nfc(_ s: String) -> String { s.precomposedStringWithCanonicalMapping }

    nonisolated static func scan(_ root: URL) -> ([LabeledImage], [Int: String]) {
        let fm = FileManager.default
        var images: [URL] = []
        var labelIndex: [String: URL] = [:]           // NFC 파일 이름(확장자 제외) → 라벨
        if let e = fm.enumerator(at: root, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles]) {
            for case let u as URL in e {
                let ext = u.pathExtension.lowercased()
                if imageExts.contains(ext) { images.append(u) }
                else if ext == "txt", u.lastPathComponent != "classes.txt" {
                    let key = nfc(u.deletingPathExtension().lastPathComponent)
                    // 오토라벨링 결과가 있으면 그게 우선 (사용자가 방금 확인하려는 것)
                    if labelIndex[key] == nil || u.path.contains("labels_auto") { labelIndex[key] = u }
                }
            }
        }
        // YOLO 기본 구조: images/train 을 고르면 짝인 labels/train 도 본다 (★없으면 라벨이 0개로 나왔다)
        let parts = root.pathComponents
        if let k = parts.lastIndex(of: "images") {
            var p = parts; p[k] = "labels"
            let labels = URL(fileURLWithPath: NSString.path(withComponents: p))
            if let e = fm.enumerator(at: labels, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles]) {
                for case let u as URL in e where u.pathExtension == "txt" && u.lastPathComponent != "classes.txt" {
                    let key = nfc(u.deletingPathExtension().lastPathComponent)
                    if labelIndex[key] == nil { labelIndex[key] = u }
                }
            }
        }
        // 이미지 옆 폴더의 labels_auto 도 본다 (결과는 대상 폴더 밖에 쓰이므로)
        let sibling = root.deletingLastPathComponent().appending(path: "labels_auto")
        if let e = fm.enumerator(at: sibling, includingPropertiesForKeys: nil) {
            for case let u as URL in e where u.pathExtension == "txt" {
                labelIndex[nfc(u.deletingPathExtension().lastPathComponent)] = u
            }
        }
        images.sort { $0.path < $1.path }
        let items = images.map { LabeledImage(id: $0, label: labelIndex[nfc($0.deletingPathExtension().lastPathComponent)]) }
        return (items, classNames(near: root))
    }

    /// data.yaml / classes.txt 에서 클래스 이름. 위로 세 칸까지 찾아본다
    nonisolated static func classNames(near root: URL) -> [Int: String] {
        var dir = root
        for _ in 0..<4 {
            for f in ["data.yaml", "dataset.yaml", "data.yml"] {
                if let s = try? String(contentsOf: dir.appending(path: f), encoding: .utf8), let n = parseNames(s) { return n }
            }
            if let s = try? String(contentsOf: dir.appending(path: "classes.txt"), encoding: .utf8) {
                return Dictionary(uniqueKeysWithValues: s.split(whereSeparator: \.isNewline).enumerated().map { ($0.offset, String($0.element)) })
            }
            dir = dir.deletingLastPathComponent()
        }
        return [:]
    }

    nonisolated static func parseNames(_ yaml: String) -> [Int: String]? {
        let lines = yaml.components(separatedBy: .newlines)
        guard let i = lines.firstIndex(where: { $0.hasPrefix("names:") }) else { return nil }
        let inline = lines[i].dropFirst(6).trimmingCharacters(in: .whitespaces)
        if inline.hasPrefix("[") {                        // names: [a, b]
            let parts = inline.trimmingCharacters(in: CharacterSet(charactersIn: "[]")).split(separator: ",")
            return Dictionary(uniqueKeysWithValues: parts.enumerated().map { ($0.offset, $0.element.trimmingCharacters(in: .init(charactersIn: " '\""))) })
        }
        var out: [Int: String] = [:]
        var idx = 0
        for l in lines[(i + 1)...] {
            guard l.hasPrefix(" ") || l.hasPrefix("\t") || l.hasPrefix("-") else { break }
            let t = l.trimmingCharacters(in: .whitespaces)
            if t.hasPrefix("- ") { out[idx] = String(t.dropFirst(2)).trimmingCharacters(in: .init(charactersIn: "'\"")); idx += 1 }
            else if let c = t.firstIndex(of: ":"), let k = Int(t[..<c]) { out[k] = t[t.index(after: c)...].trimmingCharacters(in: .init(charactersIn: " '\"")) }
        }
        return out.isEmpty ? nil : out
    }

    nonisolated static func parse(_ url: URL) -> [YoloBox] {
        guard let s = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        return s.split(whereSeparator: \.isNewline).compactMap { line in
            let v = line.split(separator: " ").compactMap { Double($0) }
            guard v.count >= 5 else { return nil }
            var rest = Array(v.dropFirst(5))
            var conf: Double?
            if rest.count % 3 == 1 { conf = rest.removeLast() }          // 오토라벨링: 맨 끝이 신뢰도
            else if rest.count == 1 { conf = rest.removeFirst() }
            var kp: [(Double, Double, Double)] = []
            if rest.count >= 3 && rest.count % 3 == 0 {
                for k in stride(from: 0, to: rest.count, by: 3) { kp.append((rest[k], rest[k + 1], rest[k + 2])) }
            } else if rest.count >= 2 && rest.count % 2 == 0 {
                for k in stride(from: 0, to: rest.count, by: 2) { kp.append((rest[k], rest[k + 1], 2)) }
            }
            return YoloBox(cls: Int(v[0]), cx: v[1], cy: v[2], w: v[3], h: v[4], conf: conf, kpts: kp)
        }
    }
}

// 클래스별 색. 같은 클래스는 늘 같은 색
func classColor(_ c: Int) -> Color {
    let palette: [Color] = [.blue, .warn, .good, .pink, .mixup, .teal, .gold, .bad, .indigo, .mint, .cyan, .brown]
    return palette[c % palette.count]
}

struct DatasetView: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink
    @State private var ds = Dataset()
    @State private var progress = LabelProgress()          // ✓ ○ · 진행 상태(LabelTool.swift)
    @State private var selected: LabeledImage?
    @State private var filter = "all"
    @State private var thumb = 150.0
    @State private var showLabels = true
    @AppStorage("datasetFolder") private var lastFolder = ""      // 마지막에 연 폴더를 기억한다

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            if ds.root == nil {
                ContentUnavailableView {
                    Label("Look at your labels", systemImage: "photo.stack")
                } description: {
                    Text("Choose a folder of images. Boxes from YOLO labels are drawn on top.")
                } actions: {
                    Button("Choose Folder…") { pick() }.primaryButton()
                }
                .frame(maxHeight: .infinity)
            } else if ds.loading {
                ProgressView("Reading labels…").frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                grid
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .task {
            if ds.root == nil, !lastFolder.isEmpty, FileManager.default.fileExists(atPath: lastFolder) {
                await ds.open(URL(fileURLWithPath: lastFolder))
            }
        }
        .sheet(item: $selected) { it in LabelingViewer(ds: ds, progress: progress, items: shown, current: it).frame(minWidth: 900, minHeight: 680) }
        .onChange(of: ds.root) { _, r in if let r { progress.open(r) } }
    }

    private var shown: [LabeledImage] {
        switch filter {
        case "unlabeled": ds.items.filter { $0.label == nil }
        case "empty": ds.items.filter { $0.label != nil && ds.boxes($0).isEmpty }
        case "unseen": ds.items.filter { progress.status($0, boxes: ds.boxes($0).count) == .unseen }
        default:
            if let c = Int(filter) { ds.items.filter { ds.boxes($0).contains { $0.cls == c } } } else { ds.items }
        }
    }

    private var toolbar: some View {
        HStack(spacing: 12) {
            Button { pick() } label: { Label(ds.root?.lastPathComponent ?? L("Choose Folder…"), systemImage: "folder") }
            if ds.root != nil {
                let labeled = ds.items.filter { $0.label != nil }.count
                Label("\(ds.items.count)", systemImage: "photo").font(.ui(12)).foregroundStyle(ink.soft).help("Images")
                    .accessibilityLabel(L("Images: %lld", ds.items.count))
                Label("\(labeled)", systemImage: "tag").font(.ui(12)).foregroundStyle(ink.soft).help("Labeled")
                    .accessibilityLabel(L("Labeled: %lld", labeled))
                let seen = ds.items.filter { progress.status($0, boxes: ds.boxes($0).count) != .unseen }.count
                Label("\(seen)/\(ds.items.count)", systemImage: "checkmark.circle").font(.ui(12)).foregroundStyle(ink.soft)
                    .help("Checked: has boxes or marked nothing to label (N)").contentTransition(.numericText())
                Image(systemName: "line.3.horizontal.decrease.circle").foregroundStyle(ink.soft).help("Show").accessibilityHidden(true)
                Picker("Show", selection: $filter) {
                    Text("All").tag("all")
                    Text("No label file").tag("unlabeled")
                    Text("Empty labels").tag("empty")
                    Text("Not checked yet").tag("unseen")
                    if !ds.classes.isEmpty { Divider() }
                    ForEach(ds.classes.keys.sorted(), id: \.self) { k in Text(ds.classes[k] ?? "\(k)").tag("\(k)") }
                }
                .labelsHidden().frame(width: 160)
                Spacer()
                Toggle(isOn: $showLabels) { Image(systemName: "square.dashed") }
                    .toggleStyle(.button).controlSize(.small).help("Boxes").accessibilityLabel("Boxes")
                HStack(spacing: 4) {
                    Image(systemName: "photo").font(.ui(10)).foregroundStyle(ink.soft).accessibilityHidden(true)
                    Slider(value: $thumb, in: 90...300).frame(width: 100).controlSize(.small)
                        .accessibilityLabel("Thumbnail size")
                    Image(systemName: "photo").font(.ui(15)).foregroundStyle(ink.soft).accessibilityHidden(true)
                }
                .help("Thumbnail size")
            } else { Spacer() }
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
    }

    private var grid: some View {
        ScrollView {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: thumb), spacing: 10)], spacing: 10) {
                ForEach(shown) { it in
                    Thumb(item: it, boxes: showLabels ? ds.boxes(it) : [], classes: ds.classes, side: thumb)
                        .overlay(alignment: .topTrailing) {
                            let st = progress.status(it, boxes: ds.boxes(it).count)
                            Image(systemName: st.symbol).font(.ui(12, weight: .bold)).foregroundStyle(st.tint)
                                .padding(5).background(.black.opacity(0.45), in: Circle()).padding(5).help(st.title)
                        }
                        .onTapGesture { selected = it }
                        .contextMenu {                              // 오른쪽 클릭: 파일 찾기
                            Button("Show in Finder", systemImage: "folder") { NSWorkspace.shared.activateFileViewerSelecting([it.id]) }
                            if let l = it.label {
                                Button("Show label file", systemImage: "doc.text") { NSWorkspace.shared.activateFileViewerSelecting([l]) }
                            }
                            Divider()
                            Button("Copy Path", systemImage: "doc.on.doc") { copyText(it.id.path, store) }
                        }
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(it.label == nil ? L("%@, no label file", it.name) : L("%@, %lld boxes", it.name, ds.boxes(it).count))
                        .accessibilityAddTraits(.isButton)
                }
            }
            .padding(16)
        }
    }

    private func pick() {
        let p = NSOpenPanel()
        p.canChooseDirectories = true; p.canChooseFiles = false
        p.message = String(localized: "Choose a folder of images (or a dataset folder)")
        if p.runModal() == .OK, let u = p.url { lastFolder = u.path; Task { await ds.open(u) } }
    }
}

extension Thumb {
    var badge: some View {
        HStack(spacing: 4) {
            if item.label == nil { Image(systemName: "questionmark.circle.fill").foregroundStyle(.warn).help("No label file") }
            else { Text("\(boxes.count)").font(.ui(10, weight: .bold, design: .rounded)).foregroundStyle(.white) }
        }
        .padding(.horizontal, 6).padding(.vertical, 2)
        .background(.black.opacity(0.62), in: Capsule())      // ★반투명 재질은 밝은 하늘 위에서 숫자가 안 읽혔다
        .padding(5)
    }
}

// 썸네일. 큰 사진을 통째로 읽지 않고 작게 디코딩한다 (수천 장 폴더에서도 가볍게)
