"""The word ledger: migration from the three old records, and one status for a word everywhere."""
import json
import time
import zipfile

import pytest

from echoloop import config, placement, review, words

NOW = 1_800_000_000


@pytest.fixture
def lib(tmp_path, monkeypatch):
    lib = tmp_path / "library"
    lib.mkdir()
    monkeypatch.setattr(config, "LIBRARY_DIR", lib)
    monkeypatch.setattr(placement, "LIBRARY_DIR", lib)
    monkeypatch.setattr(placement, "PROFILE_PATH", lib / "profile.json")
    return lib


def old_files(lib):
    vocab = [
        {"en": "inevitable", "type": "word", "videoId": "youtube-abc", "time": 12.5, "sentence": "It was inevitable.",
         "srs": {"due": NOW - 100, "ivl": 6, "ease": 2.5, "reps": 3, "lapses": 0, "last": NOW - 6 * 86400, "seen": NOW - 30 * 86400}},
        {"en": "abandon", "type": "word", "book": "ielts", "srs": {"due": NOW + 86400, "ivl": 30, "ease": 2.6, "reps": 5, "lapses": 1}},
        {"en": "take care of", "type": "phrase", "articleId": "a1", "sentenceIndex": 2},
        {"en": "Commute", "type": "word", "videoId": "youtube-abc", "srs": {"due": NOW - 5, "ivl": 1, "ease": 2.5, "reps": 1, "lapses": 0}},
    ]
    (lib / "vocab.json").write_text(json.dumps(vocab))
    (lib / "profile.json").write_text(json.dumps({"current": 6, "target": 7, "vocabSize": 4200, "known": ["commute", "crucial"]}))
    (lib / "wordbook.json").write_text(json.dumps({"book": "ielts", "skipEasy": False}))
    return vocab


def test_migration_reconciles(lib):
    vocab = old_files(lib)
    due_before = sum(1 for v in vocab if v.get("srs") and v["srs"]["due"] <= NOW and v["en"].lower() not in ("commute",))
    summary = words.migrate(now=NOW)
    items = words.load()
    # every saved word and every known word, once
    assert len(items) == len({v["en"].lower() for v in vocab} | {"commute", "crucial"}) == 5
    assert summary == {"words": 5, "known": 2, "due": due_before}
    by = {words.key(r["en"]): r for r in items}
    # review schedules come over untouched
    for v in vocab:
        assert by[v["en"].lower()].get("srs") == v.get("srs")
    assert by["inevitable"]["status"] == "learning" and by["inevitable"]["sources"] == ["video"]
    assert by["abandon"]["sources"] == ["ielts"] and by["take care of"]["sources"] == ["article"]
    assert by["commute"]["status"] == "known" and by["commute"]["sources"] == ["video", "marked"]
    assert by["crucial"] == {"en": "crucial", "type": "word", "status": "known", "sources": ["marked"], "added": NOW}
    # the old files: zipped, vocab.json renamed, the known list and skipEasy gone (with .bak copies)
    assert sorted(zipfile.ZipFile(lib / "backup-before-words-merge.zip").namelist()) == ["profile.json", "vocab.json", "wordbook.json"]
    assert not (lib / "vocab.json").exists() and (lib / "vocab.json.bak").exists()
    assert "known" not in json.loads((lib / "profile.json").read_text())
    assert json.loads((lib / "profile.json.bak").read_text())["known"] == ["commute", "crucial"]
    assert json.loads((lib / "wordbook.json").read_text()) == {"book": "ielts"}
    assert words.migrate() is None  # only once


def test_due_reviews_unchanged_by_migration(lib):
    vocab = old_files(lib)
    words.migrate(now=NOW)
    q = review.queue(words.load(), lib, now=NOW)
    # the known word is no longer reviewed; the other due word still is, with the same schedule
    assert [c["en"] for c in q["cards"] if not c["isNew"]] == ["inevitable"]
    assert [c["en"] for c in q["cards"] if c["isNew"]] == ["take care of"]


def test_fresh_library(lib):
    assert words.migrate() is None and words.load() == []


def test_known_is_the_same_everywhere(lib):
    old_files(lib)
    words.migrate(now=NOW)
    words.add({"en": "foster", "type": "word", "videoId": "youtube-abc", "sentence": "We foster growth."}, "video")
    assert "foster" not in placement.public_profile(words.load())["known"]
    assert any(c["en"] == "foster" for c in review.queue(words.load(), lib, now=NOW)["cards"])  # saved: straight into review
    words.set_known("Foster", True)  # ✓ 认识 in review
    items = words.load()
    assert "foster" in placement.public_profile(items)["known"]           # no longer marked as a hard word
    assert "foster" in words.taken(items)                                 # no longer offered by a 词书
    assert all(c["en"] != "foster" for c in review.queue(items, lib, now=NOW)["cards"])  # no longer reviewed
    words.set_known("foster", False)  # taken back: it was saved, so it is learned again
    assert words.find(words.load(), "foster")["status"] == "learning"
    words.set_known("crucial", False)  # only ever marked: the record goes
    assert words.find(words.load(), "crucial") is None


def test_saving_again_keeps_progress_and_adds_the_source(lib):
    words.add({"en": "abandon", "type": "word", "book": "ielts"}, "ielts")
    words.grade("abandon", "good", now=NOW)
    srs = words.find(words.load(), "abandon")["srs"]
    words.set_known("abandon", True)
    rec = words.add({"en": "Abandon", "type": "word", "videoId": "youtube-x", "sentence": "Abandon ship!"}, "video")
    assert rec["srs"] == srs and rec["status"] == "learning" and rec["sources"] == ["ielts", "marked", "video"]
    assert len(words.load()) == 1


def test_book_word_joins_on_first_answer(lib):
    assert words.grade("sustainable", "good") is None  # not in the ledger and not a book word
    rec = words.grade("sustainable", "again", {"en": "sustainable", "type": "word", "book": "ielts"}, now=NOW)
    assert rec["status"] == "learning" and rec["sources"] == ["ielts"] and rec["srs"]["due"] == NOW + review.AGAIN_DELAY


def test_remove_keeps_known(lib):
    words.add({"en": "commute", "type": "word"}, "video")
    words.set_known("commute", True)
    words.remove("commute")
    assert words.find(words.load(), "commute") == {"en": "commute", "type": "word", "status": "known",
                                                   "sources": ["marked"], "added": pytest.approx(time.time(), abs=5)}
    words.add({"en": "park", "type": "word"}, "video")
    assert words.remove("park") and words.find(words.load(), "park") is None


def test_sentences(lib):
    a = words.add_sentence({"text": "Practice makes perfect.", "zh": "熟能生巧。", "videoId": "v", "time": 3.0})
    assert words.add_sentence({"text": "Practice makes perfect."})["id"] == a["id"]  # once
    assert [s["text"] for s in words.load_sentences()] == ["Practice makes perfect."]
    assert words.remove_sentence(a["id"]) and words.load_sentences() == []
