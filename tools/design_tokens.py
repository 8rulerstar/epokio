"""디자인 토큰(design/tokens.json) → 맥 앱 DesignTokens.swift + 웹 web/tokens.css.

사용: python3 tools/design_tokens.py          (다시 만든다)
      python3 tools/design_tokens.py --check  (어긋나 있으면 1로 끝남. 테스트가 부른다)
★두 파일은 손으로 고치지 않는다. 값은 tokens.json 한 곳. 규칙 설명은 docs/DESIGN.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "design" / "tokens.json"
SWIFT = ROOT / "mac" / "Sources" / "Epokio" / "DesignTokens.swift"
CSS = ROOT / "src" / "epokio" / "web" / "tokens.css"


def _rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def swift(t: dict) -> str:
    out = ["// ★자동 생성: design/tokens.json → tools/design_tokens.py. 손으로 고치지 말 것 (규칙: docs/DESIGN.md)",
           "import SwiftUI", "import AppKit", "",
           "/// 라이트·다크에서 다른 색 (시스템이 모드를 바꾸면 따라간다)",
           "private func dyn(_ l: (Double, Double, Double), _ d: (Double, Double, Double)) -> Color {",
           "    Color(nsColor: NSColor(name: nil) { a in",
           "        let c = a.bestMatch(from: [.darkAqua, .vibrantDark]) != nil ? d : l",
           "        return NSColor(srgbRed: c.0, green: c.1, blue: c.2, alpha: 1)",
           "    })",
           "}", "",
           "/// 색 역할. `.foregroundStyle(.good)`처럼 쓴다. 시스템 색(.green 등)을 직접 쓰지 않는다(test_house_rules)",
           "extension ShapeStyle where Self == Color {"]
    for name, c in t["color"].items():
        l, d = _rgb(c["light"]), _rgb(c["dark"])
        f = lambda v: "(" + ", ".join(f"{x:.3f}" for x in v) + ")"
        out.append(f"    /// {c['use']}")
        out.append(f"    static var {name}: Color {{ dyn({f(l)}, {f(d)}) }}")
    out.append("}")
    out += ["", "extension LinearGradient {"]
    for name, (a, b) in t["gradient"].items():
        out.append(f"    static var {name}: LinearGradient {{ LinearGradient(colors: [.{a}, .{b}], startPoint: .leading, endPoint: .trailing) }}")
    out += ["}", "", "/// 글꼴 역할. `.font(.role(.headline))`. 글씨 크기 설정(작게·보통·크게)을 따른다",
            "enum TypeRole: CaseIterable {"]
    out.append("    case " + ", ".join(t["type"]) )
    out.append("    var size: CGFloat { switch self { " + "; ".join(f"case .{k}: {v['size']}" for k, v in t["type"].items()) + " } }")
    out.append("    var weight: Font.Weight { switch self { " + "; ".join(f"case .{k}: .{v['weight']}" for k, v in t["type"].items()) + " } }")
    out.append("    var design: Font.Design { switch self { " + "; ".join(f"case .{k}: .{v['design']}" for k, v in t["type"].items()) + " } }")
    out += ["}", "", "extension Font {",
            "    static func role(_ r: TypeRole, weight: Font.Weight? = nil) -> Font { .ui(r.size, weight: weight ?? r.weight, design: r.design) }",
            "}", "",
            "/// 역할 크기 사다리. Font.ui(크기)는 가장 가까운 칸으로 맞춘다(흩어진 크기를 모은다)",
            "let typeLadder: [CGFloat] = [" + ", ".join(str(v["size"]) for v in sorted(t["type"].values(), key=lambda v: v["size"])) + "]", "",
            "enum Space { " + "; ".join(f"static let {k}: CGFloat = {v}" for k, v in t["space"].items()) + " }",
            "enum Radius { " + "; ".join(f"static let {k}: CGFloat = {v}" for k, v in t["radius"].items()) + " }", "",
            "/// 움직임 역할. `withAnimation(Motion.change) { … }`",
            "/// 길이는 설정 → 모양 \"움직임 속도\"(motionScale: 0.5 빠르게 ~ 2 느리게, 0 끄기)를 곱한다",
            "/// 시스템 손쉬운 사용의 \"동작 줄이기\"가 켜져 있으면 앱 설정과 무관하게 멈춘다 (SystemPrefs.swift)",
            "enum Motion {",
            "    static var scale: Double {",
            "        if SystemPrefs.reduceMotion { return 0.001 }",
            "        let v = UserDefaults.standard.object(forKey: \"motionScale\") as? Double ?? 1",
            "        return v <= 0 ? 0.001 : v",
            "    }"]
    for k, m in t["motion"].items():
        if m["kind"] == "spring":
            expr = f".spring(duration: {m['duration']} * scale, bounce: {m['bounce']})"
        else:
            expr = f".{m['kind']}(duration: {m['duration']} * scale)"
        out.append(f"    /// {m['use']}")
        out.append(f"    static var {k}: Animation {{ {expr} }}")
    out.append(f"    static var stagger: Double {{ {t['motion']['appear']['stagger']} * scale }}")
    out.append("}")
    return "\n".join(out) + "\n"


def css(t: dict) -> str:
    out = ["/* ★자동 생성: design/tokens.json → tools/design_tokens.py. 손으로 고치지 말 것 (규칙: docs/DESIGN.md) */", ":root {"]
    out += [f"  --{k}: {c['light']};" for k, c in t["color"].items()]
    out += [f"  --t-{k}: {v['size']}px;" for k, v in t["type"].items()]
    out += [f"  --s-{k}: {v}px;" for k, v in t["space"].items()]
    out += [f"  --r-{k}: {v}px;" for k, v in t["radius"].items()]
    ease = {"snappy": "cubic-bezier(.2,.8,.2,1)", "smooth": "cubic-bezier(.4,0,.2,1)", "spring": "cubic-bezier(.34,1.3,.64,1)", "bouncy": "cubic-bezier(.34,1.56,.64,1)"}
    out += [f"  --m-{k}: {m['duration']}s {ease[m['kind']]};" for k, m in t["motion"].items()]
    a, b = t["gradient"]["brand"]
    out += [f"  --grad-brand: linear-gradient(90deg, var(--{a}), var(--{b}));", "}",
            "@media (prefers-color-scheme: dark) {", "  :root {"]
    out += [f"    --{k}: {c['dark']};" for k, c in t["color"].items()]
    out += ["  }", "}"]
    return "\n".join(out) + "\n"


def main():
    t = json.loads(SRC.read_text(encoding="utf-8"))
    want = {SWIFT: swift(t), CSS: css(t)}
    if "--check" in sys.argv:
        bad = [p for p, s in want.items() if not p.exists() or p.read_text(encoding="utf-8") != s]
        if bad:
            print("out of date:", *[str(p.relative_to(ROOT)) for p in bad])
            sys.exit(1)
        return
    for p, s in want.items():
        p.write_text(s, encoding="utf-8")
        print("wrote", p.relative_to(ROOT))


if __name__ == "__main__":
    main()
