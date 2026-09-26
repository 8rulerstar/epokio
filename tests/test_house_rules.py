"""사용자 규칙을 코드로 강제한다. 사람(과 에이전트)은 잊지만 테스트는 안 잊는다."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".venv", ".build", "build", "build.noindex", ".cache", "dist", ".git", "__pycache__", ".claude",
        "site-packages", "node_modules"}   # .claude: 다른 세션의 작업 트리(우리 소스가 아니다)

# 이름이 달라도 가상환경이면 건너뛴다(★저장소 안의 다른 이름 venv 때문에 수천 건이 걸렸다)
SKIP |= {d.name for d in ROOT.iterdir() if d.is_dir() and (d / "pyvenv.cfg").exists()}

# 빌드 산출물 폴더. build_app.sh가 여기에 CPython 3.12 stdlib를 통째로 넣는다
# (pydoc_data/topics.py에 엠 대시가 있어 집 규칙 테스트가 커밋을 막았다). 우리 소스가 아니다.
BUILD_DIRS = ("mac/build.noindex", "mac/build", "mac/.build", "mac/.cache", "dist", ".venv")
EXTS = {".py", ".swift", ".md", ".sh", ".toml", ".command"}


def files():
    skip_roots = {(ROOT / d).resolve() for d in BUILD_DIRS}
    for f in ROOT.rglob("*"):
        if not f.is_file() or f.suffix not in EXTS or (SKIP & set(f.parts)):
            continue
        if skip_roots & set(f.parents):
            continue
        yield f


def test_no_em_dash():
    """엠 대시(—) 금지. 문서·주석·UI 문구 전부. (규칙을 설명하는 한 줄만 예외)"""
    bad = []
    for f in files():
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if "—" in line and "엠 대시(—)" not in line and "엠 대시(—)" not in line:
                bad.append(f"{f.relative_to(ROOT)}:{i}")
    assert not bad, "엠 대시가 있다: " + ", ".join(bad[:10])


def test_no_source_s_plural():
    """'source(s)' 같은 엉성한 복수 표기 금지 (UI 문구)."""
    import re
    lit = re.compile(r'"[^"]*\(s\)[^"]*"')          # 문자열 안의 (s)만. 주석의 설명은 괜찮다
    bad = []
    for f in files():
        if f.suffix != ".swift":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            code = line.split("//")[0]
            if lit.search(code):
                bad.append(f"{f.relative_to(ROOT)}:{i}")
    assert not bad, "UI에 '(s)' 복수 표기: " + ", ".join(bad)


MAX_LINES = 400      # 혼자 유지보수할 수 있는 크기. 넘으면 기능별로 나눈다(agent.py → api/, ReviewView → Models·Actions)


def test_files_stay_small():
    """코드 파일 하나가 MAX_LINES를 넘지 않는다. (2026-09-22 모듈화 뒤 가장 큰 것 약 300줄)"""
    big = []
    for f in files():
        if f.suffix in (".py", ".swift") and "tests" not in f.parts and "fixtures" not in f.parts:
            n = sum(1 for _ in f.open(encoding="utf-8", errors="ignore"))
            if n > MAX_LINES:
                big.append(f"{f.relative_to(ROOT)} ({n})")
    assert not big, f"{MAX_LINES}줄을 넘었다. 기능별로 나눌 것: " + ", ".join(big)


def test_one_translation_table():
    """파이썬 쪽 번역 표는 locales/*.json 한 벌. 예전에 i18n.py(19개 언어)와 explain._KO가
    따로 있어 알림 제목이 세 곳에 흩어졌다. 파이썬 파일 안에 번역 사전을 다시 만들지 말 것."""
    import re
    src = ROOT / "src" / "epokio"
    codes = "KO|JA|ES|FR|DE|VI|ZH_HANS|ZH_HANT|PT_BR|EN"
    tables = [f"{f.name}:{m}" for f in src.rglob("*.py")
              for m in re.findall(rf"^(_?(?:{codes}))\s*=\s*\{{", f.read_text(encoding="utf-8"), re.M)]
    assert not tables, tables
    langs = sorted(p.stem for p in (src / "locales").glob("*.json"))
    assert langs, "locales 폴더가 비었다"


def test_feature_routes_live_in_api():
    """새 기능의 HTTP 요청은 api/ 모듈에. agent.py가 다시 커지지 않게"""
    text = (ROOT / "src" / "epokio" / "agent.py").read_text(encoding="utf-8")
    for route in ("/review/", "/sweeps", "/models", "/data-diff"):
        assert f'"{route}' not in text, f"{route} 처리가 agent.py로 돌아왔다(api/로)"


def test_design_tokens_are_generated_from_source():
    """DesignTokens.swift · web/tokens.css 는 design/tokens.json에서 만든다(손으로 고치면 어긋난다)"""
    import subprocess, sys
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "design_tokens.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + " → python3 tools/design_tokens.py"


def test_no_raw_system_colors_in_swift():
    """색은 뜻으로(docs/DESIGN.md): .good·.warn·.bad·.mixup·.gold·.brand. 시스템 색을 직접 쓰지 않는다.
    accentColor도 금지: .tint(.brand)를 걸어도 Color.accentColor는 시스템 파랑으로 남는다(2026-09-22 학습 화면에서 발견)"""
    import re
    pat = re.compile(r"(?<![A-Za-z0-9_])\.(green|orange|red|purple|yellow|accentColor)\b|\bColor\.(green|orange|red|purple|yellow|accentColor)\b")
    bad = []
    for f in (ROOT / "mac" / "Sources" / "Epokio").glob("*.swift"):
        if f.name == "DesignTokens.swift":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line.split("//")[0]):
                bad.append(f"{f.name}:{i}")
    assert not bad, "시스템 색 직접 사용: " + ", ".join(bad[:10])


def test_no_raw_animation_speeds_in_swift():
    """움직임은 Motion 토큰만(docs/DESIGN.md §5). `.smooth(duration: 0.9)`처럼 새 속도를 만들지 않는다.
    필요하면 design/tokens.json에 역할을 하나 더한다(2026-09-22: 진행률 속도가 0.55·0.6·0.8로 흩어져 있었다)"""
    import re
    pat = re.compile(r"\.(snappy|smooth|spring|bouncy|easeInOut|easeIn|easeOut|linear)\(duration:")
    bad = []
    for f in (ROOT / "mac" / "Sources" / "Epokio").glob("*.swift"):
        if f.name == "DesignTokens.swift":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("//")[0]
            if pat.search(code) and "repeatForever" not in code:     # 끝없는 장식 반복(숨쉬기·빛줄기)만 예외
                bad.append(f"{f.name}:{i}")
    assert not bad, "Motion 토큰 대신 속도를 직접 씀: " + ", ".join(bad[:10])


def test_repeat_forever_is_never_started_with_withAnimation():
    """withAnimation(… .repeatForever)은 같은 갱신의 모든 변화(부모 화면의 전환·배치)까지 영원히 반복시킨다.
    도는 학습을 고르면 상세 화면이 줄어든 채 멈춰 보였다(2026-09-22). 반복은 `.animation(…, value:)`로 그 한 겹에만"""
    import re
    bad = []
    for f in (ROOT / "mac" / "Sources" / "Epokio").glob("*.swift"):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"withAnimation\(.*repeatForever", line.split("//")[0]):
                bad.append(f"{f.name}:{i}")
    assert not bad, "withAnimation(repeatForever): " + ", ".join(bad)


def test_web_motion_uses_tokens():
    """웹도 움직임은 토큰(var(--m-…))만. 끝없이 도는 장식(infinite)만 예외(2026-09-22: .1s·.15s·.2s·.25s·.5s·.9s가 흩어져 있었다)"""
    import re
    css = (ROOT / "src" / "epokio" / "web" / "style.css").read_text(encoding="utf-8")
    bad = [f"style.css:{i}" for i, l in enumerate(css.splitlines(), 1)
           if ("transition" in l or "animation" in l) and "infinite" not in l and re.search(r"(?<![\w.-])\d*\.\d+s\b", l)]
    assert not bad, "토큰 대신 시간을 직접 씀: " + ", ".join(bad[:10])
    assert "prefers-reduced-motion" in css and ":focus-visible" in css


def test_no_system_link_style():
    """시스템 `.buttonStyle(.link)`는 브랜드색을 따르지 않고 파랗다. BrandLink()를 쓴다(2026-09-22)"""
    bad = [f"{f.name}:{i}" for f in (ROOT / "mac" / "Sources" / "Epokio").glob("*.swift")
           for i, l in enumerate(f.read_text(encoding="utf-8").splitlines(), 1) if "buttonStyle(.link)" in l.split("//")[0]]
    assert not bad, ", ".join(bad)
