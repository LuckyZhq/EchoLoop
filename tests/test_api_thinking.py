"""Translation requests ask reasoning models not to think (hidden reasoning is billed as output)."""
import io
import json
from urllib.error import HTTPError

import pytest

from echoloop import translate
from echoloop.settings import TranslationSettings

REPLY = {"choices": [{"message": {"content": "[\"你好\"]"}}]}


@pytest.fixture
def sent(monkeypatch):
    """Records each request body; a body containing a key listed in `reject` gets HTTP 400."""
    class Bodies(list):
        reject: set

    bodies, reject = Bodies(), set()

    class Opener:
        def open(self, request, timeout):
            body = json.loads(request.data)
            bodies.append(body)
            if reject & body.keys():
                raise HTTPError(request.full_url, 400, "unknown field", {}, io.BytesIO(b"{}"))
            return io.BytesIO(json.dumps(REPLY).encode())

    monkeypatch.setattr(translate, "build_opener", lambda *handlers: Opener())
    bodies.reject = reject
    return bodies


def api(provider, base_url="https://api.example.com/v1"):
    return TranslationSettings(engine="api", provider=provider, base_url=base_url, model="m", api_key="k")


def test_translation_turns_thinking_off_for_deepseek(sent):
    assert translate.translate_batch(["Hello."], api("deepseek", "https://api.deepseek.com")) == ["你好"]
    assert sent[0]["thinking"] == {"type": "disabled"}


def test_each_provider_gets_its_own_switch(sent):
    translate._completion(["Hello."], api("qwen"))
    translate._completion(["Hello."], api("openai"))
    translate._completion(["Hello."], api("custom", "https://api.deepseek.com/v1"))
    assert sent[0]["enable_thinking"] is False
    assert "thinking" not in sent[1] and "enable_thinking" not in sent[1]
    assert sent[2]["thinking"] == {"type": "disabled"}


def test_feedback_requests_keep_thinking(sent):
    translate.chat("essay", api("deepseek"), "grade it")
    assert "thinking" not in sent[0]


def test_a_provider_that_rejects_the_switch_is_asked_again_without_it(sent):
    sent.reject.add("thinking")
    assert translate._completion(["Hello."], api("glm")) == "[\"你好\"]"
    assert [("thinking" in body) for body in sent] == [True, False]


def test_other_errors_are_not_retried(monkeypatch):
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append(1)
            raise HTTPError(request.full_url, 401, "bad key", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(translate, "build_opener", lambda *handlers: Opener())
    with pytest.raises(translate.TranslationError, match="401"):
        translate._completion(["Hello."], api("deepseek"))
    assert calls == [1]
