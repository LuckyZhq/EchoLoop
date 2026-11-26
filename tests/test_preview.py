"""Members-only videos download as a short preview: the real length is recorded and the full one kept."""
import subprocess

from echoloop import media, pipeline
from echoloop.storage import ffmpeg_exe


def make_video(path, seconds):
    subprocess.run([ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i", f"sine=duration={seconds}", "-c:a", "aac",
                    str(path)], check=True)


def test_preview_is_detected(tmp_path):
    make_video(tmp_path / "video.m4a", 5)
    data = {"video": "video.m4a", "duration": 1291.0}
    logs = []
    pipeline.check_preview(data, tmp_path, logs.append)
    assert data["preview"] == {"full": 1291.0} and 4.5 < data["duration"] < 5.5 and data["lengthChecked"]
    assert "试看片段" in logs[0]


def test_full_download_is_left_alone(tmp_path):
    make_video(tmp_path / "video.m4a", 5)
    data = {"video": "video.m4a", "duration": 5.3}  # sites round the length
    pipeline.check_preview(data, tmp_path)
    assert "preview" not in data and data["duration"] == 5.3


def test_covers_use_https():
    assert media.https("http://i0.hdslb.com/x.png") == "https://i0.hdslb.com/x.png"
    assert media.https("https://i.ytimg.com/x.jpg") == "https://i.ytimg.com/x.jpg"


def test_apple_podcasts_episode_resolves_to_its_audio(monkeypatch):
    import json

    media.resolve_podcast.cache_clear()
    seen = []

    def fetch(url, limit=0):
        seen.append(url)
        return json.dumps({"results": [
            {"wrapperType": "track", "kind": "podcast", "collectionName": "6 Minute English"},
            {"trackId": 1000802907917, "trackName": "Are microplastics harming us?", "trackTimeMillis": 403000,
             "collectionName": "6 Minute English", "episodeUrl": "http://x.example/ep.mp3", "artworkUrl600": "https://a/b.jpg"},
        ]}).encode()

    monkeypatch.setattr(media, "_fetch", fetch)
    info = media.probe("https://podcasts.apple.com/us/podcast/are-microplastics/id262026947?i=1000802907917&uo=4")
    assert seen == ["https://itunes.apple.com/lookup?id=262026947&entity=podcastEpisode&limit=200"]
    assert info["_media_url"] == "http://x.example/ep.mp3" and info["duration"] == 403
    assert media.video_key(info) == "applepodcasts-1000802907917" and info["uploader"] == "6 Minute English"
    media.resolve_podcast.cache_clear()


def test_xiaoyuzhou_episode_resolves_to_its_audio(monkeypatch):
    media.resolve_podcast.cache_clear()
    page = (b'<meta property="og:title" content="EP46 | Books &amp; football"/>'
            b'<meta property="og:audio" content="https://media.xyzcdn.net/x/a.m4a"/>')
    monkeypatch.setattr(media, "_fetch", lambda url, limit=0: page)
    info = media.resolve_podcast("https://www.xiaoyuzhoufm.com/episode/6a36bfb175ba9e0c53367c76")
    assert info["title"] == "EP46 | Books & football" and info["_media_url"].endswith("a.m4a")
    assert media.resolve_podcast("https://www.youtube.com/watch?v=x") is None
    media.resolve_podcast.cache_clear()
