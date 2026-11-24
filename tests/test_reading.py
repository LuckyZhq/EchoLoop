"""Reading: pasted articles are split into paragraphs and sentences."""
from ielts_study.reading import ARTICLE_ID, new_id, split_sentences


def test_paragraphs_and_sentences():
    cues = split_sentences("Parks matter. They reduce stress.\n\nHowever, cities grow fast.")
    assert [(c["p"], c["text"]) for c in cues] == [
        (0, "Parks matter."), (0, "They reduce stress."), (1, "However, cities grow fast."),
    ]
    assert [c["i"] for c in cues] == [0, 1, 2]


def test_single_line_breaks_start_new_paragraphs_and_blank_lines_are_skipped():
    cues = split_sentences("First line.\nSecond line.\n\n\n   \nThird line.")
    assert [c["p"] for c in cues] == [0, 1, 2]


def test_article_ids_are_safe_path_names():
    aid = new_id()
    assert ARTICLE_ID.match(aid)
    assert not ARTICLE_ID.match("../library")


def test_old_articles_are_reannotated_and_saved(tmp_path, monkeypatch):
    from ielts_study import reading
    from ielts_study.annotate import ANNOTATION_VERSION
    from ielts_study.dictionary import Dictionary

    monkeypatch.setattr(reading, "ARTICLES_DIR", tmp_path)
    old = {"id": "a000000000001", "title": "t", "annotation": 1,
           "cues": [{"i": 0, "p": 0, "text": "Cities must mitigate congestion.", "zh": "城市必须缓解拥堵。"}]}
    reading.save_article(old)
    data = reading.ensure_article_annotation(reading.load_article(old["id"]), Dictionary())
    assert data["annotation"] == ANNOTATION_VERSION
    assert "gl" in data["cues"][0] and "marks" in data["cues"][0]
    assert reading.load_article(old["id"])["annotation"] == ANNOTATION_VERSION  # written back to disk
