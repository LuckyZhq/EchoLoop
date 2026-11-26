"""Translation settings: what the settings page may save."""
import pytest

from echoloop.settings import TranslationSettings, settings_from

SAVED = TranslationSettings(
    engine="api", base_url="https://api.deepseek.com", model="deepseek-flash", api_key="sk-saved",
    provider="deepseek",
)


def test_switching_model_keeps_the_saved_key():
    s = settings_from({"engine": "api", "provider": "deepseek", "model": "deepseek-v4-pro"}, SAVED)
    assert (s.model, s.api_key) == ("deepseek-v4-pro", "sk-saved")


def test_changing_the_address_drops_the_saved_key():
    with pytest.raises(ValueError, match="API Key"):
        settings_from({"engine": "api", "provider": "deepseek", "baseUrl": "https://other.example.com/v1"}, SAVED)


def test_remote_http_is_refused_but_local_http_is_fine():
    with pytest.raises(ValueError, match="HTTPS"):
        settings_from({"engine": "api", "provider": "custom", "baseUrl": "http://api.example.com/v1", "model": "m"}, SAVED)
    s = settings_from({"engine": "api", "provider": "custom", "baseUrl": "http://127.0.0.1:11434/v1", "model": "m"}, SAVED)
    assert s.base_url == "http://127.0.0.1:11434/v1"


def test_address_must_not_carry_a_key_or_query():
    with pytest.raises(ValueError):
        settings_from({"engine": "api", "provider": "custom", "baseUrl": "https://api.example.com/v1?key=abc", "model": "m"}, SAVED)


def test_chat_completions_suffix_is_trimmed():
    s = settings_from({"engine": "api", "provider": "custom", "baseUrl": "http://localhost:8080/v1/chat/completions/", "model": "m"}, SAVED)
    assert s.base_url == "http://localhost:8080/v1"


def test_local_engine_keeps_api_profiles():
    s = settings_from({"engine": "local"}, SAVED)
    assert s.engine == "local"
    assert s.api_profiles()["deepseek"]["api_key"] == "sk-saved"


def test_unknown_engine_or_provider_is_refused():
    with pytest.raises(ValueError):
        settings_from({"engine": "cloud"}, SAVED)
    with pytest.raises(ValueError):
        settings_from({"engine": "api", "provider": "nope"}, SAVED)


def test_a_key_can_be_saved_without_switching_translation():
    s = settings_from({"engine": "api", "provider": "groq", "apiKey": "gsk-1", "keepActive": True}, SAVED)
    assert (s.engine, s.provider, s.api_key) == ("api", "deepseek", "sk-saved")
    assert s.profiles["groq"]["api_key"] == "gsk-1" and "deepseek" not in s.profiles
    # keepActive on the provider already in use is an ordinary save
    s = settings_from({"engine": "api", "provider": "deepseek", "model": "deepseek-v4-pro", "keepActive": True}, SAVED)
    assert (s.provider, s.model, s.api_key) == ("deepseek", "deepseek-v4-pro", "sk-saved")
