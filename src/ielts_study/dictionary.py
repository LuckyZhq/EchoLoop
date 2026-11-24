"""Offline English→Chinese dictionary built from ECDICT, plus a curated phrase list."""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import threading
from pathlib import Path

from .config import DATA_DIR

CSV_PATH = DATA_DIR / "ecdict.csv"
DB_PATH = DATA_DIR / "ecdict.db"
CURATED_PATH = Path(__file__).resolve().parent / "phrases_curated.json"
DB_VERSION = 3

# Words that make a multi-word entry look like a phrasal verb / idiom rather than a noun compound.
FUNCTION_WORDS = {
    "up", "down", "out", "off", "in", "on", "over", "away", "back", "through", "around", "round",
    "about", "along", "across", "by", "for", "into", "onto", "with", "without", "after", "to", "of",
    "at", "from", "as", "apart", "together", "ahead", "behind", "forward", "aside", "under", "against",
    "the", "a", "an", "it", "one's", "oneself", "all", "no", "not", "so", "than", "what", "how",
    "way", "time", "mind", "sense", "deal", "hand", "point", "matter", "case", "end", "least", "most",
}
LIGHT_VERBS = {
    "make", "take", "get", "go", "come", "have", "do", "give", "keep", "put", "set", "turn", "look",
    "bring", "run", "break", "pay", "catch", "hold", "let", "fall", "pick", "carry", "figure", "work",
    "end", "find", "point", "show", "sort", "call", "cut", "deal", "stand", "move", "check", "hang",
    "mess", "pull", "push", "throw", "wrap", "sum", "fill", "hit", "kick", "play", "lay", "pass",
    "rule", "settle", "sign", "stick", "wind", "back", "blow", "burn", "calm", "cheer", "chill",
    "count", "drop", "freak", "grow", "head", "jump", "knock", "lose", "miss", "open", "pop", "rely",
    "shut", "slow", "speak", "step", "stay", "switch", "talk", "think", "try", "wake", "watch", "wear",
}
# Too basic to be worth highlighting.
TOO_EASY = {
    "a lot", "of course", "you know", "i mean", "kind of", "sort of", "thank you", "a little",
    "a bit", "right now", "so much", "at all", "and so on", "all right", "go to", "come to", "come on",
    "look at", "a few", "as well", "at home", "at the", "in the", "on the", "of the", "to the",
    "have to", "want to", "going to", "get to", "out of", "a lot of", "lots of", "so that", "such as",
    "and then", "because of", "as if", "each other", "go on", "this is", "that is", "it is",
    "there is", "get up", "sit down", "stand up", "come in", "go out", "come back", "go back",
    "go home", "every day", "all the", "the same", "at first", "the end", "on time", "in time",
}
STOP_WORDS = {
    "a", "an", "the", "be", "is", "am", "are", "was", "were", "been", "being", "to", "of", "in", "on",
    "at", "by", "for", "with", "from", "as", "it", "its", "this", "that", "these", "those", "and", "or",
    "but", "if", "so", "do", "does", "did", "have", "has", "had", "will", "would", "can", "could",
    "shall", "should", "may", "might", "must", "i", "you", "he", "she", "we", "they", "me", "him",
    "her", "us", "them", "my", "your", "his", "our", "their", "not", "no", "there", "here", "what",
    "which", "who", "when", "where", "how", "all", "any", "some", "one", "up", "out", "into", "about",
    "than", "then", "too", "very", "just", "also", "only", "more", "most", "such", "own", "same",
}
DOMAIN_TAG = re.compile(r"^\s*\[[^\]]+\]")
PHRASE_OK = re.compile(r"^[a-z][a-z' -]*[a-z]$")
POS_PREFIX = {
    "NOUN": ("n.",),
    "VERB": ("v.", "vt.", "vi."),
    "AUX": ("v.", "aux."),
    "ADJ": ("a.", "adj."),
    "ADV": ("ad.", "adv."),
}


def _rank(frq: str, bnc: str) -> int:
    vals = [int(x) for x in (frq, bnc) if x and x.isdigit() and x != "0"]
    return min(vals) if vals else 0


def _split_lines(translation: str) -> list[str]:
    return [ln.strip() for ln in translation.replace("\\n", "\n").split("\n") if ln.strip()]


def clean_translation(translation: str, pos: str | None = None, max_senses: int = 3, max_lines: int = 2) -> str:
    """Pick the general-purpose lines for this part of speech (e.g. both vt. and vi.) and trim each.

    ECDICT often lists archaic senses first ("commute: vt. 交换, 折偿"), so showing the second
    matching line ("vi. 经常乘车来往") gives the learner a better chance of seeing the right sense.
    """
    lines = _split_lines(translation or "")
    general = [ln for ln in lines if not DOMAIN_TAG.match(ln)]
    if not general:
        general = [DOMAIN_TAG.sub("", ln).strip() for ln in lines if ln.startswith("[网络]")]
    if not general:
        return ""
    chosen = []
    if pos and pos in POS_PREFIX:
        chosen = [ln for ln in general if ln.startswith(POS_PREFIX[pos])][:max_lines]
    if not chosen:
        chosen = general[:1] if pos else general[:max_lines]
    parts = []
    for line in chosen:
        m = re.match(r"^([a-z]+\.)\s*(.*)$", line)
        prefix, body = (m.group(1) + " ", m.group(2)) if m else ("", line)
        senses = list(dict.fromkeys(x.strip() for x in re.split(r"[；;,，]", body) if x.strip()))
        parts.append(prefix + "；".join(senses[:max_senses]))
    return "　".join(parts)


def build_database(log=print) -> None:
    if DB_PATH.exists():
        con = sqlite3.connect(DB_PATH)
        try:
            ver = con.execute("select v from meta").fetchone()[0]
        except sqlite3.Error:
            ver = 0
        con.close()
        if ver == DB_VERSION:
            return
        DB_PATH.unlink()
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"缺少词典文件 {CSV_PATH}，请先运行 setup（见 README）")
    log("首次运行：正在建立离线词典索引（约 30 秒）…")
    csv.field_size_limit(10_000_000)

    ranks: dict[str, int] = {}
    with CSV_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            w = row["word"]
            if " " in w:
                continue
            lw, r = w.lower(), _rank(row["frq"], row["bnc"])
            old = ranks.get(lw, 0)
            ranks[lw] = r if r and (not old or r < old) else old

    def common(w: str) -> bool:
        r = ranks.get(w, 0)
        return w in ("one's", "oneself") or 0 < r <= 20000

    tmp = DB_PATH.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    con.executescript(
        """
        create table meta(v int);
        create table words(word text primary key, phonetic text, translation text,
                           tag text, rank int, exchange text);
        create table phrases(word text primary key, translation text);
        """
    )
    con.execute("insert into meta values (?)", (DB_VERSION,))
    words, phrases = [], []
    with CSV_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            w = row["word"].strip()
            tr = row["translation"]
            if not tr:
                continue
            if " " not in w:
                # lowercase originals sort last so "insert or replace" lets them win over "May"/"Bill"…
                words.append((w == w.lower(), (w.lower(), row["phonetic"], tr, row["tag"], _rank(row["frq"], row["bnc"]), row["exchange"])))
                continue
            lw = w.lower()
            parts = lw.split()
            if w != lw or not PHRASE_OK.match(lw) or not 2 <= len(parts) <= 4 or lw in TOO_EASY:
                continue
            first_line = _split_lines(tr)[0] if _split_lines(tr) else ""
            if not first_line or DOMAIN_TAG.match(first_line):
                continue
            if not all(common(p) for p in parts):
                continue
            if not (parts[0] in LIGHT_VERBS or any(p in FUNCTION_WORDS for p in parts[1:])):
                continue
            if all(p in STOP_WORDS for p in parts):  # "is to", "in the", "be to" …
                continue
            phrases.append((lw, tr))
    words.sort(key=lambda x: x[0])
    con.executemany("insert or replace into words values (?,?,?,?,?,?)", [w for _, w in words])
    con.executemany("insert or ignore into phrases values (?,?)", phrases)
    con.commit()
    con.close()
    tmp.rename(DB_PATH)
    log(f"词典就绪：{len(words)} 个单词，{len(phrases)} 条短语")


class Dictionary:
    def __init__(self, log=print):
        build_database(log)
        self._con = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._lock = threading.Lock()
        self._phrases: dict[str, str] = dict(self._con.execute("select word, translation from phrases"))
        self.curated: dict[str, dict] = {}
        for e in json.loads(CURATED_PATH.read_text(encoding="utf-8")):
            self.curated[e["en"].lower()] = e

    def _row(self, w: str):
        with self._lock:
            return self._con.execute(
                "select word, phonetic, translation, tag, rank, exchange from words where word = ?", (w,)
            ).fetchone()

    def word(self, w: str, pos: str | None = None) -> dict | None:
        row = self._row(w.lower())
        if not row:
            return None
        word, phonetic, tr, tag, rank, exchange = row
        return {
            "en": word,
            "phonetic": phonetic or "",
            "zh": clean_translation(tr, pos),
            "tag": tag or "",
            "rank": rank or 0,
            "exchange": exchange or "",
        }

    def base_form(self, w: str) -> str:
        """Return the dictionary lemma of an inflected form using ECDICT's exchange field."""
        row = self._row(w.lower())
        if row and row[5]:
            for part in row[5].split("/"):
                if part.startswith("0:"):
                    return part[2:]
        return w.lower()

    def lookup(self, w: str) -> dict | None:
        base = self.base_form(w)
        return self.word(base) or self.word(w)

    def phrase(self, key: str) -> dict | None:
        key = key.lower()
        if key in self.curated:
            e = self.curated[key]
            return {"en": e["en"], "zh": e["zh"], "note": e.get("note", ""), "source": "curated"}
        if key in TOO_EASY:
            return None
        tr = self._phrases.get(key)
        if tr:
            zh = clean_translation(tr, max_senses=3)
            if zh:
                return {"en": key, "zh": zh, "note": "", "source": "ecdict"}
        return None
