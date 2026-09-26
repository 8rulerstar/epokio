// swift-tools-version: 6.0
// Epokio 맥 앱. 화면만 담당한다. 데이터는 전부 파이썬 agent(HTTP)에서 받는다.
// 윈도우 앱도 같은 agent를 부르므로 로직은 파이썬 한 벌뿐이다.
import PackageDescription

let package = Package(
    name: "Epokio",
    platforms: [.macOS(.v15)],
    dependencies: [
        // 자동 업데이트(2026-09-22 사용자 결정). EdDSA 서명된 appcast만 받는다
        // 상한을 둔다: 3.0의 깨지는 변경이 조용히 들어오지 않게
        .package(url: "https://github.com/sparkle-project/Sparkle", "2.6.0" ..< "3.0.0"),
    ],
    targets: [
        .executableTarget(name: "Epokio", dependencies: [.product(name: "Sparkle", package: "Sparkle")], path: "Sources/Epokio",
                          linkerSettings: [.unsafeFlags(["-Xlinker", "-rpath", "-Xlinker", "@executable_path/../Frameworks",       // 앱 번들
                                                         "-Xlinker", "-rpath", "-Xlinker", "@executable_path"])])      // swift build 결과(시험·스냅샷)
    ]
)
