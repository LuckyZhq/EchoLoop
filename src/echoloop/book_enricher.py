"""Resume optional sentence translation and lessons for imported classics."""
from __future__ import annotations

import argparse
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import book_importer, goals, reading, sentence
from .settings import load_settings, settings_for_engine

log = logging.getLogger(__name__)


def chapter_indices(value, total):
    if value is None:
        return list(range(1, min(total, 3) + 1))
    if value.strip().lower() == "all":
        return list(range(1, total + 1))
    selected = set()
    try:
        for part in value.split(","):
            parts = part.strip().split("-")
            if len(parts) == 1:
                selected.add(int(parts[0]))
            elif len(parts) == 2:
                first, last = map(int, parts)
                if first < 1 or first > last or last > total:
                    raise ValueError
                selected.update(range(first, last + 1))
            else:
                raise ValueError
    except ValueError:
        raise ValueError("章节范围应为 1-3、1,2,5 或 all") from None
    if not selected or min(selected) < 1 or max(selected) > total:
        raise ValueError(f"章节范围必须在 1 到 {total} 之间")
    return sorted(selected)


def enrich_book(book_id, chapters=None, translator=None, concurrency=2, dry_run=False, *,
                settings=None, track=None, dic=None, translate_fn=None):
    manifest = book_importer.load_manifest(book_id)
    if not manifest:
        raise ValueError("找不到导入的书籍")
    if concurrency < 1 or concurrency > 32:
        raise ValueError("并发数必须在 1 到 32 之间")
    engine = {"local": "local", "llm": "api", None: None}.get(translator, "invalid")
    if engine == "invalid":
        raise ValueError("翻译器必须是 local 或 llm")
    settings = settings_for_engine(engine, settings or load_settings())
    track = goals.track() if track is None else track
    explicit_engine = translator is not None
    indices = chapter_indices(chapters, manifest["totalChapters"])
    selected = {chapter["chapterIndex"]: chapter for chapter in manifest["chapters"]
                if chapter["chapterIndex"] in indices}
    stats = {"total": 0, "cached": 0, "pending": 0, "requests": 0, "processed": 0, "failed": 0}
    groups = {}
    for chapter_index in indices:
        chapter = selected[chapter_index]
        article = reading.load_article(chapter["articleId"])
        if not article:
            raise ValueError(f"无法读取章节 {chapter_index}")
        directory = reading.article_path(article["id"]).parent
        lock = threading.Lock()
        for cue in article["cues"]:
            if cue.get("zh") and article.get("translator") in ("api", "local"):
                cue.setdefault("translationEngine", article["translator"])
            stats["total"] += 1
            needs_translation = not cue.get("zh") and article.get("lang", "zh-CN") != "en"
            if not needs_translation and sentence.read_cache(directory, cue, settings, track, explicit_engine) is not None:
                stats["cached"] += 1
                continue
            stats["pending"] += 1
            key = (article["id"], sentence.cache_key(cue, track))
            group = groups.setdefault(key, {"article": article, "directory": directory, "cues": [],
                                            "lock": lock, "chapter": chapter_index})
            group["cues"].append(cue)
    stats["requests"] = len(groups)
    if dry_run or not groups:
        return stats
    if dic is None:
        from .dictionary import Dictionary
        dic = Dictionary(log=lambda message: log.info("%s", message))
    if translate_fn is None:
        from .translate import translate_cues
        translate_fn = translate_cues

    def process(group):
        cue = dict(group["cues"][0])
        article = group["article"]
        if (not cue.get("zh") or cue.get("translationEngine") != settings.engine) and article.get("lang", "zh-CN") != "en":
            used = translate_fn([cue], settings=settings, lang=article.get("lang", "zh-CN"))
            if not cue.get("zh"):
                raise RuntimeError("翻译结果为空")
            if used != settings.engine:
                raise RuntimeError(f"所选翻译引擎失败，实际返回 {used}")
            cue["translationEngine"] = used
            with group["lock"]:
                for original in group["cues"]:
                    for key in ("zh", "seg", "zhLow", "translationEngine"):
                        if key in cue:
                            original[key] = cue[key]
                engines = {item.get("translationEngine") for item in article["cues"] if item.get("zh")}
                article["translator"] = used if engines == {used} else "api+local"
                article["translatorModel"] = settings.model if "api" in engines else ""
                reading.save_article(article)
        sentence.analyze(group["directory"], cue, dic, settings, track, explicit_engine=explicit_engine)
        if sentence.read_cache(group["directory"], cue, settings, track, explicit_engine) is None:
            raise RuntimeError("句子解析缓存写入失败")
        return len(group["cues"])

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(process, group): group for group in groups.values()}
        for future in as_completed(futures):
            group = futures[future]
            try:
                stats["processed"] += future.result()
            except Exception as error:
                stats["failed"] += len(group["cues"])
                message = str(error)
                if settings.api_key:
                    message = message.replace(settings.api_key, "[redacted]")
                log.error("chapter_index=%s sentence_index=%s: %s: %s", group["chapter"],
                          group["cues"][0]["i"] + 1, type(error).__name__, message)
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description="Precompute sentence translations and lessons for a classic.")
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--chapters", help="1-3, 1,2,5, or all; defaults to the first three")
    parser.add_argument("--translator", choices=("local", "llm"))
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    stats = enrich_book(args.book_id, args.chapters, args.translator, args.concurrency, args.dry_run)
    print(f"句子={stats['total']} 缓存命中={stats['cached']} 待处理={stats['pending']} "
          f"去重后待处理={stats['requests']} 已处理={stats['processed']} 失败={stats['failed']}")
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
