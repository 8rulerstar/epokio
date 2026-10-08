import AppKit
import UniformTypeIdentifiers

// 모든 학습을 표 파일(CSV)로. 엑셀·넘버스·구글 시트에서 열린다(웹 downloadCSV와 같은 칸·같은 규칙).

/// CSV 한 칸. 이름·태그는 남이 정할 수 있어 = + - @ 로 시작하면 엑셀이 수식으로 실행한다. 숫자가 아니면 ' 를 붙인다
func csvCell(_ v: String) -> String {
    var s = v
    let numeric = Double(v) != nil                  // -0.5 같은 숫자는 그대로
    if let c = s.unicodeScalars.first, !numeric, "=+-@\t\r".unicodeScalars.contains(c) { s = "'" + s }
    // ★글자(Character)로 보면 "\r\n"이 한 글자라 \n·\r 어느 쪽과도 같지 않아, 줄바꿈이 든 칸이 따옴표 없이 나가 줄이 깨졌다
    let special: Set<Unicode.Scalar> = [",", "\"", "\n", "\r"]
    return s.unicodeScalars.contains(where: { special.contains($0) })
        ? "\"" + s.replacingOccurrences(of: "\"", with: "\"\"") + "\"" : s
}

func runsCSV(_ runs: [Run]) -> String {
    let cols = ["name", "state", "epoch", "total", "best", "best_epoch", "metric_name", "framework", "source", "tags", "path", "x_axis"]   // x_axis=step이면 epoch·total·best_epoch가 step 번호
    // ★한 식에 몰아 쓰면 컴파일러가 타입을 못 정한다(CI에서 시간 초과). 칸을 하나씩 채운다
    let rows: [String] = runs.map { (r: Run) -> String in
        var c: [String] = [r.displayName, r.state, String(r.epoch)]
        c.append(r.total.map { String($0) } ?? "")
        c.append(r.best.map { String($0) } ?? "")
        c.append(r.best_epoch.map { String($0) } ?? "")
        c.append(r.metric_name)
        c.append(r.framework ?? "")
        c.append(r.source)
        c.append((r.meta?.tags ?? []).joined(separator: " "))
        c.append(r.path)
        c.append(r.isStepAxis ? "step" : "epoch")
        return c.map(csvCell).joined(separator: ",")
    }
    let lines: [String] = [cols.joined(separator: ",")] + rows
    return "\u{FEFF}" + lines.joined(separator: "\r\n")   // BOM: 엑셀이 한글을 안 깨게
}

/// 저장 위치를 물어 쓰고 Finder에서 보여 준다
@MainActor func exportRunsCSV(_ runs: [Run]) {
    let p = NSSavePanel()
    let day = Date().formatted(Date.ISO8601FormatStyle(timeZone: .current).year().month().day())   // ★UTC면 한국 오전 9시 전엔 어제 날짜
    p.nameFieldStringValue = "epokio-runs-\(day).csv"
    p.allowedContentTypes = [.commaSeparatedText]
    guard p.runModal() == .OK, let url = p.url else { return }
    do {
        try runsCSV(runs).write(to: url, atomically: true, encoding: .utf8)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    } catch {
        NSAlert(error: error).runModal()
    }
}
