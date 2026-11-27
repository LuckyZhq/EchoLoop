"""Download a video from a pasted link and obtain English subtitle cues.

1. yt-dlp downloads the video (mp4) and any *human-made* English subtitles.
2. If there are none, Whisper (MLX, local on Apple Silicon) transcribes the audio.
"""
from __future__ import annotations

import copy
import html
import json
import re
import sys
import time
from functools import lru_cache
from pathlib import Path

from .config import DATA_DIR, QUALITY_FORMATS


def ffmpeg_dir() -> Path:
    import imageio_ffmpeg

    bin_dir = DATA_DIR / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / FFMPEG_NAME
    exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not link.exists() or (link.is_symlink() and link.resolve() != exe.resolve()):
        if link.is_symlink() or link.exists():
            link.unlink()
        try:
            link.symlink_to(exe)
        except OSError:  # Windows without symlink rights: a copy works the same
            import shutil

            shutil.copy2(exe, link)
    return bin_dir


FFMPEG_NAME = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


THUMB_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def local_thumbnail(vdir: Path) -> Path | None:
    return next((f for f in (vdir / f"thumb{ext}" for ext in THUMB_TYPES.values()) if f.is_file()), None)


def https(url: str) -> str:
    """Bilibili (and some others) give cover addresses as http://; the same image is served over https."""
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


def save_thumbnail(url: str, vdir: Path) -> Path | None:
    """Download the cover image into vdir as thumb.jpg/png/webp. Returns None if it can't be fetched."""
    from urllib.request import Request, urlopen

    url = https(url)
    if not url.startswith("https://"):
        return None
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=10) as r:
            ext = THUMB_TYPES.get(r.headers.get_content_type())
            body = r.read(3_000_001)
    except OSError:
        return None
    if not ext or len(body) > 3_000_000:
        return None
    target = vdir / f"thumb{ext}"
    tmp = target.with_suffix(".part")
    tmp.write_bytes(body)
    tmp.replace(target)
    return target


def _base_opts(log) -> dict:
    class _Logger:
        def debug(self, msg):
            if not msg.startswith("[debug]"):
                log(msg)

        def info(self, msg):
            log(msg)

        def warning(self, msg):
            log("⚠ " + msg)

        def error(self, msg):
            log("✗ " + msg)

    return {
        "logger": _Logger(),
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 5,
        "extractor_retries": 5,
        "ffmpeg_location": str(ffmpeg_dir()),
        "js_runtimes": {"deno": {}, "node": {}},
    }


def _transient_network_error(err: Exception) -> bool:
    msg = str(err).lower()
    return any(tok in msg for tok in (
        "unexpected_eof_while_reading",
        "sslerror",
        "ssleoferror",
        "timed out",
        "connection reset",
        "incompleteread",
        "unable to download webpage",
        "failed to download m3u8",
    ))


APPLE_EPISODE = re.compile(r"^https://podcasts\.apple\.com/.*?/id(\d+)\?(?:.*&)?i=(\d+)")
XIAOYUZHOU_EPISODE = re.compile(r"^https://www\.xiaoyuzhoufm\.com/episode/([0-9a-f]{24})")


def _fetch(url: str, limit: int = 3_000_000) -> bytes:
    from urllib.request import Request, urlopen

    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
        return r.read(limit)


@lru_cache(maxsize=64)
def resolve_podcast(url: str) -> dict | None:
    """Episode pages whose audio yt-dlp can't find, as an info dict pointing at the audio file ("_media_url").
    Apple Podcasts: Apple's public lookup API lists a show's latest 200 episodes with their audio files.
    小宇宙: the episode page names its audio in og:audio. Anything else: None (yt-dlp handles it)."""
    m = APPLE_EPISODE.match(url)
    if m:
        show, episode = m.groups()
        data = json.loads(_fetch(f"https://itunes.apple.com/lookup?id={show}&entity=podcastEpisode&limit=200"))
        ep = next((r for r in data.get("results", []) if str(r.get("trackId")) == episode), None)
        if not ep or not ep.get("episodeUrl"):
            raise RuntimeError("在 Apple Podcasts 里找不到这一集的音频（可能太早了，只能找到最近 200 集）。"
                               "可以换成这一集在其他平台的链接。")
        return {"id": episode, "extractor_key": "ApplePodcasts", "title": ep.get("trackName") or episode,
                "uploader": ep.get("collectionName") or "", "duration": (ep.get("trackTimeMillis") or 0) / 1000 or None,
                "thumbnail": ep.get("artworkUrl600") or "", "webpage_url": url, "_media_url": ep["episodeUrl"]}
    m = XIAOYUZHOU_EPISODE.match(url)
    if m:
        page = _fetch(url).decode("utf-8", "replace")
        meta = {k: html.unescape(v) for k, v in re.findall(r'<meta property="og:(\w+)" content="([^"]*)"', page)}
        if not meta.get("audio"):
            raise RuntimeError("小宇宙这一集的页面里没有找到音频，可能需要登录或已下架。")
        return {"id": m.group(1), "extractor_key": "Xiaoyuzhou", "title": meta.get("title") or m.group(1),
                "uploader": "", "duration": None, "thumbnail": meta.get("image", ""), "webpage_url": url,
                "_media_url": meta["audio"]}
    from urllib.parse import unquote, urlparse

    path = urlparse(url).path
    if url.startswith(("http://", "https://")) and Path(path).suffix.lower() in (".mp3", ".m4a", ".aac", ".ogg", ".opus"):
        import hashlib  # a direct link to an audio file, e.g. from a podcast's RSS feed

        name = unquote(Path(path).stem)
        return {"id": hashlib.sha1(url.encode()).hexdigest()[:16], "extractor_key": "Audio", "title": name,
                "uploader": "", "duration": None, "thumbnail": "", "webpage_url": url, "_media_url": url}
    return None


def probe(url: str, log=print) -> dict:
    import yt_dlp

    podcast = resolve_podcast(url)
    if podcast:
        return podcast
    # a show or feed address: only its newest item is read (resolving a whole feed takes minutes)
    opts = {**_base_opts(log), "skip_download": True, "playlist_items": "1"}
    last_error = None
    for attempt in range(3):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if info.get("_type") == "playlist" and info.get("entries"):
                info = next(e for e in info["entries"] if e)
            if info.get("formats") or info.get("url") or attempt == 2:
                return info
            log("⚠ 未获取到视频格式，正在重试解析…")
        except Exception as err:
            last_error = err
            if attempt == 2 or not _transient_network_error(err):
                raise
            log(f"⚠ 连接波动，正在第 {attempt + 2} 次重试解析…")
        time.sleep(1.5 * (attempt + 1))
    raise last_error  # pragma: no cover


def video_key(info: dict) -> str:
    ex = re.sub(r"[^a-z0-9]+", "", (info.get("extractor_key") or info.get("extractor") or "web").lower())
    vid = re.sub(r"[^A-Za-z0-9_-]+", "_", str(info.get("id") or "video"))
    return f"{ex}-{vid}"[:80]


def english_sub_langs(info: dict) -> list[str]:
    subs = info.get("subtitles") or {}
    langs = [l for l in subs if re.match(r"^en($|[-_])", l, re.I) and "live_chat" not in l]
    langs.sort(key=lambda l: (l.lower() != "en", len(l)))
    return langs[:1]


AUDIO_TYPES = {"audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
               "audio/aac": ".aac", "audio/ogg": ".ogg", "audio/opus": ".opus", "audio/wav": ".wav", "audio/x-wav": ".wav"}


def download_audio(url: str, out_dir: Path, log=print, progress=None) -> Path:
    """Download a podcast episode's audio file. (yt-dlp's generic downloader trips over some podcast
    tracking redirects, e.g. BBC's, that a plain download follows fine.)"""
    from urllib.parse import urlparse
    from urllib.request import Request, urlopen

    log("下载播客音频…")
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
            ext = AUDIO_TYPES.get(r.headers.get_content_type()) or Path(urlparse(r.url).path).suffix.lower()
            if ext not in MEDIA_TYPES:
                ext = ".mp3"
            total = int(r.headers.get("Content-Length") or 0)
            target = out_dir / f"video{ext}"
            done = 0
            with target.open("wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    if total and progress:
                        progress(min(0.99, done / total))
    except OSError as error:
        raise RuntimeError(f"播客音频下载失败：{error}") from None
    if done < 10_000:
        raise RuntimeError("播客音频下载失败：文件是空的")
    return target


# video files, and the audio files podcasts come as
MEDIA_TYPES = (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".aac", ".ogg", ".opus", ".wav", ".flac")


def download(url: str, out_dir: Path, quality: str, log=print, progress=None, info: dict | None = None) -> tuple[Path, Path | None]:
    """Returns (video_path, subtitle_path_or_None)."""
    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)
    if info is None:
        info = probe(url, log)
    if info.get("_media_url"):  # a podcast episode: its audio is a plain file
        return download_audio(info["_media_url"], out_dir, log, progress), None
    sub_langs = english_sub_langs(info)

    def hook(d):
        if d.get("status") == "downloading" and progress:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                progress(min(0.99, d.get("downloaded_bytes", 0) / total))

    opts = {
        **_base_opts(log),
        "outtmpl": str(out_dir / "video.%(ext)s"),
        "format": QUALITY_FORMATS.get(quality, QUALITY_FORMATS["720"]),
        # Prefer resolution, then browser-friendly codecs among equal resolutions.
        "format_sort": ["hasvid", "height", "vcodec:h264", "acodec:aac", "ext:mp4:m4a"],
        "format_sort_force": True,
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
        "writesubtitles": bool(sub_langs),
        "writeautomaticsub": False,
        "subtitleslangs": sub_langs,
        "subtitlesformat": "vtt/srt/best",
        "overwrites": True,
    }
    for attempt in range(3):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                if info.get("formats") or info.get("url"):
                    ydl.process_ie_result(copy.deepcopy(info), download=True)
                else:
                    ydl.download([info.get("webpage_url") or url])
            break
        except Exception as err:
            if attempt == 2 or not _transient_network_error(err):
                raise
            log(f"⚠ 下载连接中断，正在第 {attempt + 2} 次重试…")
            time.sleep(1.5 * (attempt + 1))

    video = next((p for p in out_dir.glob("video.*") if p.suffix.lower() in MEDIA_TYPES), None)
    if video is None:
        raise RuntimeError("视频下载失败：没有找到输出文件")
    if video.suffix.lower() not in (".mp4", ".m4a", ".mp3", ".webm"):
        log(f"⚠ 视频格式为 {video.suffix}，部分浏览器可能无法播放")
    sub = next((p for p in out_dir.glob("video.*") if p.suffix.lower() in (".vtt", ".srt")), None)
    return video, sub


# ---------------------------------------------------------------- subtitle parsing

_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
# a stray timing line duplicated inside the subtitle text (seen in scraped VTT)
_TS_LINE = re.compile(_TS.pattern + r"\s*-->\s*" + _TS.pattern)


def _secs(m) -> float:
    h, mi, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def _clean_text(t: str) -> str:
    if _TS_LINE.search(t):  # the text after each stray timing line repeats the cue, so keep one copy
        t = next((p for p in _TS_LINE.sub("\0", t).split("\0") if p.strip()), "")
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    t = re.sub(r"\[[^\]]*\]|\([^)]*(music|applause|laughter|inaudible)[^)]*\)", "", t, flags=re.I)
    t = t.replace("♪", "").replace("\n", " ")
    t = re.sub(r"^\s*(>>|-)\s*", "", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_subtitles(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8", errors="replace").replace("\r", "")
    cues = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [l for l in block.split("\n") if l.strip()]
        for j, line in enumerate(lines):
            if "-->" in line:
                a, b = line.split("-->", 1)
                ma, mb = _TS.search(a), _TS.search(b)
                if not (ma and mb):
                    break
                text = _clean_text("\n".join(lines[j + 1 :]))
                if text:
                    cues.append({"start": _secs(ma), "end": _secs(mb), "text": text})
                break
    # drop exact consecutive duplicates (common in scraped VTT)
    out = []
    for c in cues:
        if out and out[-1]["text"] == c["text"]:
            out[-1]["end"] = max(out[-1]["end"], c["end"])
        else:
            out.append(c)
    return out


# ---------------------------------------------------------------- whisper

def transcribe(video: Path, log=print, progress=None) -> list[dict]:
    """English cues with word timings, from the engine chosen in Settings (see asr.py)."""
    from . import asr

    words, segments, _ = asr.words_and_segments(video, log, progress)
    if not words:  # fall back to segment-level cues
        return [s for s in segments if s.get("text")]
    return regroup_words(words)


WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]*")  # same as the player's WORD_RE
# Words that usually start a new clause: a good place to split a long sentence.
CLAUSE_STARTS = {"and", "but", "so", "because", "which", "when", "if", "or", "then", "while", "where",
                 "who", "although", "though", "since", "unless", "until", "whereas"}


def _make_cue(ws: list[dict]) -> dict | None:
    """Join Whisper words into one cue and keep a [start, end] timing for every word the player highlights."""
    text, spans = "", []
    for w in ws:
        piece = re.sub(r"\s+", " ", w["word"])
        if not text:
            piece = piece.lstrip()
        spans.append((len(text), len(text) + len(piece), w["start"], w["end"]))
        text += piece
    text = text.rstrip()
    if not text:
        return None
    timings = []
    for m in WORD_RE.finditer(text):
        owner = next((sp for sp in spans if sp[0] <= m.start() < sp[1]), spans[-1])
        timings.append([round(owner[2], 2), round(owner[3], 2)])
    return {"start": ws[0]["start"], "end": ws[-1]["end"], "text": text, "wt": timings}


def regroup_words(words: list[dict], soft_words: int = 14, max_words: int = 26, max_gap: float = 0.9) -> list[dict]:
    """Turn word timestamps into readable cues that follow sentence boundaries.

    A cue ends at a full stop / question mark. A long sentence is split only at a comma or
    before a clause word ("and", "because", ...) once it has `soft_words` words, at a pause,
    or as a last resort at `max_words`.
    """
    cues, cur = [], []

    def flush():
        if cur:
            cue = _make_cue(cur)
            if cue:
                cues.append(cue)
        cur.clear()

    for w in words:
        token = w["word"].strip()
        bare = token.lower().strip(",.;:!?\"'")
        if cur:
            gap = w["start"] - cur[-1]["end"]
            if gap > max_gap or (len(cur) >= soft_words and (gap > 0.45 or bare in CLAUSE_STARTS)):
                flush()
        cur.append(w)
        ends_sentence = bool(re.search(r"[.?!]['\"]?$", token))
        soft_break = bool(re.search(r"[,;:]$", token)) and len(cur) >= soft_words
        if ends_sentence or soft_break or len(cur) >= max_words:
            flush()
    flush()
    return cues


def merge_fragments(cues: list[dict], max_words: int = 22, max_secs: float = 9.0) -> list[dict]:
    """Join subtitle lines that split one sentence across several cues."""
    out: list[dict] = []
    for c in cues:
        prev = out[-1] if out else None
        if (
            prev
            and not re.search(r"[.?!…]['\"]?$", prev["text"])
            and len(prev["text"].split()) + len(c["text"].split()) <= max_words
            and c["end"] - prev["start"] <= max_secs
            and c["start"] - prev["end"] < 1.0
        ):
            prev["text"] = f'{prev["text"]} {c["text"]}'
            prev["end"] = c["end"]
        else:
            out.append(dict(c))
    return out


def get_cues(video: Path, sub: Path | None, log=print, progress=None) -> tuple[list[dict], str]:
    if sub is not None:
        cues = merge_fragments(parse_subtitles(sub))
        if len(cues) >= 3:
            log(f"使用平台自带的英文字幕（{len(cues)} 句），跳过语音识别")
            return cues, "subtitles"
    return transcribe(video, log, progress), "whisper"
