"""Natural read-aloud: the Kokoro-82M voice model (Apache-2.0), run on this computer with kokoro-onnx.

The model (half precision, about 165 MB) and three voices are downloaded on first use from Hugging Face,
pinned to one revision and checked against their SHA-256; hf-mirror.com is tried when huggingface.co can't be
reached. Synthesised sentences are cached as WAV files, so a sentence heard again plays at once.

Kokoro has British and American English voices; British ones are phonemised with British pronunciation
(espeak "en-gb"). There is no Australian voice: the pages use the system voice for that accent.
"""
from __future__ import annotations

import hashlib
import io
import threading
import wave

from .config import DATA_DIR

REVISION = "1939ad2a8e416c0acfeecc08a694d14ef25f2231"
SOURCES = [f"https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/{REVISION}",
           f"https://hf-mirror.com/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/{REVISION}"]
MODEL = ("onnx/model_fp16.onnx", "ba4527a874b42b21e35f468c10d326fdff3c7fc8cac1f85e9eb6c0dfc35c334a", 163_234_740)
VOICE_FILES = {
    "bf_emma": "669fe0647f9dd04fcab92f1439a40eeb4c8b4ab1f82e4996fe3d918ce4a63b73",
    "bm_george": "c4b235a4c1f2cd3b939fed08b899ce9385638b763f7b73a59616c4fc9bd6c9bc",
    "af_heart": "d583ccff3cdca2f7fae535cb998ac07e9fcb90f09737b9a41fa2734ec44a8f0b",
}
VOICE_BYTES = 522_240
# accent -> (voice, espeak language)
ACCENTS = {"uk": ("bf_emma", "en-gb"), "uk-male": ("bm_george", "en-gb"), "us": ("af_heart", "en-us")}
MAX_CHARS = 600
CACHE_FILES = 3000

TTS_DIR = DATA_DIR / "tts"
MODEL_PATH = TTS_DIR / "model_fp16.onnx"
VOICES_PATH = TTS_DIR / "voices.npz"
CACHE_DIR = TTS_DIR / "cache"
TOTAL_BYTES = MODEL[2] + VOICE_BYTES * len(VOICE_FILES)

_state = {"status": "missing", "done": 0, "error": ""}
_state_lock = threading.Lock()
_engine = None
_engine_lock = threading.Lock()


def ready() -> bool:
    return MODEL_PATH.is_file() and VOICES_PATH.is_file()


def status() -> dict:
    with _state_lock:
        s = dict(_state)
    if ready():
        s.update(status="ready", done=TOTAL_BYTES)
    return {**s, "total": TOTAL_BYTES, "percent": round(100 * s["done"] / TOTAL_BYTES) if TOTAL_BYTES else 0}


RESUME_TRIES = 20
PARTS = 6                 # large files are fetched as this many byte ranges at once
PART_MIN = 8_000_000      # below this size, one connection


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


class _SourceRefused(Exception):
    pass


def _fetch_range(url: str, piece, start: int, end: int, progress) -> None:
    """Fill `piece` with bytes start..end of url, continuing after dropped connections."""
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    want = end - start + 1
    last_error = None
    for _ in range(RESUME_TRIES):
        have = piece.stat().st_size if piece.exists() else 0
        if have >= want:
            return
        headers = {"User-Agent": "ielts-study", "Range": f"bytes={start + have}-{end}"}
        try:
            with urlopen(Request(url, headers=headers), timeout=60) as r:
                if r.status != 206:
                    raise _SourceRefused("这个来源不支持断点续传")
                with piece.open("ab") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk[:want - have])
                        progress(min(len(chunk), want - have))
                        have += len(chunk)
                        if have >= want:
                            break
        except HTTPError as error:
            if error.code < 500 and error.code not in (408, 429):
                raise _SourceRefused(str(error)) from None
            last_error = error
        except OSError as error:
            last_error = error  # dropped connection: continue from where it stopped
    raise OSError(f"连接一直中断：{last_error}")


def _fetch(path: str, target, sha256: str, size: int, done_before: int) -> None:
    """Download one file, verify it, then move it into place.

    Single connections to Hugging Face can be slow or drop part-way, so a large file is fetched as several byte
    ranges at once, each continuing where it stopped; pieces left by an earlier run are continued too. When a
    source keeps failing, the mirror is tried."""
    from concurrent.futures import ThreadPoolExecutor

    parts = PARTS if size >= PART_MIN else 1
    step = -(-size // parts)
    ranges = [(i, i * step, min(size, (i + 1) * step) - 1) for i in range(parts)]
    pieces = [target.with_suffix(target.suffix + f".part{i}") for i in range(parts)]
    lock = threading.Lock()
    done = [sum(p.stat().st_size for p in pieces if p.exists())]

    def progress(n: int) -> None:
        with lock:
            done[0] += n
            with _state_lock:
                _state["done"] = done_before + done[0]

    last_error = None
    for base in SOURCES:
        try:
            with ThreadPoolExecutor(parts) as pool:
                for job in [pool.submit(_fetch_range, f"{base}/{path}", pieces[i], a, b, progress) for i, a, b in ranges]:
                    job.result()
        except (_SourceRefused, OSError) as error:
            last_error = error
            continue
        joined = target.with_suffix(target.suffix + ".part")
        with joined.open("wb") as out:
            for piece in pieces:
                out.write(piece.read_bytes())
        for piece in pieces:
            piece.unlink(missing_ok=True)
        if joined.stat().st_size == size and _sha256(joined) == sha256:
            joined.replace(target)
            return
        joined.unlink(missing_ok=True)
        done[0] = 0
        last_error = RuntimeError("文件校验失败")
    raise RuntimeError(f"神经语音模型下载失败，请检查网络后重试：{last_error}")


def _download() -> None:
    import numpy as np

    try:
        TTS_DIR.mkdir(parents=True, exist_ok=True)
        done = 0
        if not MODEL_PATH.is_file():
            _fetch(MODEL[0], MODEL_PATH, MODEL[1], MODEL[2], done)
        done += MODEL[2]
        voices = {}
        for name, sha in VOICE_FILES.items():
            target = TTS_DIR / f"{name}.bin"
            if not target.is_file():
                _fetch(f"voices/{name}.bin", target, sha, VOICE_BYTES, done)
            done += VOICE_BYTES
            voices[name] = np.fromfile(target, dtype=np.float32).reshape(-1, 1, 256)
        tmp = TTS_DIR / "voices.tmp.npz"
        np.savez(tmp, **voices)  # the voice pack format kokoro-onnx loads
        tmp.replace(VOICES_PATH)
        with _state_lock:
            _state.update(status="ready", done=TOTAL_BYTES, error="")
    except Exception as error:  # noqa: BLE001 - shown on the settings page
        with _state_lock:
            _state.update(status="error", error=str(error))


def start_download() -> dict:
    with _state_lock:
        if _state["status"] == "downloading" or ready():
            pass
        else:
            _state.update(status="downloading", done=0, error="")
            threading.Thread(target=_download, daemon=True).start()
    return status()


def _kokoro():
    global _engine
    with _engine_lock:
        if _engine is None:
            from kokoro_onnx import Kokoro

            _engine = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
        return _engine


def _wav(samples, rate: int) -> bytes:
    import numpy as np

    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _prune_cache() -> None:
    files = sorted(CACHE_DIR.glob("*.wav"), key=lambda f: f.stat().st_mtime)
    for f in files[:max(0, len(files) - CACHE_FILES)]:
        f.unlink(missing_ok=True)


def synthesize(text: str, accent: str = "uk", speed: float = 1.0) -> bytes:
    """WAV audio of `text` read in the accent's voice. Raises if the model is not downloaded yet."""
    if not ready():
        raise RuntimeError("神经语音模型还没下载")
    text = " ".join(str(text).split())[:MAX_CHARS]
    if not text:
        raise ValueError("empty")
    voice, lang = ACCENTS.get(accent, ACCENTS["uk"])
    speed = min(2.0, max(0.5, round(float(speed), 2)))
    key = hashlib.sha1(f"{voice}|{lang}|{speed}|{text}".encode()).hexdigest()
    cached = CACHE_DIR / f"{key}.wav"
    if cached.is_file():
        cached.touch()
        return cached.read_bytes()
    engine = _kokoro()
    with _engine_lock:  # one synthesis at a time: the model already uses every core
        samples, rate = engine.create(text, voice=voice, speed=speed, lang=lang)
    data = _wav(samples, rate)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = cached.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(cached)
    if len(key) and int(key[:2], 16) == 0:  # now and then, keep the cache bounded
        _prune_cache()
    return data
