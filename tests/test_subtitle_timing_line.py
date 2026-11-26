from echoloop.media import parse_subtitles


def test_stray_timing_line_keeps_one_copy(tmp_path):
    f = tmp_path / "v.vtt"
    f.write_text("WEBVTT\n\n00:00:27.685 --> 00:00:30.163\nBut the thing I liked\n00:00:27.685 --> 00:00:30.163\nBut the thing I liked\n\n", encoding="utf-8")
    cues = parse_subtitles(f)
    assert [c["text"] for c in cues] == ["But the thing I liked"]
