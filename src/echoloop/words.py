"""The word ledger: one record per word or phrase, in LIBRARY_DIR/words.json.

Every page asks this one place what state a word is in:

    status    unseen    has a record but isn't being studied (e.g. 认识 taken back on a word never reviewed)
              learning  in 单词复习: new until its first answer, then scheduled by its `srs`
              known     the learner knows it: never marked as a hard word, never offered by a 词书, never reviewed
    sources   where it came from — "video", "article", a 词书 id ("cet4", "ielts", …), "marked" (✓ 认识), "saved";
              labels only: a word met in several places is still one record
    srs       the spaced-repetition state from review.schedule (unchanged SM-2), kept even if the word becomes known

The other fields are the ones a review card needs: zh, note, phonetic, the sentence it was met in (sentence,
sentenceZh, spans) and where (videoId + time, or articleId + sentenceIndex).

Sentences saved on their own (句子收藏) are kept apart in LIBRARY_DIR/sentences.json.

This replaced three separate records (vocab.json, profile.json's "known" list, wordbook.json's skipEasy);
`migrate()` folds them in once, keeping every review schedule as it was.
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
import zipfile

from . import config

STATUSES = ("unseen", "learning", "known")
MATURE_IVL = 21  # days: well remembered, so no longer marked as a hard word (unchanged rule)
_lock = threading.RLock()


def path():
    return config.LIBRARY_DIR / "words.json"


def sentences_path():
    return config.LIBRARY_DIR / "sentences.json"


def _read(p, default):
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def _write(p, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def key(en: str) -> str:
    return " ".join(str(en or "").lower().split())


# ------------------------------------------------------------------ migration from the three old records

def _sources_of(v: dict) -> list[str]:
    if v.get("book"):
        return [v["book"]]  # its sentence (if any) is only an example
    if v.get("videoId"):
        return ["video"]
    if v.get("articleId"):
        return ["article"]
    return ["saved"]


def migrate(now: float | None = None) -> dict | None:
    """Fold vocab.json, profile.json's known list and wordbook.json into words.json (once).

    The three old files are zipped to backup-before-words-merge.zip first; afterwards vocab.json becomes
    vocab.json.bak, and profile.json / wordbook.json keep a .bak copy of how they were. Returns a summary, or
    None when there was nothing to do."""
    lib = config.LIBRARY_DIR
    vocab_file, profile_file, book_file = lib / "vocab.json", lib / "profile.json", lib / "wordbook.json"
    with _lock:
        if path().exists():
            return None
        old = [f for f in (vocab_file, profile_file, book_file) if f.is_file()]
        if not old:
            _write(path(), [])
            return None
        now = time.time() if now is None else now
        vocab = _read(vocab_file, [])
        profile = _read(profile_file, {})
        book = _read(book_file, {})
        known = [key(w) for w in profile.get("known") or [] if key(w)]

        records, index = [], {}
        for v in vocab:
            k = key(v.get("en"))
            if not k or k in index:
                continue
            rec = {**v, "status": "learning", "sources": _sources_of(v)}
            index[k] = rec
            records.append(rec)
        for k in dict.fromkeys(known):
            if k in index:
                index[k]["status"] = "known"
                if "marked" not in index[k]["sources"]:
                    index[k]["sources"].append("marked")
            else:
                rec = {"en": k, "type": "word", "status": "known", "sources": ["marked"], "added": int(now)}
                index[k] = rec
                records.append(rec)

        with zipfile.ZipFile(lib / "backup-before-words-merge.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for f in old:
                z.write(f, f.name)
        _write(path(), records)
        if vocab_file.is_file():
            vocab_file.replace(lib / "vocab.json.bak")
        if profile_file.is_file():
            shutil.copy2(profile_file, lib / "profile.json.bak")
            profile.pop("known", None)
            _write(profile_file, profile)
        if book_file.is_file():
            shutil.copy2(book_file, lib / "wordbook.json.bak")
            _write(book_file, {"book": book.get("book")})
        return {"words": len(records), "known": sum(r["status"] == "known" for r in records),
                "due": sum(1 for r in records if r["status"] == "learning" and r.get("srs") and r["srs"]["due"] <= now)}


# ------------------------------------------------------------------ reading

def load() -> list[dict]:
    """Every record (migrating the old files the first time)."""
    if not path().exists():
        migrate()
    items = _read(path(), [])
    for r in items:  # tolerate hand-edited files
        if r.get("status") not in STATUSES:
            r["status"] = "learning"
        r.setdefault("sources", ["saved"])
    return items


def find(items: list[dict], en: str) -> dict | None:
    k = key(en)
    return next((r for r in items if key(r.get("en")) == k), None)


def learning(items: list[dict]) -> list[dict]:
    """The words in 单词复习."""
    return [r for r in items if r["status"] == "learning"]


def known_words(items: list[dict]) -> list[str]:
    return sorted(key(r["en"]) for r in items if r["status"] == "known")


def mature_words(items: list[dict]) -> list[str]:
    return sorted(key(r["en"]) for r in items
                  if r["status"] == "learning" and (r.get("srs") or {}).get("ivl", 0) >= MATURE_IVL)


def taken(items: list[dict]) -> set[str]:
    """Words a 词书 won't offer as new: being learned or known. (The one place this is decided.)"""
    return {key(r["en"]) for r in items if r["status"] in ("learning", "known")}


# ------------------------------------------------------------------ changes (each loads, changes, saves under the lock)

def save(items: list[dict]) -> None:
    with _lock:
        _write(path(), items)


def _merge_source(rec: dict, source: str) -> None:
    if source and source not in rec.setdefault("sources", []):
        rec["sources"].append(source)


def add(item: dict, source: str) -> dict:
    """Save a word or phrase from a video or article: it joins 单词复习 at once (a known word is learned again).
    Saving it again refreshes its sentence and keeps its review progress."""
    with _lock:
        items = load()
        rec = find(items, item["en"])
        if rec:
            items.remove(rec)
            merged = {**rec, **{k: v for k, v in item.items() if v not in ("", None) or k not in rec}}
            merged["status"] = "learning"
            _merge_source(merged, source)
        else:
            merged = {**item, "status": "learning", "sources": [source]}
        items.insert(0, merged)
        save(items)
        return merged


def remove(en: str) -> bool:
    """Take a word out of 我的生词 / 单词复习. A known word stays known (only its study data goes)."""
    with _lock:
        items = load()
        rec = find(items, en)
        if not rec:
            return False
        if rec["status"] == "known":
            items[items.index(rec)] = {"en": rec["en"], "type": rec.get("type", "word"), "status": "known",
                                       "sources": ["marked"], "added": rec.get("added", int(time.time()))}
        else:
            items.remove(rec)
        save(items)
        return True


def set_known(en: str, known: bool) -> dict | None:
    """✓ 认识 (or taking it back). A known word leaves review but keeps its schedule, so taking it back resumes it."""
    k = key(en)[:100]
    if not k:
        return None
    with _lock:
        items = load()
        rec = find(items, k)
        if known:
            if rec:
                rec["status"] = "known"
                _merge_source(rec, "marked")
            else:
                rec = {"en": k, "type": "word", "status": "known", "sources": ["marked"], "added": int(time.time())}
                items.insert(0, rec)
        elif rec and rec["status"] == "known":
            studied = rec.get("srs") or any(s != "marked" for s in rec.get("sources", []))
            if studied:
                rec["status"] = "learning"
                rec["sources"] = [s for s in rec["sources"] if s != "marked"] or ["saved"]
            else:
                items.remove(rec)
                rec = None
        save(items)
        return rec


def grade(en: str, answer: str, new_item: dict | None = None, now: float | None = None) -> dict | None:
    """Record a review answer (review.schedule, unchanged). `new_item` is a 词书 word met for the first time."""
    from . import review

    with _lock:
        items = load()
        rec = find(items, en)
        if not rec and new_item:
            rec = {**new_item, "status": "learning", "sources": [new_item["book"]]}
            items.insert(0, rec)
        if not rec:
            return None
        rec["srs"] = review.schedule(rec.get("srs"), answer, time.time() if now is None else now)
        rec["status"] = "learning"
        save(items)
        return rec


# ------------------------------------------------------------------ 句子收藏

def load_sentences() -> list[dict]:
    return _read(sentences_path(), [])


def add_sentence(item: dict) -> dict:
    with _lock:
        items = load_sentences()
        same = next((s for s in items if s["text"] == item["text"]), None)
        if same:
            return same
        entry = {"id": uuid.uuid4().hex[:12], "added": int(time.time()), **item}
        items.insert(0, entry)
        _write(sentences_path(), items)
        return entry


def remove_sentence(sid: str) -> bool:
    with _lock:
        items = load_sentences()
        rest = [s for s in items if s.get("id") != sid]
        if len(rest) == len(items):
            return False
        _write(sentences_path(), rest)
        return True
