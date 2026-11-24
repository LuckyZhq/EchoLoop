"""Speaking and writing practice: question banks, delivery measures, marking replies, saved history."""
import json

import pytest

from ielts_study import speaking, writing


def test_question_banks_are_complete():
    q = speaking.questions()
    assert len(q["part1"]) >= 10 and all(len(t["questions"]) >= 3 for t in q["part1"])
    assert all(len(c["points"]) == 3 and len(c["part3"]) >= 3 for c in q["part2"])
    t = writing.tasks()
    ids = [x["id"] for k in ("task2", "task1", "letters") for x in t[k]]
    assert len(ids) == len(set(ids)) and len(t["task2"]) >= 12
    for task in t["task1"]:
        c = task["chart"]
        assert c["kind"] in ("bar", "line", "table") and len(c["series"]) <= 3  # three colours validated all-pairs
        assert all(len(s["values"]) == len(c["categories"]) for s in c["series"])


def test_delivery_measures():
    words = [{"word": "Well,", "start": 0, "end": .3}, {"word": "um", "start": .4, "end": .6},
             {"word": "I", "start": 2.0, "end": 2.1, "p": .3}, {"word": "think", "start": 2.1, "end": 2.4},
             {"word": "so.", "start": 2.4, "end": 3.0}]
    d = speaking.delivery(words, 3.2)
    assert d["words"] == 5 and d["pauses"] == 1 and d["fillers"] == 1 and d["unclear"] == ["I"]
    assert d["wpm"] == 100


def test_feedback_is_cleaned():
    reply = {"overall": "6.3", "criteria": [{"name": "Fluency and Coherence", "band": 6.2, "comment": "ok"},
                                            {"name": "x", "band": "bad", "comment": ""}],
             "corrections": [{"original": "he go", "better": "he goes", "why": "agreement"}, {"original": ""}],
             "strengths": "not a list", "sample": "Sample."}
    out = speaking.clean_feedback(reply)
    assert out["overall"] == 6.5 and out["criteria"][0]["band"] == 6.0 and out["criteria"][1]["band"] is None
    assert out["corrections"] == [{"original": "he go", "better": "he goes", "why": "agreement"}]
    assert out["strengths"] == []


def test_recording_types(tmp_path, monkeypatch):
    monkeypatch.setattr(speaking, "REC_DIR", tmp_path)
    path = speaking.save_recording(b"abc", "audio/webm;codecs=opus")
    assert path.suffix == ".webm" and speaking.recording_path(path.name) == path
    with pytest.raises(ValueError):
        speaking.save_recording(b"abc", "text/html")
    assert speaking.recording_path("../vocab.json") is None


def test_shadow_sentences_are_whole_sentences():
    assert speaking._good_sentence("Many people believe that working from home is better.")
    assert not speaking._good_sentence("and then we went to the")
    assert all(speaking._good_sentence(s["text"]) for s in speaking.passage_sentences(50))


def test_essay_marking_and_history(tmp_path, monkeypatch):
    monkeypatch.setattr(writing, "WRITING_DIR", tmp_path)
    sent = {}

    def chat(source, settings, instructions, timeout=90):
        sent.update(json.loads(source), instructions=instructions)
        return json.dumps({"overall": 6, "criteria": [{"name": n, "band": 6, "comment": "c"} for n in writing.CRITERIA["task1"]],
                           "corrections": [{"original": "rised", "better": "rose", "why": "irregular verb"}],
                           "rewrite": "Better."})

    monkeypatch.setattr("ielts_study.translate.chat", chat)
    kind, task = writing.find_task("t1-energy")
    result = writing.mark(kind, task["prompt"], "Coal rised. " * 30, None, "zh-CN", task["chart"])
    assert "Renewables: 2000 = 5" in sent["data"] and "Task Achievement" in sent["instructions"]
    assert result["overall"] == 6.0 and result["corrections"][0]["better"] == "rose"
    entry = writing.save({"kind": kind, "prompt": task["prompt"], "essay": "x", "words": 60, "result": result})
    assert writing.load(entry["id"])["result"]["overall"] == 6.0
    assert writing.history()[0]["id"] == entry["id"]
    assert writing.load("../x") is None
    assert writing.delete(entry["id"]) and not writing.history()


def test_word_count():
    assert writing.word_count("It's a well-known fact: 3 of 10 people agree.") == 9
