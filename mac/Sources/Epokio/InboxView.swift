import SwiftUI

// 알림함: 맥 알림은 한 번 뜨고 사라지므로, 사건을 여기에 쌓아 둔다. 누르면 그 학습의 상세로.
struct InboxView: View {
    @Environment(Store.self) private var store
    @Environment(\.ink) private var ink

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Notifications").font(.ui(17, weight: .bold))
                Spacer()
                IconButton(symbol: "checkmark.circle", help: "Mark All as Read") { withAnimation { store.markRead() } }
                    .disabled(store.unread == 0)
                IconButton(symbol: "square.and.arrow.up", help: "Export") { exportInbox() }.disabled(store.inbox.isEmpty)
                IconButton(symbol: "trash", help: "Clear") { withAnimation { store.clearInbox() } }.disabled(store.inbox.isEmpty)
            }
            .controlSize(.small)
            .padding(.horizontal, 16).padding(.vertical, 12)
            if store.inbox.isEmpty {
                ContentUnavailableView("No notifications yet", systemImage: "bell",
                                       description: Text("When a run finishes, fails or stalls, it shows up here."))
                    .frame(maxHeight: .infinity)
            } else {
                List {
                    ForEach(groups, id: \.0) { day, items in
                        Section(day) {
                            ForEach(items) { item in
                                Button {                        // 버튼이라 Tab·스페이스와 VoiceOver로도 누른다
                                    store.markRead(item.id)
                                    if !item.isMachine { store.showInbox = false; store.open(run: item.runID) }
                                } label: { InboxRow(item: item).contentShape(.rect) }
                                    .buttonStyle(.plain)
                                    .focusable()
                                    .accessibilityHint(item.isMachine ? L("Marks it as read") : L("Opens the results of this run"))
                                    .contextMenu {                  // 오른쪽 클릭: 읽음 처리, 관련 학습 열기
                                        if !item.read {
                                            Button("Mark as Read", systemImage: "checkmark.circle") { withAnimation { store.markRead(item.id) } }
                                        }
                                        if !item.isMachine {
                                            Button("Show Results", systemImage: "chart.xyaxis.line") {
                                                store.markRead(item.id); store.showInbox = false; store.open(run: item.runID)
                                            }
                                        }
                                    }
                            }
                        }
                    }
                }
                .listStyle(.inset)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    private func exportInbox() {
        let p = NSSavePanel(); p.nameFieldStringValue = "epokio-notifications.csv"
        guard p.runModal() == .OK, let url = p.url else { return }
        let f = ISO8601DateFormatter()
        var csv = "time,event,run,machine,epoch,total,best\n"
        for i in store.inbox {
            csv += "\(f.string(from: i.date)),\(i.kind),\"\(i.runName)\",\(i.machine),\(i.epoch),\(i.total.map(String.init) ?? ""),\(i.best.map { String(format: "%.4f", $0) } ?? "")\n"
        }
        writeExport(csv, to: url, store)
    }

    /// 오늘 / 어제 / 날짜별로 묶는다
    private var groups: [(String, [InboxItem])] {
        let cal = Calendar.current
        let f = DateFormatter(); f.dateStyle = .medium; f.timeStyle = .none; f.doesRelativeDateFormatting = true
        var out: [(String, [InboxItem])] = []
        for item in store.inbox {
            let key = f.string(from: cal.startOfDay(for: item.date))
            if let i = out.firstIndex(where: { $0.0 == key }) { out[i].1.append(item) } else { out.append((key, [item])) }
        }
        return out
    }
}

struct InboxRow: View {
    let item: InboxItem
    @Environment(\.ink) private var ink
    @State private var hover = false

    private var tint: Color {
        switch item.kind {
        case "finished", "job_done": .good
        case "failed", "job_failed": .bad
        case "stalled", "stopped_early", "disk_low", "gpu_hot", "gpu_mem", "fan_max": .warn
        default: .brand
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            Circle().fill(item.read ? Color.clear : Color.brand).frame(width: 7, height: 7)
                .accessibilityLabel(item.read ? "" : L("Unread")).accessibilityHidden(item.read)
                .help(item.read ? "" : L("Unread"))
            Image(systemName: item.symbol).font(.ui(16, weight: .semibold)).foregroundStyle(tint)
                .frame(width: 32, height: 32).background(tint.opacity(0.14), in: Circle()).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: item.title).font(.ui(13, weight: item.read ? .regular : .semibold))
                Text(verbatim: detail).font(.ui(11.5)).foregroundStyle(ink.soft).lineLimit(1).truncationMode(.middle)
            }
            Spacer()
            Text(item.date, style: .time).font(.ui(11.5)).foregroundStyle(ink.soft)
            Image(systemName: "chevron.right").font(.ui(11.5)).foregroundStyle(ink.faint).opacity(hover ? 1 : 0.4)
                .accessibilityHidden(true)
        }
        .accessibilityElement(children: .combine)
        .padding(.vertical, 4)
        .onHover { h in withAnimation(Motion.hover) { hover = h } }
    }

    private var detail: String {
        if item.isMachine { return item.runName + (item.machine != "local" ? "  ·  " + item.machine : "") }
        var parts = [item.runName, L("epoch %@", "\(item.epoch)/\(item.total.map(String.init) ?? "?")")]
        if let b = item.best { parts.append(L("best %@", String(format: "%.4f", b))) }
        if item.machine != "local" { parts.append(item.machine) }
        return parts.joined(separator: "  ·  ")
    }
}
