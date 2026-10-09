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
    from epokio.sysrec import _IDLE_TIP_OTHER, _IDLE_TIPS   # GPU가 놀 때 해 볼 것(프레임워크마다, tr(표의 값))
    out.update(_IDLE_TIPS.values())
    out.add(_IDLE_TIP_OTHER)
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


def test_tray_menu_and_phone_alert_bodies_are_translated():
    """★윈도우 트레이 메뉴·툴팁과 폰 알림 본문(디스크·GPU 경고)이 일본어·중국어·스페인어 등 8개 언어에서 영어로 남았고,
    번체 중국어 표에 간체 글자(小时·轮次)가, 스윕 중단 알림에 '스캔'(扫描)이 있었다"""
    from epokio import i18n
    keys = [i18n.PHRASES[k] for k in i18n.PHRASES if k.startswith(("tray.", "info.", "menu."))]
    keys += ["{gb} GB free on the disk with {folder}", "{gpu} at {c} \u00b0C", "{gpu} memory {used} of {total} GB"]
    same_ok = {("fr", "Notifications"), ("es", "GPU %"), ("fr", "GPU %"), ("de", "GPU %"), ("pt-BR", "GPU %"), ("vi", "GPU %"),
               ("ja", "GPU %"), ("zh-Hans", "GPU %"), ("zh-Hant", "GPU %"), ("zh-Hant", "Epoch"), ("vi", "Epoch")}   # 번체·베트남어는 맥 앱처럼 epoch을 그대로 쓴다
    for code in msg.LANGS:
        if code in ("en", "ko"):
            continue
        left = [k for k in keys if msg.TABLE[code].get(k, k) == k and (code, k) not in same_ok]
        assert not left, (code, left)
    hant = msg.TABLE["zh-Hant"]
    assert "小时" not in hant.values() and "轮次" not in hant.values()
    assert "扫参" in msg.TABLE["zh-Hans"]["Sweep stopped a run that fell behind"]
