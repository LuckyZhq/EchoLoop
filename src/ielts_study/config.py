"""Paths and tunable settings."""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

# Messages are printed in Chinese and other languages. On Windows, output going to a pipe or log file uses the
# legacy code page (cp1252 …), which cannot encode them and would crash the first print: write UTF-8 instead.
for _stream in (sys.stdout, sys.stderr):
    if _stream and (getattr(_stream, "encoding", "") or "").lower().replace("-", "") != "utf8":
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
# IELTS_LIBRARY points a second copy (e.g. a test server) at another folder, leaving the real library alone.
LIBRARY_DIR = Path(os.environ["IELTS_LIBRARY"]) if os.environ.get("IELTS_LIBRARY") else ROOT / "library"
# pasted and graded reading articles, kept apart from the video library
ARTICLES_DIR = Path(os.environ["IELTS_ARTICLES"]) if os.environ.get("IELTS_ARTICLES") else ROOT / "articles"
STATIC_DIR = Path(__file__).resolve().parent / "static"

HOST = "127.0.0.1"
# IELTS_* variables; the old WHATSUB_* names still work.
PORT = int(os.environ.get("IELTS_PORT") or os.environ.get("WHATSUB_PORT") or "8765")

# Local speech recognition (see asr.py): mlx-whisper on Apple Silicon, faster-whisper elsewhere. The model size
# is chosen in Settings; IELTS_WHISPER still overrides it (an MLX repo on Apple Silicon, a faster-whisper model
# name elsewhere).
APPLE_SILICON = sys.platform == "darwin" and platform.machine() == "arm64"
WHISPER_MODEL = os.environ.get("IELTS_WHISPER") or os.environ.get("WHATSUB_WHISPER") or ""

# Hard-word candidates saved at import time. The player chooses which to show from the
# vocabulary level in Settings (IELTS 5.5–7.5+ or general), so these are deliberately generous.
MAX_WORD_CANDIDATES_PER_CUE = 10
# Words more common than this are never marked (the, make, people…); everything rarer is kept as a
# candidate with its frequency rank, and the player marks the ones between your current and target level.
MIN_CANDIDATE_RANK = 400
# 中考 (Chinese middle-school) words are taught early: treat them as at most this common.
SCHOOL_WORD_RANK = 1500

QUALITY_FORMATS = {
    str(height): f"bv*[height<={height}]+ba/b[height<={height}]"
    for height in (480, 720, 1080, 1440, 2160)
}
QUALITY_FORMATS["best"] = "bv*+ba/b"

# A stalled Hugging Face model download should fail (and resume on retry) instead of hanging forever.
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# Make sure tools installed in the venv (deno for yt-dlp, our ffmpeg symlink) are on PATH.
_VENV_BIN = str(Path(sys.executable).parent)
_FFMPEG_BIN = str(DATA_DIR / "bin")
os.environ["PATH"] = os.pathsep.join([_FFMPEG_BIN, _VENV_BIN, os.environ.get("PATH", "")])
