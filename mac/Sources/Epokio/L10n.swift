import Foundation

/// String 변수로 넘어온 문구를 번역한다. SwiftUI의 Text("글자")는 알아서 번역되지만,
/// Text(변수)는 그대로 찍히므로 화면에 나가는 String은 전부 여기를 거친다.
/// 번역은 Resources/<언어>.lproj/Localizable.strings. 없는 키는 영어 그대로 나온다.
func L(_ key: String) -> String { Bundle.main.localizedString(forKey: key, value: key, table: nil) }

/// "%d images" 같은 틀을 번역한 뒤 값을 채운다.
func L(_ key: String, _ args: CVarArg...) -> String { String(format: L(key), locale: .current, arguments: args) }
