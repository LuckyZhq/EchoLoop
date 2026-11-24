"""学习计划: stage presets from the current band, a daily plan, and a log of what was studied each day.

Stages (by current band) recommend playback settings and daily amounts. With an exam date, the daily
new-word quota comes from the vocabulary still missing for the target band and the days left.
"""
from __future__ import annotations

import json
import math
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import LIBRARY_DIR

ACTIVITY_PATH = LIBRARY_DIR / "activity.json"
_lock = threading.Lock()

# name, bands from, playback presets, daily amounts
STAGES = [
    {"id": "starter", "name": "入门", "from": 0, "speed": "0.75", "zh": True, "gloss": True,
     "newWords": 10, "listenMin": 10, "dictation": 5, "readMin": 5,
     "focus": "最常用的 2000 词；慢速听，中文和逐词释义全开，先听懂短句。"},
    {"id": "basic", "name": "基础", "from": 3, "speed": "0.9", "zh": True, "gloss": True,
     "newWords": 15, "listenMin": 15, "dictation": 10, "readMin": 10,
     "focus": "2000–4000 词；接近原速，靠短语对照理解整句，整句听写。"},
    {"id": "improve", "name": "提升", "from": 5, "speed": "1", "zh": True, "gloss": False,
     "newWords": 20, "listenMin": 20, "dictation": 15, "readMin": 15,
     "focus": "4000–6000 词和学术词；原速，先听一遍再看中文，练雅思听力和阅读的话题。"},
    {"id": "sprint", "name": "冲刺", "from": 6.5, "speed": "1", "zh": False, "gloss": False,
     "newWords": 25, "listenMin": 30, "dictation": 20, "readMin": 20,
     "focus": "6000 词以上；默认不看中文（按 C 再看），长难句、讲座和同义替换。"},
]
MAX_NEW_PER_DAY = 40


def stage_for(band: float | None) -> dict:
    band = 5.5 if band is None else band
    return [s for s in STAGES if band >= s["from"]][-1]


def today_key(now: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() if now is None else now))


# ------------------------------------------------------------------ activity log
def load_activity() -> dict:
    try:
        return json.loads(ACTIVITY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def log_activity(kind: str, amount: float = 1, now: float | None = None) -> dict:
    """Add to today's counter: listen / read (seconds), dictate / review / new (counts)."""
    if kind not in ("listen", "read", "dictate", "review", "new"):
        raise ValueError("unknown activity")
    with _lock:
        log = load_activity()
        day = log.setdefault(today_key(now), {})
        day[kind] = round(day.get(kind, 0) + amount, 1)
        if len(log) > 400:  # keep a bit more than a year
            for old in sorted(log)[:-400]:
                del log[old]
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        tmp = ACTIVITY_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")
        tmp.replace(ACTIVITY_PATH)
        return day


def streak(log: dict, now: float | None = None) -> int:
    """Days in a row with any study, counting back from today (or from yesterday if today is still empty)."""
    day = datetime.fromtimestamp(time.time() if now is None else now).date()
    if not any(log.get(day.isoformat(), {}).values()):
        day -= timedelta(days=1)
    n = 0
    while any(log.get(day.isoformat(), {}).values()):
        n += 1
        day -= timedelta(days=1)
    return n


def history(log: dict, days: int = 30, now: float | None = None) -> list[dict]:
    end = datetime.fromtimestamp(time.time() if now is None else now).date()
    out = []
    for i in range(days - 1, -1, -1):
        d = (end - timedelta(days=i)).isoformat()
        a = log.get(d, {})
        out.append({"date": d, "listenMin": round(a.get("listen", 0) / 60, 1), "readMin": round(a.get("read", 0) / 60, 1),
                    "dictate": int(a.get("dictate", 0)), "review": int(a.get("review", 0)), "new": int(a.get("new", 0))})
    return out


# ------------------------------------------------------------------ quota and plan
def new_per_day(profile: dict, now: float | None = None) -> dict:
    """Daily new words: the stage default, or what the exam date requires (capped at MAX_NEW_PER_DAY)."""
    from .placement import BAND_VOCAB

    stage = stage_for(profile.get("current"))
    current_vocab = profile.get("vocabSize")
    if current_vocab is None and profile.get("current") is not None:
        current_vocab = BAND_VOCAB.get(profile["current"])
    target = profile.get("target")
    gap = max(0, BAND_VOCAB[target] - current_vocab) if target is not None and current_vocab is not None else None
    days_left = None
    if profile.get("examDate"):
        try:
            exam = date.fromisoformat(profile["examDate"])
            days_left = (exam - datetime.fromtimestamp(time.time() if now is None else now).date()).days
        except ValueError:
            days_left = None
    count = stage["newWords"]
    if gap is not None and days_left is not None and days_left > 0:
        count = max(count, math.ceil(gap / days_left))
    return {"count": min(MAX_NEW_PER_DAY, count), "gap": gap, "daysLeft": days_left,
            "needed": math.ceil(gap / days_left) if gap and days_left and days_left > 0 else None,
            "daysAtThisPace": math.ceil(gap / count) if gap else None}


def daily_plan(profile: dict, vocab: list[dict], dictated_today: int, now: float | None = None) -> dict:
    from .review import due_count, start_of_today

    now = time.time() if now is None else now
    stage = stage_for(profile.get("current"))
    quota = new_per_day(profile, now)
    log = load_activity()
    today = log.get(today_key(now), {})
    start = start_of_today(now)
    reviews_left = due_count(vocab, now, new_per_day=0)  # reviews only
    new_today = sum(1 for v in vocab if v.get("srs") and v["srs"].get("seen", 0) >= start
                    and v.get("status", "learning") == "learning")
    from .wordbook import new_left

    in_wordbook = new_left(vocab, profile)
    new_left_in_book = sum(1 for v in vocab if v.get("status", "learning") == "learning" and not v.get("srs")) + (in_wordbook or 0)
    tasks = [
        {"id": "review", "label": "复习到期的词", "href": "/review", "unit": "个",
         "done": int(today.get("review", 0)) - int(today.get("new", 0)), "goal": None, "left": reviews_left},
        {"id": "new", "label": "学新词", "href": "/review", "unit": "个", "done": new_today, "goal": quota["count"],
         "note": None if new_left_in_book >= quota["count"] - new_today else
         "选一本词书，每天自动安排新词" if in_wordbook is None else
         f"只剩 {new_left_in_book} 个新词，换一本词书或多收藏一些"},
        {"id": "listen", "label": "精听视频", "href": "/listening", "unit": "分钟",
         "done": round(today.get("listen", 0) / 60), "goal": stage["listenMin"]},
        {"id": "dictate", "label": "听写", "href": "/listening", "unit": "句", "done": dictated_today, "goal": stage["dictation"]},
        {"id": "read", "label": "精读文章", "href": "/reading", "unit": "分钟",
         "done": round(today.get("read", 0) / 60), "goal": stage["readMin"]},
    ]
    for t in tasks:
        t["complete"] = (t["left"] == 0) if t["goal"] is None else t["done"] >= t["goal"]
    return {"stage": stage, "stages": STAGES, "quota": quota, "tasks": tasks, "streak": streak(log, now),
            "examDate": profile.get("examDate"), "history": history(log, 30, now)}
