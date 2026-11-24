"""Paths and tunable settings."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
LIBRARY_DIR = ROOT / "library"
ARTICLES_DIR = ROOT / "articles"  # pasted reading articles, kept apart from the video library
STATIC_DIR = Path(__file__).resolve().parent / "static"

HOST = "127.0.0.1"
# IELTS_* variables; the old WHATSUB_* names still work.
PORT = int(os.environ.get("IELTS_PORT") or os.environ.get("WHATSUB_PORT") or "8765")

# Local Whisper model (MLX, Apple Silicon). Downloaded from Hugging Face on first use.
WHISPER_MODEL = os.environ.get("IELTS_WHISPER") or os.environ.get("WHATSUB_WHISPER") or "mlx-community/whisper-large-v3-turbo"

# Hard-word candidates saved at import time. The player chooses which to show from the
# vocabulary level in Settings (IELTS 5.5–7.5+ or general), so these are deliberately generous.
CANDIDATE_RANK = 2500   # IELTS-list words rarer than this are candidates (lowest level shows > 2500)
GENERAL_RANK = 4000     # general level: any word rarer than this
MAX_WORD_CANDIDATES_PER_CUE = 6

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
