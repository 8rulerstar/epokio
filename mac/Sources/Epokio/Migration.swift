import Foundation

/// 예전 이름(TrainBar)에서 옮겨 온다. 앱을 처음 켤 때 한 번만, 새 자리가 비어 있을 때만.
/// ① ~/.trainbar → ~/.epokio (토큰·대기열·알림함, 파일 안의 옛 경로도 고친다)
/// ② 설정(io.github.8rulerstar.trainbar) → 이 앱 설정
/// ③ ~/Library/Application Support/TrainBar → Epokio
enum Migration {
    static func run() {
        let fm = FileManager.default
        let home = fm.homeDirectoryForCurrentUser
        let old = home.appending(path: ".trainbar"), new = home.appending(path: ".epokio")
        if fm.fileExists(atPath: old.path), !fm.fileExists(atPath: new.path), (try? fm.moveItem(at: old, to: new)) != nil {
            for f in (try? fm.contentsOfDirectory(at: new, includingPropertiesForKeys: nil)) ?? [] where f.pathExtension == "json" {
                if let t = try? String(contentsOf: f, encoding: .utf8), t.contains("/.trainbar/") {
                    try? t.replacingOccurrences(of: "/.trainbar/", with: "/.epokio/").write(to: f, atomically: true, encoding: .utf8)
                }
            }
        }
        let d = UserDefaults.standard
        if !d.bool(forKey: "migratedFromTrainBar") {
            if let prev = d.persistentDomain(forName: "io.github.8rulerstar.trainbar") {
                for (k, v) in prev where d.object(forKey: k) == nil || k == "AppleLanguages" { d.set(v, forKey: k) }
            }
            // 창 위치·크기 기록은 가져오지 않는다(옛 기록이 화면보다 커서 창이 바닥까지 찼다)
            for k in d.dictionaryRepresentation().keys where k.hasPrefix("NSWindow Frame") || k.hasPrefix("NSSplitView") {
                d.removeObject(forKey: k)
            }
            d.set(true, forKey: "migratedFromTrainBar")
        }
        let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let oldS = support.appending(path: "TrainBar"), newS = support.appending(path: "Epokio")
        if fm.fileExists(atPath: oldS.path), !fm.fileExists(atPath: newS.path) { try? fm.moveItem(at: oldS, to: newS) }
    }
}
