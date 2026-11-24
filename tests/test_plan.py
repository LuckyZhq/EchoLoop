"""学习计划: stages, the new-word quota, the activity log and today's plan."""
import time
from datetime import datetime, timedelta

import pytest

from ielts_study import goals, placement, plan

NOW = time.mktime((2026, 11, 24, 15, 0, 0, 0, 0, -1))


def day(offset):
    return (datetime.fromtimestamp(NOW).date() + timedelta(days=offset)).isoformat()


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(plan, "ACTIVITY_PATH", tmp_path / "activity.json")
    monkeypatch.setattr(plan, "LIBRARY_DIR", tmp_path)
    return tmp_path / "activity.json"


@pytest.mark.parametrize("band,stage", [(None, "improve"), (0, "starter"), (2.5, "starter"), (3, "basic"),
                                        (4.5, "basic"), (5, "improve"), (6, "improve"), (6.5, "sprint"), (9, "sprint")])
def test_stage_for_band(band, stage):
    assert plan.stage_for(band)["id"] == stage


def new_per_day(profile, now):
    return goals.new_words(profile, goals.stage(profile)[0], now)


def test_new_words_follow_the_stage_without_an_exam_date():
    q = new_per_day({"current": 4, "target": 5.5, "vocabSize": 2450}, NOW)
    assert q["count"] == 15 and q["gap"] == 1050 and q["daysLeft"] is None and q["daysAtThisPace"] == 70


def test_exam_date_raises_the_quota_but_not_past_the_cap():
    close = new_per_day({"current": 4, "target": 6, "vocabSize": 2200, "examDate": day(60)}, NOW)
    assert close["daysLeft"] == 60 and close["needed"] == 30 and close["count"] == 30
    rushed = new_per_day({"current": 4, "target": 7, "vocabSize": 2200, "examDate": day(10)}, NOW)
    assert rushed["needed"] == 380 and rushed["count"] == plan.MAX_NEW_PER_DAY
    relaxed = new_per_day({"current": 6.5, "target": 7, "vocabSize": 5800, "examDate": day(300)}, NOW)
    assert relaxed["count"] == 25  # the stage default when the date asks for less


def test_activity_log_streak_and_history(log_file):
    for offset in (-3, -2, -1):
        plan.log_activity("listen", 300, NOW + offset * 86400)
    assert plan.streak(plan.load_activity(), NOW) == 3  # today still empty: counts up to yesterday
    plan.log_activity("dictate", 1, NOW)
    plan.log_activity("dictate", 1, NOW)
    log = plan.load_activity()
    assert plan.streak(log, NOW) == 4 and log[day(0)]["dictate"] == 2
    h = plan.history(log, 5, NOW)
    assert [d["date"] for d in h] == [day(i) for i in range(-4, 1)]
    assert h[1]["listenMin"] == 5.0 and h[0]["listenMin"] == 0
    with pytest.raises(ValueError):
        plan.log_activity("sleep", 1, NOW)


def test_daily_plan_tasks(log_file):
    plan.log_activity("listen", 600, NOW)
    plan.log_activity("review", 3, NOW)
    plan.log_activity("new", 1, NOW)
    vocab = [{"en": "a", "srs": {"due": NOW - 60, "seen": NOW - 9 * 86400}},
             {"en": "b", "srs": {"due": NOW + 86400, "seen": NOW - 600}},  # learned today
             {"en": "c"}]
    p = plan.daily_plan({"current": 4, "target": 5.5, "vocabSize": 2450}, vocab, dictated_today=12, now=NOW)
    tasks = {t["id"]: t for t in p["tasks"]}
    assert p["stage"]["id"] == "basic"
    assert tasks["review"]["left"] == 1 and tasks["review"]["done"] == 2 and not tasks["review"]["complete"]
    assert tasks["new"]["done"] == 1 and tasks["new"]["goal"] == 15
    assert "选一本词书" in tasks["new"]["note"]  # only 1 saved word left and no 词书 chosen
    assert tasks["listen"]["done"] == 10 and tasks["listen"]["goal"] == 15
    assert tasks["dictate"]["complete"] and tasks["dictate"]["done"] == 12


@pytest.fixture
def profile_file(tmp_path, monkeypatch, log_file):
    monkeypatch.setattr(placement, "LIBRARY_DIR", tmp_path)
    monkeypatch.setattr(placement, "PROFILE_PATH", tmp_path / "profile.json")
    return tmp_path / "profile.json"


def test_one_source_for_stage_amounts_and_marking(profile_file):
    placement.update_profile({"current": 4, "target": 5.5, "examDate": day(60)})
    g = goals.today(now=NOW)
    assert g["stage"]["id"] == "basic" and g["stageMode"] == "auto"
    assert g["reason"] == {"current": 4, "target": 5.5, "bandGap": 1.5, "daysLeft": 60, "examDate": day(60)}
    assert g["quota"] == {"newWords": 22, "listenMin": 15, "dictation": 10, "readMin": 10} and g["overrides"] == {}  # 1300 words in 60 days
    assert g["markRange"] == {"lo": 2200, "hi": 4200, "perCue": 3, "current": 4, "target": 5.5}
    # a higher target: the new-word quota, the marking range and today's plan follow at once
    placement.update_profile({"target": 7})
    g = goals.today(now=NOW)
    assert g["quota"]["newWords"] == 40  # 3800 words in 60 days, capped
    assert g["markRange"]["hi"] == 7200
    tasks = {t["id"]: t for t in plan.daily_plan(placement.load_profile(), [], 0, now=NOW)["tasks"]}
    assert tasks["new"]["goal"] == goals.new_per_day(now=NOW) == 40


def test_manual_stage_and_quota_overrides(profile_file):
    placement.update_profile({"current": 4, "target": 5.5, "stage": "sprint", "quotas": {"listenMin": 45, "dictation": 0,
                                                                                          "readMin": "x", "bogus": 3}})
    g = goals.today(now=NOW)
    assert g["stage"]["id"] == "sprint" and g["stageMode"] == "manual" and g["autoStage"] == "basic"
    assert g["overrides"] == {"listenMin": 45}  # out of range and unknown items are dropped
    assert g["quota"] == {"newWords": 25, "listenMin": 45, "dictation": 20, "readMin": 20}
    tasks = {t["id"]: t for t in plan.daily_plan(placement.load_profile(), [], 0, now=NOW)["tasks"]}
    assert tasks["listen"]["goal"] == 45 and tasks["new"]["goal"] == 25
    placement.update_profile({"stage": "nonsense", "quotas": {}})
    g = goals.today(now=NOW)
    assert g["stageMode"] == "auto" and g["quota"]["listenMin"] == 15
