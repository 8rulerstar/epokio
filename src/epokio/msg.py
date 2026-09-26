"""agent가 앱에 돌려주는 문장(데이터셋 검진, 보고서 해설)의 번역.

키는 영어 원문 틀이고 {자리}는 str.format으로 채운다. 요청마다 앱이 보낸 Accept-Language로
언어를 정한다(agent.py). 표에 없는 문장은 영어로 나간다.
알림 제목(notify.KINDS)·트레이 문구는 i18n.py(짧은 키)가 번역한다. 앱이 언어를 보내 주지 않는 곳이라서.

★문장 번역 표는 `locales/<코드>.json` 한 벌만 둔다(explain._KO는 지웠다).
  코드는 맥 앱의 .lproj 이름과 맞춘다: en, ko, ja, zh-Hans, zh-Hant, es, fr, de, pt-BR, vi.
  용어·말투도 그쪽에 맞춘다(mac/Resources/<코드>.lproj/Localizable.strings).

새 문장을 넣을 때: locales/en.json에 원문을 그대로 키·값으로 넣고 각 언어 파일에 번역을 더한다.
빠진 것·자리 이름 불일치 확인은 `python tools/py_msgs.py --strict`.
"""
from __future__ import annotations

import contextvars
import json
from pathlib import Path

_DIR = Path(__file__).with_name("locales")

# 지원 언어. en은 원문이라 표가 비어도 된다
LANGS = ("en", "ko", "ja", "zh-Hans", "zh-Hant", "es", "fr", "de", "pt-BR", "vi")

# Accept-Language의 첫 태그(소문자) → 우리 코드. 여기 없으면 앞의 언어 부분만 보고 고른다.
# ★zh와 pt는 지역을 떼면 어느 표를 쓸지 정할 수 없어 여기서 갈라야 한다
_ALIAS = {
    "zh": "zh-Hans", "zh-cn": "zh-Hans", "zh-sg": "zh-Hans", "zh-hans": "zh-Hans",
    "zh-tw": "zh-Hant", "zh-hk": "zh-Hant", "zh-mo": "zh-Hant", "zh-hant": "zh-Hant",
    "pt": "pt-BR", "pt-br": "pt-BR", "pt-pt": "pt-BR",
}

_lang: contextvars.ContextVar[str] = contextvars.ContextVar("lang", default="en")
_tag: contextvars.ContextVar[str] = contextvars.ContextVar("tag", default="en")   # zh-Hans 처럼 전체


def _load(code: str) -> dict[str, str]:
    f = _DIR / f"{code}.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):       # 파일이 빠져도 영어로 굴러가야 한다. 죽이지 않는다
        return {}


TABLE: dict[str, dict[str, str]] = {c: _load(c) for c in LANGS}

KO = TABLE["ko"]        # 옛 이름. tests/test_msg.py와 밖의 코드가 이 이름을 쓴다


def resolve(tag: str | None) -> str:
    """'ko-KR' · 'zh-TW' · 'pt' → 우리 언어 코드. 모르면 'en'."""
    t = (tag or "").strip().lower()
    if t in _ALIAS:
        return _ALIAS[t]
    for c in LANGS:                     # 'zh-Hans' 같은 정확한 일치를 여기서 잡는다
        if c.lower() == t:
            return c
    base = t.split("-")[0]              # 'ko-kr' → 'ko'
    if base in _ALIAS:
        return _ALIAS[base]
    for c in LANGS:
        if c.lower() == base:
            return c
    return "en"


def set_from_header(accept_language: str | None) -> None:
    """'ko-KR,ko;q=0.9,en;q=0.8' 에서 첫 언어만 본다."""
    first = (accept_language or "").split(",")[0].split(";")[0].strip()
    _tag.set(first or "en")
    _lang.set(resolve(first))


def tag() -> str:
    """이 요청을 보낸 앱의 언어 태그 그대로(웹후크 문구 언어로 저장한다)"""
    return _tag.get()


def tr(template: str, **kw) -> str:
    s = TABLE.get(_lang.get(), {}).get(template, template)
    return s.format(**kw) if kw else s
