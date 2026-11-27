"""Reading: pasted articles are split into paragraphs and sentences."""
from echoloop.reading import ARTICLE_ID, new_id, split_sentences


def test_paragraphs_and_sentences():
    cues = split_sentences("Parks matter. They reduce stress.\n\nHowever, cities grow fast.")
    assert [(c["p"], c["text"]) for c in cues] == [
        (0, "Parks matter."), (0, "They reduce stress."), (1, "However, cities grow fast."),
    ]
    assert [c["i"] for c in cues] == [0, 1, 2]


def test_single_line_breaks_start_new_paragraphs_and_blank_lines_are_skipped():
    cues = split_sentences("First line.\nSecond line.\n\n\n   \nThird line.")
    assert [c["p"] for c in cues] == [0, 1, 2]


def test_article_ids_are_safe_path_names():
    aid = new_id()
    assert ARTICLE_ID.match(aid)
    assert not ARTICLE_ID.match("../library")


def test_old_articles_are_reannotated_and_saved(tmp_path, monkeypatch):
    from echoloop import reading
    from echoloop.annotate import ANNOTATION_VERSION
    from echoloop.dictionary import Dictionary

    monkeypatch.setattr(reading, "ARTICLES_DIR", tmp_path)
    old = {"id": "a000000000001", "title": "t", "annotation": 1,
           "cues": [{"i": 0, "p": 0, "text": "Cities must mitigate congestion.", "zh": "城市必须缓解拥堵。"}]}
    reading.save_article(old)
    data = reading.ensure_article_annotation(reading.load_article(old["id"]), Dictionary())
    assert data["annotation"] == ANNOTATION_VERSION
    assert "gl" in data["cues"][0] and "marks" in data["cues"][0]
    assert reading.load_article(old["id"])["annotation"] == ANNOTATION_VERSION  # written back to disk


def test_sections_preserve_legacy_articles_and_reading_progress(tmp_path, monkeypatch):
    from echoloop import classics, graded, reading

    monkeypatch.setattr(reading, "ARTICLES_DIR", tmp_path)
    legacy = [
        {"id": "a000000000001", "title": "Built in", "graded": graded.passages()[0]["id"], "level": "cet4"},
        {"id": "a000000000002", "title": "Generated", "level": "cet6", "ai": True},
        {"id": "a000000000003", "title": "Pasted"},
    ]
    for article in legacy:
        reading.save_article(article)
    articles = {article["id"]: article for article in reading.list_articles()}
    assert articles[legacy[0]["id"]]["section"] == "periodical"
    assert articles[legacy[1]["id"]]["section"] == articles[legacy[2]["id"]]["section"] == "custom"
    for language in ("zh-CN", "en"):
        periodicals = graded.overview(language)["periodicals"]
        assert len(periodicals) == len(graded.passages())
        assert next(item for item in periodicals if item["id"] == legacy[0]["graded"])["articleId"] == legacy[0]["id"]
        assert all(item["topic"] and item["level"] and item["cefr"] for item in periodicals)

    book = classics.BOOKS[0]
    first, second = book["chapters"][:2]
    for chapter, aid in ((first, "a000000000004"), (second, "a000000000005")):
        reading.save_article({"id": aid, "title": chapter["title"], "section": "classic",
                              "bookId": book["id"], "chapterIndex": chapter["chapterIndex"]})
    data_path = reading.article_path("a000000000004")
    original = data_path.read_bytes()
    times = iter((100, 101, 102))
    monkeypatch.setattr(reading.time, "time", lambda: next(times))
    reading.mark_progress("a000000000004")
    assert classics.overview()[0]["lastReadChapterId"] == "a000000000004"
    assert classics.overview()[0]["completedChapters"] == 0
    reading.mark_progress("a000000000004", completed=True)
    reading.mark_progress("a000000000005")
    overview = classics.overview()[0]
    assert overview["lastReadChapterId"] == "a000000000005"
    assert overview["completedChapters"] == 1
    assert [bool(chapter["completedAt"]) for chapter in overview["chapters"]] == [True, False]
    assert data_path.read_bytes() == original
    assert reading.mark_progress(legacy[1]["id"], completed=True) is None


def test_classic_open_reuses_article_and_running_job(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import threading
    from echoloop import classics, reading

    monkeypatch.setattr(reading, "ARTICLES_DIR", tmp_path)
    book = classics.BOOKS[0]
    index = book["chapters"][0]["chapterIndex"]
    key = f"classic:{book['id']}:{index}"
    job = SimpleNamespace(url=key, stage="translating", to_json=lambda: {"id": "job-1"})
    pipeline = SimpleNamespace(jobs={"job-1": job}, _jobs_lock=threading.Lock())
    assert classics.open_chapter(pipeline, book["id"], index) == {"job": {"id": "job-1"}}
    reading.save_article({"id": "a000000000001", "section": "classic",
                          "bookId": book["id"], "chapterIndex": index})
    assert classics.open_chapter(pipeline, book["id"], index) == {"articleId": "a000000000001"}
    assert classics.open_chapter(pipeline, book["id"], 999) == {"error": "not found"}


def test_new_classic_chapter_uses_article_pipeline(tmp_path, monkeypatch):
    import time
    from types import SimpleNamespace
    from echoloop import annotate, classics, meanings, pipeline, reading, settings, translate, usage

    monkeypatch.setattr(reading, "ARTICLES_DIR", tmp_path)
    monkeypatch.setattr(settings, "load_settings", lambda: SimpleNamespace(engine="local", model="test"))
    monkeypatch.setattr(pipeline, "learner_language", lambda: "zh-CN")
    monkeypatch.setattr(translate, "translate_cues", lambda *args, **kwargs: "local")
    monkeypatch.setattr(annotate, "annotate_cues", lambda *args, **kwargs: None)
    monkeypatch.setattr(meanings, "fill_notes", lambda *args, **kwargs: None)
    monkeypatch.setattr(usage, "snapshot", lambda: {})
    monkeypatch.setattr(usage, "since", lambda _before: {})
    monkeypatch.setattr(usage, "describe", lambda _usage: "")
    worker = pipeline.Pipeline(None)
    book = classics.BOOKS[0]
    chapter = book["chapters"][0]
    result = classics.open_chapter(worker, book["id"], chapter["chapterIndex"])
    job = worker.jobs[result["job"]["id"]]
    deadline = time.monotonic() + 5
    while job.stage not in ("done", "error") and time.monotonic() < deadline:
        time.sleep(.01)
    assert job.stage == "done", job.error
    article = reading.load_article(job.video_id)
    assert article["section"] == "classic"
    assert (article["bookId"], article["chapterIndex"]) == (book["id"], chapter["chapterIndex"])
    assert article["cues"][0]["text"].startswith("It is a truth universally acknowledged")
    assert classics.open_chapter(worker, book["id"], chapter["chapterIndex"]) == {"articleId": job.video_id}
