import os
import unicodedata

from epokio.textnorm import deep_nfc, mixed_forms, resolve


def test_resolve_finds_nfd_folder_from_nfc_input(tmp_path):
    real = tmp_path / unicodedata.normalize("NFD", "전주_0380")
    real.mkdir()
    (real / "a.jpg").write_text("x")
    asked = str(tmp_path / unicodedata.normalize("NFC", "전주_0380") / "a.jpg")
    got = resolve(asked)
    assert os.path.exists(got)


def test_deep_nfc():
    d = deep_nfc({"name": unicodedata.normalize("NFD", "학습"), "xs": [unicodedata.normalize("NFD", "한")]})
    assert d["name"] == unicodedata.normalize("NFC", "학습") and d["xs"][0] == "한"


def test_mixed_forms(tmp_path):
    (tmp_path / unicodedata.normalize("NFD", "가")).mkdir()
    (tmp_path / unicodedata.normalize("NFC", "나")).mkdir()
    r = mixed_forms(str(tmp_path))
    assert r["mixed"] and r["nfd"] == 1 and r["nfc"] == 1 and r["found"]
    (tmp_path / "ascii").mkdir()
    (tmp_path / "ascii" / "a.jpg").write_bytes(b"")
    assert mixed_forms(str(tmp_path / "ascii"))["found"] and not mixed_forms(str(tmp_path / "nope"))["found"]
