"""앱 화면 문구의 번역 키를 전부 뽑아, 번역 파일에 빠진 것을 보여 준다.

키는 컴파일러가 만든다(-emit-localized-strings). SwiftUI Text("...")의 보간이 %@·%lld로 바뀐
실제 키라 손으로 짐작하지 않아도 된다. L("...")로 넘기는 문구는 소스에서 따로 줍는다.

    python3 tools/l10n_keys.py            # ko의 빠진 키 출력, 있으면 종료 코드 1
    python3 tools/l10n_keys.py --all      # 전체 키
    python3 tools/l10n_keys.py --langs    # 모든 .lproj: 누락·중복·포맷 지정자 불일치 보고
    python3 tools/l10n_keys.py --strict   # --langs와 같고, 문제가 하나라도 있으면 종료 코드 1
    python3 tools/l10n_keys.py --langs ja,de   # 특정 언어만
    python3 tools/l10n_keys.py --langs --same  # 번역이 영어 원문과 같은 항목도 경고로

언어별 보고 줄은 "<언어> missing: 키", "<언어> duplicate: 키", "<언어> format: 키 | 원문 → 번역".
--same은 "<언어> same: 키"를 덧붙인다. 경고일 뿐이라 --strict의 종료 코드에는 넣지 않는다.
독일어 "Format"처럼 영어와 철자가 같은 낱말이 흔해서, 사람이 보고 판단할 목록이다.
고유명사·약어·경로·코드 예시는 SAME_OK와 SAME_SKIP이 미리 걸러낸다.
"""
import json, re, subprocess, sys, tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAC = ROOT / "mac"
RES = MAC / "Resources"
SKIP = re.compile(r"^[\W\d_%@lld]*$")          # 숫자·기호·보간만 있는 키("–", "%lld%%")는 번역할 것이 없다
ENTRY = re.compile(r'^"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)";', re.M)
# 번역해도 영어와 같아야 하는 것: 고유명사·측정 이름·약어
SAME_OK = {"Apple", "CPU", "GPU %", "Epokio", "Epokio Studio", "Python", "YOLO", "Nano",
           "F1", "P", "R", "Top-1", "mAP50", "mAP50-95", "conf", "Box F1"}
SAME_SKIP = re.compile(r"://|\\|\.pt\b|\.yaml\b|^\W")     # 경로·URL·파일명·코드 예시
SPEC = re.compile(r"%(?:(\d+)\$)?[-+#0]*\d*(?:\.\d+)?(hh|h|ll|l|q|z|t|j|L)?([@dDiuUxXoOfFeEgGcCsSpaA%])")


def keys():
    out = set()
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["swift", "build", "-c", "release", "-Xswiftc", "-emit-localized-strings",
                        "-Xswiftc", "-emit-localized-strings-path", "-Xswiftc", d],
                       cwd=MAC, check=True, capture_output=True)
        for f in Path(d).glob("*.stringsdata"):
            for e in json.loads(f.read_text(encoding="utf-8")).get("tables", {}).get("Localizable", []):
                out.add(e["key"])
    for f in (MAC / "Sources").rglob("*.swift"):
        out |= {k.replace('\\"', '"') for k in re.findall(r'\bL\("((?:[^"\\]|\\.)*)"', f.read_text(encoding="utf-8"))}
    return {k for k in out if not SKIP.match(k)}


def _un(t):
    return t.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")   # 파일 속 이스케이프를 푼다


def entries(text):
    """(키, 값) 목록. 중복도 그대로 남긴다."""
    return [(_un(k), _un(v)) for k, v in ENTRY.findall(text)]


def table(lang):
    p = RES / f"{lang}.lproj" / "Localizable.strings"
    if not p.exists():
        return {}
    return dict(entries(p.read_text(encoding="utf-8")))


def specs(s):
    """포맷 지정자를 인자 번호 순으로. 위치 번호가 없으면 나온 순서. %%는 뺀다.
    길이 수식어는 종류에 포함한다(%lld와 %d는 다른 인자형)."""
    out, n = [], 0
    for pos, length, conv in SPEC.findall(s):
        if conv == "%":
            continue
        n += 1
        out.append((int(pos) if pos else n, (length or "") + conv))
    return sorted(out)


def langs():
    return sorted(p.name[:-6] for p in RES.glob("*.lproj")
                  if (p / "Localizable.strings").exists() and p.name != "en.lproj")


def same_as_english(ks, tab):
    """번역이 영어 원문과 글자까지 같은 키. 고유명사·약어·경로는 뺀다."""
    return sorted(k for k, v in tab.items()
                  if k == v and k in ks and k not in SAME_OK and not SAME_SKIP.search(k))


def check(lang, ks, text, same=False):
    """한 언어 파일의 문제: missing, duplicate, format. same은 경고라 따로 센다."""
    es = entries(text)
    tab = dict(es)
    dup = sorted(k for k, c in Counter(k for k, _ in es).items() if c > 1)
    miss = sorted(k for k in ks if k not in tab)
    fmt = sorted((k, v) for k, v in tab.items() if specs(k) != specs(v))
    out = {"missing": miss, "duplicate": dup, "format": fmt}
    if same:
        out["warn_same"] = same_as_english(ks, tab)
    return out


def report(sel, ks, same=False):
    bad = 0
    for lang in sel:
        p = RES / f"{lang}.lproj" / "Localizable.strings"
        r = check(lang, ks, p.read_text(encoding="utf-8") if p.exists() else "", same)
        for k in r["missing"]:
            print(f"{lang} missing:", k)
        for k in r["duplicate"]:
            print(f"{lang} duplicate:", k)
        for k, v in r["format"]:
            print(f"{lang} format: {k} | {' '.join(t for _, t in specs(k)) or '-'} → {' '.join(t for _, t in specs(v)) or '-'}")
        for k in r.get("warn_same", []):
            print(f"{lang} same:", k)
        bad += sum(len(v) for k, v in r.items() if not k.startswith("warn_"))
        line = f"{lang}: {len(r['missing'])} missing, {len(r['duplicate'])} duplicate, {len(r['format'])} format"
        print(line + (f", {len(r['warn_same'])} same (warning)" if same else ""))
    return bad


if __name__ == "__main__":
    argv = sys.argv[1:]
    ks = keys()
    if "--all" in argv:
        print("\n".join(sorted(ks)))
        sys.exit(0)
    if "--langs" in argv or "--strict" in argv:
        sel = langs()
        for i, a in enumerate(argv):
            if a == "--langs" and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                sel = argv[i + 1].split(",")
        bad = report(sel, ks, "--same" in argv)
        print(f"{len(ks)} keys, {len(sel)} languages, {bad} problems")
        sys.exit(1 if bad and "--strict" in argv else 0)
    ko = table("ko")
    missing = sorted(k for k in ks if k not in ko)
    unused = sorted(k for k in ko if k not in ks)
    for k in missing:
        print("missing:", k)
    for k in unused:
        print("unused:", k)
    print(f"{len(ks)} keys, {len(missing)} missing, {len(unused)} unused")
    sys.exit(1 if missing else 0)
