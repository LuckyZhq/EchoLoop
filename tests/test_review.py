"""单词复习 scheduling (simplified SM-2) and the daily queue."""
import pytest

from ielts_study.review import AGAIN_DELAY, DAY, NEW_PER_DAY, due_count, previews, queue, schedule

NOW = 1_800_000_000.0


def run(grades, start=NOW):
    s, t = None, start
    for g in grades:
        s = schedule(s, g, t)
        t = s["due"]
    return s


def test_new_word_intervals():
    assert schedule(None, "again", NOW)["due"] == NOW + AGAIN_DELAY
    assert schedule(None, "hard", NOW)["ivl"] == 1
    assert schedule(None, "good", NOW)["ivl"] == 1
    assert schedule(None, "easy", NOW)["ivl"] == 4


def test_good_answers_space_out():
    assert [run(["good"] * n)["ivl"] for n in (1, 2, 3, 4)] == [1, 3, 8, 20]


def test_forgetting_resets_and_lowers_ease():
    s = run(["good", "good", "good", "again"])
    assert s["reps"] == 0 and s["lapses"] == 1 and s["ivl"] == 0
    assert s["ease"] == pytest.approx(2.3)
    assert run(["good", "good", "good", "again", "good"])["ivl"] == 1  # starts over


def test_ease_stays_in_bounds_and_interval_is_capped():
    assert run(["again"] * 20)["ease"] == 1.3
    assert run(["easy"] * 30)["ease"] == 3.0
    assert run(["easy"] * 30)["ivl"] == 365


def test_unknown_grade_is_refused():
    with pytest.raises(ValueError):
        schedule(None, "perfect", NOW)


def test_previews_name_each_button():
    p = previews(None, NOW)
    assert p == {"again": "10 分钟", "hard": "1 天", "good": "1 天", "easy": "4 天"}


def test_queue_puts_due_reviews_first_and_limits_new_words(tmp_path):
    vocab = [{"en": f"new{i}", "added": i} for i in range(NEW_PER_DAY + 5)]
    vocab += [
        {"en": "overdue", "srs": {**schedule(None, "good", NOW - 5 * DAY), "seen": NOW - 5 * DAY}},
        {"en": "later", "srs": {**schedule(None, "easy", NOW), "seen": NOW - 10 * DAY}},  # not new today
    ]
    q = queue(vocab, tmp_path, now=NOW)
    names = [c["en"] for c in q["cards"]]
    assert names[0] == "overdue" and "later" not in names
    assert q["due"] == 1 and q["new"] == NEW_PER_DAY and q["newLeft"] == NEW_PER_DAY + 5
    assert names[1:4] == ["new0", "new1", "new2"]  # oldest saves first
    assert due_count(vocab, now=NOW) == 1 + NEW_PER_DAY


def test_new_words_started_today_count_against_the_limit(tmp_path):
    started = [{"en": f"s{i}", "srs": schedule(None, "good", NOW)} for i in range(NEW_PER_DAY - 3)]
    fresh = [{"en": f"n{i}", "added": i} for i in range(10)]
    assert queue(started + fresh, tmp_path, now=NOW + 60)["new"] == 3
