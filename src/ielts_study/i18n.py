"""Languages: the interface (简体 / 繁體 / English) and the translation shown for content (简体 / 繁體·台灣).

Everything is stored in Simplified Chinese and converted on the way out, so switching is instant:
  * Traditional: OpenCC "s2twp" (Taiwan characters and phrasing: 视频→影片, 软件→軟體).
  * English interface: every Chinese interface fragment in pages, scripts and server messages has an entry in
    i18n_en.json. Text is cut into fragments the same way the table was built and a fragment is replaced only
    when it matches an entry exactly, so content that is not in the table (example translations, dictionary
    meanings) stays as it is.
"""
from __future__ import annotations

import json
import re
import threading
from functools import lru_cache
from pathlib import Path

from .config import LIBRARY_DIR

UI_LANGS = {"zh-CN": "简体中文", "zh-TW": "繁體中文", "en": "English"}
ZH_VARIANTS = {"zh-CN": "简体中文", "zh-TW": "繁體中文（台灣用語）"}
HTML_LANG = {"zh-CN": "zh-CN", "zh-TW": "zh-TW", "en": "en"}
SETTINGS_PATH = LIBRARY_DIR / "language.json"  # next to profile.json, so a test library keeps its own
EN_PATH = Path(__file__).with_name("i18n_en.json")
_lock = threading.Lock()

CJK = r"　-〿一-鿿＀-￯—…·「-』"
_INNER = rf"{CJK}A-Za-z0-9 ,.%+×→←/!?\-:;'’（）()"
SEGMENT = re.compile(rf"[{_INNER}]*[{CJK}][{_INNER}]*")
HAN = re.compile(r"[一-鿿]")
EDGE = " ,.:;-/"
PUNCTUATION = {"。": ".", "，": ", ", "、": ", ", "：": ": ", "；": "; ", "！": "!", "？": "?"}


# ------------------------------------------------------------------ settings
def load() -> dict:
    try:
        s = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    return {"ui": s.get("ui") if s.get("ui") in UI_LANGS else "zh-CN",
            "zh": s.get("zh") if s.get("zh") in ZH_VARIANTS else "zh-CN"}


def save(changes: dict) -> dict:
    with _lock:
        s = load()
        if changes.get("ui") in UI_LANGS:
            s["ui"] = changes["ui"]
        if changes.get("zh") in ZH_VARIANTS:
            s["zh"] = changes["zh"]
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
        tmp.replace(SETTINGS_PATH)
        return s


def public() -> dict:
    return {**load(), "uiOptions": UI_LANGS, "zhOptions": ZH_VARIANTS}


# ------------------------------------------------------------------ converters
_cc: dict = {}


def _opencc(config: str):
    if config not in _cc:
        from opencc import OpenCC

        _cc[config] = OpenCC(config)
    return _cc[config]


@lru_cache(maxsize=200_000)
def to_traditional(text: str) -> str:
    return _opencc("s2twp").convert(text) if HAN.search(text) else text


@lru_cache(maxsize=20_000)
def to_simplified(text: str) -> str:
    return _opencc("tw2sp").convert(text) if HAN.search(text) else text


@lru_cache(maxsize=1)
def _english() -> dict:
    return json.loads(EN_PATH.read_text(encoding="utf-8"))


def _translate_piece(piece: str, table: dict) -> str:
    core = piece.strip(EDGE)
    if not core:
        return piece
    start = piece.index(core)
    if core in table:
        if table[core] == "":  # a Chinese measure word with no English counterpart: drop it and its leading space
            return piece[start + len(core):]
        return piece[:start] + table[core] + piece[start + len(core):]
    # "个新词。": the fragment with its closing Chinese punctuation, which the table lists without it
    bare = core.rstrip("".join(PUNCTUATION))
    if bare != core and bare in table:
        tail = "".join(PUNCTUATION[c] for c in core[len(bare):]).rstrip()
        return piece[:start] + table[bare] + tail + piece[start + len(core):]
    return piece


@lru_cache(maxsize=50_000)
def to_english(text: str) -> str:
    """Replace interface fragments that have an English entry; leave everything else untouched."""
    if not HAN.search(text):
        return PUNCTUATION.get(text, text)  # a lone Chinese full stop or comma between tags
    table = _english()

    def replace(m: re.Match) -> str:
        seg = m.group(0)
        out = _translate_piece(seg, table)
        if out != seg:
            return out
        # Runtime text has numbers filled in ("使用 API 重新翻译 140 句字幕…"): try the parts between numbers.
        parts = re.split(r"(\d+(?:\.\d+)?)", seg)
        return "".join(p if i % 2 else _translate_piece(p, table) for i, p in enumerate(parts))

    return SEGMENT.sub(replace, text)


def ui_text(text: str, lang: str) -> str:
    if lang == "zh-TW":
        return to_traditional(text)
    if lang == "en":
        return to_english(text)
    return text


def content_text(text: str, variant: str) -> str:
    return to_traditional(text) if variant == "zh-TW" else text


def walk(value, fn):
    """Apply fn to every string inside JSON-like data (dict keys are left alone)."""
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, list):
        return [walk(v, fn) for v in value]
    if isinstance(value, dict):
        return {k: walk(v, fn) for k, v in value.items()}
    return value


# ------------------------------------------------------------------ pages
_page_cache: dict = {}


def page(path: Path, lang: str) -> bytes:
    """A static page or script in the interface language (cached until the file changes)."""
    raw = path.read_bytes()
    if lang == "zh-CN":
        return raw
    key = (str(path), path.stat().st_mtime_ns, lang)
    if key not in _page_cache:
        text = raw.decode("utf-8")
        text = to_traditional(text) if lang == "zh-TW" else _english_page(text)
        text = text.replace('<html lang="zh-CN">', f'<html lang="{HTML_LANG[lang]}">')
        _page_cache[key] = text.encode("utf-8")
    return _page_cache[key]


def _english_page(text: str) -> str:
    # comments are left as they are (they are not shown); everything else goes through the fragment table
    return SEGMENT.sub(lambda m: to_english(m.group(0)), text)
