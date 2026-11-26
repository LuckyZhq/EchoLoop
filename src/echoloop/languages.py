"""Learner languages: what subtitles, phrase glosses and word meanings are translated into.

Each entry: native name (shown in menus), English name (used in API prompts), Argos Translate code for
offline subtitle translation (None = no offline model), and whether the offline Chinese dictionary applies.

Chinese is special: the ECDICT dictionary is English→Chinese, so Chinese learners get offline meanings and
word-by-word glosses. Other languages get English definitions offline and native meanings through the API.
Traditional Chinese is stored as Simplified and converted on display (Taiwan wording), so the two switch
instantly; every other language needs the video to be translated again.
"""
from __future__ import annotations

LANGUAGES: dict[str, dict] = {
    "zh-CN": {"name": "简体中文", "english": "Simplified Chinese", "argos": "zh"},
    "zh-TW": {"name": "繁體中文（台灣）", "english": "Traditional Chinese (Taiwan)", "argos": "zh"},
    "es": {"name": "Español", "english": "Spanish", "argos": "es"},
    "pt": {"name": "Português", "english": "Portuguese (Brazilian)", "argos": "pt"},
    "fr": {"name": "Français", "english": "French", "argos": "fr"},
    "de": {"name": "Deutsch", "english": "German", "argos": "de"},
    "ja": {"name": "日本語", "english": "Japanese", "argos": "ja"},
    "ko": {"name": "한국어", "english": "Korean", "argos": "ko"},
    "vi": {"name": "Tiếng Việt", "english": "Vietnamese", "argos": "vi"},
    "id": {"name": "Bahasa Indonesia", "english": "Indonesian", "argos": "id"},
    "th": {"name": "ไทย", "english": "Thai", "argos": "th"},
    "tr": {"name": "Türkçe", "english": "Turkish", "argos": "tr"},
    "ru": {"name": "Русский", "english": "Russian", "argos": "ru"},
    "ar": {"name": "العربية", "english": "Arabic", "argos": "ar", "rtl": True},
    "hi": {"name": "हिन्दी", "english": "Hindi", "argos": "hi"},
    "en": {"name": "English (English-only)", "english": "English", "argos": None},
}
DEFAULT = "zh-CN"


def valid(code) -> bool:
    return code in LANGUAGES


def stored(code: str) -> str:
    """The language translations are stored in: Traditional Chinese is kept as Simplified."""
    return "zh-CN" if code in ("zh-CN", "zh-TW") else code


def is_chinese(code: str | None) -> bool:
    return stored(code or DEFAULT) == "zh-CN"


def english_name(code: str) -> str:
    return LANGUAGES.get(code, LANGUAGES[DEFAULT])["english"]


def native_name(code: str) -> str:
    return LANGUAGES.get(code, LANGUAGES[DEFAULT])["name"]


def options() -> dict[str, str]:
    return {code: info["name"] for code, info in LANGUAGES.items()}
