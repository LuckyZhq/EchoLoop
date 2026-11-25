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


@pytest.mark.parametrize("name", ["home.html", "player.html", "settings.html", "goals.html", "review.html", "common.js"])
def test_english_pages_keep_their_markup(name):
    path = server.STATIC_DIR / name
    out = i18n.page(path, "en").decode()
    assert out.count("<script") == path.read_text(encoding="utf-8").count("<script")
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
    assert i18n.load() == {"ui": "zh-CN", "native": "zh-CN", "zh": "zh-CN"}
    assert i18n.save({"ui": "en", "native": "zh-TW"}) == {"ui": "en", "native": "zh-TW", "zh": "zh-TW"}
    assert i18n.save({"ui": "xx", "native": "xx"})["ui"] == "en"  # unknown values are ignored
    s = i18n.save({"native": "vi"})
    assert s["native"] == "vi" and s["zh"] == "zh-CN"  # stored Chinese is only shown Traditional for zh-TW
    # files written before 母语 existed only had the Chinese variant
    (tmp_path / "language.json").write_text('{"ui": "zh-CN", "zh": "zh-TW"}', encoding="utf-8")
    assert i18n.load()["native"] == "zh-TW"


def test_language_from_the_browser(tmp_path, monkeypatch):
    assert i18n.from_browser("es-MX,es;q=0.9,en;q=0.8") == "es"
    assert i18n.from_browser("zh-TW,zh;q=0.9") == "zh-TW" and i18n.from_browser("zh-Hant-HK") == "zh-TW"
    assert i18n.from_browser("zh-CN,zh;q=0.9,en;q=0.8") == "zh-CN"
    assert i18n.from_browser("nl-NL,nl;q=0.9,en;q=0.5") == "en"  # first supported one
    assert i18n.from_browser("") is None
    monkeypatch.setattr(i18n, "SETTINGS_PATH", tmp_path / "language.json")
    monkeypatch.setattr(i18n, "LIBRARY_DIR", tmp_path)
    # a fresh install follows the browser and remembers it
    assert i18n.load("ja-JP,ja;q=0.9") == {"ui": "ja", "native": "ja", "zh": "zh-CN"}
    assert i18n.load("es") ["ui"] == "ja"  # saved: a later browser change doesn't switch it


def test_existing_library_keeps_the_chinese_default(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "SETTINGS_PATH", tmp_path / "language.json")
    monkeypatch.setattr(i18n, "LIBRARY_DIR", tmp_path)
    (tmp_path / "some-video").mkdir()
    (tmp_path / "some-video" / "data.json").write_text("{}", encoding="utf-8")
    assert i18n.load("en-US,en;q=0.9")["ui"] == "zh-CN"
    assert not (tmp_path / "language.json").exists()


def test_other_languages_fall_back_to_english(monkeypatch):
    i18n.to_ui.cache_clear()
    monkeypatch.setattr(i18n, "table", lambda lang: {"单词复习": "Repaso de palabras"} if lang == "es" else
                        __import__("json").loads(i18n.EN_PATH.read_text(encoding="utf-8")))
    assert i18n.to_ui("单词复习", "es") == "Repaso de palabras"
    assert i18n.to_ui("收藏词句", "es") == "Saved words"  # not in the Spanish table yet
    i18n.to_ui.cache_clear()


def test_ui_table_generator_keeps_edges_and_only_fills_gaps(tmp_path, monkeypatch):
    from ielts_study import ui_translate
    from ielts_study.settings import TranslationSettings

    monkeypatch.setattr(i18n, "UI_DIR", tmp_path)
    (tmp_path / "en.json").write_text(json.dumps({
        "单词复习": "Word review", "继续上次：": "Continue: ", "分": "", "n会按服务商价格计费。": "nThis is billed.",
        "阶段 · 现在": " stage · now"}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "fr.json").write_text(json.dumps({"单词复习": "Révision"}, ensure_ascii=False), encoding="utf-8")
    i18n.table.cache_clear()
    sent = []

    def fake(items, settings, instructions, purpose=None):
        sent.extend(items)
        return json.dumps([f"FR<{i['en']}>" for i in items])

    monkeypatch.setattr(ui_translate, "_completion", fake)
    api = TranslationSettings(engine="api", base_url="https://x/v1", model="m", api_key="k", provider="custom")
    out = ui_translate.generate("fr", api, log=lambda m: None)
    assert out["单词复习"] == "Révision"                      # existing entries are kept, not re-sent
    assert out["继续上次："] == "FR<Continue:> "               # trailing space put back
    assert out["阶段 · 现在"] == " FR<stage · now>"            # leading space put back
    assert out["分"] == ""                                     # empty stays empty, never sent
    assert out["n会按服务商价格计费。"] == "nFR<This is billed.>"  # the "\n" artifact survives
    assert {i["zh"] for i in sent} == {"继续上次：", "阶段 · 现在", "会按服务商价格计费。"}
    i18n.table.cache_clear()


def test_arabic_pages_are_right_to_left(monkeypatch):
    monkeypatch.setattr(i18n, "table", lambda lang: {})
    out = i18n.page(server.STATIC_DIR / "home.html", "ar").decode()
    assert '<html lang="ar" dir="rtl">' in out


def test_ui_table_generator_accepts_echoed_objects(tmp_path, monkeypatch):
    # without reasoning, a model may answer [{"zh": ..., "en": <translation>}] instead of plain strings
    from ielts_study import ui_translate
    from ielts_study.settings import TranslationSettings

    monkeypatch.setattr(i18n, "UI_DIR", tmp_path)
    (tmp_path / "en.json").write_text(json.dumps({"单词复习": "Word review"}, ensure_ascii=False), encoding="utf-8")
    i18n.table.cache_clear()
    monkeypatch.setattr(ui_translate, "_completion",
                        lambda items, settings, instructions, purpose=None: json.dumps(
                            [{"zh": i["zh"], "en": "Révision"} for i in items], ensure_ascii=False))
    api = TranslationSettings(engine="api", base_url="https://x/v1", model="m", api_key="k", provider="custom")
    assert ui_translate.generate("fr", api, log=lambda m: None)["单词复习"] == "Révision"
    i18n.table.cache_clear()
