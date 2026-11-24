"""Backups of the learning record: one zip with everything except the large video files.

Included: saved words and review history, mistakes and dictation scores, word-book progress, level and plan,
articles, speaking and writing history, and the clips kept from deleted videos. Videos can be included too.
Not included: API keys and other settings in data/ (they stay on this computer).

A backup can be downloaded, restored (files that would be overwritten are copied aside first), and written
automatically once a day into a folder of your choice, for example an iCloud Drive, OneDrive, Dropbox or
Nutstore folder, so a broken computer doesn't take a year of records with it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import time
import zipfile
import zlib
from pathlib import Path, PurePosixPath

from .config import ARTICLES_DIR, DATA_DIR, LIBRARY_DIR

BACKUP_SETTINGS = DATA_DIR / "backup.json"
RESTORE_DIR = DATA_DIR / "backups"
ROOTS = {"library": LIBRARY_DIR, "articles": ARTICLES_DIR}
VIDEO_FILE = re.compile(r"^video\.[A-Za-z0-9]+$")
SKIP = re.compile(r"(\.part\d*|\.tmp|\.incomplete|\.DS_Store)$")
NAME = re.compile(r"^IELTS-Study-backup-\d{8}-\d{6}\.zip$")
DAY = 24 * 3600
_lock = threading.Lock()


def _files(include_videos: bool):
    for root_name, root in ROOTS.items():
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink() or SKIP.search(path.name):
                continue
            rel = path.relative_to(root)
            # library/<video id>/video.mp4 is the large part; everything else is small
            if not include_videos and root_name == "library" and len(rel.parts) == 2 and VIDEO_FILE.match(rel.name):
                continue
            yield path, f"{root_name}/{rel.as_posix()}"


def write_zip(target: Path, include_videos: bool = False) -> dict:
    """Write a backup to `target` (via a temporary file); returns what it holds."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    count = size = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path, name in _files(include_videos):
            # videos are already compressed: store them as they are
            z.write(path, name, compress_type=zipfile.ZIP_STORED if VIDEO_FILE.match(path.name) else None)
            count += 1
            size += path.stat().st_size
        z.writestr("manifest.json", json.dumps({"app": "ielts-study", "created": int(time.time()),
                                                "videos": include_videos, "files": count}))
    tmp.replace(target)
    return {"files": count, "bytes": size, "zipBytes": target.stat().st_size}


def file_name() -> str:
    return time.strftime("IELTS-Study-backup-%Y%m%d-%H%M%S.zip")


def _member_target(name: str) -> Path | None:
    """Where a zip member goes, or None if it is not a valid backup path."""
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or len(p.parts) < 2 or p.parts[0] not in ROOTS or "\\" in name:
        return None
    return ROOTS[p.parts[0]].joinpath(*p.parts[1:])


def _crc(path: Path) -> int:
    crc = 0
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            crc = zlib.crc32(chunk, crc)
    return crc


def restore(zip_path: Path) -> dict:
    """Put a backup's files back. Files it replaces are first copied to data/backups/before-restore-<time>/."""
    with zipfile.ZipFile(zip_path) as z:
        try:
            manifest = json.loads(z.read("manifest.json"))
        except (KeyError, ValueError):
            raise ValueError("这不是 IELTS Study 的备份文件。") from None
        if manifest.get("app") != "ielts-study":
            raise ValueError("这不是 IELTS Study 的备份文件。")
        members = [(m, _member_target(m.filename)) for m in z.infolist() if not m.is_dir() and m.filename != "manifest.json"]
        bad = [m.filename for m, t in members if t is None]
        if bad:
            raise ValueError(f"备份里有不认识的文件：{bad[0]}")
        aside = RESTORE_DIR / time.strftime("before-restore-%Y%m%d-%H%M%S")
        saved = restored = 0
        with _lock:
            for member, target in members:
                if target.is_file() and target.stat().st_size == member.file_size and _crc(target) == member.CRC:
                    continue  # already the same
                if target.is_file():
                    copy = aside / member.filename
                    copy.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, copy)
                    saved += 1
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".restore")
                with z.open(member) as src, tmp.open("wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
                tmp.replace(target)
                restored += 1
    return {"restored": restored, "keptAside": saved, "asideFolder": str(aside) if saved else "",
            "created": manifest.get("created")}


# ------------------------------------------------------------------ automatic backups into a folder

class MissingFolder(ValueError):
    pass


def load_settings() -> dict:
    try:
        data = json.loads(BACKUP_SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"folder": str(data.get("folder") or ""), "keep": int(data.get("keep") or 10),
            "last": int(data.get("last") or 0), "lastError": str(data.get("lastError") or "")}


def _save_settings(data: dict) -> None:
    BACKUP_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".backup-", dir=BACKUP_SETTINGS.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(name, BACKUP_SETTINGS)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def set_folder(folder: str, keep: int | None = None) -> dict:
    data = load_settings()
    folder = os.path.expanduser(folder.strip())
    if folder:
        path = Path(folder)
        if not path.is_absolute():
            raise ValueError("请填写文件夹的完整路径。")
        if not path.is_dir():
            raise MissingFolder("找不到这个文件夹，请填写完整路径。")
        if not os.access(path, os.W_OK):
            raise ValueError("没有权限写入这个文件夹。")
        inside = [p for p in ROOTS.values() if path.resolve() == p.resolve() or p.resolve() in path.resolve().parents]
        if inside:
            raise ValueError("备份文件夹不能放在资料库里面。")
    data["folder"] = folder
    if keep is not None:
        data["keep"] = max(1, min(60, int(keep)))
    _save_settings(data)
    return data


def suggestions() -> list[dict]:
    """Synced folders that exist on this computer."""
    home = Path.home()
    candidates = [("iCloud Drive", home / "Library/Mobile Documents/com~apple~CloudDocs"),
                  ("Dropbox", home / "Dropbox"), ("OneDrive", home / "OneDrive"), ("坚果云", home / "Nutstore Files"),
                  ("Google Drive", home / "Google Drive")]
    cloud = home / "Library/CloudStorage"
    if cloud.is_dir():
        candidates += [(p.name.split("-")[0], p) for p in sorted(cloud.iterdir()) if p.is_dir()]
    seen, out = set(), []
    for label, path in candidates:
        if path.is_dir() and path not in seen:
            seen.add(path)
            out.append({"label": label, "path": str(path / "IELTS Study 备份")})
    return out


def backup_now() -> dict:
    data = load_settings()
    if not data["folder"]:
        raise ValueError("还没有选择备份文件夹。")
    folder = Path(data["folder"])
    try:
        with _lock:
            info = write_zip(folder / file_name())
            old = sorted((p for p in folder.iterdir() if NAME.match(p.name)), key=lambda p: p.name)
            for p in old[:max(0, len(old) - data["keep"])]:
                p.unlink(missing_ok=True)
        data.update(last=int(time.time()), lastError="")
    except OSError as error:
        data["lastError"] = str(error)[:300]
        _save_settings(data)
        raise ValueError(f"备份失败：{error}") from None
    _save_settings(data)
    return {**data, **info}


def status() -> dict:
    data = load_settings()
    folder = Path(data["folder"]) if data["folder"] else None
    files = sorted((p.name for p in folder.iterdir() if NAME.match(p.name)), reverse=True) if folder and folder.is_dir() else []
    return {**data, "files": files[:data["keep"]], "suggestions": suggestions()}


def _loop() -> None:
    while True:
        data = load_settings()
        if data["folder"] and time.time() - data["last"] > DAY and Path(data["folder"]).is_dir():
            try:
                backup_now()
            except ValueError:
                pass
        time.sleep(3600)


def start_auto() -> None:
    threading.Thread(target=_loop, daemon=True).start()
