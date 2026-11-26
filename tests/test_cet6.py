"""CET-6 (六级) transformations: placement/goals/plan, word annotations, writing & translation, speaking, reading."""
import json
from types import SimpleNamespace

import pytest

from echoloop import annotate, goals, graded, placement, plan, speaking, wordbook, writing
from echoloop.dictionary import Dictionary


def test_cet6_profile_defaults_and_track_switching(tmp_path, monkeypatch):
    monkeypatch.setattr(placement, "LIBRARY_DIR", tmp_path)
    monkeypatch.setattr(placement, "PROFILE_PATH", tmp_path / "profile.json")
    monkeypatch.setattr(plan, "LIBRARY_DIR", tmp_path)
    monkeypatch.setattr(plan, "ACTIVITY_PATH", tmp_path / "activity.json")

    p = placement.load_profile()
    assert p["track"] == "cet6"

    res = placement.estimate([(800, True), (2500, True), (4200, True), (6000, False)])
    assert res["cet"] == placement.cet_for(res["vocabSize"])
    p = placement.record_test({"vocabSize": 4600, "band": 6.0, "cet": 425})
    assert p["track"] == "cet6" and p["current"] == 425 and p["target"] == 550

    g = goals.today()
    assert g["track"] == "cet6" and g["stage"]["id"] == "improve"
    assert g["reason"]["bandGap"] == 125
    assert g["markRange"]["lo"] == 4600 and g["markRange"]["hi"] > 6300

    # Switching track to IELTS converts current score from vocabSize
    p2 = placement.update_profile({"track": "ielts"})
    assert p2["track"] == "ielts" and p2["current"] == placement.band_for(4600)
    assert goals.today()["stage"]["id"] == "improve"


def test_cet_stages_and_wordbook_examples():
    assert plan.stage_for(None, "cet6")["id"] == "improve"
    assert plan.stage_for(300, "cet6")["id"] == "starter"
    assert plan.stage_for(400, "cet6")["id"] == "basic"
    assert plan.stage_for(450, "cet6")["id"] == "improve"
    assert plan.stage_for(550, "cet6")["id"] == "sprint"

    assert wordbook.BOOKS[0]["id"] == "cet6"
    assert "CET-6" in wordbook.example_instructions("zh-CN", track="cet6")
    assert "IELTS" in wordbook.example_instructions("zh-CN", track="ielts")


def test_annotate_marks_cet6_flag():
    dic = Dictionary()
    cues = [{"text": "Universities should mitigate academic burnout and foster resilience."}]
    annotate.annotate_cues(cues, dic, lang="zh-CN")
    notes = cues[0]["notes"]
    word_notes = [n for n in notes.values() if n["type"] == "word"]
    assert word_notes
    assert all("cet6" in n and "cet4" in n for n in word_notes)


def test_cet6_writing_and_translation_marking(tmp_path, monkeypatch):
    monkeypatch.setattr(writing, "WRITING_DIR", tmp_path)
    bank = writing.tasks()
    assert len(bank["cet6_essay"]) >= 6
    assert len(bank["cet6_trans"]) >= 6

    captured = {}

    def fake_chat(source, settings, instructions, timeout=90, **options):
        captured["source"] = json.loads(source)
        captured["instructions"] = instructions
        return json.dumps({
            "overall": 12.0,
            "criteria": [{"name": n, "band": 12.0, "comment": "良好"} for n in writing.CRITERIA["cet6_trans"]],
            "summary": "译文整体准确。",
            "strengths": ["主干清晰"],
            "improve": ["注意被动语态"],
            "corrections": [{"original": "Tea have long history", "better": "Tea has a long history", "why": "主谓一致与冠词"}],
            "vocabulary": [{"instead": "very famous", "try": "widely renowned", "why": "表达更地道"}],
            "structure": "适当合并短句。",
            "rewrite": "Tea has a history spanning thousands of years in China.",
        })

    monkeypatch.setattr("echoloop.translate.chat", fake_chat)
    kind, task = writing.find_task("c6t-tea")
    assert kind == "cet6_trans"
    result = writing.mark(kind, task["prompt"], "Tea have long history in China.", None, "zh-CN")
    assert "15-point translation scale" in captured["instructions"]
    assert result["scale"] == "cet15"
    assert result["overall"] == 12.0
    assert result["scaled"] == round(12.0 / 15.0 * 106.5, 1)


def test_cet6_speaking_bank_and_feedback(monkeypatch):
    q = speaking.questions()
    assert len(q["cet6"]["qa"]) >= 4
    assert len(q["cet6"]["presentation"]) >= 4
    for card in q["cet6"]["presentation"]:
        assert len(card["points"]) == 3 and len(card["followup"]) >= 3

    def fake_chat(source, settings, instructions, timeout=90, **options):
        assert "CET-SET6" in instructions
        return json.dumps({
            "overall": 13.0,
            "criteria": [{"name": "准确性与词汇语法范围", "band": 13.0, "comment": "好"}],
            "strengths": ["流利"],
            "improve": ["多用连接词"],
            "corrections": [],
            "vocabulary": [],
            "sample": "Sample CET-6 presentation.",
        })

    monkeypatch.setattr("echoloop.translate.chat", fake_chat)
    out = speaking.feedback(2, "AI in education", "I think AI is helpful for study.", {"wpm": 120}, None, "zh-CN", mode="cet6")
    assert out["scale"] == "cet15" and out["overall"] == 13.0 and out["grade"] == "A"


def test_cet6_graded_passages_expanded():
    cet6_items = [p for p in graded.passages() if p["level"] == "cet6"]
    assert len(cet6_items) >= 8
    lv = next(x for x in graded.LEVELS if x["id"] == "cet6")
    assert "British spelling" not in graded.instructions(lv)
