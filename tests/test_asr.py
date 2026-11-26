"""Speech recognition: model choice (small first, large in the background), cloud transcription, fallback."""
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from echoloop import asr, settings


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    monkeypatch.setattr(asr, "ASR_PATH", tmp_path / "asr.json")
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")  # the providers and their keys
    return tmp_path / "asr.json"


def test_auto_uses_small_while_large_downloads(monkeypatch, settings_file):
    started = []
    monkeypatch.setattr(asr, "auto_size", lambda: "large")
    monkeypatch.setattr(asr, "is_downloaded", lambda size: size == "small")
    monkeypatch.setattr(asr, "download", started.append)
    assert asr.local_model(log=lambda m: None) == "small"
    assert started == ["large"]


def test_auto_uses_large_once_downloaded(monkeypatch, settings_file):
    monkeypatch.setattr(asr, "auto_size", lambda: "large")
    monkeypatch.setattr(asr, "is_downloaded", lambda size: True)
    monkeypatch.setattr(asr, "download", lambda size: pytest.fail("nothing to download"))
    assert asr.local_model() == "large"


def test_first_use_takes_the_quick_model(monkeypatch, settings_file):
    started = []
    monkeypatch.setattr(asr, "auto_size", lambda: "large")
    monkeypatch.setattr(asr, "is_downloaded", lambda size: False)
    monkeypatch.setattr(asr, "download", started.append)
    assert asr.local_model(log=lambda m: None) == asr.QUICK  # ~480 MB now instead of 1.6 GB
    assert started == ["large"]


def test_chosen_size_is_used_as_is(monkeypatch, settings_file):
    monkeypatch.setattr(asr, "is_downloaded", lambda size: False)
    monkeypatch.setattr(asr, "download", lambda size: None)
    asr.save_settings({"model": "medium"})
    assert asr.local_model() == "medium"


def test_cloud_uses_the_one_saved_key(settings_file):
    with pytest.raises(ValueError, match="服务商与密钥"):
        asr.save_settings({"engine": "cloud", "provider": "groq"})
    # the key is typed once, in the provider list; translation keeps using its own provider
    settings.save_settings({"engine": "local"})
    settings.save_settings({"engine": "api", "provider": "groq", "apiKey": "gsk_test123", "keepActive": True})
    assert settings.load_settings().engine == "local"
    s = asr.save_settings({"engine": "cloud", "provider": "groq", "apiKey": "ignored"})
    assert s.endpoint() == ("https://api.groq.com/openai/v1", "whisper-large-v3-turbo", "gsk_test123")
    assert "gsk_test123" not in json.dumps(s.public()) and "gsk_test123" not in settings_file.read_text()
    assert [p["hasKey"] for p in s.public()["providers"]] == [False, True, False]


def test_keys_from_the_old_form_move_to_the_provider_list(settings_file):
    settings.save_settings({"engine": "api", "provider": "deepseek", "model": "deepseek-flash", "apiKey": "sk-ds"})
    settings_file.write_text(json.dumps({"engine": "cloud", "provider": "openai", "keys": {"openai": "sk-old", "groq": "gsk-old"}}))
    assert asr.migrate_keys() == 2
    assert settings.provider_access("openai") == ("https://api.openai.com/v1", "sk-old")
    assert settings.provider_access("groq")[1] == "gsk-old"
    saved = settings.load_settings()
    assert (saved.engine, saved.provider, saved.api_key) == ("api", "deepseek", "sk-ds")  # translation unchanged
    assert "keys" not in settings_file.read_text() or json.loads(settings_file.read_text())["keys"] == {}
    assert asr.load_settings().endpoint()[2] == "sk-old" and asr.migrate_keys() == 0


def test_punctuation_comes_from_segments():
    words = [{"word": "Hello", "start": 0, "end": .4}, {"word": "there", "start": .4, "end": .8},
             {"word": "How", "start": 1, "end": 1.2}, {"word": "are", "start": 1.2, "end": 1.3},
             {"word": "you", "start": 1.3, "end": 1.5}]
    segments = [{"text": " Hello there."}, {"text": " How are you?"}]
    out = asr.punctuate(words, segments)
    assert [w["word"] for w in out] == [" Hello", " there.", " How", " are", " you?"]


@pytest.fixture
def cloud(tmp_path):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append((self.path, self.headers.get("Authorization"), body))
            reply = {"text": "Good morning everyone.",
                     "segments": [{"start": 0.0, "end": 1.5, "text": " Good morning everyone."}],
                     "words": [{"word": "Good", "start": 0.1, "end": 0.4}, {"word": "morning", "start": 0.4, "end": 0.9},
                               {"word": "everyone", "start": 0.9, "end": 1.4}]}
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    audio = tmp_path / "a.wav"
    with wave.open(str(audio), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 16000 * 2)
    yield f"http://127.0.0.1:{httpd.server_port}/v1", seen, audio
    httpd.shutdown()


def test_cloud_transcription(cloud):
    url, seen, audio = cloud
    settings = asr.AsrSettings(engine="cloud", provider="custom", base_url=url, cloud_model="whisper-1", keys={"custom": "k1"})
    words, segments = asr.cloud_words(audio, settings, log=lambda m: None)
    assert [w["word"] for w in words] == [" Good", " morning", " everyone."]
    path, auth, body = seen[0]
    assert path == "/v1/audio/transcriptions" and auth == "Bearer k1"
    assert b'name="timestamp_granularities[]"\r\n\r\nword' in body and b"audio/mpeg" in body


def test_cloud_failure_falls_back_to_local(monkeypatch, settings_file):
    settings.store_key("openai", "sk-test")
    asr.save_settings({"engine": "cloud", "provider": "openai"})

    def broken(*a, **k):
        raise asr.CloudError("连不上云端识别服务")

    monkeypatch.setattr(asr, "cloud_words", broken)
    monkeypatch.setattr(asr, "local_words", lambda *a, **k: ([{"word": " Hi.", "start": 0, "end": .5}], []))
    log = []
    words, _, engine = asr.words_and_segments("x.wav", log.append)
    assert engine == "local" and words and "本地" in log[0]
