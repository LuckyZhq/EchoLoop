"""The 句子解析 endpoint, its cache and the lesson structure it returns."""
import hashlib
import json
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from echoloop import annotate, reading, sentence, server
from echoloop.annotate import ANNOTATION_VERSION
from echoloop.dictionary import Dictionary
from echoloop.settings import TranslationSettings

LESSON = {"source": "local", "structure": [{"segment": "She", "role": "主语"}],
          "vocabulary": [], "expressions": []}


@pytest.fixture
def base(tmp_path, monkeypatch):
    cues = [{"text": "She picked it up quickly.", "zh": "她很快把它捡了起来。", "start": 0, "end": 2, "notes": {}}]
    library = tmp_path / "library"
    (library / "v1").mkdir(parents=True)
    (library / "v1" / "data.json").write_text(json.dumps({"title": "t", "cues": cues}), encoding="utf-8")
    monkeypatch.setattr(server, "LIBRARY_DIR", library)
    monkeypatch.setattr(server, "ensure_annotation", lambda vdir, data, dic: data)
    monkeypatch.setattr(server, "load_settings", lambda: TranslationSettings())
    calls = []

    def local_lesson(cue, dic, label=None):
        calls.append(cue["text"])
        return dict(LESSON)

    monkeypatch.setattr(sentence, "_local_lesson", local_lesson)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(
        SimpleNamespace(dic=SimpleNamespace(word=lambda *a, **k: None, base_form=lambda w: w), pipeline=None)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", calls, cues
    httpd.shutdown()


def call(url, body, headers=None):
    request = Request(url, method="POST", data=json.dumps(body).encode(), headers=headers or {})
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


@pytest.fixture
def article(base, tmp_path, monkeypatch):
    url, calls, cues = base
    monkeypatch.setattr(reading, "ARTICLES_DIR", tmp_path / "articles")
    aid = "a0123456789ab"
    reading.save_article({"id": aid, "annotation": ANNOTATION_VERSION,
                          "cues": [cues[0], {"text": "   ", "zh": ""}]})
    return url, calls, cues, aid


def test_article_lesson_cache_is_deleted_with_article(article):
    url, calls, cues, aid = article
    body = {"articleId": aid, "index": 0, "text": cues[0]["text"]}
    status, first = call(url + "/api/sentence/analyze", body)
    assert status == 200
    assert first["sentence"] == cues[0]["text"] and first["translation"] == cues[0]["zh"]
    assert first["structure"] == LESSON["structure"] and first["cached"] is False

    status, cached = call(url + "/api/sentence/analyze", body)
    assert status == 200 and cached["cached"] is True and len(calls) == 1
    directory = reading.article_path(aid).parent
    assert len(list(directory.glob("lesson-*-local.json"))) == 1

    with urlopen(Request(url + "/api/reading/" + aid, method="DELETE"), timeout=5) as response:
        assert response.status == 200
    assert not directory.exists()


def test_article_lesson_refreshes_old_annotation(article, monkeypatch):
    url, _, cues, aid = article
    data = reading.load_article(aid)
    data["annotation"] = 0
    reading.save_article(data)
    def annotate_cues(items, dic, lang):
        items[0]["zh"] = "更新后的译文"

    monkeypatch.setattr(annotate, "annotate_cues", annotate_cues)
    status, lesson = call(url + "/api/sentence/analyze", {"articleId": aid, "index": 0})
    assert status == 200 and lesson["sentence"] == cues[0]["text"]
    assert lesson["translation"] == "更新后的译文"
    assert reading.load_article(aid)["annotation"] == ANNOTATION_VERSION


@pytest.mark.parametrize("body,status", [
    ({"index": 0}, 400),
    ({"videoId": "v1", "articleId": "a0123456789ab", "index": 0}, 400),
    ({"videoId": None, "articleId": "a0123456789ab", "index": 0}, 400),
    ({"articleId": "../escape", "index": 0}, 400),
    ({"articleId": "a0123456789ab\n", "index": 0}, 400),
    ({"articleId": "affffffffffff", "index": 0}, 404),
    ({"articleId": "a0123456789ab", "index": True}, 400),
    ({"articleId": "a0123456789ab", "index": -1}, 400),
    ({"articleId": "a0123456789ab", "index": 2}, 404),
    ({"articleId": "a0123456789ab", "index": 1}, 400),
    ({"articleId": "a0123456789ab", "index": 0, "text": "changed"}, 409),
    ({"articleId": "a0123456789ab", "index": 0, "engine": "bogus"}, 400),
])
def test_article_lesson_rejects_bad_requests(article, body, status):
    url, _, _, _ = article
    assert call(url + "/api/sentence/analyze", body)[0] == status


def test_article_engines_force_and_track_filter(article, monkeypatch):
    url, _, cues, aid = article
    monkeypatch.setattr(server, "load_settings", lambda: TranslationSettings(
        engine="local", profiles={"example": {"base_url": "https://example.com", "model": "test-model"}}))
    track = ["cet6"]
    monkeypatch.setattr(server.goals, "track", lambda: track[0])
    monkeypatch.setattr(sentence, "_track_candidates", lambda text, dic, labels: ["picked"])
    monkeypatch.setattr(sentence.translate, "chat", lambda *args, **kwargs: json.dumps({
        "structure": [{"segment": "She", "role": "主语"}],
        "vocabulary": [
            {"word": "picked", "pos": "v", "meaning": "捡起"},
            {"word": "quickly", "pos": "adv", "meaning": "迅速"},
        ],
        "expressions": [],
    }))
    local_labels = []

    def local_lesson(cue, dic, labels):
        local_labels.append(labels)
        return dict(LESSON)

    monkeypatch.setattr(sentence, "_local_lesson", local_lesson)
    body = {"articleId": aid, "index": 0, "text": cues[0]["text"]}
    status, api_lesson = call(url + "/api/sentence/analyze", {**body, "engine": "api"})
    assert status == 200 and api_lesson["source"] == "api"
    assert [entry["word"] for entry in api_lesson["vocabulary"]] == ["picked"]
    assert api_lesson["target"] == "六级 + 考研"

    status, local_lesson_result = call(url + "/api/sentence/analyze", {**body, "engine": "local"})
    assert status == 200 and local_lesson_result["source"] == "local"
    assert local_lesson_result["cached"] is False and local_labels == [("六级", "考研")]
    assert call(url + "/api/sentence/analyze", {**body, "engine": "local"})[1]["cached"] is True
    assert call(url + "/api/sentence/analyze", {**body, "engine": "local", "force": True})[1]["cached"] is False
    assert len(local_labels) == 2
    track[0] = "ielts"
    status, new_track = call(url + "/api/sentence/analyze", {**body, "engine": "local"})
    assert status == 200 and new_track["cached"] is False and new_track["target"] == "雅思 + 托福"
    assert local_labels[-1] == ("雅思", "托福")
    directory = reading.article_path(aid).parent
    assert list(directory.glob("lesson-*-api.json")) and list(directory.glob("lesson-*-local.json"))


def test_article_explicit_api_failure_does_not_fall_back(article, monkeypatch):
    url, calls, _, aid = article
    monkeypatch.setattr(server, "load_settings", lambda: TranslationSettings(
        engine="local", profiles={"example": {"base_url": "https://example.com", "model": "test-model"}}))

    def fail(*args):
        raise RuntimeError("解析失败")

    monkeypatch.setattr(sentence, "_model_lesson", fail)
    status, result = call(url + "/api/sentence/analyze", {"articleId": aid, "index": 0, "engine": "api"})
    assert status == 502 and result["error"] == "解析失败"
    assert calls == []


def test_lesson_is_cached_per_sentence(base):
    url, calls, cues = base
    status, lesson = call(url + "/api/sentence/analyze", {"videoId": "v1", "index": 0, "text": cues[0]["text"]})
    assert status == 200
    assert lesson["sentence"] == cues[0]["text"] and lesson["translation"] == cues[0]["zh"]
    assert lesson["structure"] == [{"segment": "She", "role": "主语"}]
    assert lesson["vocabulary"] == [] and lesson["expressions"] == []
    assert call(url + "/api/sentence/analyze", {"videoId": "v1", "index": 0})[1]["structure"] == lesson["structure"]
    assert len(calls) == 1 and len(list((server.LIBRARY_DIR / "v1").glob("lesson-*-local.json"))) == 1


@pytest.mark.parametrize("body,status", [
    ({"videoId": "../etc", "index": 0}, 400),
    ({"videoId": "v1", "index": True}, 400),
    ({"videoId": "v1", "index": -1}, 400),
    ({"videoId": "v1", "index": 5}, 404),
    ({"videoId": "v1", "index": 0, "text": "changed"}, 409),
])
def test_bad_requests(base, body, status):
    url, _, _ = base
    assert call(url + "/api/sentence/analyze", body)[0] == status


def test_lesson_refuses_foreign_sites(base):
    url, _, _ = base
    status, _ = call(url + "/api/sentence/analyze", {"videoId": "v1", "index": 0}, {"Origin": "http://evil.example"})
    assert status == 403


def test_model_lessons_speak_the_documented_contract(monkeypatch):
    meaning = "捡起并把东西带回原处（pick的过去式，表示已经完成的动作）"
    reply = {"structure": [{"segment": "She", "role": "主语"}],
             "vocabulary": [{"word": "quickly", "pos": "adv", "meaning": "迅速地"},
                            {"word": "picked", "pos": "v.", "meaning": meaning}],
             "expressions": [{"phrase": "pick up", "explanation": "捡起（代词放在中间）"}]}
    monkeypatch.setattr(sentence.translate, "chat", lambda *a, **k: json.dumps(reply))

    def word(w, pos=None):
        return {"en": w, "phonetic": "p", "tag": "cet6", "zh": "x"}

    dic = SimpleNamespace(word=word, base_form=lambda w: "pick" if w == "picked" else w)
    lesson = sentence._model_lesson("{}", dic, TranslationSettings(engine="api"))
    assert lesson["structure"] == reply["structure"]
    assert lesson["vocabulary"][0] == {"word": "quickly", "lemma": "quickly", "pos": "adv.", "meaning": "迅速地",
                                       "tags": ["六级"], "phonetic": "p"}
    assert lesson["vocabulary"][1]["pos"] == "v."
    assert lesson["vocabulary"][1]["lemma"] == "pick"
    assert lesson["vocabulary"][1]["meaning"] == meaning
    assert "level" not in lesson["vocabulary"][0]
    assert lesson["expressions"] == reply["expressions"]


def test_model_meanings_allow_up_to_eighty_characters(monkeypatch):
    meaning = "字" * 80
    reply = {"structure": [], "expressions": [],
             "vocabulary": [{"word": "alpha", "pos": "n.", "meaning": meaning},
                            {"word": "beta", "pos": "n.", "meaning": meaning + "多"}]}
    monkeypatch.setattr(sentence.translate, "chat", lambda *a, **k: json.dumps(reply))
    dic = SimpleNamespace(word=lambda w: {"tag": ""}, base_form=lambda w: w)
    lesson = sentence._model_lesson("{}", dic, TranslationSettings(engine="api"))
    assert [entry["meaning"] for entry in lesson["vocabulary"]] == [meaning, meaning]


@pytest.mark.parametrize("raw,clean", [("v", "v."), ("v.", "v."), ("adj..", "adj."), (" n ", "n."), ("", "")])
def test_pos_keeps_one_trailing_period(raw, clean):
    assert sentence._pos(raw) == clean


def test_local_vocabulary_keeps_only_the_target_exam_range():
    cue = {"text": "She picked it up quickly.", "zh": ""}
    dic = SimpleNamespace(
        word=lambda w, pos=None: {"en": w, "phonetic": "", "zh": "x",
                                  "tag": "cet4" if w == "quick" else "cet4 cet6 ky ielts"},
        base_form=lambda w: "quick" if w == "quickly" else w)
    lesson = sentence._local_lesson(cue, dic, ("四级", "六级"))
    assert [v["word"] for v in lesson["vocabulary"]] == ["picked", "quickly"]
    assert [v["lemma"] for v in lesson["vocabulary"]] == ["pick", "quickly"]
    assert all(v["tags"] == ["四级", "六级"] for v in lesson["vocabulary"])
    assert all(v["word"] != v["lemma"] or v["word"] == "quickly" for v in lesson["vocabulary"])


def test_model_vocabulary_is_filtered_to_the_target_exam(monkeypatch):
    reply = {"structure": [], "expressions": [],
             "vocabulary": [{"word": "alpha", "pos": "n.", "meaning": "甲"},
                            {"word": "beta", "pos": "n.", "meaning": "乙"}]}
    monkeypatch.setattr(sentence.translate, "chat", lambda *a, **k: json.dumps(reply))
    dic = SimpleNamespace(
        word=lambda w, pos=None: {"en": w, "phonetic": "", "zh": "x",
                                  "tag": "cet6" if w == "alpha" else "cet4"},
        base_form=lambda w: w)
    lesson = sentence._model_lesson('{"text": "alpha beta", "candidates": ["alpha"]}', dic,
                                    TranslationSettings(engine="api"), ("六级", "考研"))
    assert [v["word"] for v in lesson["vocabulary"]] == ["alpha"]
    assert all(v["lemma"] == v["word"] for v in lesson["vocabulary"])


def test_a_word_outside_every_word_list_has_no_tags():
    dic = SimpleNamespace(word=lambda w, pos=None: {"en": w, "phonetic": "", "tag": "", "zh": "x"}, base_form=lambda w: w)
    assert sentence.exam_info("zzzzz", dic) == {"tags": [], "phonetic": ""}


def test_an_inflected_word_is_looked_up_by_its_base_form():
    looked_up = []

    def word(w, pos=None):
        looked_up.append(w)
        return {"en": w, "phonetic": "p", "tag": "cet4" if w == "quick" else "", "zh": "x"}

    dic = SimpleNamespace(word=word, base_form=lambda w: "quick")
    assert sentence.exam_info("quickly", dic)["tags"] == ["四级"]
    assert looked_up == ["quickly", "quick"]


def test_api_cache_hit_skips_model_and_survives_model_or_notes_change(tmp_path, monkeypatch):
    cue = {"text": "Hello there.", "zh": "你好。", "notes": {}}
    chat_calls = []

    def chat(*args, **kwargs):
        chat_calls.append(1)
        return '{"structure": [{"segment": "first", "role": "r"}], "vocabulary": [], "expressions": []}'

    monkeypatch.setattr(sentence.translate, "chat", chat)
    first = TranslationSettings(engine="api", model="model-a")
    second = TranslationSettings(engine="api", model="model-b")

    res1 = sentence.analyze(tmp_path, cue, None, first)
    assert res1["cached"] is False
    assert res1["model"] == "model-a"
    assert res1["structure"][0]["segment"] == "first"

    # Second call on the same sentence hits disk cache without calling translate.chat
    res2 = sentence.analyze(tmp_path, cue, None, first)
    assert res2["cached"] is True
    assert res2["structure"][0]["segment"] == "first"

    # Switching model or changing cue["notes"] still hits the existing API cache
    res3 = sentence.analyze(tmp_path, {**cue, "notes": {"w": {"type": "word", "en": "hello"}}}, None, second)
    assert res3["cached"] is True
    assert res3["model"] == "model-a"
    assert len(chat_calls) == 1

    # Disk JSON must not store the transient "cached" flag
    cached_files = list(tmp_path.glob("lesson-*-api.json"))
    assert len(cached_files) == 1
    assert "cached" not in json.loads(cached_files[0].read_text(encoding="utf-8"))


def test_local_mode_reuses_existing_api_cache(tmp_path, monkeypatch):
    cue = {"text": "Hello there.", "zh": "你好。", "notes": {}}
    monkeypatch.setattr(sentence.translate, "chat", lambda *a, **k: (
        '{"structure": [{"segment": "api-part", "role": "r"}], "vocabulary": [], "expressions": []}'
    ))
    monkeypatch.setattr(sentence, "_local_lesson", lambda *a: pytest.fail("must reuse API cache"))

    api_res = sentence.analyze(tmp_path, cue, None, TranslationSettings(engine="api", model="model-a"))
    assert api_res["cached"] is False

    local_res = sentence.analyze(tmp_path, cue, None, TranslationSettings(engine="local"))
    assert local_res["cached"] is True
    assert local_res["source"] == "api"
    assert local_res["structure"] == [{"segment": "api-part", "role": "r"}]


def test_force_analyze_bypasses_cache_and_rewrites_it(tmp_path, monkeypatch):
    cue = {"text": "Hello there.", "zh": "你好。"}
    replies = iter([
        '{"structure": [{"segment": "first", "role": "r"}], "vocabulary": [], "expressions": []}',
        '{"structure": [{"segment": "rebuilt", "role": "r"}], "vocabulary": [], "expressions": []}',
    ])
    monkeypatch.setattr(sentence.translate, "chat", lambda *a, **k: next(replies))
    settings = TranslationSettings(engine="api", model="model-a")

    first = sentence.analyze(tmp_path, cue, None, settings)
    assert first["cached"] is False
    assert first["structure"][0]["segment"] == "first"

    forced = sentence.analyze(tmp_path, cue, None, settings, force=True)
    assert forced["cached"] is False
    assert forced["structure"][0]["segment"] == "rebuilt"

    after = sentence.analyze(tmp_path, cue, None, settings)
    assert after["cached"] is True
    assert after["structure"][0]["segment"] == "rebuilt"


def test_endpoint_forwards_force_parameter(base):
    url, calls, cues = base
    status1, lesson1 = call(url + "/api/sentence/analyze", {"videoId": "v1", "index": 0, "text": cues[0]["text"]})
    assert status1 == 200 and lesson1["cached"] is False

    status2, lesson2 = call(url + "/api/sentence/analyze", {"videoId": "v1", "index": 0, "text": cues[0]["text"]})
    assert status2 == 200 and lesson2["cached"] is True

    status3, lesson3 = call(url + "/api/sentence/analyze", {"videoId": "v1", "index": 0, "text": cues[0]["text"], "force": True})
    assert status3 == 200 and lesson3["cached"] is False
    assert len(calls) == 2


def test_endpoint_uses_saved_api_profile_when_global_engine_is_local(base, monkeypatch):
    url, _, cues = base
    monkeypatch.setattr(server, "load_settings", lambda: TranslationSettings(
        engine="local",
        profiles={"deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "api_key": "sk-test"}},
    ))
    seen_settings = []

    def chat(context, settings, *args, **kwargs):
        seen_settings.append(settings)
        return '{"structure": [{"segment": "She", "role": "主语"}], "vocabulary": [], "expressions": []}'

    monkeypatch.setattr(sentence.translate, "chat", chat)
    status, lesson = call(url + "/api/sentence/analyze", {"videoId": "v1", "index": 0, "text": cues[0]["text"], "engine": "api"})
    assert status == 200
    assert lesson["source"] == "api"
    assert lesson["model"] == "deepseek-flash"
    assert seen_settings and seen_settings[0].engine == "api" and seen_settings[0].api_key == "sk-test"


def test_endpoint_rejects_api_engine_without_saved_api_config(base):
    url, _, cues = base
    status, body = call(url + "/api/sentence/analyze", {"videoId": "v1", "index": 0, "text": cues[0]["text"], "engine": "api"})
    assert status == 400
    assert "配置 API 模型" in body["error"]


def test_endpoint_rejects_invalid_engine_value(base):
    url, _, cues = base
    status, body = call(url + "/api/sentence/analyze", {"videoId": "v1", "index": 0, "text": cues[0]["text"], "engine": "bogus"})
    assert status == 400
    assert "解析引擎" in body["error"]


def test_explicit_local_engine_does_not_reuse_api_cache(base, monkeypatch):
    url, calls, cues = base
    monkeypatch.setattr(server, "load_settings", lambda: TranslationSettings(
        engine="local",
        profiles={"openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-test", "api_key": "sk-test"}},
    ))
    monkeypatch.setattr(sentence.translate, "chat", lambda *a, **k: (
        '{"structure": [{"segment": "api-seg", "role": "r"}], "vocabulary": [], "expressions": []}'
    ))
    status_api, api_lesson = call(url + "/api/sentence/analyze", {"videoId": "v1", "index": 0, "text": cues[0]["text"], "engine": "api"})
    assert status_api == 200 and api_lesson["source"] == "api"

    status_local, local_lesson = call(url + "/api/sentence/analyze", {"videoId": "v1", "index": 0, "text": cues[0]["text"], "engine": "local"})
    assert status_local == 200
    assert local_lesson["source"] == "local"
    assert local_lesson["cached"] is False
    assert local_lesson["structure"] == [{"segment": "She", "role": "主语"}]
    assert len(calls) == 1
    assert list((server.LIBRARY_DIR / "v1").glob("lesson-*-api.json"))
    assert list((server.LIBRARY_DIR / "v1").glob("lesson-*-local.json"))


def test_old_lesson_cache_is_rebuilt(tmp_path, monkeypatch):
    cue = {"text": "Hello there.", "zh": "你好。", "notes": {}}
    context = json.dumps(cue, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(("lesson-v7:::" + context).encode()).hexdigest()
    old_cache = tmp_path / f"lesson-{digest}-local.json"
    old_cache.write_text(json.dumps(LESSON), encoding="utf-8")
    fresh = {**LESSON, "structure": [{"segment": "new", "role": "r"}]}
    monkeypatch.setattr(sentence, "_local_lesson", lambda *args: fresh)
    assert sentence.analyze(tmp_path, cue, None, TranslationSettings()) == {**fresh, "cached": False}
    assert old_cache.exists()


def test_an_unwritable_cache_still_returns_the_lesson(tmp_path, monkeypatch):
    cue = {"text": "Hello there.", "zh": "你好。"}
    monkeypatch.setattr(sentence, "_local_lesson", lambda *a: {
        "source": "local", "structure": [{"segment": "g", "role": "r"}], "vocabulary": [], "expressions": []})
    monkeypatch.setattr(sentence.hashlib, "sha256", lambda *a, **k: SimpleNamespace(hexdigest=lambda: "0" * 64))
    monkeypatch.setattr(sentence, "_locks", [threading.Lock()])
    # a directory where the cache file should go: the rename that saves the lesson fails
    (tmp_path / ("lesson-" + "0" * 64 + "-local.json")).mkdir()
    assert sentence.analyze(tmp_path, cue, None, TranslationSettings())["structure"][0]["segment"] == "g"


def test_local_structure_names_each_part_of_a_real_sentence():
    doc = sentence.annotate.nlp()("On November 19th, OpenAI, an American AI company, held its first conference.")
    parts = sentence._split_structure(next(iter(doc.sents)))
    segments = [p["segment"] for p in parts]
    assert "On November 19th" in segments
    assert any(p["segment"] == "an American AI company" and "同位语" in p["role"] for p in parts)
    assert any("介词短语" in p["role"] for p in parts)
    assert all(p["segment"] in doc.text for p in parts)
    assert not any(a != b and b in a for a in segments for b in segments)


@pytest.mark.parametrize("reply", [
    '{"structure": [], "vocabulary": [{"word": "a", "pos": "v"}], "expressions": []}',
    '{"structure": [{"segment": "a"}], "vocabulary": [], "expressions": []}',
    '{"structure": [], "vocabulary": [], "expressions": {}}',
])
def test_a_malformed_model_lesson_is_not_cached(reply, monkeypatch):
    monkeypatch.setattr(sentence.translate, "chat", lambda *a, **k: reply)
    with pytest.raises(RuntimeError, match="格式不完整"):
        sentence._model_lesson("{}", SimpleNamespace(word=lambda *a, **k: None, base_form=lambda w: w),
                               TranslationSettings(engine="api"))


def test_track_candidates_only_returns_words_on_the_track_exam_list():
    from types import SimpleNamespace
    from echoloop import sentence

    dic = SimpleNamespace(
        word=lambda w, pos=None: {"en": w, "tag": "cet6" if w == "rarely" else ""},
        base_form=lambda w: w)
    assert sentence._track_candidates("Dogs rarely bark.", dic, ("六级", "考研")) == ["rarely"]
    assert sentence._track_candidates("Dogs rarely bark.", dic, ()) == []


def test_ecdict_tag_candidates_survive_model_lesson(monkeypatch):
    reply = {"structure": [], "expressions": [],
             "vocabulary": [{"word": "rarely", "lemma": "rarely", "pos": "adv.", "meaning": "很少"}]}
    contexts = []

    def chat(context, *args, **kwargs):
        contexts.append(json.loads(context))
        return json.dumps(reply)

    monkeypatch.setattr(sentence.translate, "chat", chat)
    dic = Dictionary()
    assert {"cet6", "ky"} <= set(dic.word("rarely")["tag"].split())
    labels = ("六级", "考研")
    candidates = sentence._track_candidates("Dogs rarely do.", dic, labels)
    lesson = sentence._model_lesson(json.dumps({"text": "Dogs rarely do.", "candidates": candidates}),
                                    dic, TranslationSettings(engine="api"), labels)
    assert candidates == ["rarely"]
    assert contexts[0]["candidates"] == candidates
    assert [entry["lemma"] for entry in lesson["vocabulary"]] == ["rarely"]
    assert lesson["vocabulary"][0]["tags"] == ["六级", "考研"]


def test_instructions_require_raw_json_non_overlapping_and_single_words():
    from echoloop import sentence

    text = sentence._instructions(("六级", "考研"))
    assert "Return raw JSON only (no markdown fences or extra text)" in text
    assert "non-overlapping" in text
    assert "lemma" in text
    assert "Only choose from the candidates list" in text
    assert "at most five single words" in text
    assert "at most 15 characters" in text


def test_empty_candidates_means_no_vocabulary(monkeypatch):
    reply = {"structure": [], "expressions": [],
             "vocabulary": [{"word": "alpha", "lemma": "alpha", "pos": "n.", "meaning": "甲"}]}
    monkeypatch.setattr(sentence.translate, "chat", lambda *a, **k: json.dumps(reply))
    dic = SimpleNamespace(word=lambda w, pos=None: {"en": w, "phonetic": "", "zh": "x", "tag": "cet6"},
                          base_form=lambda w: w)
    lesson = sentence._model_lesson('{"text": "alpha beta", "candidates": []}', dic,
                                    TranslationSettings(engine="api"), ("六级", "考研"))
    assert lesson["vocabulary"] == []


@pytest.mark.parametrize("notes", [{}, {"w:pick": {"type": "word", "en": "pick", "zh": "v. 捡起"}}])
def test_local_vocabulary_fills_in_when_the_model_returns_nothing(tmp_path, monkeypatch, notes):
    cue = {"text": "She picked it up quickly.", "zh": "",
           "notes": notes}
    monkeypatch.setattr(sentence.translate, "chat", lambda *a, **k: json.dumps(
        {"structure": [], "vocabulary": [], "expressions": []}))
    monkeypatch.setattr(sentence, "_split_structure", lambda *a: pytest.fail("must not build local structure"))
    dic = SimpleNamespace(word=lambda w, pos=None: {
        "en": w, "phonetic": "p", "zh": "v. 将某物从地面捡起来并妥善收好",
        "tag": "cet4 cet6 ky ielts" if w == "pick" else "cet4"},
                          base_form=lambda w: "pick" if w == "picked" else w)
    lesson = sentence.analyze(tmp_path, cue, dic, TranslationSettings(engine="api"), track="cet6")
    assert [v["lemma"] for v in lesson["vocabulary"]] == ["pick"]
    assert lesson["vocabulary"][0] == {
        "word": "picked", "lemma": "pick", "pos": "v.",
        "meaning": "将某物从地面捡起来并妥善收好（pick的过去式）",
        "tags": ["六级", "考研"], "phonetic": "p"}
    assert list(tmp_path.glob("lesson-*-api.json"))


@pytest.mark.parametrize("track", [None, "cet6"])
def test_model_context_excludes_notes_and_cache_reuses_across_notes(tmp_path, monkeypatch, track):
    contexts = []

    def chat(context, *args, **kwargs):
        contexts.append(json.loads(context))
        return json.dumps({"structure": [], "vocabulary": [], "expressions": []})

    monkeypatch.setattr(sentence.translate, "chat", chat)
    cue = {"text": "She picked it up.", "zh": "她捡起了它。", "notes": {}}
    dic = SimpleNamespace(
        word=lambda w, pos=None: {"en": w, "phonetic": "", "zh": "v. 捡起", "tag": "cet6"},
        base_form=lambda w: w)
    settings = TranslationSettings(engine="api")
    first = sentence.analyze(tmp_path, cue, dic, settings, track)
    second = sentence.analyze(tmp_path, {**cue, "notes": {"p": {"type": "phrase", "en": "pick up", "zh": "捡起"}}},
                              dic, settings, track)
    assert len(contexts) == 1
    assert first["cached"] is False and second["cached"] is True
    assert set(contexts[0]) == ({"text", "zh", "candidates"} if track else {"text", "zh"})
