"""Paths and tunable settings."""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
# IELTS_LIBRARY points a second copy (e.g. a test server) at another folder, leaving the real library alone.
LIBRARY_DIR = Path(os.environ["IELTS_LIBRARY"]) if os.environ.get("IELTS_LIBRARY") else ROOT / "library"
ARTICLES_DIR = ROOT / "articles"  # pasted reading articles, kept apart from the video library
STATIC_DIR = Path(__file__).resolve().parent / "static"

HOST = "127.0.0.1"
# IELTS_* variables; the old WHATSUB_* names still work.
PORT = int(os.environ.get("IELTS_PORT") or os.environ.get("WHATSUB_PORT") or "8765")

# Local speech recognition, downloaded from Hugging Face on first use:
#   Apple Silicon Mac  → mlx-whisper (GPU through MLX), large-v3-turbo
#   Windows / Linux / Intel Mac → faster-whisper: large-v3-turbo on an NVIDIA GPU, small.en on the CPU
# IELTS_WHISPER overrides the model (an MLX repo on Apple Silicon, a faster-whisper model name elsewhere).
APPLE_SILICON = sys.platform == "darwin" and platform.machine() == "arm64"
WHISPER_MODEL = os.environ.get("IELTS_WHISPER") or os.environ.get("WHATSUB_WHISPER") or (
    "mlx-community/whisper-large-v3-turbo" if APPLE_SILICON else "")

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
