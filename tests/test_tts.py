"""Neural read-aloud: the model download survives dropped connections; synthesised audio is cached."""
import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import numpy as np
import pytest

from ielts_study import tts

BLOB = bytes(range(256)) * 4000  # ~1 MB


@pytest.fixture
def flaky_server():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            rng = (self.headers.get("Range") or "bytes=0-")[6:]
            start, _, end = rng.partition("-")
            start, end = int(start), int(end) if end else len(BLOB) - 1
            calls.append(start)
            body = BLOB[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if len(calls) <= 2:  # the first two connections drop part-way
                self.wfile.write(body[:len(body) // 3])
                self.wfile.flush()
                self.connection.shutdown(2)
                return
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", calls
    httpd.shutdown()


def test_download_resumes_after_dropped_connections(tmp_path, monkeypatch, flaky_server):
    base, calls = flaky_server
    monkeypatch.setattr(tts, "SOURCES", [base])
    target = tmp_path / "model.onnx"
    tts._fetch("model.onnx", target, hashlib.sha256(BLOB).hexdigest(), len(BLOB), 0)
    assert target.read_bytes() == BLOB
    assert calls[:3] == [0, len(BLOB) // 3, len(BLOB) // 3 + (len(BLOB) - len(BLOB) // 3) // 3]  # continued
    assert not list(tmp_path.glob("*.part*"))


def test_large_files_come_in_parallel_ranges(tmp_path, monkeypatch, flaky_server):
    base, calls = flaky_server
    monkeypatch.setattr(tts, "SOURCES", [base])
    monkeypatch.setattr(tts, "PART_MIN", 1000)
    target = tmp_path / "model.onnx"
    tts._fetch("model.onnx", target, hashlib.sha256(BLOB).hexdigest(), len(BLOB), 0)
    assert target.read_bytes() == BLOB
    assert len({c for c in calls}) >= tts.PARTS  # each range asked for separately


def test_corrupt_download_is_rejected(tmp_path, monkeypatch, flaky_server):
    base, _ = flaky_server
    monkeypatch.setattr(tts, "SOURCES", [base])
    with pytest.raises(RuntimeError, match="校验"):
        tts._fetch("model.onnx", tmp_path / "m.onnx", "0" * 64, len(BLOB), 0)
    assert not list(tmp_path.iterdir())


def test_synthesis_is_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(tts, "ready", lambda: True)
    made = []

    def create(text, voice, speed, lang):
        made.append((text, voice, speed, lang))
        return np.zeros(2400, dtype=np.float32), 24000

    monkeypatch.setattr(tts, "_kokoro", lambda: SimpleNamespace(create=create))
    a = tts.synthesize("  The quick   brown fox. ", "uk", 1)
    b = tts.synthesize("The quick brown fox.", "uk", 1.0)
    assert a == b and a[:4] == b"RIFF" and len(made) == 1
    assert made[0] == ("The quick brown fox.", "bf_emma", 1.0, "en-gb")  # British voice, British pronunciation
    tts.synthesize("The quick brown fox.", "us", 0.7)
    assert made[-1][1:] == ("af_heart", 0.7, "en-us")


def test_not_downloaded_yet(monkeypatch):
    monkeypatch.setattr(tts, "ready", lambda: False)
    with pytest.raises(RuntimeError):
        tts.synthesize("hello")
