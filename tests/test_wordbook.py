"""词书: lists from the dictionary's tags, what is left to learn, and examples from your own material."""
import json
import sqlite3
import threading
from types import SimpleNamespace

import pytest

from ielts_study import config, wordbook


@pytest.fixture
def dic(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(config, "ARTICLES_DIR", tmp_path / "articles")
    monkeypatch.setattr(wordbook, "_lists", {})
    monkeypatch.setattr(wordbook, "_forms", {})
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute("create table words(word text primary key, phonetic text, translation text, tag text, rank int, "
                "exchange text, definition text)")
    rows = [
        ("the", "", "art. 这", "", 1, "", ""),
        ("government", "", "n. 政府", "cet4 ielts", 124, "", ""),        # too basic for exam books
        ("abandon", "", "v. 放弃", "cet4 cet6 ielts", 2057, "d:abandoned/p:abandoned/i:abandoning/3:abandons", "v. give up"),
        ("abandoned", "", "a. 被抛弃的", "cet6", 4000, "0:abandon/1:d", ""),  # an inflected form: not listed
        ("sustainable", "", "a. 可持续的", "ielts", 6000, "", "a. capable of being sustained"),
        ("x-ray", "", "n. X 光", "cet4", 0, "", ""),                     # no frequency: last
        ("London", "", "n. 伦敦", "ielts", 900, "", ""),                  # proper noun
    ]
    con.executemany("insert into words values (?,?,?,?,?,?,?)", rows)

    def word(w, pos=None):
        r = con.execute("select word, phonetic, translation, rank, definition from words where word=?", (w,)).fetchone()
        return r and {"en": r[0], "phonetic": r[1], "zh": r[2], "rank": r[3], "def": r[4], "tag": "", "exchange": ""}

    return SimpleNamespace(_con=con, _lock=threading.Lock(), word=word)


def test_lists(dic):
    assert [w for w, _ in wordbook.words(dic, "core")] == ["the", "government", "abandon", "sustainable"]
    assert [w for w, _ in wordbook.words(dic, "cet4")] == ["abandon", "x-ray"]
    assert [w for w, _ in wordbook.words(dic, "ielts")] == ["abandon", "sustainable"]
    assert "abandoned" not in dict(wordbook.words(dic, "cet6"))
    assert wordbook.headword("abandoning") == "abandon"
    assert {b["id"] for b in wordbook.books_for("es")} == {"core", "ielts", "toefl"}  # no Chinese exams
    assert "cet4" in {b["id"] for b in wordbook.books_for("zh-TW")}


def test_remaining_skips_what_you_know(dic):
    profile = {"known": ["abandon"], "vocabSize": None, "current": None}
    assert wordbook.remaining(dic, "ielts", [], profile, True) == [("sustainable", 6000)]
    assert wordbook.remaining(dic, "ielts", [{"en": "Sustainable"}], {"known": []}, True) == [("abandon", 2057)]
    # a tested vocabulary of 3000 words: more frequent words are skipped when skipEasy is on
    assert [w for w, _ in wordbook.remaining(dic, "ielts", [], {"known": [], "vocabSize": 3000}, True)] == ["sustainable"]
    assert len(wordbook.remaining(dic, "ielts", [], {"known": [], "vocabSize": 3000}, False)) == 2
    p = wordbook.progress(dic, "ielts", [{"en": "abandon", "srs": {"ivl": 30}}], {"known": [], "vocabSize": 3000}, True)
    assert p == {"total": 2, "learning": 1, "mature": 1, "known": 0, "easy": 0, "left": 1}


def test_state_is_saved(dic):
    assert wordbook.load_state() == {"book": None, "skipEasy": True}
    assert wordbook.save_state({"book": "ielts", "skipEasy": False}) == {"book": "ielts", "skipEasy": False}
    assert wordbook.save_state({"book": "nope"})["book"] is None


def test_cards_use_your_own_sentences(dic):
    vdir = config.LIBRARY_DIR / "youtube-abc"
    vdir.mkdir(parents=True)
    (vdir / "data.json").write_text(json.dumps({"cues": [
        {"text": "Too short abandoned.", "start": 1},
        {"text": "They abandoned the plan after the storm.", "zh": "他们放弃了计划。", "start": 5.0},
    ]}), encoding="utf-8")
    abandon, sustainable = wordbook.cards(dic, "ielts", ["abandon", "sustainable"], "zh-CN", None)
    assert abandon["zh"] == "v. 放弃" and abandon["book"] == "ielts" and abandon["isNew"]
    assert abandon["sentence"] == "They abandoned the plan after the storm." and abandon["spans"] == [[5, 14]]
    assert abandon["videoId"] == "youtube-abc" and abandon["time"] == 5.0
    assert sustainable["sentence"] == ""  # none of your own: the page asks the API for one
    # another learner language without an API: the English definition stands in for the meaning
    (es,) = wordbook.cards(dic, "ielts", ["sustainable"], "es", None)
    assert es["zh"] == "a. capable of being sustained" and es["note"] == ""


def test_api_examples_are_cached(dic, monkeypatch):
    from ielts_study import translate

    calls = []

    def fake(items, settings, instructions):
        calls.append(items)
        return json.dumps([{"s": f"We need a {w} way to live.", "t": "译文"} for w in items])

    monkeypatch.setattr(translate, "_completion", fake)
    api = SimpleNamespace(engine="api")
    assert wordbook.api_examples(["sustainable"], "zh-CN", api)["sustainable"]["sentence"] == "We need a sustainable way to live."
    assert wordbook.api_examples(["sustainable"], "zh-CN", api)["sustainable"]["sentenceZh"] == "译文"
    assert len(calls) == 1  # second time from the cache
    assert wordbook.api_examples(["other"], "zh-CN", None) == {}  # no API: nothing
