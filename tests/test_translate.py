"""Phrase alignment: the API's [english, chinese] chunks are mapped back onto the subtitle text."""
from ielts_study.translate import align_chunks


def spans(text, segs):
    return [(text[g["s"]:g["e"]], g["zh"]) for g in segs]


def test_chunks_map_onto_the_text_in_order():
    text = "Nature landscapes for tourists, for everyone."
    segs = align_chunks(text, [["Nature landscapes", "自然景观"], ["for tourists", "供游客"], ["for everyone", "供所有人"]])
    assert spans(text, segs) == [("Nature landscapes", "自然景观"), ("for tourists", "供游客"), ("for everyone", "供所有人")]


def test_repeated_words_match_the_next_occurrence():
    text = "for tourists and for everyone"
    segs = align_chunks(text, [["for", "为"], ["tourists", "游客"], ["and", "和"], ["for", "为"], ["everyone", "大家"]])
    assert [g["s"] for g in segs] == [0, 4, 13, 17, 21]


def test_punctuation_and_curly_apostrophes_are_ignored():
    text = "It’s a well-known fact."
    segs = align_chunks(text, [["It's", "这是"], ["a well-known fact", "众所周知的事实"]])
    assert spans(text, segs) == [("It’s", "这是"), ("a well-known fact", "众所周知的事实")]


def test_numbers_are_kept():
    text = "Try these 5 simple exercises"
    segs = align_chunks(text, [["Try", "试试"], ["these 5 simple exercises", "这5个简单练习"]])
    assert spans(text, segs)[1][0] == "these 5 simple exercises"


def test_paraphrased_chunks_are_dropped_not_misplaced():
    text = "I usually listen to podcasts"
    segs = align_chunks(text, [["I", "我"], ["normally hear", "通常听"], ["podcasts", "播客"]])
    assert spans(text, segs) == [("I", "我"), ("podcasts", "播客")]


def test_a_chunk_far_ahead_is_skipped():
    # A match more than 3 words ahead usually means the model skipped or reordered words.
    text = "one two three four five six seven"
    segs = align_chunks(text, [["one", "一"], ["six", "六"]])
    assert spans(text, segs) == [("one", "一")]


def test_malformed_chunks_are_ignored():
    assert align_chunks("hello world", None) == []
    assert align_chunks("hello world", [["hello"], [1, 2], "x", ["", "空"], ["world", "世界"]]) == [{"s": 6, "e": 11, "zh": "世界"}]
