"""水平测试 and the learner profile: current level, target, exam date, stage and daily amounts (see goals.py).

The test: three short passages from easy to hard. The learner clicks every word they don't know; a short
spot-check then asks the meaning of a few harder words they did *not* click, because people tend to skip
words they only half know. Each word has a frequency rank, so the answers show how far up the frequency
list the learner's vocabulary reaches. That estimate is mapped to a rough IELTS band (BAND_VOCAB).

BAND_VOCAB is an approximation for guidance, not an official conversion: it is in line with published
estimates of the vocabulary size typical at each band, and vocabulary is only one part of the exam.
"""
from __future__ import annotations

import json
import random
import threading
import time
from functools import lru_cache
from pathlib import Path

from .config import LIBRARY_DIR

PASSAGES_FILE = Path(__file__).with_name("placement_passages.json")
PROFILE_PATH = LIBRARY_DIR / "profile.json"
_lock = threading.Lock()

# Typical vocabulary (most frequent N words known) at each band — an estimate, see the module docstring.
BAND_VOCAB = {0: 0, 1: 300, 2: 800, 2.5: 1100, 3: 1500, 3.5: 1800, 4: 2200, 4.5: 2600, 5: 3000, 5.5: 3500,
              6: 4000, 6.5: 5000, 7: 6000, 7.5: 7000, 8: 8500, 8.5: 9500, 9: 11000}
BANDS = sorted(BAND_VOCAB)
# Frequency bands the estimate is computed over (rank ranges).
EDGES = [0, 1000, 2000, 3000, 5000, 8000, 12000]
UNRANKED = 9000  # words missing from the frequency lists are rare
MAX_CHECKS = 8


# ------------------------------------------------------------------ passages
@lru_cache(maxsize=1)
def _passages_raw() -> list[dict]:
    return json.loads(PASSAGES_FILE.read_text(encoding="utf-8"))


def build_passages(dic, school: bool = True) -> list[dict]:
    """Passages with every scored (content) word: id, character range, dictionary form, rank, meaning.
    `school`: Chinese learners count 中考 words as common (see annotate.word_info)."""
    from .annotate import nlp, word_info
    from .dictionary import clean_translation

    out = []
    for pi, p in enumerate(_passages_raw()):
        words = []
        for t in nlp()(p["text"]):
            found = word_info(t, dic, school)
            if not found:
                continue
            info, rank, _, _ = found
            zh = clean_translation(info["zh"], None, max_senses=2, max_lines=1) or info["zh"].split("\n")[0]
            words.append({"id": f"{pi}:{len(words)}", "s": t.idx, "e": t.idx + len(t.text), "en": info["en"],
                          "rank": rank or UNRANKED, "zh": zh[:40], "phonetic": info.get("phonetic", "")})
        out.append({"title": p["title"], "level": p["level"], "text": p["text"], "words": words})
    return out


_cache: dict = {}


def passages(dic, lang: str = "zh-CN") -> list[dict]:
    from .languages import is_chinese

    school = is_chinese(lang)
    if school not in _cache:
        _cache[school] = build_passages(dic, school)
    return _cache[school]


def _all_words(dic, lang: str = "zh-CN") -> dict:
    return {w["id"]: w for p in passages(dic, lang) for w in p["words"]}


def _meanings(dic, words: list[dict], lang: str, settings) -> dict:
    """{dictionary form: meaning} in the learner's language (Chinese from the dictionary, others via meanings)."""
    from . import meanings
    from .languages import is_chinese

    if is_chinese(lang):
        return {w["en"]: w["zh"] for w in words}
    return meanings.for_words(sorted({w["en"] for w in words}), lang, settings, dic)


# ------------------------------------------------------------------ spot-check
def spot_check(dic, unknown: set[str], seed: int | None = None, lang: str = "zh-CN", settings=None) -> list[dict]:
    """Ask the meaning of a few harder words the learner did not click (spread over the frequency bands).
    Options are in the learner's language (English definitions when no translation is available)."""
    rng = random.Random(seed)
    words = _all_words(dic, lang)
    candidates = [w for w in words.values() if w["id"] not in unknown and w["rank"] > 600]
    by_band: dict[int, list] = {}
    for w in candidates:
        by_band.setdefault(_band_index(w["rank"]), []).append(w)
    picked: list[dict] = []
    seen_en: set[str] = set()
    while len(picked) < MAX_CHECKS and any(by_band.values()):
        for band in sorted(by_band, reverse=True):  # hardest bands first, one word each round
            pool = [w for w in by_band[band] if w["en"] not in seen_en]
            by_band[band] = pool
            if pool and len(picked) < MAX_CHECKS:
                w = rng.choice(pool)
                picked.append(w)
                seen_en.add(w["en"])
    others = rng.sample([w for w in words.values() if w not in picked], min(30, len(words) - len(picked)))
    meaning = _meanings(dic, picked + others, lang, settings)
    pool = list({meaning[w["en"]] for w in others if meaning.get(w["en"])})
    questions = []
    for w in picked:
        right = meaning.get(w["en"]) or w["en"]
        wrong = rng.sample([m for m in pool if m != right], min(3, len([m for m in pool if m != right])))
        options = wrong + [right]
        rng.shuffle(options)
        questions.append({"id": w["id"], "en": w["en"], "options": options, "answer": options.index(right)})
    return questions


# ------------------------------------------------------------------ estimate
def _band_index(rank: int) -> int:
    for i in range(len(EDGES) - 1):
        if rank <= EDGES[i + 1]:
            return i
    return len(EDGES) - 2


def estimate(ranks_known: list[tuple[int, bool]], checks: list[tuple[int, bool]] = ()) -> dict:
    """Vocabulary size from (rank, known) for every scored word, corrected by spot-check results.

    Per frequency band: the share of words known. Spot-check failures show that unclicked words were not
    all really known: every claimed word at least as rare as the easiest failed word is discounted by the
    failure rate of the checks in that range. Honest answers (no failures) are taken as they are."""
    n = len(EDGES) - 1
    failed_ranks = [rank for rank, ok in checks if not ok]
    doubt_from = min(failed_ranks) if failed_ranks else None
    # failure rate among checks at least as hard as the easiest failure (easier checks say nothing here)
    hard_checks = [ok for rank, ok in checks if doubt_from is not None and rank >= doubt_from]
    fail_rate = hard_checks.count(False) / len(hard_checks) if hard_checks else 0.0
    total, claimed = [0] * n, [0.0] * n
    for rank, ok in ranks_known:
        b = _band_index(rank)
        total[b] += 1
        if ok:
            claimed[b] += 1 - fail_rate if doubt_from is not None and rank >= doubt_from else 1
    ratios: list[float | None] = [claimed[b] / total[b] if total[b] >= 2 else None for b in range(n)]
    # Bands with too few words: take the neighbours' average (or the band below, at the top end).
    for b in range(n):
        if ratios[b] is None:
            lower = next((ratios[i] for i in range(b - 1, -1, -1) if ratios[i] is not None), None)
            upper = next((ratios[i] for i in range(b + 1, n) if ratios[i] is not None), None)
            ratios[b] = (lower + upper) / 2 if lower is not None and upper is not None else (lower or upper or 0.0)
    size = sum((EDGES[b + 1] - EDGES[b]) * ratios[b] for b in range(n))
    size = int(round(size / 50) * 50)
    return {"vocabSize": size, "band": band_for(size),
            "bands": [{"from": EDGES[b], "to": EDGES[b + 1], "known": round(ratios[b], 2)} for b in range(n)]}


def band_for(vocab: int) -> float:
    """Highest band whose typical vocabulary the learner reaches."""
    return max(b for b in BANDS if BAND_VOCAB[b] <= max(0, vocab))


def score_test(dic, unknown: set[str], wrong: set[str], checked: set[str], lang: str = "zh-CN",
               settings=None) -> dict:
    words = _all_words(dic, lang)
    ranks_known = [(w["rank"], w["id"] not in unknown) for w in words.values()]
    checks = [(words[i]["rank"], i not in wrong) for i in checked if i in words]
    result = estimate(ranks_known, checks)
    missed = [words[i] for i in unknown | wrong if i in words]
    meaning = _meanings(dic, missed, lang, settings)
    result["unknownWords"] = sorted({(w["en"], meaning.get(w["en"], ""), w["phonetic"]) for w in missed},
                                    key=lambda x: x[0])
    return result


# ------------------------------------------------------------------ profile
def load_profile() -> dict:
    try:
        p = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        p = {}
    p.setdefault("current", None)
    p.setdefault("target", None)
    p.setdefault("vocabSize", None)
    p.setdefault("tests", [])
    p.setdefault("examDate", None)
    p.setdefault("stage", "auto")
    p.setdefault("quotas", {})
    return p


def save_profile(p: dict) -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PROFILE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(PROFILE_PATH)


def _band_value(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v in BAND_VOCAB else None


def _exam_date(value):
    from datetime import date

    try:
        return date.fromisoformat(str(value)).isoformat() if value else None
    except ValueError:
        return None


def update_profile(changes: dict) -> dict:
    with _lock:
        p = load_profile()
        for key in ("current", "target"):
            if key in changes:
                p[key] = _band_value(changes[key])
        if "examDate" in changes:
            p["examDate"] = _exam_date(changes["examDate"])
        if "vocabSize" in changes and changes["vocabSize"] is None:
            p["vocabSize"] = None  # choosing a level by hand replaces the tested vocabulary
        if "stage" in changes:  # a stage id chosen by hand, or "auto"
            from .goals import STAGE_IDS
            p["stage"] = changes["stage"] if changes["stage"] in STAGE_IDS else "auto"
        if "quotas" in changes:  # per-item daily amounts; a missing item follows the recommendation
            from .goals import clean_overrides
            p["quotas"] = clean_overrides(changes["quotas"])
        save_profile(p)
        return p


def record_test(result: dict) -> dict:
    with _lock:
        p = load_profile()
        p["vocabSize"] = result["vocabSize"]
        p["current"] = result["band"]
        if p["target"] is None or p["target"] <= p["current"]:
            p["target"] = min(9, p["current"] + 1.5)
        p["tests"].append({"at": int(time.time()), "vocabSize": result["vocabSize"], "band": result["band"]})
        p["tests"] = p["tests"][-50:]
        save_profile(p)
        return p


def public_profile(items: list[dict]) -> dict:
    """Profile for the pages, with the words to stop marking from the word ledger: known words, and words
    already well remembered in 单词复习."""
    from . import goals, words

    p = load_profile()
    p.pop("known", None)  # a profile saved before the word ledger
    return {**p, "known": words.known_words(items), "mature": words.mature_words(items),
            "bandVocab": {str(k): v for k, v in BAND_VOCAB.items()}, "markRange": goals.mark_range(p)}
