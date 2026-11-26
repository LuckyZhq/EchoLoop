import json

import pytest

from echoloop import annotate, pipeline, reading
from echoloop.dictionary import Dictionary


@pytest.fixture(scope="module")
def dic():
    return Dictionary()


def phrase_marks(cue):
    marks = cue["marks"]
    assert all(a["e"] <= b["s"] for a, b in zip(marks, marks[1:]))
    return [(cue["text"][m["s"]:m["e"]], cue["notes"][m["key"]]["en"])
            for m in marks if m["type"] == "phrase"]


@pytest.mark.parametrize(("text", "expected"), [
    ("You can take advantage of this offer and make a difference.",
     [("take advantage of", "take advantage of"), ("make a difference", "make a difference")]),
    ("They go to court and resort to threats.", [("go to court", "go to court")]),
    ("We pay close attention to making a big difference.",
     [("pay close attention to", "pay attention to"), ("making a big difference", "make a big difference")]),
    ("They attributed the failure to rising costs and went to court.",
     [("attributed", "attribute to"), ("to", "attribute to")]),
    ("They attribute their success to hard work.", [("attribute", "attribute to"), ("to", "attribute to")]),
    ("The change is often attributed to chance.", [("attributed to", "attribute to")]),
    ("The change was attributed to chance.", [("was attributed to", "be attributed to")]),
    ("We pick it up and make a difference.",
     [("pick", "pick up"), ("up", "pick up"), ("make a difference", "make a difference")]),
    ("Make a difference, make a difference, make a difference.",
     [("Make a difference", "make a difference"), ("make a difference", "make a difference")]),
])
def test_phrase_ranges(dic, text, expected):
    cue = {"text": text}
    annotate.annotate_cues([cue], dic)
    assert phrase_marks(cue) == expected
    assert {key for key in cue["notes"] if key.startswith("p:")} == {"p:" + en for _, en in expected}
    if text.startswith("They attributed"):
        assert [m["s"] for m in cue["marks"] if m["type"] == "phrase"] == [text.index("attributed"), text.index("to ")]


def test_attribute_does_not_borrow_an_infinitive_or_another_verbs_preposition(dic):
    doc = annotate.nlp()("They attribute a desire to succeed and go to court.")
    assert all(entry["en"] != "attribute to" for _, _, entry in annotate._phrase_candidates(doc, dic))


def test_variants_share_meanings_in_both_languages(dic):
    assert dic.phrase("pay close attention to") == dic.phrase("pay attention to")
    cue = {"text": "She paid close attention to making a big difference."}
    annotate.annotate_cues([cue], dic, lang="en")
    assert phrase_marks(cue) == [("paid close attention to", "pay attention to"),
                                 ("making a big difference", "make a big difference")]
    for note in cue["notes"].values():
        if note["type"] == "phrase":
            assert note["zh"] == note["def"] and note["def"]


@pytest.mark.parametrize("kind", ["video", "article"])
def test_version_six_reannotates_once(dic, tmp_path, monkeypatch, kind):
    cue = {"i": 0, "p": 0, "start": 1.0, "end": 4.5,
           "text": "We pick it up and make a difference.", "zh": "我们把它捡起来，起到了作用。",
           "seg": [{"s": 3, "e": 13, "zh": "把它捡起来"}]}
    old = {"id": "a000000000001", "title": "Test", "annotation": 6, "cues": [dict(cue, notes={}, marks=[])]}
    if kind == "article":
        monkeypatch.setattr(reading, "ARTICLES_DIR", tmp_path)
        reading.save_article(old)
        path = reading.article_path(old["id"])
        upgrade = reading.ensure_article_annotation
    else:
        path = tmp_path / "data.json"
        path.write_text(json.dumps(old), encoding="utf-8")
        def upgrade(data, dic):
            return pipeline.ensure_annotation(tmp_path, data, dic)

    updated = upgrade(old, dic)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == updated and saved["annotation"] == annotate.ANNOTATION_VERSION == 7
    result = saved["cues"][0]
    assert {key: result[key] for key in cue} == cue
    assert phrase_marks(result) == [("pick", "pick up"), ("up", "pick up"), ("make a difference", "make a difference")]

    def unexpected(*args, **kwargs):
        pytest.fail("already-upgraded content was annotated again")

    monkeypatch.setattr(annotate, "annotate_cues", unexpected)
    assert upgrade(saved, dic) is saved
    assert upgrade(old, dic) == saved
