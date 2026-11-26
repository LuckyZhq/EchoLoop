"""The 句子解析 endpoint, its cache and the lesson structure it returns."""
import json
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from echoloop import sentence, server
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
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(SimpleNamespace(dic=None, pipeline=None)))
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
    reply = {"structure": [{"segment": "She", "role": "主语"}],
             "vocabulary": [{"word": "quickly", "pos": "adv", "meaning": "迅速地"},
                            {"word": "picked", "pos": "v.", "meaning": "捡起（pick的过去式）"}],
             "expressions": [{"phrase": "pick up", "explanation": "捡起（代词放在中间）"}]}
    monkeypatch.setattr(sentence.translate, "chat", lambda *a, **k: json.dumps(reply))

    def word(w, pos=None):
        return {"en": w, "phonetic": "p", "tag": "cet6", "zh": "x"}

    dic = SimpleNamespace(word=word, base_form=lambda w: "pick" if w == "picked" else w)
    lesson = sentence._model_lesson("{}", dic, TranslationSettings(engine="api"))
    assert lesson["structure"] == reply["structure"]
    assert lesson["vocabulary"][0] == {"word": "quickly", "pos": "adv.", "meaning": "迅速地",
                                       "tags": ["六级"], "phonetic": "p"}
    assert lesson["vocabulary"][1]["pos"] == "v."
    assert "level" not in lesson["vocabulary"][0]
    assert lesson["expressions"] == reply["expressions"]


@pytest.mark.parametrize("raw,clean", [("v", "v."), ("v.", "v."), ("adj..", "adj."), (" n ", "n."), ("", "")])
def test_pos_keeps_one_trailing_period(raw, clean):
    assert sentence._pos(raw) == clean


def test_local_vocabulary_keeps_only_the_target_exam_range():
    cue = {"text": "She picked it up quickly.", "zh": ""}
    dic = SimpleNamespace(
        word=lambda w, pos=None: {"en": w, "phonetic": "", "zh": "x", "tag": "cet4" if w == "quick" else "cet6"},
        base_form=lambda w: "quick" if w == "quickly" else w)
    assert [v["word"] for v in sentence._local_lesson(cue, dic, ("四级", "六级"))["vocabulary"]] == ["pick", "quickly"]


def test_model_vocabulary_is_filtered_to_the_target_exam(monkeypatch):
    reply = {"structure": [], "expressions": [],
             "vocabulary": [{"word": "alpha", "pos": "n.", "meaning": "甲"},
                            {"word": "beta", "pos": "n.", "meaning": "乙"}]}
    monkeypatch.setattr(sentence.translate, "chat", lambda *a, **k: json.dumps(reply))
    dic = SimpleNamespace(
        word=lambda w, pos=None: {"en": w, "phonetic": "", "zh": "x",
                                  "tag": "cet6" if w == "alpha" else "cet4"},
        base_form=lambda w: w)
    lesson = sentence._model_lesson("{}", dic, TranslationSettings(engine="api"), ("六级", "考研"))
    assert [v["word"] for v in lesson["vocabulary"]] == ["alpha"]


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


def test_each_model_has_its_own_cache(tmp_path, monkeypatch):
    cue = {"text": "Hello there.", "zh": "你好。"}
    replies = iter(['{"structure": [{"segment": "first", "role": "r"}], "vocabulary": [], "expressions": []}',
                    '{"structure": [{"segment": "second", "role": "r"}], "vocabulary": [], "expressions": []}'])
    monkeypatch.setattr(sentence.translate, "chat", lambda *a, **k: next(replies))
    first = TranslationSettings(engine="api", model="model-a")
    second = TranslationSettings(engine="api", model="model-b")
    assert sentence.analyze(tmp_path, cue, None, first)["structure"][0]["segment"] == "first"
    assert sentence.analyze(tmp_path, cue, None, first)["structure"][0]["segment"] == "first"
    assert sentence.analyze(tmp_path, cue, None, second)["structure"][0]["segment"] == "second"


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
