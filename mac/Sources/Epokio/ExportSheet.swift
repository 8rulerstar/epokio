import SwiftUI

// 내보내기 시트: 형식 · 해상도 · FP16/INT8/dynamic. 마지막 선택을 기억해 Return 한 번이면 예전처럼 바로 내보낸다.
// 형식별 가능 여부 출처: docs.ultralytics.com/modes/export (Arguments·Quantization 표, 2026-09 확인)
//   onnx·coreml·openvino·engine: FP16·INT8·dynamic 가능 / tflite: INT8만(FP16·dynamic 없음)

struct ExportFormat: Identifiable {
    let id: String
    let title: String
    var half = true, int8 = true, dynamic = true

    static var all: [ExportFormat] {
        [ExportFormat(id: "onnx", title: L("ONNX (servers, most tools)")),
         ExportFormat(id: "coreml", title: L("Core ML (Mac and iPhone apps)")),
         ExportFormat(id: "tflite", title: L("TensorFlow Lite (Android, small devices)"), half: false, dynamic: false),
         ExportFormat(id: "openvino", title: L("OpenVINO (Intel CPUs)")),
         ExportFormat(id: "engine", title: L("TensorRT (NVIDIA, fastest)"))]
    }
}

/// 내보내기 요청에 실을 값. nil이면 보내지 않아 서버 기본 동작(run의 학습 imgsz, 형식 기본값)을 따른다
struct ExportOptions {
    var format: String
    var imgsz: Int?
    var half: Bool?
    var int8: Bool?
    var dynamic: Bool?

    var params: [String: Any] {
        var p: [String: Any] = ["format": format]
        if let imgsz { p["imgsz"] = imgsz }
        if let half { p["half"] = half }
        if let int8 { p["int8"] = int8 }
        if let dynamic { p["dynamic"] = dynamic }
        return p
    }
}

/// 레일의 내보내기 버튼. 누르면 시트, Option을 누른 채 누르면 마지막 선택으로 바로 내보낸다
struct ExportRailButton: View {
    let enabled: Bool
    /// run의 학습 imgsz(args.yaml). 시트의 기본값 표시용
    let trainImgsz: Int?
    let export: (ExportOptions) -> Void
    @State private var show = false

    var body: some View {
        Button {
            if NSEvent.modifierFlags.contains(.option) { export(ExportSheet.lastOptions()) } else { show = true }
        } label: { RailLabel(symbol: "shippingbox", title: L("Export"), enabled: enabled) }
            .buttonStyle(PressStyle()).disabled(!enabled)
            .help(L("Save the model in another format for an app, a server or a phone"))
            .accessibilityLabel(L("Export"))
            .sheet(isPresented: $show) {
                ExportSheet(trainImgsz: trainImgsz) { o in show = false; export(o) } cancel: { show = false }
            }
    }
}

struct ExportSheet: View {
    let trainImgsz: Int?
    let export: (ExportOptions) -> Void
    let cancel: () -> Void

    @AppStorage("export.format") private var format = "onnx"
    @AppStorage("export.half") private var half = false
    @AppStorage("export.int8") private var int8 = false
    @AppStorage("export.dynamic") private var dynamic = false
    /// 비워 두면 학습 imgsz를 그대로 쓴다(보내지 않음)
    @State private var size = ""

    private var spec: ExportFormat { ExportFormat.all.first { $0.id == format } ?? ExportFormat.all[0] }
    private var sizeValue: Int? { Int(size.trimmingCharacters(in: .whitespaces)).flatMap { $0 >= 32 ? $0 : nil } }
    private var sizeBad: Bool { !size.trimmingCharacters(in: .whitespaces).isEmpty && sizeValue == nil }

    /// 저장된 선택을 형식이 받는 값만 남겨 요청으로. 꺼진 토글은 보내지 않는다(서버 기본값 유지)
    static func lastOptions(imgsz: Int? = nil) -> ExportOptions {
        let d = UserDefaults.standard
        let f = ExportFormat.all.first { $0.id == d.string(forKey: "export.format") } ?? ExportFormat.all[0]
        let half = f.half && d.bool(forKey: "export.half"), int8 = f.int8 && d.bool(forKey: "export.int8")
        return ExportOptions(format: f.id, imgsz: imgsz, half: half && !int8 ? true : nil, int8: int8 ? true : nil,
                             dynamic: f.dynamic && d.bool(forKey: "export.dynamic") ? true : nil)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.l) {
            Text("Export Model").font(.ui(15, weight: .semibold))
            Form {
                Picker(L("Format"), selection: $format) {
                    ForEach(ExportFormat.all) { Text(verbatim: $0.title).tag($0.id) }
                }
                TextField(L("Image size"), text: $size, prompt: Text(verbatim: trainImgsz.map(String.init) ?? "640"))
                    .help(L("Leave empty to use the training image size"))
                toggle(L("Half precision (FP16)"), $half, ok: spec.half, hint: L("Smaller and faster on GPUs"))
                    .onChange(of: half) { _, v in if v { withAnimation(Motion.change) { int8 = false } } }
                toggle("INT8", $int8, ok: spec.int8, hint: L("Smallest file. Accuracy may drop a little"))
                    .onChange(of: int8) { _, v in if v { withAnimation(Motion.change) { half = false } } }
                toggle(L("Dynamic input size"), $dynamic, ok: spec.dynamic, hint: L("Accept images of any size"))
            }
            .formStyle(.grouped).scrollDisabled(true)
            HStack {
                Spacer()
                Button(L("Cancel"), action: cancel).secondaryButton().keyboardShortcut(.cancelAction)
                Button(L("Export")) { export(Self.lastOptions(imgsz: sizeValue)) }
                    .primaryButton().keyboardShortcut(.defaultAction).disabled(sizeBad)
            }
        }
        .padding(Space.xl)
        .frame(width: 400)
        .animation(Motion.change, value: format)
    }

    /// 형식이 받지 않는 옵션은 꺼 두고 이유를 툴팁으로
    private func toggle(_ title: String, _ v: Binding<Bool>, ok: Bool, hint: String) -> some View {
        Toggle(title, isOn: ok ? v : .constant(false))
            .disabled(!ok)
            .help(ok ? hint : L("Not available for this format"))
    }
}
