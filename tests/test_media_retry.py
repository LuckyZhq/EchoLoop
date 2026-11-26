"""Media probe/download resilience: reuse probed info and retry transient TLS/network errors."""
from pathlib import Path
from types import SimpleNamespace

import yt_dlp

from echoloop import media


def test_probe_retries_transient_ssl_eof(monkeypatch):
    calls = {"n": 0}
    logs = []
    monkeypatch.setattr(media.time, "sleep", lambda *_: None)

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            calls["n"] += 1
            if calls["n"] == 1:
                raise yt_dlp.utils.DownloadError(
                    "ERROR: Unable to download webpage: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred"
                )
            return {"id": "1042", "title": "TED", "formats": [{"format_id": "hls-720"}]}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    info = media.probe("https://www.ted.com/talks/example", log=logs.append)
    assert info["id"] == "1042" and calls["n"] == 2
    assert any("重试" in m for m in logs)


def test_download_reuses_probed_info_without_reprobing(tmp_path, monkeypatch):
    probed = {"id": "1042", "title": "TED", "webpage_url": "https://www.ted.com/talks/example",
              "formats": [{"format_id": "hls-720"}], "subtitles": {"en": [{"ext": "vtt"}]}}
    monkeypatch.setattr(media, "probe", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not re-probe")))
    seen = {}

    class FakeYDL:
        def __init__(self, opts):
            seen["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def process_ie_result(self, ie_result, download=True):
            seen["processed"] = (ie_result["id"], download)
            (tmp_path / "video.mp4").write_bytes(b"mp4")
            (tmp_path / "video.en.vtt").write_text("WEBVTT\n", encoding="utf-8")

        def download(self, urls):
            raise AssertionError("should download via process_ie_result when info has formats")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    video, sub = media.download("https://www.ted.com/talks/example", tmp_path, "720", info=probed)
    assert video.name == "video.mp4" and sub.name == "video.en.vtt"
    assert seen["processed"] == ("1042", True)
