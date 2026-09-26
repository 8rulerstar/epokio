import SwiftUI

// 학습 화면 조각: 출발 전 점검. (작업 종류 버튼·설정 한 줄은 TrainHelpers.swift, 다시 학습의 모든 설정은 TrainSubmit.swift loadRetrain)

extension TrainView {
    /// 출발 전 점검. 데이터에 진짜 오류(level "error")가 있거나 못 읽으면 그 문장들을 돌려준다.
    /// 폴더를 적었으면 agent가 찾은 data.yaml 경로도 돌려준다. 검진 요청 자체가 실패하면 막지 않는다(웹과 같다)
    func preflight(_ dataArg: String) async -> (errors: [String], data: String?) {
        guard let r: HealthReport = try? await client.get("health-check", ["data": dataArg]) else { return ([], nil) }
        if !r.ok { return ([r.error ?? L("The data.yaml could not be read.")], nil) }
        return ((r.warnings ?? []).filter { $0.level == "error" }.map(\.text), r.data)
    }
}

/// 출발 전 점검에 걸렸을 때: 무엇이 문제인지와 "그래도 시작"
struct PreflightCard: View {
    let errors: [String]
    let startAnyway: () -> Void
    @State private var hover = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(errors.count == 1 ? L("Not started. The data has a problem.") : L("Not started. The data has %d problems.", errors.count),
                  systemImage: "xmark.octagon.fill")
                .font(.ui(13, weight: .semibold)).foregroundStyle(.bad)
                .contentTransition(.numericText())
                .symbolEffect(.bounce, value: errors.count)
            ForEach(errors, id: \.self) { e in
                Text(verbatim: e).font(.ui(11.5)).fixedSize(horizontal: false, vertical: true)
            }
            Button("Start anyway", action: startAnyway)
                .buttonStyle(PressStyle())
                .font(.ui(12, weight: .semibold))
                .padding(.horizontal, 10).padding(.vertical, 5)
                .background(Color.bad.opacity(hover ? 0.18 : 0.1), in: .rect(cornerRadius: 8))
                .onHover { h in withAnimation(Motion.hover) { hover = h } }
                .padding(.top, 2)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.bad.opacity(0.07), in: .rect(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Color.bad.opacity(0.25)))
    }
}
