"""分级阅读: the built-in passages, which levels show for whom, and API-written passages."""
import json
from types import SimpleNamespace

import pytest

from ielts_study import graded, reading


def test_builtin_passages():
    items = graded.passages()
    assert len({p["id"] for p in items}) == len(items)
    for level in graded.LEVEL_IDS:
        ours = [p for p in items if p["level"] == level]
        assert len(ours) >= 3, level
    for p in items:
        words = len(p["text"].split())
        assert p["title"] and p["topic"] and 200 <= words <= 700, (p["id"], words)
        assert "  " not in p["text"] and p["text"].count("\n\n") >= 4
    # higher levels are longer on average
    avg = {lv: sum(len(p["text"].split()) for p in items if p["level"] == lv) / 3 for lv in ("cet4", "ielts75")}
    assert avg["cet4"] < avg["ielts75"]


def test_levels_follow_the_learner_language():
    assert [lv["id"] for lv in graded.levels_for("zh-CN")] == ["cet4", "cet6", "ielts55", "ielts65", "ielts75"]
    assert [lv["id"] for lv in graded.levels_for("ja")] == ["ielts55", "ielts65", "ielts75"]


def test_overview_links_opened_and_written_articles(monkeypatch):
    monkeypatch.setattr(reading, "list_articles", lambda: [
        {"id": "a000000000001", "graded": "cet4-libraries", "level": "cet4", "title": "x", "wordCount": 240},
        {"id": "a000000000002", "ai": True, "level": "ielts65", "title": "Ocean Plastic", "topic": "the ocean",
         "wordCount": 470, "created": 5},
        {"id": "a000000000003", "level": None, "title": "Pasted", "wordCount": 100},
    ])
    out = graded.overview("zh-CN")
    by_id = {a["id"]: a for a in out["articles"]}
    assert by_id["cet4-libraries"]["articleId"] == "a000000000001"
    assert by_id["cet4-failure"]["articleId"] is None
    assert by_id["a000000000002"]["ai"] and by_id["a000000000002"]["level"] == "ielts65"
    assert "a000000000003" not in by_id  # pasted articles live under 我的文章
    assert not any(a["level"] == "cet4" for a in graded.overview("es")["articles"])


def test_opening_an_opened_passage_returns_its_article(monkeypatch):
    monkeypatch.setattr(reading, "list_articles", lambda: [{"id": "a000000000001", "graded": "cet4-libraries"}])
    pipeline = SimpleNamespace(jobs={}, _jobs_lock=__import__("threading").Lock())
    assert graded.open_passage(pipeline, "cet4-libraries") == {"articleId": "a000000000001"}
    assert graded.open_passage(pipeline, "nope") == {"error": "not found"}


def test_write_passage(monkeypatch):
    from ielts_study import translate

    sent = {}

    def fake(lines, settings, instructions):
        sent["lines"], sent["instructions"] = lines, instructions
        return json.dumps({"title": "Plastic in the Sea", "text": "Word " * 300})

    monkeypatch.setattr(translate, "_completion", fake)
    title, text, topic = graded.write_passage("ielts65", "海洋塑料", SimpleNamespace())
    assert title == "Plastic in the Sea" and topic == "海洋塑料" and sent["lines"] == ["Topic: 海洋塑料"]
    assert "band 6.5" in sent["instructions"] and "do not copy" in sent["instructions"]
    monkeypatch.setattr(translate, "_completion", lambda *a: json.dumps({"title": "t", "text": "too short"}))
    with pytest.raises(translate.TranslationError):
        graded.write_passage("cet4", "", SimpleNamespace())
