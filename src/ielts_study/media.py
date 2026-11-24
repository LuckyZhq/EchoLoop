"""Download a video from a pasted link and obtain English subtitle cues.

1. yt-dlp downloads the video (mp4) and any *human-made* English subtitles.
2. If there are none, Whisper (MLX, local on Apple Silicon) transcribes the audio.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from .config import APPLE_SILICON, DATA_DIR, QUALITY_FORMATS, WHISPER_MODEL


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


def save_thumbnail(url: str, vdir: Path) -> Path | None:
    """Download the cover image into vdir as thumb.jpg/png/webp. Returns None if it can't be fetched."""
    from urllib.request import Request, urlopen

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
        "retries": 3,
        "fragment_retries": 3,
        "ffmpeg_location": str(ffmpeg_dir()),
        "js_runtimes": {"deno": {}, "node": {}},
    }


def probe(url: str, log=print) -> dict:
    import yt_dlp

    with yt_dlp.YoutubeDL({**_base_opts(log), "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist" and info.get("entries"):
        info = next(e for e in info["entries"] if e)
    return info


def video_key(info: dict) -> str:
    ex = re.sub(r"[^a-z0-9]+", "", (info.get("extractor_key") or info.get("extractor") or "web").lower())
    vid = re.sub(r"[^A-Za-z0-9_-]+", "_", str(info.get("id") or "video"))
    return f"{ex}-{vid}"[:80]


def english_sub_langs(info: dict) -> list[str]:
    subs = info.get("subtitles") or {}
    langs = [l for l in subs if re.match(r"^en($|[-_])", l, re.I) and "live_chat" not in l]
    langs.sort(key=lambda l: (l.lower() != "en", len(l)))
    return langs[:1]


def download(url: str, out_dir: Path, quality: str, log=print, progress=None) -> tuple[Path, Path | None]:
    """Returns (video_path, subtitle_path_or_None)."""
    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)
    info = probe(url, log)
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
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([info.get("webpage_url") or url])

    video = next((p for p in out_dir.glob("video.*") if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")), None)
    if video is None:
        raise RuntimeError("视频下载失败：没有找到输出文件")
    if video.suffix.lower() != ".mp4":
        log(f"⚠ 视频格式为 {video.suffix}，部分浏览器可能无法播放")
    sub = next((p for p in out_dir.glob("video.*") if p.suffix.lower() in (".vtt", ".srt")), None)
    return video, sub


# ---------------------------------------------------------------- subtitle parsing

_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


def _secs(m) -> float:
    h, mi, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def _clean_text(t: str) -> str:
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
    """English cues with word timings, from the best local engine for this computer."""
    if not APPLE_SILICON:
        return transcribe_faster_whisper(video, log, progress)
    import mlx_whisper

    log(f"本地语音识别中（模型 {WHISPER_MODEL}，首次使用会自动下载）…")
    if progress:
        progress(0.05)
    result = mlx_whisper.transcribe(
        str(video),
        path_or_hf_repo=WHISPER_MODEL,
        language="en",
        word_timestamps=True,
        condition_on_previous_text=False,
        verbose=None,
    )
    words = [w for seg in result.get("segments", []) for w in seg.get("words", [])]
    if not words:  # fall back to segment-level cues
        return [
            {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
            for s in result.get("segments", [])
            if s["text"].strip()
        ]
    return regroup_words(words)


def _faster_whisper_setup() -> tuple[str, str, str]:
    """(model, device, compute type): the large model on an NVIDIA GPU, a small English one on the CPU."""
    try:
        import ctranslate2

        gpu = ctranslate2.get_cuda_device_count() > 0
    except Exception:  # no CUDA runtime
        gpu = False
    model = WHISPER_MODEL or ("large-v3-turbo" if gpu else "small.en")
    return model, ("cuda" if gpu else "cpu"), ("float16" if gpu else "int8")


def _audio_16k(video: Path):
    """Mono 16 kHz float audio decoded with our own ffmpeg (faster-whisper's PyAV decoder varies by platform)."""
    import subprocess

    import numpy as np

    raw = subprocess.run([str(ffmpeg_dir() / FFMPEG_NAME), "-nostdin", "-v", "error", "-i", str(video),
                          "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def transcribe_faster_whisper(video: Path, log=print, progress=None) -> list[dict]:
    from faster_whisper import WhisperModel

    model_name, device, compute = _faster_whisper_setup()
    log(f"本地语音识别中（模型 {model_name}，首次使用会自动下载）…")
    if progress:
        progress(0.05)
    model = WhisperModel(model_name, device=device, compute_type=compute)
    segments, info = model.transcribe(_audio_16k(video), language="en", word_timestamps=True,
                                      condition_on_previous_text=False, vad_filter=True)
    words, plain = [], []
    for seg in segments:  # a generator: recognition happens while iterating
        plain.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        words.extend({"word": w.word, "start": w.start, "end": w.end} for w in (seg.words or []))
        if progress and info.duration:
            progress(min(0.99, 0.05 + 0.95 * seg.end / info.duration))
    if not words:  # fall back to segment-level cues
        return [s for s in plain if s["text"]]
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
