"""Sentences kept after their video is deleted: the mistakes and saved words still need the text and the sound.

Deleting a video moves the sentences that matter (dictation below the pass mark, and the ones saved words came
from) into LIBRARY_DIR/kept/<video id>/, together with a short audio clip of each sentence:

    kept/<vid>/meta.json   {"id", "title", "cues": {"12": {"text", "zh", "start", "end", "audio"}},
                            "dictation": {"12": {score, best, tries, typed, at}}}
    kept/<vid>/12.m4a      the sentence, cut from the video (about 40 KB)

Video ids always contain "-" (extractor-id), so the "kept" folder never collides with a video.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import config

PASS = 0.9
PAD_BEFORE, PAD_AFTER = 0.1, 0.3  # seconds of air around the sentence, so the first and last words are whole
BATCH = 60                        # clips per ffmpeg run (one decoding pass each; keeps the command line short)
AUDIO_NAME = re.compile(r"^\d{1,6}\.m4a$")
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def kept_dir() -> Path:
    return config.LIBRARY_DIR / "kept"


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def load(vid: str) -> dict | None:
    if not SAFE_ID.match(vid or ""):
        return None
    meta = _read(kept_dir() / vid / "meta.json", None)
    return meta if isinstance(meta, dict) else None


def save(meta: dict) -> None:
    d = kept_dir() / meta["id"]
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "meta.tmp"
    tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    tmp.replace(d / "meta.json")


def all_kept() -> list[dict]:
    if not kept_dir().is_dir():
        return []
    return [m for d in sorted(kept_dir().iterdir()) if (m := load(d.name))]


def audio_path(vid: str, name: str) -> Path | None:
    return kept_dir() / vid / name if AUDIO_NAME.match(name) else None


def nearest_cue(cues: list[dict], t: float) -> int | None:
    """Index of the cue a saved word came from (saved with the cue's start time)."""
    best = min(range(len(cues)), key=lambda i: abs(cues[i].get("start", 1e9) - t), default=None)
    if best is None or abs(cues[best].get("start", 1e9) - t) > 1:
        return None
    return best


def cut_clips(media: Path, clips: list[tuple[float, float, Path]], ffmpeg: str) -> set[Path]:
    """Cut each (start, end, out) from media as mono AAC. Returns the files that were written."""
    written = set()
    for k in range(0, len(clips), BATCH):
        batch = clips[k:k + BATCH]
        cmd = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", "-i", str(media)]
        for start, end, out in batch:
            s = max(0.0, start - PAD_BEFORE)
            cmd += ["-map", "0:a:0", "-ss", f"{s:.3f}", "-to", f"{end + PAD_AFTER:.3f}",
                    "-ac", "1", "-c:a", "aac", "-b:a", "64k", str(out)]
        try:
            subprocess.run(cmd, capture_output=True, timeout=600)
        except (OSError, subprocess.SubprocessError):
            continue
        written |= {out for _, _, out in batch if out.is_file() and out.stat().st_size > 0}
    return written


def archive(vdir: Path, vocab: list[dict], ffmpeg: str | None = None) -> dict:
    """Keep what a video's mistakes and saved words need before the video folder is deleted."""
    vid = vdir.name
    data = _read(vdir / "data.json", None)
    if not isinstance(data, dict):
        return {"sentences": 0, "audio": 0}
    cues = data.get("cues") or []
    records = _read(vdir / "dictation.json", {})
    records = records if isinstance(records, dict) else {}
    wrong = {i: r for i, r in records.items()
             if i.isdigit() and int(i) < len(cues) and isinstance(r, dict) and r.get("score", 1) < PASS}
    wanted = {int(i) for i in wrong}
    for v in vocab:
        if v.get("videoId") == vid:
            i = nearest_cue(cues, float(v.get("time") or 0))
            if i is not None:
                wanted.add(i)

    meta = load(vid) or {"id": vid, "cues": {}, "dictation": {}}  # a re-imported video deleted again
    meta["title"] = data.get("title") or meta.get("title") or vid
    meta["url"] = data.get("url") or meta.get("url", "")
    meta["dictation"].update(wrong)
    if not wanted:
        if meta["cues"]:
            save(meta)
        return {"sentences": 0, "audio": 0}

    d = kept_dir() / vid
    d.mkdir(parents=True, exist_ok=True)
    media = vdir / (data.get("video") or "")
    todo = []
    for i in sorted(wanted):
        c = cues[i]
        meta["cues"][str(i)] = {"text": c.get("text", ""), "zh": c.get("zh", ""),
                                "start": c.get("start", 0), "end": c.get("end", 0), "audio": ""}
        todo.append((float(c.get("start", 0)), float(c.get("end", 0)), d / f"{i}.m4a"))
    if media.is_file() and data.get("video"):
        if ffmpeg is None:
            from .storage import ffmpeg_exe
            ffmpeg = ffmpeg_exe()
        for out in cut_clips(media, todo, ffmpeg):
            meta["cues"][out.stem]["audio"] = out.name
    save(meta)
    return {"sentences": len(wanted), "audio": sum(1 for i in wanted if meta["cues"][str(i)]["audio"])}


def clip(vid: str, t: float) -> dict | None:
    """The kept clip of the sentence a saved word came from, shaped like the review page expects."""
    meta = load(vid)
    if not meta:
        return None
    cues = meta.get("cues") or {}
    keys = list(cues)
    i = nearest_cue([cues[k] for k in keys], t)
    if i is None:
        return None
    c = cues[keys[i]]
    if not c.get("audio"):
        return None
    return clip_of(vid, c)


def clip_of(vid: str, cue: dict) -> dict:
    length = max(0.5, float(cue.get("end", 0)) - max(0.0, float(cue.get("start", 0)) - PAD_BEFORE) + PAD_AFTER)
    return {"src": f"/kept/{vid}/{cue['audio']}", "start": 0, "end": round(length, 3)}


def record_dictation(vid: str, i: int, update) -> dict | None:
    """Store a new dictation try for a kept sentence. `update(prev) -> record`."""
    meta = load(vid)
    if not meta or str(i) not in (meta.get("cues") or {}):
        return None
    meta.setdefault("dictation", {})
    meta["dictation"][str(i)] = update(meta["dictation"].get(str(i), {}))
    save(meta)
    return meta["dictation"][str(i)]


def mistakes(skip: set[str]) -> list[dict]:
    """Mistakes from deleted videos (videos in `skip` are back in the library and listed from there)."""
    out = []
    for meta in all_kept():
        if meta["id"] in skip:
            continue
        for i, r in (meta.get("dictation") or {}).items():
            c = (meta.get("cues") or {}).get(i)
            if not c or not isinstance(r, dict) or r.get("score", 1) >= PASS:
                continue
            out.append({
                "videoId": meta["id"], "title": meta.get("title") or meta["id"], "i": int(i), "deleted": True,
                "text": c["text"], "zh": c.get("zh", ""), "start": c.get("start", 0),
                "clip": clip_of(meta["id"], c) if c.get("audio") else None,
                "score": r.get("score", 0), "best": r.get("best", 0), "tries": r.get("tries", 1),
                "typed": r.get("typed", ""), "at": r.get("at", 0),
            })
    return out
