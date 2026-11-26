"""我的目标: the one place that decides today's amounts and which words get marked.

The state lives in profile.json (see placement): current band and tested vocabulary, target band, exam date,
the stage ("auto", or a stage id chosen by hand) and per-item overrides of the daily amounts. plan.STAGES is
the table of what each stage recommends. Every page that shows or uses a daily amount or the marking range
gets it from today(), so the numbers agree everywhere.
"""
from __future__ import annotations

import math
import time
from datetime import date, datetime

from . import plan
from .placement import BAND_VOCAB, CET_VOCAB, DEFAULT_TRACK, load_profile, vocab_table

# daily amounts that can be adjusted one by one, with the largest value accepted
QUOTA_KEYS = {"newWords": plan.MAX_NEW_PER_DAY, "listenMin": 240, "dictation": 200, "readMin": 240}
STAGE_IDS = [s["id"] for s in plan.STAGES]


def _track(profile: dict) -> str:
    if profile.get("track"):
        return profile["track"]
    for key in ("current", "target"):
        val = profile.get(key)
        if val is not None and val in BAND_VOCAB and val <= 9:
            return "ielts"
    return DEFAULT_TRACK


def track(profile: dict | None = None) -> str:
    """The exam track chosen in 我的目标, used by pages that need exam-specific content."""
    return _track(load_profile() if profile is None else profile)


def _days_left(profile: dict, now: float) -> int | None:
    if not profile.get("examDate"):
        return None
    try:
        exam = date.fromisoformat(profile["examDate"])
    except ValueError:
        return None
    return (exam - datetime.fromtimestamp(now).date()).days


def stage(profile: dict) -> tuple[dict, str]:
    """(the stage in use, "auto" or "manual"). Auto: from the current score/band."""
    track = _track(profile)
    stages = plan.stages_for(track)
    chosen = profile.get("stage")
    if chosen in STAGE_IDS:
        return next(s for s in stages if s["id"] == chosen), "manual"
    return plan.stage_for(profile.get("current"), track), "auto"


def new_words(profile: dict, stage_info: dict, now: float | None = None) -> dict:
    """Daily new words: the stage default, or what the exam date requires (capped at MAX_NEW_PER_DAY)."""
    now = time.time() if now is None else now
    table = vocab_table(_track(profile))
    current_vocab = profile.get("vocabSize")
    if current_vocab is None and profile.get("current") is not None:
        current_vocab = table.get(profile["current"])
    target = profile.get("target")
    gap = max(0, table[target] - current_vocab) if target in table and current_vocab is not None else None
    days_left = _days_left(profile, now)
    count = stage_info["newWords"]
    if gap is not None and days_left is not None and days_left > 0:
        count = max(count, math.ceil(gap / days_left))
    return {"count": min(plan.MAX_NEW_PER_DAY, count), "gap": gap, "daysLeft": days_left,
            "needed": math.ceil(gap / days_left) if gap and days_left and days_left > 0 else None,
            "daysAtThisPace": math.ceil(gap / count) if gap else None}


def mark_range(profile: dict) -> dict:
    """Words worth marking lie between what you already know and a little beyond your target:
    lo = your vocabulary (tested, or typical for your current score), hi = typical for the target + 20%."""
    track = _track(profile)
    table = vocab_table(track)
    if track == "ielts":
        current = profile.get("current")
        current = 5.5 if current is None else current
        target = profile.get("target")
        target = min(9, current + 1.5) if target is None else target
        lo = profile.get("vocabSize") or table.get(current, 3500)
        hi = max(table.get(target, lo) * 1.2, lo + 1500)
        per_cue = 3 if current < 5 else 2
        return {"lo": lo, "hi": round(hi), "perCue": per_cue, "current": current, "target": target}
    default_cur = 350 if track == "cet4" else 425
    default_tgt = 480 if track == "cet4" else 550
    current = profile.get("current")
    current = default_cur if current is None else current
    target = profile.get("target")
    target = default_tgt if target is None else target
    lo = profile.get("vocabSize") or table.get(current, 4500)
    hi = max(table.get(target, lo) * 1.15, lo + 1500)
    per_cue = 3 if current < 425 else 2
    return {"lo": lo, "hi": round(hi), "perCue": per_cue, "current": current, "target": target}


def clean_overrides(value) -> dict:
    """Keep only known items with a whole number in range; anything else means "use the recommendation"."""
    out = {}
    if not isinstance(value, dict):
        return out
    for key, top in QUOTA_KEYS.items():
        v = value.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and 1 <= v <= top:
            out[key] = int(v)
    return out


def today(profile: dict | None = None, now: float | None = None) -> dict:
    """Everything a page needs about the goal: the stage and why, today's amounts, and the marking range."""
    profile = load_profile() if profile is None else profile
    now = time.time() if now is None else now
    track = _track(profile)
    stages = plan.stages_for(track)
    used, mode = stage(profile)
    auto = plan.stage_for(profile.get("current"), track)
    words = new_words(profile, used, now)
    recommended = {"newWords": words["count"], "listenMin": used["listenMin"],
                   "dictation": used["dictation"], "readMin": used["readMin"]}
    overrides = clean_overrides(profile.get("quotas"))
    current, target = profile.get("current"), profile.get("target")
    gap = round(target - current, 1) if current is not None and target is not None else None
    if isinstance(gap, float) and gap.is_integer():
        gap = int(gap) if track != "ielts" else gap
    return {
        "track": track,
        "stage": used, "stageMode": mode, "autoStage": auto["id"], "stages": stages,
        "reason": {"current": current, "target": target,
                   "bandGap": gap,
                   "daysLeft": words["daysLeft"], "examDate": profile.get("examDate")},
        "quota": {**recommended, **overrides}, "recommended": recommended, "overrides": overrides,
        "newWords": words, "markRange": mark_range(profile),
    }


def new_per_day(profile: dict | None = None, now: float | None = None) -> int:
    """Today's new-word limit, the same number on every page."""
    return today(profile, now)["quota"]["newWords"]
