"""Deleting a video keeps its mistakes and the sentences saved words came from, with their sound."""
import json
import subprocess

import pytest

from ielts_study import config, keep, review
from ielts_study.storage import ffmpeg_exe


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path)
    vdir = tmp_path / "youtube-abc"
    vdir.mkdir()
    subprocess.run([ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
                    "-c:a", "aac", str(vdir / "video.m4a")], check=True)
    cues = [{"text": f"Sentence number {n}.", "zh": f"第 {n} 句", "start": n * 2.0, "end": n * 2.0 + 1.5}
            for n in range(4)]
    (vdir / "data.json").write_text(json.dumps({"title": "Talk", "video": "video.m4a", "cues": cues}), encoding="utf-8")
    (vdir / "dictation.json").write_text(json.dumps({
        "1": {"score": 0.5, "best": 0.5, "tries": 1, "typed": "sentence", "at": 10},
        "2": {"score": 0.95, "best": 0.95, "tries": 1, "typed": "ok", "at": 11},  # passed: not kept
    }), encoding="utf-8")
    return tmp_path, vdir


def test_archive_keeps_text_and_audio(library):
    root, vdir = library
    vocab = [{"en": "number", "videoId": "youtube-abc", "time": 6.0}, {"en": "other", "videoId": "x-y", "time": 0}]
    assert keep.archive(vdir, vocab) == {"sentences": 2, "audio": 2}
    meta = keep.load("youtube-abc")
    assert meta["title"] == "Talk" and set(meta["cues"]) == {"1", "3"} and set(meta["dictation"]) == {"1"}
    assert (root / "kept" / "youtube-abc" / "1.m4a").stat().st_size > 1000

    # the mistake is listed from the kept copy once the video is gone, with its clip
    assert keep.mistakes(skip={"youtube-abc"}) == []
    (m,) = keep.mistakes(skip=set())
    assert m["deleted"] and m["i"] == 1 and m["text"] == "Sentence number 1." and m["clip"]["src"] == "/kept/youtube-abc/1.m4a"
    assert 1.5 < m["clip"]["end"] < 2.5

    # a new try is recorded on the kept sentence; passing it removes it from the list
    keep.record_dictation("youtube-abc", 1, lambda prev: {**prev, "score": 1.0, "tries": prev["tries"] + 1})
    assert keep.mistakes(skip=set()) == []
    assert keep.record_dictation("youtube-abc", 0, lambda prev: {}) is None  # never kept


def test_review_plays_the_kept_clip_after_delete(library):
    root, vdir = library
    word = {"en": "number", "videoId": "youtube-abc", "time": 6.0}
    assert review._clip(word, root, {})["src"] == "/media/youtube-abc/video.m4a"
    keep.archive(vdir, [word])
    (vdir / "data.json").unlink()  # the video is deleted
    assert review._clip(word, root, {}) == keep.clip("youtube-abc", 6.0)
    assert review._clip(word, root, {})["src"] == "/kept/youtube-abc/3.m4a"


def test_unsafe_names_are_refused():
    assert keep.load("../etc") is None
    assert keep.audio_path("youtube-abc", "../data.json") is None
