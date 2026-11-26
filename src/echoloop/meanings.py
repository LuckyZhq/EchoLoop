"""Word and phrase meanings in the learner's language.

Chinese learners get the offline English→Chinese dictionary. For every other language the offline fallback is
the English definition; with an API configured, meanings are translated in batches and cached per language in
library/meanings/<lang>.json, so a word is only ever paid for once.
"""
from __future__ import annotations

import json
import threading

from . import languages
from .config import LIBRARY_DIR

MEANINGS_DIR = LIBRARY_DIR / "meanings"
_lock = threading.Lock()
_caches: dict[str, dict] = {}


def _path(lang: str):
    return MEANINGS_DIR / f"{lang}.json"


def _cache(lang: str) -> dict:
    if lang not in _caches:
        try:
            _caches[lang] = json.loads(_path(lang).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _caches[lang] = {}
    return _caches[lang]


def _remember(lang: str, found: dict) -> None:
    with _lock:
        cache = _cache(lang)
        cache.update({k.lower(): v for k, v in found.items() if v})
        MEANINGS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _path(lang).with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_path(lang))


def _api_settings(settings):
    return settings if settings is not None and settings.engine == "api" else None


def translate(items: list[tuple[str, str]], lang: str, settings, log=lambda m: None) -> dict:
    """{word: meaning} for [(word, sentence)] in `lang`: cached ones first, the rest through the API."""
    from .translate import translate_meanings

    lang = languages.stored(lang)
    cache = _cache(lang)
    out = {w: cache[w.lower()] for w, _ in items if w.lower() in cache}
    missing = list({w.lower(): (w, s) for w, s in items if w.lower() not in cache}.values())
    if missing and _api_settings(settings) and lang != "en":
        log(f"翻译 {len(missing)} 个生词的释义…")
        found = dict(zip((w for w, _ in missing),
                         translate_meanings([{"w": w, "s": s} for w, s in missing], settings, lang, log)))
        _remember(lang, found)
        out.update({w: m for w, m in found.items() if m})
    return out


def fill_notes(cues: list[dict], lang: str, settings, log=lambda m: None) -> None:
    """Replace English-definition meanings in the cues' notes with meanings in `lang` (cache, then API)."""
    lang = languages.stored(lang)
    if languages.is_chinese(lang) or lang == "en":
        return
    todo: dict[str, str] = {}  # word -> first sentence it appears in
    for cue in cues:
        for note in (cue.get("notes") or {}).values():
            if not note.get("api"):
                todo.setdefault(note["en"], cue["text"])
    if not todo:
        return
    found = translate(list(todo.items()), lang, settings, log)
    for cue in cues:
        for note in (cue.get("notes") or {}).values():
            meaning = found.get(note["en"])
            if meaning and not note.get("api"):
                note["zh"], note["api"] = meaning, True


def lookup(info: dict, lang: str, settings) -> dict:
    """A dictionary-lookup result (from Dictionary.lookup) with "zh" in the learner's language."""
    lang = languages.stored(lang)
    if languages.is_chinese(lang) or not info.get("en"):
        return info
    meaning = translate([(info["en"], "")], lang, settings).get(info["en"]) if lang != "en" else None
    return {**info, "zh": meaning or info.get("def") or "", "native": bool(meaning)}


def for_words(words: list[str], lang: str, settings, dictionary) -> dict:
    """Meanings for a list of dictionary forms, e.g. the level test's options: native if possible, else English."""
    lang = languages.stored(lang)
    found = translate([(w, "") for w in words], lang, settings) if lang != "en" else {}
    out = {}
    for w in words:
        info = dictionary.word(w) or {}
        out[w] = found.get(w) or info.get("def") or ""
    return out
