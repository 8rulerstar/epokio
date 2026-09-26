"""작은 YAML 읽기. Ultralytics data.yaml·args.yaml 정도를 읽는 용도.

PyYAML이 깔려 있으면 yaml.safe_load를 쓴다 (선택 의존성, `pip install epokio[yaml]`).
없으면 표준 라이브러리만으로 흔한 부분집합을 읽는다:
  들여쓴 매핑(여러 단계), 블록 리스트(`- a`), 흐름 리스트(`[a, b]`), 흐름 매핑(`{0: a, 1: b}`),
  여러 줄에 걸친 흐름 괄호, 따옴표('..', ".."), 줄 끝 주석, 정수·실수·null·true/false.
모르는 문법(앵커 &·별칭 *·태그 !·블록 문자열 |·>·문서 구분 ---)은 조용히 틀리지 않고
그 키를 빼고 경고를 남긴다.

load(text) -> (값, 경고 목록). 경고는 msg.tr()을 거친다(요청 언어).
"""
from __future__ import annotations

import re

from .msg import tr

_INT = re.compile(r"[-+]?\d+$")
_FLOAT = re.compile(r"[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")


class Unsupported(ValueError):
    pass


def load(text: str, *, use_pyyaml: bool = True):
    """(값, 경고) 를 돌려준다. 값은 보통 dict. 읽지 못하면 ({}, [이유])."""
    if use_pyyaml:
        try:
            import yaml  # type: ignore
        except ImportError:
            yaml = None
        if yaml is not None:
            try:
                data = yaml.safe_load(text)
            except yaml.YAMLError as e:
                return {}, [tr("YAML could not be read: {err}", err=str(e).splitlines()[0])]
            return ({} if data is None else data), []
    warns: list[str] = []
    try:
        lines = _logical_lines(text, warns)
        if not lines:
            return {}, warns
        value, i = _block(lines, 0, lines[0][0], warns)
        if i < len(lines):
            warns.append(tr("line {no}: unexpected indentation, ignored the rest", no=lines[i][2]))
    except Unsupported as e:
        return {}, warns + [str(e)]
    return value, warns


# ── 줄 다듬기 ──────────────────────────────────────

def _strip_comment(s: str) -> str:
    q = None
    for i, ch in enumerate(s):
        if q:
            if ch == q:
                q = None
        elif ch in "'\"" and (i == 0 or s[i - 1] in " \t[{,:"):
            q = ch
        elif ch == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
    return s.rstrip()


def _depth(s: str) -> int:
    d, q = 0, None
    for ch in s:
        if q:
            q = None if ch == q else q
        elif ch in "'\"":
            q = ch
        elif ch in "[{":
            d += 1
        elif ch in "]}":
            d -= 1
    return d


def _logical_lines(text: str, warns: list[str]) -> list[tuple[int, str, int]]:
    """(들여쓰기, 내용, 줄번호). 빈 줄·주석 제거, 열린 흐름 괄호는 다음 줄과 합친다."""
    out: list[tuple[int, str, int]] = []
    pending = None
    for no, raw in enumerate(text.splitlines(), 1):
        if raw.startswith("﻿"):
            raw = raw[1:]
        body = _strip_comment(raw)
        if not body.strip():
            continue
        if pending is not None:
            ind, acc, n0 = pending
            acc += " " + body.strip()
            pending = (ind, acc, n0) if _depth(acc) > 0 else None
            if pending is None:
                out.append((ind, acc, n0))
            continue
        stripped = body.lstrip(" ")
        if stripped.startswith("\t") or body.startswith("\t"):
            raise Unsupported(tr("line {no}: tab indentation is not supported", no=no))
        if stripped in ("---", "...") or stripped.startswith("--- ") or stripped.startswith("%"):
            if out:
                warns.append(tr("line {no}: only the first YAML document is read", no=no))
                break
            continue
        ind = len(body) - len(stripped)
        if _depth(stripped) > 0:
            pending = (ind, stripped, no)
        else:
            out.append((ind, stripped, no))
    if pending is not None:
        warns.append(tr("line {no}: bracket is never closed, ignored", no=pending[2]))
    return out


# ── 블록 ──────────────────────────────────────────

def _is_item(s: str) -> bool:
    return s == "-" or s.startswith("- ")


def _split_key(s: str) -> tuple[str, str] | None:
    q, d = None, 0
    for i, ch in enumerate(s):
        if q:
            q = None if ch == q else q
        elif ch in "'\"" and i == 0:
            q = ch
        elif ch in "[{":
            d += 1
        elif ch in "]}":
            d -= 1
        elif ch == ":" and d == 0 and (i + 1 == len(s) or s[i + 1] in " \t"):
            return s[:i].strip(), s[i + 1:].strip()
    return None


def _child(lines, i, ind, warns, allow_same_indent_list):
    """키 뒤가 비었을 때: 더 들여쓴 블록, 또는 같은 들여쓰기의 '- ' 리스트, 아니면 None."""
    if i < len(lines):
        nind, ns, _ = lines[i]
        if nind > ind or (allow_same_indent_list and nind == ind and _is_item(ns)):
            return _block(lines, i, nind, warns)
    return None, i


def _block(lines, i, ind, warns):
    if _is_item(lines[i][1]):
        return _seq(lines, i, ind, warns)
    return _map(lines, i, ind, warns)


def _seq(lines, i, ind, warns):
    out = []
    while i < len(lines) and lines[i][0] == ind and _is_item(lines[i][1]):
        rest, no = lines[i][1][1:].strip(), lines[i][2]
        i += 1
        if not rest:
            v, i = _child(lines, i, ind, warns, False)
            out.append(v)
        elif _split_key(rest) and not rest.startswith(("[", "{", "'", '"')):
            raise Unsupported(tr("line {no}: a mapping inside a '- ' list item is not supported", no=no))
        else:
            try:
                out.append(_inline(rest))
            except Unsupported as e:
                warns.append(tr("line {no}: {err}, item skipped", no=no, err=e))
    return out, i


def _map(lines, i, ind, warns):
    out: dict = {}
    while i < len(lines) and lines[i][0] == ind:
        s, no = lines[i][1], lines[i][2]
        if _is_item(s):
            break
        kv = _split_key(s)
        i += 1
        if kv is None:
            warns.append(tr("line {no}: not a 'key: value' line, ignored", no=no))
            continue
        k, rest = _scalar(kv[0]), kv[1]
        if not rest:
            v, i = _child(lines, i, ind, warns, True)
            out[k] = v
            continue
        try:
            out[k] = _inline(rest)
        except Unsupported as e:
            warns.append(tr("line {no}: {err}, key '{key}' skipped", no=no, err=e, key=k))
            while i < len(lines) and lines[i][0] > ind:   # 블록 문자열 몸통 건너뛰기
                i += 1
    while i < len(lines) and lines[i][0] > ind:
        warns.append(tr("line {no}: unexpected indentation, ignored", no=lines[i][2]))
        i += 1
    return out, i


# ── 한 줄 값 ──────────────────────────────────────

def _inline(s: str):
    s = s.strip()
    if s[:1] in ("&", "*", "!", "|", ">", "@", "`"):
        raise Unsupported(tr("'{ch}' syntax is not supported", ch=s[:1]))
    if s.startswith("[") or s.startswith("{"):
        v, j = _flow(s, 0)
        if s[j:].strip():
            raise Unsupported(tr("text after a closing bracket"))
        return v
    return _scalar(s)


def _flow(s: str, j: int):
    close = "]" if s[j] == "[" else "}"
    is_map = close == "}"
    out: list | dict = {} if is_map else []
    j += 1
    while True:
        while j < len(s) and s[j] in " \t,":
            j += 1
        if j >= len(s):
            raise Unsupported(tr("bracket is never closed"))
        if s[j] == close:
            return out, j + 1
        if s[j] in "[{":
            item, j = _flow(s, j)
        else:
            item, j = _flow_token(s, j, close)
        if is_map:
            k = item
            while j < len(s) and s[j] == " ":
                j += 1
            if j < len(s) and s[j] == ":":
                j += 1
                while j < len(s) and s[j] == " ":
                    j += 1
                if j < len(s) and s[j] in "[{":
                    val, j = _flow(s, j)
                else:
                    val, j = _flow_token(s, j, close)
            else:
                val = None
            out[k] = val
        else:
            out.append(item)


def _flow_token(s: str, j: int, close: str):
    if j < len(s) and s[j] in "'\"":
        q, k = s[j], j + 1
        while k < len(s):
            if s[k] == q:
                if q == "'" and k + 1 < len(s) and s[k + 1] == "'":
                    k += 2
                    continue
                if q == '"' and s[k - 1] == "\\":
                    k += 1
                    continue
                break
            k += 1
        return _scalar(s[j:k + 1]), k + 1
    k = j
    stops = ",:" + close if close == "}" else "," + close
    while k < len(s) and s[k] not in stops:
        k += 1
    if close == "}" and k < len(s) and s[k] == ":" and k + 1 < len(s) and s[k + 1] not in " \t,}":
        # 'a:b' 처럼 붙은 콜론은 값의 일부
        k2 = k + 1
        while k2 < len(s) and s[k2] not in ",}":
            k2 += 1
        return _scalar(s[j:k2]), k2
    return _scalar(s[j:k]), k


def _scalar(s: str):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return (s[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t")
                .replace("\\\\", "\\"))
    if s in ("", "~", "null", "Null", "NULL"):
        return None
    if s in ("true", "True", "TRUE"):
        return True
    if s in ("false", "False", "FALSE"):
        return False
    if _INT.match(s):
        return int(s)
    if _FLOAT.match(s):
        return float(s)
    return s
