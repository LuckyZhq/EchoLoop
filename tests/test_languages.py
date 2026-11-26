"""Learner languages: prompts, definitions, annotation, meanings and the level test for non-Chinese learners."""
import json

import pytest

from echoloop import languages, meanings, placement, translate
from echoloop.annotate import annotate_cues
from echoloop.dictionary import Dictionary, english_definition
from echoloop.settings import TranslationSettings

API = TranslationSettings(engine="api", base_url="https://api.example.com/v1", model="m", api_key="k", provider="custom")


@pytest.fixture(scope="module")
def dic():
    return Dictionary()


def test_language_registry():
    assert languages.stored("zh-TW") == "zh-CN" and languages.stored("es") == "es"
    assert languages.is_chinese("zh-TW") and not languages.is_chinese("ja")
    assert languages.english_name("vi") == "Vietnamese"
    assert languages.LANGUAGES["en"]["argos"] is None  # English-only: nothing to translate


def test_prompts_name_the_target_language():
    assert "into Vietnamese" in translate.aligned_instructions("vi")
    assert "1-4 words" in translate.aligned_instructions("es") and "characters" in translate.aligned_instructions("zh-CN")
    assert "natural Japanese" in translate.plain_instructions("ja")


def test_tidy_only_rewrites_chinese_punctuation():
    assert translate._tidy("你好 , 世界", "zh-CN") == "你好，世界"
    assert translate._tidy("  Hola,   mundo ", "es") == "Hola, mundo"


def test_aligned_reply_accepts_new_and_old_keys(monkeypatch):
    replies = iter(['[{"t": "Hola mundo", "chunks": [["Hello", "Hola"], ["world", "mundo"]]}]',
                    '[{"zh": "你好世界", "chunks": []}]'])
    monkeypatch.setattr(translate, "_completion", lambda lines, settings, instructions: next(replies))
    assert translate.translate_batch_aligned(["Hello world"], API, "es")[0][0] == "Hola mundo"
    assert translate.translate_batch_aligned(["Hello world"], API, "zh-CN")[0][0] == "你好世界"


def test_english_only_learners_get_no_translation():
    cues = [{"text": "Hello world", "zh": "旧的", "seg": [{"s": 0, "e": 5, "zh": "x"}]}]
    assert translate.translate_cues(cues, lang="en") == "none"
    assert cues[0]["zh"] == "" and "seg" not in cues[0]


def test_english_definitions(dic):
    assert english_definition("n. a covering\\nv. to cover", "VERB").startswith("v. to cover")
    # proper-noun senses (WordNet) are skipped when there is an ordinary one
    assert "songwriter" not in dic.word("foster", "VERB")["def"]
    assert english_definition("") == ""


def test_annotation_follows_the_learner_language(dic):
    zh = [{"text": "Cities must mitigate traffic congestion."}]
    es = [{"text": "Cities must mitigate traffic congestion."}]
    annotate_cues(zh, dic, lang="zh-CN")
    annotate_cues(es, dic, lang="es")
    note_zh = zh[0]["notes"]["w:mitigate"]
    note_es = es[0]["notes"]["w:mitigate"]
    assert "缓和" in note_zh["zh"] and note_es["zh"] == note_es["def"] and note_es["def"].startswith("v.")
    assert zh[0]["gl"] and es[0]["gl"] == []          # word-by-word glosses come from the Chinese dictionary
    assert "雅思" in note_zh["note"] and note_es["note"] in ("", "TOEFL / IELTS / GRE", "IELTS / GRE", "TOEFL / IELTS")


def test_meanings_are_translated_once_and_kept(tmp_path, monkeypatch, dic):
    monkeypatch.setattr(meanings, "MEANINGS_DIR", tmp_path)
    meanings._caches.clear()
    calls = []

    def fake(items, settings, lang, log):
        calls.append([i["w"] for i in items])
        return [f"{lang}:{i['w']}" for i in items]

    monkeypatch.setattr(translate, "translate_meanings", fake)
    cues = [{"text": "Cities must mitigate traffic congestion."}]
    annotate_cues(cues, dic, lang="es")
    meanings.fill_notes(cues, "es", API)
    note = cues[0]["notes"]["w:mitigate"]
    assert note["zh"] == "es:mitigate" and note["api"] is True
    assert json.loads((tmp_path / "es.json").read_text(encoding="utf-8"))["mitigate"] == "es:mitigate"
    # annotating again (e.g. a new annotation format) keeps the translated meaning; no second API call
    annotate_cues(cues, dic, lang="es")
    meanings.fill_notes(cues, "es", API)
    assert cues[0]["notes"]["w:mitigate"]["zh"] == "es:mitigate" and len(calls) == 1
    # lookups reuse the cache; without an API the English definition is the fallback
    assert meanings.lookup({"en": "mitigate", "zh": "缓和", "def": "v. lessen"}, "es", None)["zh"] == "es:mitigate"
    assert meanings.lookup({"en": "rare", "zh": "稀有", "def": "a. not common"}, "ja", None)["zh"] == "a. not common"
    assert meanings.lookup({"en": "rare", "zh": "稀有", "def": "a. not common"}, "zh-TW", None)["zh"] == "稀有"


def test_level_test_options_in_the_learner_language(tmp_path, monkeypatch, dic):
    monkeypatch.setattr(meanings, "MEANINGS_DIR", tmp_path)
    meanings._caches.clear()
    monkeypatch.setattr(translate, "translate_meanings",
                        lambda items, settings, lang, log: [f"[{lang}] {i['w']}" for i in items])
    qs = placement.spot_check(dic, set(), seed=2, lang="ko", settings=API)
    assert qs and all(len(q["options"]) == 4 for q in qs)
    assert all(q["options"][q["answer"]] == f"[ko] {q['en']}" for q in qs)
    # offline, the meanings fetched before are reused from the cache
    cached = placement.spot_check(dic, set(), seed=2, lang="ko", settings=None)
    assert all(q["options"][q["answer"]] == f"[ko] {q['en']}" for q in cached)
    # offline with nothing cached: English definitions
    monkeypatch.setattr(meanings, "MEANINGS_DIR", tmp_path / "empty")
    meanings._caches.clear()
    offline = placement.spot_check(dic, set(), seed=2, lang="ko", settings=None)
    assert all(not opt.startswith("[ko]") for q in offline for opt in q["options"])
    assert any(opt[:3] in ("n. ", "v. ", "a. ", "r. ", "s. ") for q in offline for opt in q["options"])
