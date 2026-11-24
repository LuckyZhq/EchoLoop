"""Shrinking a video: run on a generated 1080p clip in a temp folder, never on the real library."""
import json
import subprocess

import pytest

from ielts_study.storage import ffmpeg_exe, media_info, shrink


@pytest.fixture
def video_dir(tmp_path):
    clip = tmp_path / "video.mp4"
    subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-c:v", "libx264", "-b:v", "8M", "-c:a", "aac", "-shortest", str(clip)], check=True)
    (tmp_path / "data.json").write_text(json.dumps({"id": "t", "video": "video.mp4", "cues": []}))
    return tmp_path


def test_shrink_to_720p_replaces_the_file_and_keeps_the_name(video_dir):
    before = (video_dir / "video.mp4").stat().st_size
    result = shrink(video_dir, "720")
    assert result["before"] == before and result["after"] < before
    assert media_info(video_dir / "video.mp4")["height"] == 720
    data = json.loads((video_dir / "data.json").read_text())
    assert data["video"] == "video.mp4" and data["shrunk"] == "720"
    assert not (video_dir / "shrinking.mp4").exists()


def test_audio_only_switches_to_m4a_and_removes_the_mp4(video_dir):
    shrink(video_dir, "audio")
    assert not (video_dir / "video.mp4").exists()
    info = media_info(video_dir / "video.m4a")
    assert info["height"] == 0 and info["duration"] == pytest.approx(3, abs=0.2)
    assert json.loads((video_dir / "data.json").read_text())["video"] == "video.m4a"


def test_refuses_to_upscale_and_keeps_the_original(video_dir):
    shrink(video_dir, "720")
    size = (video_dir / "video.mp4").stat().st_size
    with pytest.raises(RuntimeError, match="已经是 720p"):
        shrink(video_dir, "720")
    assert (video_dir / "video.mp4").stat().st_size == size


def test_unknown_mode_is_refused(video_dir):
    with pytest.raises(RuntimeError):
        shrink(video_dir, "4k")
