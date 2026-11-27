"""Public-domain book excerpts prepared through the normal article pipeline."""
from __future__ import annotations

import threading

from . import reading

BOOKS = []
_open_lock = threading.Lock()


def _builtin_chapters(book, saved):
    chapters = []
    for chapter in sorted(book["chapters"], key=lambda item: item["chapterIndex"]):
        article = saved.get((book["id"], chapter["chapterIndex"]), {})
        chapters.append({
            "chapterIndex": chapter["chapterIndex"], "title": chapter["title"],
            "wordCount": len(chapter["text"].split()), "articleId": article.get("id"),
            "readAt": article.get("readAt", 0), "completedAt": article.get("completedAt", 0),
        })
    return chapters


def _imported_chapters(book):
    chapters = []
    for item in book["chapters"]:
        progress = reading.article_progress(item["articleId"])
        chapters.append({key: value for key, value in item.items() if key != "preview"} | {
            "readAt": progress.get("readAt", 0), "completedAt": progress.get("completedAt", 0),
        })
    return chapters


def _book_with_chapters(book, chapters):
    last = max(chapters, key=lambda chapter: chapter["readAt"], default={})
    return {
        **{key: value for key, value in book.items() if key not in ("chapters", "revision")},
        "totalChapters": len(chapters),
        "wordCount": book.get("wordCount", sum(chapter["wordCount"] for chapter in chapters)),
        "completedChapters": sum(bool(chapter["completedAt"]) for chapter in chapters),
        "lastReadChapterId": last.get("articleId") if last.get("readAt") else None,
        "chapters": chapters,
    }


def book_chapters(book_id: str) -> list[dict] | None:
    from .book_importer import load_manifest
    manifest = load_manifest(book_id)
    if manifest:
        return _imported_chapters(manifest)
    book = next((item for item in BOOKS if item["id"] == book_id), None)
    if not book:
        return None
    saved = {(a["bookId"], a["chapterIndex"]): a for a in reading.list_articles(include_managed=False)
             if a["section"] == "classic" and a.get("bookId") and a.get("chapterIndex") is not None}
    return _builtin_chapters(book, saved)


def overview(summary=False) -> list[dict]:
    saved = {(a["bookId"], a["chapterIndex"]): a for a in reading.list_articles(include_managed=False)
             if a["section"] == "classic" and a.get("bookId") and a.get("chapterIndex") is not None}
    books = [_book_with_chapters(book, _builtin_chapters(book, saved)) for book in BOOKS]
    from .book_importer import imported_books
    books.extend(_book_with_chapters(book, _imported_chapters(book)) for book in imported_books())
    if summary:
        for book in books:
            chapters = book.pop("chapters")
            last_index = (next((index for index, chapter in enumerate(chapters)
                                if chapter["articleId"] == book["lastReadChapterId"]), None)
                          if book["lastReadChapterId"] else None)
            book["resumeChapter"] = None
            if last_index is not None and not all(chapter["completedAt"] for chapter in chapters):
                last = chapters[last_index]
                book["resumeChapter"] = (last if not last["completedAt"] else
                                         next((chapter for chapter in chapters[last_index + 1:]
                                               if not chapter["completedAt"]), None) or
                                         next((chapter for chapter in chapters if not chapter["completedAt"]), None))
    return books


def open_chapter(pipeline, book_id: str, chapter_index: int) -> dict:
    from .book_importer import load_manifest
    imported = load_manifest(book_id)
    if imported:
        chapter = next((item for item in imported["chapters"] if item["chapterIndex"] == chapter_index), None)
        return {"articleId": chapter["articleId"]} if chapter else {"error": "not found"}
    book = next((item for item in BOOKS if item["id"] == book_id), None)
    chapter = next((item for item in book["chapters"] if item["chapterIndex"] == chapter_index), None) if book else None
    if not chapter:
        return {"error": "not found"}
    with _open_lock:
        for article in reading.list_articles(include_managed=False):
            if (article["section"] == "classic" and article.get("bookId") == book_id
                    and article.get("chapterIndex") == chapter_index):
                return {"articleId": article["id"]}
        key = f"classic:{book_id}:{chapter_index}"
        with pipeline._jobs_lock:
            for job in pipeline.jobs.values():
                if job.url == key and job.stage not in ("done", "error"):
                    return {"job": job.to_json()}
        job = reading.submit_article(
            pipeline, chapter["text"], chapter["title"], key=key,
            extra={"section": "classic", "bookId": book_id, "chapterIndex": chapter_index},
        )
        return {"job": job.to_json()}
