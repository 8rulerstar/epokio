"""tools/l10n_keys.py의 파일 검사(누락·중복·포맷 지정자). 컴파일러 없이 문자열만으로 돈다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import l10n_keys as L  # noqa: E402


def test_specs_order_and_position():
    assert L.specs("%@ of %lld") == [(1, "@"), (2, "lld")]
    assert L.specs("%2$lld / %1$@") == [(1, "@"), (2, "lld")]
    assert L.specs("50% or more, 100%%") == []


def test_check_reports_missing_duplicate_format():
    text = '"A %@" = "B";\n"C" = "D";\n"C" = "E";\n"%d of %@" = "%2$@ %1$d";\n'
    r = L.check("xx", {"A %@", "C", "%d of %@", "New"}, text)
    assert r["missing"] == ["New"]
    assert r["duplicate"] == ["C"]
    assert [k for k, _ in r["format"]] == ["A %@"]


def test_real_files_parse():
    for lang in L.langs():
        assert L.table(lang), lang


def test_same_as_english_is_a_warning_with_exceptions():
    text = '"Format" = "Format";\n"Save" = "Save";\n"CPU" = "CPU";\n"best.pt" = "best.pt";\n"Open" = "Öffnen";\n'
    ks = {"Format", "Save", "CPU", "best.pt", "Open"}
    r = L.check("xx", ks, text, same=True)
    assert r["warn_same"] == ["Format", "Save"]        # 고유명사·파일명은 빠진다
    assert r["missing"] == [] and r["duplicate"] == [] and r["format"] == []
    assert "warn_same" not in L.check("xx", ks, text)  # 기본값에서는 아예 안 센다
