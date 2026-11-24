"""Storage: how much space each video takes, and shrinking it (lower resolution, or audio only).

Shrinking re-encodes with the Mac's hardware H.264 encoder (VideoToolbox), or x264 on other systems. The new file replaces the old one only after it finished and came out smaller.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import ARTICLES_DIR, LIBRARY_DIR

# Target video bitrates. Speech videos stay sharp at these rates; audio is copied unchanged.
SHRINK_MODES = {"720": ("720p", 1400), "480": ("480p", 700), "audio": ("只保留音频", 0)}


def ffmpeg_exe() -> str:
    from .media import FFMPEG_NAME, ffmpeg_dir

    return str(ffmpeg_dir() / FFMPEG_NAME)


def _video_encoder(rate: int) -> list[str]:
    """The Mac's hardware encoder where there is one; x264 (fast preset) everywhere else."""
    if sys.platform == "darwin":
        return ["-c:v", "h264_videotoolbox", "-b:v", f"{rate}k"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{rate}k"]


def media_info(path: Path) -> dict:
    """Duration (s) and video height from ffmpeg's header dump; height 0 means audio only."""
    out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    duration = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0
    v = re.search(r"Stream #.*Video: .*?(\d{2,5})x(\d{2,5})", out)
    return {"duration": duration, "height": int(v[2]) if v else 0}


def _dir_bytes(d: Path) -> int:
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) if d.exists() else 0


def overview() -> dict:
    videos = []
    if LIBRARY_DIR.exists():
        for d in LIBRARY_DIR.iterdir():
            f = d / "data.json"
            if not f.is_file():
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            media = d / (data.get("video") or "")
            if not media.is_file():
                continue
            info = media_info(media)
            videos.append({
                "id": d.name, "title": data.get("title") or d.name, "bytes": media.stat().st_size,
                "height": info["height"], "duration": info["duration"], "audioOnly": info["height"] == 0,
                "shrunk": data.get("shrunk"),
            })
    videos.sort(key=lambda v: -v["bytes"])
    return {
        "videos": videos,
        "videoBytes": sum(v["bytes"] for v in videos),
        "libraryBytes": _dir_bytes(LIBRARY_DIR),
        "articleBytes": _dir_bytes(ARTICLES_DIR),
    }


def _run_ffmpeg(cmd: list[str], duration: float, progress) -> tuple[bool, str]:
    # Keep FFmpeg's error output from blocking while we read the progress pipe.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as stderr:
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=stderr, text=True,
                              encoding="utf-8", errors="replace") as proc:
            for line in proc.stdout:
                if line.startswith("out_time_us=") and duration:
                    try:
                        progress(min(0.99, int(line.split("=", 1)[1]) / 1e6 / duration))
                    except ValueError:
                        pass
            ok = proc.wait() == 0
        stderr.seek(0)
        return ok, stderr.read()


def shrink(vdir: Path, mode: str, progress=lambda p: None, log=lambda m: None) -> dict:
    """Re-encode vdir's video. Returns {"before", "after"} byte counts; raises RuntimeError on failure."""
    if mode not in SHRINK_MODES:
        raise RuntimeError("不支持的压缩方式。")
    data_file = vdir / "data.json"
    data = json.loads(data_file.read_text(encoding="utf-8"))
    src = vdir / data["video"]
    info = media_info(src)
    if mode != "audio" and info["height"] and info["height"] <= int(mode):
        raise RuntimeError(f"这个视频已经是 {info['height']}p，不需要压缩到 {mode}p。")
    if mode == "audio" and info["height"] == 0:
        raise RuntimeError("这个视频已经只有音频了。")

    ext = ".m4a" if mode == "audio" else ".mp4"
    tmp = vdir / f"shrinking{ext}"
    if mode == "audio":
        codec = ["-vn", "-c:a", "copy"]
    else:
        rate = SHRINK_MODES[mode][1]
        codec = ["-vf", f"scale=-2:{mode}", *_video_encoder(rate),
                 "-maxrate", f"{rate * 3 // 2}k", "-bufsize", f"{rate * 2}k", "-c:a", "copy"]
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostats", "-y", "-i", str(src), *codec,
           "-movflags", "+faststart", "-progress", "pipe:1", str(tmp)]
    log(f"正在压缩为{SHRINK_MODES[mode][0]}…")
    ok, err = _run_ffmpeg(cmd, info["duration"], progress)
    if not ok and "h264_videotoolbox" in cmd:  # no hardware encoder (e.g. a Mac VM): use x264 instead
        rate = SHRINK_MODES[mode][1]
        i = cmd.index("-c:v")
        cmd[i:i + 4] = ["-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{rate}k"]
        ok, err = _run_ffmpeg(cmd, info["duration"], progress)
    if not ok or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        raise RuntimeError("压缩失败：" + (err.strip().splitlines() or ["ffmpeg 出错"])[-1])

    before, after = src.stat().st_size, tmp.stat().st_size
    if after >= before:
        tmp.unlink()
        raise RuntimeError("压缩后并没有变小，已保留原视频。")
    final = vdir / f"video{ext}"
    tmp.replace(final)                       # the new file is complete before anything is replaced
    data["video"] = final.name
    data["shrunk"] = mode
    tmp_data = data_file.with_suffix(".tmp")
    tmp_data.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp_data.replace(data_file)
    if src != final:
        src.unlink(missing_ok=True)          # e.g. video.mp4 after keeping only video.m4a
    log(f"完成：{before / 1e6:.0f} MB → {after / 1e6:.0f} MB")
    return {"before": before, "after": after}
