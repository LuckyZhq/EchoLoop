"""单词复习: spaced repetition for 收藏词句 (simplified SM-2, the scheme Anki is built on).

Each saved word/phrase may carry `srs`:
    {"due": epoch s, "ivl": days, "ease": 1.3–3.0, "reps": successful reviews in a row, "lapses": n,
     "last": epoch s, "seen": epoch s of the first review}
Words without `srs` are new. At most `new_per_day` new words are introduced per day (from the study plan;
NEW_PER_DAY when there is none).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

GRADES = ("again", "hard", "good", "easy")
NEW_PER_DAY = 20
AGAIN_DELAY = 10 * 60   # a forgotten word comes back after 10 minutes
DAY = 86400
MAX_IVL = 365


def schedule(srs: dict | None, grade: str, now: float) -> dict:
    """Next review state after answering with `grade`."""
    if grade not in GRADES:
        raise ValueError("unknown grade")
    s = {"ivl": 0, "ease": 2.5, "reps": 0, "lapses": 0, **(srs or {})}
    s.setdefault("seen", now)
    reps, ivl, ease = s["reps"], s["ivl"], s["ease"]
    if grade == "again":
        s.update(reps=0, ivl=0, ease=max(1.3, ease - 0.2), lapses=s["lapses"] + (1 if reps else 0),
                 due=now + AGAIN_DELAY, last=now)
        return s
    if grade == "hard":
        ivl = 1 if reps == 0 else max(ivl + 1, round(ivl * 1.2))
        ease = max(1.3, ease - 0.15)
    elif grade == "good":
        ivl = 1 if reps == 0 else 3 if reps == 1 else round(ivl * ease)
    else:  # easy
        ivl = 4 if reps == 0 else round(max(ivl, 1) * ease * 1.3)
        ease = min(3.0, ease + 0.15)
    ivl = min(MAX_IVL, max(1, ivl))
    s.update(reps=reps + 1, ivl=ivl, ease=round(ease, 2), due=now + ivl * DAY, last=now)
    return s


def interval_label(seconds: float) -> str:
    if seconds < 3600:
        return f"{max(1, round(seconds / 60))} 分钟"
    days = seconds / DAY
    if days < 1:
        return f"{round(seconds / 3600)} 小时"
    if days < 30:
        return f"{round(days)} 天"
    if days < 365:
        return f"{round(days / 30)} 个月"
    return f"{days / 365:.1f} 年"


def previews(srs: dict | None, now: float) -> dict:
    """What each button means for this card, e.g. {"again": "10 分钟", "good": "3 天", ...}."""
    return {g: interval_label(schedule(srs, g, now)["due"] - now) for g in GRADES}


def start_of_today(now: float) -> float:
    return time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))


def _clip(item: dict, library: Path, cache: dict) -> dict | None:
    """Where to hear the original sentence: the video file and the cue's start/end."""
    vid = item.get("videoId")
    if not vid:
        return None
    if vid not in cache:
        try:
            cache[vid] = json.loads((library / vid / "data.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache[vid] = None
    data = cache[vid]
    if not data or not (library / vid / data.get("video", "")).is_file():
        return None
    t = float(item.get("time") or 0)
    cue = min(data.get("cues") or [{}], key=lambda c: abs(c.get("start", 1e9) - t))
    if "start" not in cue or abs(cue["start"] - t) > 1:
        return None
    return {"src": f"/media/{vid}/{data['video']}", "start": cue["start"], "end": cue["end"]}


def queue(vocab: list[dict], library: Path, now: float | None = None, new_per_day: int = NEW_PER_DAY) -> dict:
    """Cards to review now: due reviews first (most overdue first), then today's share of new words."""
    now = time.time() if now is None else now
    today = start_of_today(now)
    due = sorted((v for v in vocab if v.get("srs") and v["srs"]["due"] <= now), key=lambda v: v["srs"]["due"])
    started_today = sum(1 for v in vocab if v.get("srs") and v["srs"].get("seen", 0) >= today)
    fresh = sorted((v for v in vocab if not v.get("srs")), key=lambda v: v.get("added", 0))
    new = fresh[:max(0, new_per_day - started_today)]
    cache: dict = {}
    cards = [{**v, "isNew": not v.get("srs"), "preview": previews(v.get("srs"), now), "clip": _clip(v, library, cache)}
             for v in due + new]
    upcoming = [v["srs"]["due"] for v in vocab if v.get("srs") and v["srs"]["due"] > now]
    return {
        "cards": cards,
        "due": len(due), "new": len(new), "newLeft": len(fresh), "total": len(vocab),
        "learning": sum(1 for v in vocab if v.get("srs") and v["srs"]["reps"] == 0),
        "mature": sum(1 for v in vocab if v.get("srs") and v["srs"]["ivl"] >= 21),
        "nextDue": min(upcoming) if upcoming else None,
        "reviewedToday": sum(1 for v in vocab if v.get("srs") and v["srs"].get("last", 0) >= today),
    }


def due_count(vocab: list[dict], now: float | None = None, new_per_day: int = NEW_PER_DAY) -> int:
    """For the sidebar badge and the home page: reviews due plus new words still allowed today."""
    now = time.time() if now is None else now
    today = start_of_today(now)
    due = sum(1 for v in vocab if v.get("srs") and v["srs"]["due"] <= now)
    started_today = sum(1 for v in vocab if v.get("srs") and v["srs"].get("seen", 0) >= today)
    fresh = sum(1 for v in vocab if not v.get("srs"))
    return due + min(fresh, max(0, new_per_day - started_today))
