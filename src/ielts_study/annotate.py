"""Rule-based key-phrase and hard-word detection (no LLM).

For each subtitle cue we mark:
  * at most one learner-worthy phrase (curated list first, then ECDICT phrases),
    including separated phrasal verbs such as "pick it up";
  * up to N candidate hard words, each carrying its frequency rank and IELTS flag.
    The player picks which candidates to show from the learner's vocabulary level,
    so changing the level never needs a re-import.
"""
from __future__ import annotations

import re

from .config import CANDIDATE_RANK, GENERAL_RANK, MAX_WORD_CANDIDATES_PER_CUE
from .dictionary import Dictionary
from .gloss import word_glosses

_nlp = None
CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV"}
EXAM_TAGS = ("cet6", "ky", "toefl", "ielts", "gre")
MAX_PHRASE_TOKENS = 6
ANNOTATION_VERSION = 4  # bump when marks/notes change shape; old videos are re-annotated on open


def nlp():
    global _nlp
    if _nlp is None:
        import spacy

        _nlp = spacy.load("en_core_web_sm", disable=["ner"])
    return _nlp


def _word_ok(tok) -> bool:
    return tok.is_alpha or tok.text in ("'s",)


def _phrase_candidates(doc, dic: Dictionary):
    toks = list(doc)
    seen = set()
    for i in range(len(toks)):
        for n in range(min(MAX_PHRASE_TOKENS, len(toks) - i), 1, -1):
            span = toks[i : i + n]
            if not all(_word_ok(t) for t in span):
                continue
            lower = [t.lower_ for t in span]
            lemma = [t.lemma_.lower() for t in span]
            keys = {
                " ".join([lemma[0]] + lower[1:]),
                " ".join(lower),
                " ".join(lemma),
                # "on my own" / "your time" style entries: normalise possessives
                " ".join(["my" if w in ("your", "his", "her", "our", "their") else w for w in lower]),
                " ".join([lemma[0]] + ["your" if w in ("my", "his", "her", "our", "their") else w for w in lower[1:]]),
            }
            for k in keys:
                if k in seen:
                    continue
                e = dic.phrase(k)
                if e and (e["source"] == "curated" or n <= 4):
                    seen.add(k)
                    ranges = [(span[0].idx, span[-1].idx + len(span[-1].text))]
                    yield _score(e, n, span[0].pos_ == "VERB"), ranges, e
    # Separated phrasal verbs: "pick it up", "figure the problem out".
    for t in doc:
        if t.dep_ == "prt" and t.head.pos_ == "VERB" and 0 < t.i - t.head.i <= 4:
            k = f"{t.head.lemma_.lower()} {t.lower_}"
            e = dic.phrase(k)
            if e and k not in seen:
                ranges = [(t.head.idx, t.head.idx + len(t.head.text)), (t.idx, t.idx + len(t.text))]
                yield _score(e, 2, True) + 3, ranges, e


def _score(entry: dict, n_tokens: int, verb_start: bool) -> float:
    s = n_tokens * 10.0
    if entry["source"] == "curated":
        s += 100
    if verb_start:
        s += 5
    return s


def _overlaps(a, ranges) -> bool:
    return any(a[0] < r[1] and r[0] < a[1] for r in ranges)


def _hard_words(doc, dic: Dictionary, taken):
    out = []
    for t in doc:
        if not t.is_alpha or t.is_stop or len(t.text) < 3 or t.pos_ not in CONTENT_POS:
            continue
        if t.text[0].isupper() and t.i > 0:  # likely a name the tagger missed
            continue
        r = (t.idx, t.idx + len(t.text))
        if _overlaps(r, taken):
            continue
        lemma = t.lemma_.lower()
        info = dic.word(lemma, t.pos_) or dic.word(t.lower_, t.pos_)
        if t.lower_ != lemma and t.tag_ in ("VBN", "VBG", "JJ"):
            # "bored", "interested", "amazing": the adjective entry fits better than the verb's
            adjective = dic.word(t.lower_, "ADJ")
            if adjective and adjective["zh"].startswith("a."):
                info = adjective
        if not info or not info["zh"]:
            continue
        rank = info["rank"]
        tags = info["tag"].split()
        if "zk" in tags:  # 中考词汇 counts as known regardless of corpus frequency
            continue
        if t.pos_ == "ADV" and lemma.endswith("ly"):
            # "honestly" is as hard as "honest": judge -ly adverbs by their stem
            stem = dic.word(lemma[:-2]) or dic.word(lemma[:-3] + "y") or dic.word(lemma[:-2] + "e")
            if stem and stem["rank"] > 0:
                rank = min(rank, stem["rank"]) if rank else stem["rank"]
        exam = any(tag in tags for tag in EXAM_TAGS)
        ielts = "ielts" in tags
        # Keep anything that some vocabulary level could want: IELTS words above the lowest level,
        # plus rare / exam words for the general (non-IELTS) level.
        if (ielts and (rank > CANDIDATE_RANK or rank == 0)) or rank > GENERAL_RANK or (rank == 0 and exam):
            out.append((rank or 10**6, r, info, rank, ielts, exam))
    out.sort(key=lambda x: -x[0])
    return out


def annotate_cues(cues: list[dict], dic: Dictionary, progress=None) -> None:
    """Mutates each cue in place, adding `marks`, `notes` and `gl` (a short Chinese gloss per word)."""
    texts = [c["text"] for c in cues]
    total = max(1, len(cues))
    for idx, (cue, doc) in enumerate(zip(cues, nlp().pipe(texts, batch_size=64))):
        marks, notes = [], {}
        best = max(_phrase_candidates(doc, dic), key=lambda x: x[0], default=None)
        taken = []
        if best:
            _, ranges, e = best
            key = "p:" + e["en"]
            notes[key] = {"type": "phrase", "en": e["en"], "zh": e["zh"], "note": e["note"]}
            for s, en in ranges:
                marks.append({"s": s, "e": en, "type": "phrase", "key": key})
            taken.extend(ranges)
        for _, r, info, rank, ielts, exam in _hard_words(doc, dic, taken)[:MAX_WORD_CANDIDATES_PER_CUE]:
            key = "w:" + info["en"]
            notes[key] = {
                "type": "word",
                "en": info["en"],
                "zh": info["zh"],
                "phonetic": info["phonetic"],
                "note": _tag_label(info["tag"]),
                "rank": rank,
                "ielts": ielts,
                "exam": exam,
            }
            marks.append({"s": r[0], "e": r[1], "type": "word", "key": key})
            taken.append(r)
        marks.sort(key=lambda m: m["s"])
        cue["marks"] = marks
        cue["notes"] = notes
        cue["gl"] = word_glosses(doc, dic)
        if progress and idx % 10 == 0:
            progress(idx / total)


TAG_NAMES = {"zk": "中考", "gk": "高考", "cet4": "四级", "cet6": "六级", "ky": "考研", "toefl": "托福", "ielts": "雅思", "gre": "GRE"}


def _tag_label(tag: str) -> str:
    names = [TAG_NAMES[t] for t in re.split(r"\s+", tag or "") if t in TAG_NAMES]
    return " / ".join(names)
