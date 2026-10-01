"""agent 문장 번역: 코드의 tr("...") 원문이 한국어 표에 전부 있는지, 자리 이름이 맞는지."""
import ast
import re
from pathlib import Path

from epokio import msg

SRC = Path(__file__).resolve().parent.parent / "src" / "epokio"


def _templates():
    out = set()
    for f in SRC.glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args:
                a = node.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    out.add(a.value)
                elif isinstance(a, ast.Name) and a.id == "FOOTNOTE":
                    from epokio.report import FOOTNOTE
                    out.add(FOOTNOTE)
    from epokio.diagnose import RULES                   # 표에 두고 돌려줄 때 tr(제목)·tr(고칠 방법)
    for _, title, fix in RULES:
        out.update((title, fix))
    return out


def test_every_message_has_korean():
    missing = sorted(t for t in _templates() if t not in msg.KO)
    assert not missing, missing


def test_placeholders_match():
    field = re.compile(r"\{(\w+)")
    for en, ko in msg.KO.items():
        assert set(field.findall(en)) == set(field.findall(ko)), en


def test_header_picks_language():
    msg.set_from_header("ko-KR,ko;q=0.9,en;q=0.8")
    assert msg.tr("Leaderboard") == "순위표"
    msg.set_from_header(None)
    assert msg.tr("Leaderboard") == "Leaderboard"


def test_every_language_is_complete():
    """locales/*.json은 en.json과 키가 같아야 한다. 빠지면 그 언어에서 영어가 새어 나온다."""
    en = msg.TABLE["en"]
    for lang in msg.LANGS:
        assert set(msg.TABLE[lang]) == set(en), (lang, sorted(set(en) - set(msg.TABLE[lang])))


def test_placeholders_match_in_every_language():
    field = re.compile(r"\{(\w+)")
    for lang in msg.LANGS:
        for en, s in msg.TABLE[lang].items():
            assert set(field.findall(en)) == set(field.findall(s)), (lang, en)


def test_english_table_is_the_原문():
    for k, v in msg.TABLE["en"].items():
        assert k == v, k


def test_header_picks_script_and_region():
    """zh와 pt는 지역을 떼면 표를 고를 수 없다. 옛 방식(앞 두 글자만)으로는 못 갈랐다."""
    for header, want in [("zh-TW", "zh-Hant"), ("zh-CN", "zh-Hans"), ("zh", "zh-Hans"),
                         ("pt-BR,pt;q=0.9", "pt-BR"), ("pt", "pt-BR"), ("ja-JP", "ja"),
                         ("de-AT", "de"), ("xx-YY", "en"), ("", "en")]:
        msg.set_from_header(header)
        assert msg._lang.get() == want, (header, msg._lang.get())
    msg.set_from_header(None)


def test_tr_translates_in_each_language():
    for lang in msg.LANGS:
        msg.set_from_header(lang)
        got = msg.tr("Best epoch")
        assert got == msg.TABLE[lang]["Best epoch"] and got
    msg.set_from_header(None)


def test_explain_uses_the_shared_table():
    """explain.py가 자체 _KO 표를 다시 갖지 않는지. 예전에 검사망 밖에 있었다."""
    from epokio import explain
    assert not hasattr(explain, "_KO") and not hasattr(explain, "_t")
    msg.set_from_header("ja")
    assert msg.tr("No clear problem showed up in the curves.") != "No clear problem showed up in the curves."
    msg.set_from_header(None)


def test_diagnose_follows_the_request_language():
    """실패 원인은 웹·맥 화면 언어로 와야 한다(영어만 오면 한국어 화면 카드 안에 섞인다)."""
    from epokio.diagnose import diagnose
    log = "Traceback...\nModuleNotFoundError: No module named 'cv2'\n"
    msg.set_from_header("ko")
    try:
        (hit,) = diagnose(log)
        assert hit["title"] == "파이썬 패키지가 빠져 있습니다"
        assert hit["fix"].endswith("python -m pip install cv2") and "설치하세요" in hit["fix"]
    finally:
        msg.set_from_header(None)
    (hit,) = diagnose(log)
    assert hit["title"] == "A Python package is missing"


def test_korean_particles_follow_the_word_before_them():
    """★'{b:.3f}로'가 '4.860로'로, '{m}이(가)'가 괄호째 화면에 나왔다. 숫자·영문은 읽는 소리 기준"""
    from epokio.msg import josa
    assert josa("4.860(으)로 올랐습니다") == "4.860으로 올랐습니다"          # 영 → 받침
    assert josa("0.85(으)로") == "0.85로" and josa("17(으)로") == "17로"      # 오 · 칠(ㄹ 받침은 '로')
    assert josa("mAP50-95이(가) 높다") == "mAP50-95가 높다"
    assert josa("val_loss은(는)") == "val_loss는" and josa("val_acc1을(를)") == "val_acc1을"
    assert josa("defect_det과(와) 같은") == "defect_det와 같은" and josa("학습(으)로") == "학습으로"
