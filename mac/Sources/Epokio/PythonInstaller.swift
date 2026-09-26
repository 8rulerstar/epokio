import Foundation
import CryptoKit

/// Mac에 쓸 만한 파이썬이 하나도 없을 때: 독립 실행형 파이썬을 받아 ~/.epokio/python 에 푼다.
/// Astral의 python-build-standalone(uv가 쓰는 것). 판(release)과 SHA-256을 고정해, 받은 파일이 다르면 쓰지 않는다.
/// 시스템에는 아무것도 설치하지 않는다. 폴더를 지우면 끝이다.
enum PythonInstaller {
    static let release = "20260901", version = "3.12.14"
    static let sha: [String: String] = [
        "aarch64": "3ee3ee547cedfeb7c2b16b2b7156039f7b470bb8f857e226fd3d2eb11db83c76",
        "x86_64": "2e31b23f3f1319f707d0e620b48847a0046577541d357276821f9f1b5492e0ba",
    ]
    static let home = FileManager.default.homeDirectoryForCurrentUser.appending(path: ".epokio")
    static var python: URL { home.appending(path: "python/bin/python3") }
    static var installed: Bool { FileManager.default.isExecutableFile(atPath: python.path) }

    static var arch: String {
        #if arch(arm64)
        "aarch64"
        #else
        "x86_64"
        #endif
    }
    static var url: URL {
        let name = "cpython-\(version)%2B\(release)-\(arch)-apple-darwin-install_only.tar.gz"
        return URL(string: "https://github.com/astral-sh/python-build-standalone/releases/download/\(release)/\(name)")!
    }

    enum Failure: LocalizedError {
        case checksum, unpack
        var errorDescription: String? {
            switch self {
            case .checksum: L("The download did not match the expected file. Nothing was installed.")
            case .unpack: L("Could not unpack Python.")
            }
        }
    }

    static func install() async throws {
        let (tmp, _) = try await URLSession.shared.download(from: url)
        let data = try Data(contentsOf: tmp, options: .mappedIfSafe)
        let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        guard digest == sha[arch] else { throw Failure.checksum }
        try FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/tar")
        p.arguments = ["-xzf", tmp.path, "-C", home.path]            // 안에 python/ 폴더가 들어 있다
        try p.run(); p.waitUntilExit()
        guard p.terminationStatus == 0, installed else { throw Failure.unpack }
    }
}
