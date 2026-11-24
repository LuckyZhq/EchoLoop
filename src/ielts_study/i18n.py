"""Languages: the interface language, and how stored Chinese content is shown.

Pages, scripts and server messages are written in Simplified Chinese and converted on the way out:
  * 繁體中文: OpenCC "s2twp" (Taiwan characters and phrasing: 视频→影片, 软件→軟體).
  * every other interface language: a table in i18n/<lang>.json maps each Chinese interface fragment to that
    language (English is written by hand; the others are generated from it with ui_translate.py). Text is cut
    into fragments the same way the tables were built and a fragment is replaced only when it matches an entry
    exactly, so content that is not in a table (example translations, dictionary meanings) stays as it is.
    A fragment missing from a language's table falls back to English.
Content (subtitles, meanings) is stored Simplified; a Traditional-Chinese learner sees it converted.
"""
from __future__ import annotations

import json
import re
import threading
from functools import lru_cache
from pathlib import Path

from . import languages
from .config import LIBRARY_DIR

UI_DIR = Path(__file__).with_name("i18n")
EN_PATH = UI_DIR / "en.json"
ZH_VARIANTS = {"zh-CN": "简体中文", "zh-TW": "繁體中文（台灣用語）"}
SETTINGS_PATH = LIBRARY_DIR / "language.json"  # next to profile.json, so a test library keeps its own
_lock = threading.Lock()


def ui_languages() -> dict[str, str]:
    names = {"zh-CN": "简体中文", "zh-TW": "繁體中文", "en": "English"}
    names.update({code: info["name"] for code, info in languages.LANGUAGES.items() if code not in names})
    return names


UI_LANGS = ui_languages()

CJK = r"　-〿一-鿿＀-￯—…·「-』"
_INNER = rf"{CJK}A-Za-z0-9 ,.%+×→←/!?\-:;'’（）()"
SEGMENT = re.compile(rf"[{_INNER}]*[{CJK}][{_INNER}]*")
HAN = re.compile(r"[一-鿿]")
EDGE = " ,.:;-/"
PUNCTUATION = {"。": ".", "，": ", ", "、": ", ", "：": ": ", "；": "; ", "！": "!", "？": "?"}
KEEP_CJK_PUNCTUATION = {"ja"}  # Japanese uses 。、 itself


# ------------------------------------------------------------------ settings
def _fresh_install() -> bool:
    if (LIBRARY_DIR / "profile.json").exists():
        return False
    return not any((d / "data.json").exists() for d in LIBRARY_DIR.iterdir()) if LIBRARY_DIR.exists() else True


def from_browser(accept: str | None) -> str | None:
    """The first supported language in an Accept-Language header ("es-MX,es;q=0.9,en;q=0.8" → "es")."""
    for part in (accept or "").split(","):
        tag = part.split(";")[0].strip().lower()
        if not tag:
            continue
        if tag.startswith("zh"):
            return "zh-TW" if any(x in tag for x in ("tw", "hk", "mo", "hant")) else "zh-CN"
        base = tag.split("-")[0]
        if base in UI_LANGS:
            return base
    return None


def _read() -> dict | None:
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _normalize(s: dict) -> dict:
    native = s.get("native")
    if not languages.valid(native):  # older files only had the Chinese variant
        native = s.get("zh") if s.get("zh") in ZH_VARIANTS else languages.DEFAULT
    return {"ui": s.get("ui") if s.get("ui") in UI_LANGS else "zh-CN", "native": native,
            # how stored Chinese is shown: Traditional only for a zh-TW learner
            "zh": "zh-TW" if native == "zh-TW" else "zh-CN"}


def load(accept: str | None = None) -> dict:
    """{"ui", "native", "zh"}. On a fresh install with nothing saved, the browser's language is used and saved,
    so a Spanish browser opens the app in Spanish. Existing libraries keep the Chinese default."""
    s = _read()
    if s is None:
        detected = from_browser(accept)
        if detected and _fresh_install():
            return save({"ui": detected, "native": detected})
        s = {}
    return _normalize(s)


def save(changes: dict) -> dict:
    with _lock:
        current = _normalize(_read() or {})
        if changes.get("ui") in UI_LANGS:
            current["ui"] = changes["ui"]
        if languages.valid(changes.get("native")):
            current["native"] = changes["native"]
        elif changes.get("zh") in ZH_VARIANTS:
            current["native"] = changes["zh"]
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ui": current["ui"], "native": current["native"]}, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(SETTINGS_PATH)
        return _normalize(current)


def public(accept: str | None = None) -> dict:
    return {**load(accept), "uiOptions": UI_LANGS, "nativeOptions": languages.options(),
            "englishNames": {code: info["english"] for code, info in languages.LANGUAGES.items()},
            "rtl": [code for code, info in languages.LANGUAGES.items() if info.get("rtl")]}


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


@lru_cache(maxsize=32)
def table(lang: str) -> dict:
    try:
        return json.loads((UI_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _translate_piece(piece: str, lang: str) -> str:
    core = piece.strip(EDGE)
    if not core:
        return piece
    start = piece.index(core)
    tables = (table(lang), table("en"))  # the language's own entry, else English
    for t in tables:
        if core in t:
            if t[core] == "":  # a Chinese measure word with no counterpart: drop it and its leading space
                return piece[start + len(core):]
            return piece[:start] + t[core] + piece[start + len(core):]
    # "个新词。": the fragment with its closing Chinese punctuation, which the tables list without it
    bare = core.rstrip("".join(PUNCTUATION))
    if bare != core:
        for t in tables:
            if bare in t:
                tail = core[len(bare):] if lang in KEEP_CJK_PUNCTUATION else \
                    "".join(PUNCTUATION[c] for c in core[len(bare):]).rstrip()
                return piece[:start] + t[bare] + tail + piece[start + len(core):]
    return piece


@lru_cache(maxsize=100_000)
def to_ui(text: str, lang: str) -> str:
    """Interface text in `lang`: fragments with a table entry are replaced, everything else stays."""
    if lang == "zh-CN":
        return text
    if lang == "zh-TW":
        return to_traditional(text)
    if not HAN.search(text):  # a lone Chinese full stop or comma between tags
        return text if lang in KEEP_CJK_PUNCTUATION else PUNCTUATION.get(text, text)

    def replace(m: re.Match) -> str:
        seg = m.group(0)
        out = _translate_piece(seg, lang)
        if out != seg:
            return out
        # Runtime text has numbers filled in ("使用 API 重新翻译 140 句字幕…"): try the parts between numbers.
        parts = re.split(r"(\d+(?:\.\d+)?)", seg)
        return "".join(p if i % 2 else _translate_piece(p, lang) for i, p in enumerate(parts))

    return SEGMENT.sub(replace, text)


def to_english(text: str) -> str:
    return to_ui(text, "en")


def ui_text(text: str, lang: str) -> str:
    return to_ui(text, lang)


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
    """A static page or script in the interface language (cached until the file or its table changes)."""
    raw = path.read_bytes()
    if lang == "zh-CN":
        return raw
    table_file = UI_DIR / f"{lang}.json"
    key = (str(path), path.stat().st_mtime_ns, lang, table_file.stat().st_mtime_ns if table_file.exists() else 0)
    if key not in _page_cache:
        text = raw.decode("utf-8")
        text = to_traditional(text) if lang == "zh-TW" else SEGMENT.sub(lambda m: to_ui(m.group(0), lang), text)
        rtl = ' dir="rtl"' if languages.LANGUAGES.get(lang, {}).get("rtl") else ""
        text = text.replace('<html lang="zh-CN">', f'<html lang="{lang}"{rtl}>')
        _page_cache[key] = text.encode("utf-8")
    return _page_cache[key]
