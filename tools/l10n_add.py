"""번역 추가: python3 tools/l10n_add.py <json 파일>  ({"영어 키": "한국어"}). 안 쓰는 키는 지운다."""
import json, re, subprocess, sys
from pathlib import Path

P = Path(__file__).resolve().parent.parent / "mac/Resources/ko.lproj/Localizable.strings"
esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
add = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else {}
lines = P.read_text(encoding="utf-8").rstrip("\n").split("\n")
out = subprocess.run([sys.executable, str(Path(__file__).parent / "l10n_keys.py")], capture_output=True, text=True).stdout
unused = {l[len("unused: "):] for l in out.splitlines() if l.startswith("unused: ")}
keep = [l for l in lines if not (l.startswith('"') and re.match(r'^"((?:[^"\\]|\\.)*)"', l).group(1) in {esc(u) for u in unused})]
keep += [f'"{esc(k)}" = "{esc(v)}";' for k, v in add.items()]
head = [l for l in keep if not l.startswith('"')]
body = sorted(set(l for l in keep if l.startswith('"')))
P.write_text("\n".join(head + body) + "\n", encoding="utf-8")
print(f"added {len(add)}, removed {len(unused)}")
