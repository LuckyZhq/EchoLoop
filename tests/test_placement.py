"""水平测试: vocabulary estimate, spot-check, profile; and the word ranks it relies on."""
import pytest

from ielts_study import placement as pl
from ielts_study.annotate import nlp, word_info
from ielts_study.dictionary import Dictionary


@pytest.fixture(scope="module")
def dic():
    return Dictionary()


@pytest.fixture(scope="module")
def words(dic):
    return [w for p in pl.passages(dic) for w in p["words"]]


def take_test(dic, words, knows_top, overclaim=0, seed=0):
    """A simulated learner who knows the `knows_top` most frequent words and leaves `overclaim` more unclicked."""
    unknown = {w["id"] for w in words if w["rank"] > knows_top + overclaim}
    qs = pl.spot_check(dic, unknown, seed=seed)
    by_id = {w["id"]: w for w in words}
    wrong = {q["id"] for q in qs if by_id[q["id"]]["rank"] > knows_top}
    return pl.score_test(dic, unknown, wrong, {q["id"] for q in qs})


def test_passages_cover_easy_to_rare_words(words):
    ranks = [w["rank"] for w in words]
    assert len(ranks) > 120
    assert sum(r <= 1000 for r in ranks) > 40 and sum(r > 5000 for r in ranks) >= 8


@pytest.mark.parametrize("knows_top,low,high", [(0, 0, 200), (1500, 1300, 2300), (2500, 2200, 3000),
                                                (4000, 3600, 4800), (6000, 5200, 6800)])
def test_honest_answers_land_near_the_true_vocabulary(dic, words, knows_top, low, high):
    assert low <= take_test(dic, words, knows_top)["vocabSize"] <= high


def test_spot_check_pulls_overclaimers_back(dic, words):
    honest = take_test(dic, words, 2500)["vocabSize"]
    claimed = take_test(dic, words, 2500, overclaim=10**6, seed=3)  # clicked nothing at all
    unchecked = pl.estimate([(w["rank"], True) for w in words])["vocabSize"]
    assert claimed["vocabSize"] < unchecked and claimed["vocabSize"] < honest + 2000


def test_spot_check_asks_harder_unclicked_words_with_one_right_answer(dic, words):
    qs = pl.spot_check(dic, set(), seed=1)
    assert len(qs) == pl.MAX_CHECKS
    assert len({q["en"] for q in qs}) == len(qs)
    for q in qs:
        assert len(q["options"]) == 4 and 0 <= q["answer"] < 4
    assert pl.spot_check(dic, {w["id"] for w in words}) == []  # everything clicked: nothing to check


def test_band_for_vocabulary():
    assert pl.band_for(0) == 0
    assert pl.band_for(2999) == 4.5 and pl.band_for(3000) == 5
    assert pl.band_for(20000) == 9


def test_profile_test_known_words_and_goal(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "PROFILE_PATH", tmp_path / "profile.json")
    monkeypatch.setattr(pl, "LIBRARY_DIR", tmp_path)
    p = pl.record_test({"vocabSize": 2600, "band": 4.5})
    assert (p["current"], p["target"], p["vocabSize"]) == (4.5, 6.0, 2600)
    p = pl.update_profile({"target": "7"})
    assert p["target"] == 7 and p["vocabSize"] == 2600
    p = pl.update_profile({"current": "5", "vocabSize": None})  # picked by hand: tested size no longer applies
    assert p["current"] == 5 and p["vocabSize"] is None
    assert pl.update_profile({"target": "10"})["target"] is None  # not a band
    pl.set_known("Commute", True)
    pl.set_known("crucial", True)
    assert pl.set_known("commute", False)["known"] == ["crucial"]
    vocab = [{"en": "Foster", "srs": {"ivl": 30}}, {"en": "park", "srs": {"ivl": 3}}]
    assert pl.public_profile(vocab)["mature"] == ["foster"]


def test_word_ranks_use_the_right_dictionary_form(dic):
    found = {t.text: word_info(t, dic) for t in nlp()("The sun was shining and parks have been linked to improving health.")}
    assert found["shining"][0]["en"] == "shine"           # spaCy says "shin"; the dictionary's forms win
    assert found["linked"][1] < 2000                      # as common as "link", not the rare adjective entry
    assert found["improving"][0]["en"] == "improve"       # a verb here, not 有启发的
    assert found["The"] is None and found["and"] is None  # function words are not scored
