"""맥과 윈도우 사이 한글(유니코드) 정규화 방지.

맥은 파일명을 NFD(자모 분리)로 만드는 경우가 있고, 윈도우와 대부분의 프로그램은 NFC다.
화면에는 똑같이 보여도 문자열 비교가 틀어져 "파일을 못 찾음"이 조용히 난다.
  ★2026-09-21 실측: 폴더명 379개가 전부 NFD, labels.csv는 전부 NFC → 정규화 없이 대조하면 379/379 불일치

규칙
  1. agent가 내보내는 모든 문자열(경로, 이름)은 NFC로 통일한다
  2. 받은 경로가 그대로 없으면 NFC·NFD 두 형태를 다 시도해 실제 파일을 찾는다
  3. 한 폴더 안에 두 형태가 섞였는지 검사할 수 있다 (데이터셋 점검용)
"""
from __future__ import annotations

import os
import unicodedata
from pathlib import Path


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def deep_nfc(obj):
    """JSON으로 나갈 값 전체를 NFC로."""
    if isinstance(obj, str):
        return nfc(obj)
    if isinstance(obj, dict):
        return {deep_nfc(k): deep_nfc(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [deep_nfc(v) for v in obj]
    return obj


def is_network(path: str) -> bool:
    """\\\\서버\\공유 · //서버/공유 같은 네트워크 경로인가. 파일 시스템을 건드리지 않고 글자만 본다.
    ★윈도우는 이런 경로를 exists()로 보기만 해도 그 서버에 로그인을 시도하며 NTLM 해시를 보낸다.
      토큰 없이 받는 /file·/run이 그렇게 해서, 같은 네트워크의 누군가가 해시를 빼 갈 수 있었다"""
    p = str(path).replace("\\", "/")
    # ★'\??\UNC\서버\공유'(NT 경로)도 같은 곳으로 간다. //로만 막았더니 이걸로 우회됐다(2026-09-26 리뷰에서 실측).
    #   '\\?\', '\\.\' 는 //로 시작해 이미 걸린다. 드라이브 문자로 시작하지 않는 이상한 접두어는 전부 네트워크로 본다
    return p.startswith("//") or p.startswith("/??/") or p.startswith("/?/") or p.lower().startswith("/device/")


def resolve(path: str) -> str:
    """받은 경로가 실제로 있는 형태를 찾는다. 없으면 원래 값을 돌려준다."""
    if os.path.exists(path):
        return path
    for form in ("NFC", "NFD"):
        alt = unicodedata.normalize(form, path)
        if os.path.exists(alt):
            return alt
    # 경로 조각마다 형태가 다를 수 있다 (상위는 NFD, 파일은 NFC). 한 칸씩 맞춰 내려간다
    p = Path(path)
    cur = Path(p.anchor) if p.anchor else Path(".")
    for part in p.parts[1 if p.anchor else 0:]:
        try:
            names = {nfc(n): n for n in os.listdir(cur)}
        except OSError:
            return path
        real = names.get(nfc(part))
        if real is None:
            return path
        cur = cur / real
    return str(cur)


def mixed_forms(folder: str) -> dict:
    """폴더 아래 이름들이 NFC·NFD로 섞였는지."""
    nfc_n = nfd_n = 0
    samples = []
    for root, dirs, files in os.walk(folder):
        for n in dirs + files:
            if n == nfc(n) and n != unicodedata.normalize("NFD", n):
                nfc_n += 1
            elif n != nfc(n):
                nfd_n += 1
                if len(samples) < 5:
                    samples.append(os.path.join(root, n))
    return {"nfc": nfc_n, "nfd": nfd_n, "mixed": nfc_n > 0 and nfd_n > 0, "nfd_samples": samples}
