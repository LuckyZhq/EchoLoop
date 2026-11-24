"""Local cover images (no network needed for these checks)."""
from ielts_study.media import local_thumbnail, save_thumbnail


def test_local_thumbnail_finds_any_saved_type(tmp_path):
    assert local_thumbnail(tmp_path) is None
    (tmp_path / "thumb.webp").write_bytes(b"x")
    assert local_thumbnail(tmp_path).name == "thumb.webp"


def test_only_https_covers_are_fetched(tmp_path):
    assert save_thumbnail("http://example.com/a.jpg", tmp_path) is None
    assert save_thumbnail("file:///etc/passwd", tmp_path) is None
    assert local_thumbnail(tmp_path) is None
