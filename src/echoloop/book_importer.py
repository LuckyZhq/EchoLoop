"""Import EPUB chapters into the existing article reader."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path

from . import epub_parser, reading

BOOK_ID = re.compile(r"^b[0-9a-f]{32}$")
REVISION = re.compile(r"^[0-9a-f]{32}$")
_import_lock = threading.Lock()


def books_dir():
    return reading.ARTICLES_DIR / "_books"


def covers_dir():
    return reading.ARTICLES_DIR / "_classic_covers"


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def _json_write(path, value):
    _atomic_write(path, json.dumps(value, ensure_ascii=False).encode("utf-8"))


def load_manifest(book_id):
    if not isinstance(book_id, str) or not BOOK_ID.fullmatch(book_id):
        return None
    try:
        data = json.loads((books_dir() / book_id / "manifest.json").read_text(encoding="utf-8"))
        if data.get("id") != book_id or not REVISION.fullmatch(data.get("revision", "")):
            return None
        return data
    except (OSError, ValueError, TypeError):
        return None


def chapter_path(book_id, revision, chapter_index):
    if (not isinstance(book_id, str) or not BOOK_ID.fullmatch(book_id) or
            not isinstance(revision, str) or not REVISION.fullmatch(revision) or
            not isinstance(chapter_index, int) or isinstance(chapter_index, bool) or chapter_index < 1):
        raise ValueError("Invalid imported chapter reference")
    return books_dir() / book_id / "revisions" / revision / f"{chapter_index}.json"


def load_chapter(book_id, chapter_index):
    manifest = load_manifest(book_id)
    if not manifest or not any(chapter["chapterIndex"] == chapter_index for chapter in manifest["chapters"]):
        return None
    try:
        data = json.loads(chapter_path(book_id, manifest["revision"], chapter_index).read_text(encoding="utf-8"))
        data["classicRevision"] = manifest["revision"]
        return data
    except (OSError, ValueError, TypeError):
        return None


def save_chapter(data):
    path = chapter_path(data["bookId"], data["classicRevision"], data["chapterIndex"])
    _json_write(path, data)


def imported_books():
    root = books_dir()
    if root.exists():
        for directory in sorted(root.iterdir()):
            if directory.is_dir():
                manifest = load_manifest(directory.name)
                if manifest:
                    yield manifest


def _remove_stub(article_id, book_id):
    if not isinstance(article_id, str) or not reading.ARTICLE_ID.fullmatch(article_id):
        return
    path = reading.article_path(article_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not data.get("classicManaged") or data.get("bookId") != book_id:
        return
    try:
        shutil.rmtree(path.parent)
    except OSError as error:
        logging.warning("Could not remove stale classic chapter %s: %s", article_id, error)


def _cleanup_overwrite(book_id, old, chapters, revision):
    if not old:
        return
    kept = {chapter["articleId"] for chapter in chapters}
    for chapter in old["chapters"]:
        if chapter["articleId"] not in kept:
            _remove_stub(chapter["articleId"], book_id)
    revisions = books_dir() / book_id / "revisions"
    try:
        stale = [entry for entry in revisions.iterdir()
                 if entry.is_dir() and entry.name != revision and REVISION.fullmatch(entry.name)]
    except OSError:
        return
    for entry in stale:
        try:
            shutil.rmtree(entry)
        except OSError as error:
            logging.warning("Could not remove stale revision %s: %s", entry.name, error)


def import_book(source, overwrite=False, *, dic=None, annotator=None, language=None, log=print,
                progress=None, filename=""):
    with _import_lock:
        return _import_book(source, overwrite, dic=dic, annotator=annotator, language=language,
                            log=log, progress=progress, filename=filename)


def _import_book(source, overwrite=False, *, dic=None, annotator=None, language=None, log=print,
                 progress=None, filename=""):
    source = Path(source)
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    source_hash = digest.hexdigest()
    book_id = "b" + source_hash[:32]
    old = load_manifest(book_id)
    if old and old["sourceHash"] != source_hash:
        raise ValueError("Book identifier collision")
    if old and not overwrite:
        return {"book": old, "skipped": True}

    parsed = epub_parser.parse_epub(source)
    if filename and parsed["title"] == source.stem:
        parsed["title"] = Path(filename).stem or parsed["title"]
    if not parsed["chapters"]:
        raise ValueError("The EPUB contains no readable chapters")
    if annotator is None:
        from .annotate import annotate_cues
        annotator = annotate_cues
    if dic is None:
        from .dictionary import Dictionary
        dic = Dictionary(log=log)
    if language is None:
        from .pipeline import learner_language
        language = learner_language()
    from .annotate import ANNOTATION_VERSION

    revision = uuid.uuid4().hex
    created = old.get("created", int(time.time())) if old else int(time.time())
    old_chapters = {chapter["chapterIndex"]: chapter for chapter in old["chapters"]} if old else {}
    allocated = {chapter["articleId"] for chapter in old_chapters.values()}
    chapters = []
    for chapter_index, chapter in enumerate(parsed["chapters"], 1):
        previous = old_chapters.get(chapter_index, {})
        aid = previous.get("articleId") or reading.new_id()
        while not previous and (aid in allocated or reading.article_path(aid).exists()):
            aid = reading.new_id()
        allocated.add(aid)
        cues = [{"i": index, "p": item["p"], "text": item["text"], "zh": ""}
                for index, item in enumerate(chapter["sentences"])]
        earlier = load_chapter(book_id, chapter_index) if previous else None
        if earlier and earlier.get("lang") == language:
            for cue, prior in zip(cues, earlier.get("cues", [])):
                if cue["text"] == prior.get("text"):
                    for key in ("zh", "seg", "zhLow", "translationEngine"):
                        if key in prior:
                            cue[key] = prior[key]
        annotator(cues, dic, lang=language)
        data = {"id": aid, "title": chapter["title"], "created": created, "translator": None,
                "translatorModel": "", "annotation": ANNOTATION_VERSION, "lang": language,
                "cues": cues, "section": "classic", "bookId": book_id, "chapterIndex": chapter_index,
                "classicRevision": revision}
        if earlier:
            data["translator"] = earlier.get("translator")
            data["translatorModel"] = earlier.get("translatorModel", "")
        save_chapter(data)
        chapters.append({"chapterIndex": chapter_index, "title": chapter["title"],
                         "wordCount": chapter["word_count"], "sentenceCount": len(cues), "articleId": aid,
                         "preview": " ".join(cue["text"] for cue in cues[:2])[:160]})
        log(f"已准备章节 {chapter_index}/{parsed['total_chapters']}: {chapter['title']}")
        if progress:
            progress(chapter_index / parsed["total_chapters"])

    cover_url = ""
    if parsed["cover"]:
        cover = parsed["cover"]
        filename = hashlib.sha256(cover["data"]).hexdigest() + cover["extension"]
        path = covers_dir() / filename
        if not path.exists():
            _atomic_write(path, cover["data"])
        cover_url = "/static/classic-covers/" + filename
    manifest = {"id": book_id, "title": parsed["title"], "zhTitle": "", "author": parsed["author"],
                "language": parsed["language"], "description": parsed["description"], "cover": cover_url,
                "accentColor": "#a7b6a6", "sourceHash": source_hash, "created": created,
                "revision": revision, "totalChapters": parsed["total_chapters"], "wordCount": parsed["total_words"],
                "chapters": chapters}
    for chapter in chapters:
        path = reading.article_path(chapter["articleId"])
        if not path.exists():
            _json_write(path, {"id": chapter["articleId"], "section": "classic", "bookId": book_id,
                               "chapterIndex": chapter["chapterIndex"], "classicManaged": True})
    _json_write(books_dir() / book_id / "manifest.json", manifest)
    _cleanup_overwrite(book_id, old, chapters, revision)
    return {"book": manifest, "skipped": False}


def delete_book(book_id: str) -> bool:
    with _import_lock:
        manifest = load_manifest(book_id)
        if not manifest:
            return False
        for chapter in manifest["chapters"]:
            article_id = chapter["articleId"]
            _remove_stub(article_id, book_id)
            if isinstance(article_id, str) and reading.ARTICLE_ID.fullmatch(article_id):
                path = reading.article_path(article_id)
                if path.exists():
                    try:
                        stub = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        stub = {}
                    if stub.get("classicManaged") and stub.get("bookId") == book_id:
                        raise OSError("无法删除名著章节")
        shutil.rmtree(books_dir() / book_id)
        cover = manifest.get("cover", "")
        prefix = "/static/classic-covers/"
        if cover.startswith(prefix) and not any(book.get("cover") == cover for book in imported_books()):
            name = cover[len(prefix):]
            if re.fullmatch(r"[0-9a-f]{64}\.(?:jpg|jpeg|png|webp)", name, re.I):
                (covers_dir() / name).unlink(missing_ok=True)
        return True


def submit_epub_import(pipeline, epub_path: Path, filename: str = "", overwrite: bool = False):
    from .pipeline import Job

    job = Job(url="epub:" + filename, overwrite=overwrite)

    def run():
        try:
            job.stage = "parse"

            def progress(fraction):
                job.stage, job.percent = "annotate", fraction

            result = import_book(epub_path, overwrite=overwrite, dic=pipeline.dic, log=job.log.append,
                                 progress=progress, filename=filename)
            job.video_id = result["book"]["id"]
            job.title = result["book"]["title"]
            job.skipped = result["skipped"]
            job.percent = 1.0
        except epub_parser.EncryptedContentError:
            job.error = "无法读取 EPUB 正文，文件可能受到加密保护。"
        except (zipfile.BadZipFile, ValueError, KeyError):
            job.error = "无法解析 EPUB，请检查文件内容是否完整。"
        except Exception as error:
            logging.exception("EPUB import failed")
            job.error = f"导入 EPUB 失败：{error}"
        finally:
            try:
                epub_path.unlink(missing_ok=True)
            except OSError:
                logging.exception("Could not remove EPUB upload")
                job.error = job.error or "无法清理临时上传文件。"
            job.stage = "error" if job.error else "done"

    with pipeline._jobs_lock:
        pipeline.jobs[job.id] = job
        threading.Thread(target=run, daemon=True).start()
    return job


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import an EPUB into the EchoLoop classics bookshelf.")
    parser.add_argument("epub", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    result = import_book(args.epub, args.overwrite)
    book = result["book"]
    print(f"{'已存在，跳过' if result['skipped'] else '导入完成'}: {book['title']}")
    print(f"book_id={book['id']} chapters={book['totalChapters']} words={book['wordCount']}")


if __name__ == "__main__":
    main()
