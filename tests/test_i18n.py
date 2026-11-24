"""Languages: Traditional conversion, the English interface table, and which API text follows which setting."""
import json

import pytest

from ielts_study import i18n, server


def test_traditional_uses_taiwan_wording():
    assert i18n.to_traditional("视频精听：粘贴视频链接，软件和网络") == "影片精聽：貼上影片連結，軟體和網路"
    assert i18n.to_traditional("Hello 123") == "Hello 123"
    assert i18n.to_simplified("影片") in ("影片", "视频")  # back to Simplified for storage


def test_english_replaces_whole_fragments_only():
    assert i18n.to_english("单词复习") == "Word review"
    # numbers filled in at runtime split the text into known fragments
    assert i18n.to_english("使用 API 重新翻译 140 句字幕…") == "Translating again with the API: 140 subtitle lines…"
    # text that is not an interface fragment stays as it is, even if it contains a key ("分" in 充分利用)
    assert i18n.to_english("这能让我充分利用通勤时间") == "这能让我充分利用通勤时间"


def test_english_table_is_valid_and_has_no_untranslated_values():
    table = json.loads(i18n.EN_PATH.read_text(encoding="utf-8"))
    assert len(table) > 600
    allowed_chinese = {"简体中文", "繁體中文", "繁體中文（台灣用語）"}  # language names stay in their own language
    for key, value in table.items():
        if value and key not in allowed_chinese:
            assert not i18n.HAN.search(value), (key, value)


@pytest.mark.parametrize("name", ["home.html", "player.html", "settings.html", "level.html", "review.html", "common.js"])
def test_english_pages_keep_their_markup(name):
    path = server.STATIC_DIR / name
    out = i18n.page(path, "en").decode()
    assert out.count("<script") == path.read_text().count("<script")
    if name.endswith(".html"):
        assert '<html lang="en">' in out


def test_api_text_follows_the_right_setting():
    lang = {"ui": "en", "zh": "zh-TW"}
    # content: Chinese meanings follow the translation language; interface keys follow the interface language
    video = server.localize({"cues": [{"zh": "我们去公园", "gl": ["软件"]}], "error": "请求需要来自本机页面。"},
                            "/api/video/x", lang)
    assert video["cues"][0]["zh"] == "我們去公園" and video["cues"][0]["gl"] == ["軟體"]
    assert video["error"] == "The request must come from a page on this computer."
    # interface responses: everything in the interface language
    plan = server.localize({"tasks": [{"label": "复习到期的词"}]}, "/api/plan", lang)
    assert plan["tasks"][0]["label"] == "Review due words"


def test_language_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "SETTINGS_PATH", tmp_path / "language.json")
    monkeypatch.setattr(i18n, "LIBRARY_DIR", tmp_path)
    assert i18n.load() == {"ui": "zh-CN", "zh": "zh-CN"}
    assert i18n.save({"ui": "en", "zh": "zh-TW"}) == {"ui": "en", "zh": "zh-TW"}
    assert i18n.save({"ui": "fr"})["ui"] == "en"  # unknown values are ignored
