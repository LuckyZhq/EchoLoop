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
