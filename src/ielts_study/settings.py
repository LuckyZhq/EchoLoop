"""Local translation settings. The API key stays on the server."""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from threading import Lock
from urllib.parse import urlsplit

from .config import DATA_DIR

SETTINGS_PATH = DATA_DIR / "settings.json"
_lock = Lock()

API_PROVIDERS = {
    "openai": ("OpenAI API", "https://api.openai.com/v1", "gpt-6.2-sol", "https://platform.openai.com/api-keys"),
    "gemini": ("Google Gemini API", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-4-hydrogen", "https://aistudio.google.com/apikey"),
    "grok": ("Grok API", "https://api.x.ai/v1", "grok-4.7", "https://console.x.ai/"),
    "deepseek": ("DeepSeek API", "https://api.deepseek.com", "deepseek-flash", "https://platform.deepseek.com/api_keys"),
    "qwen": ("通义千问 · 阿里云百炼", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", "https://bailian.console.aliyun.com/"),
    "kimi": ("Kimi · 月之暗面", "https://api.moonshot.cn/v1", "", "https://platform.moonshot.cn/"),
    "glm": ("GLM · 智谱", "https://open.bigmodel.cn/api/paas/v4", "", "https://open.bigmodel.cn/"),
    "doubao": ("豆包 · 火山方舟", "https://ark.cn-beijing.volces.com/api/v3", "doubao-seed-2-1-pro-260915", "https://console.volcengine.com/ark/"),
    "custom": ("自定义 OpenAI 兼容 API", "", "", ""),
}


@dataclass(frozen=True)
class TranslationSettings:
    engine: str = "local"
    base_url: str = ""
    model: str = ""
    api_key: str = field(default="", repr=False)
    provider: str = "custom"
    profiles: dict = field(default_factory=dict, repr=False)

    def api_profiles(self) -> dict:
        profiles = self.profiles.copy()
        if self.base_url and self.provider in API_PROVIDERS:
            profiles[self.provider] = {"base_url": self.base_url, "model": self.model, "api_key": self.api_key}
        return profiles

    def public(self) -> dict:
        profiles = self.api_profiles()
        return {
            "engine": self.engine,
            "baseUrl": self.base_url,
            "model": self.model,
            "hasApiKey": bool(self.api_key),
            "provider": self.provider,
            "providers": [
                {"id": provider, "name": name, "baseUrl": profile.get("base_url", base_url),
                 "model": profile.get("model", model), "hasSavedModel": bool(profile.get("model")),
                 "hasApiKey": bool(profile.get("api_key")), "console": console}
                for provider, (name, base_url, model, console) in API_PROVIDERS.items()
                for profile in (profiles.get(provider, {}),)
            ],
        }


def load_settings() -> TranslationSettings:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return TranslationSettings()
    except (OSError, ValueError):
        raise ValueError("无法读取本机的翻译设置。") from None
    try:
        settings = TranslationSettings(**data)
    except TypeError:
        raise ValueError("本机的翻译设置格式有误。") from None
    return settings


def _text(payload: dict, name: str, default: str, limit: int) -> str:
    value = payload.get(name, default)
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("设置字段的格式或长度有误。")
    return value.strip()


def _base_url(value: str) -> str:
    value = value.rstrip("/").removesuffix("/chat/completions").rstrip("/")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        raise ValueError("请输入有效的 API 地址。") from None
    if (not parsed.hostname or parsed.scheme not in ("http", "https") or parsed.username is not None
            or parsed.query or parsed.fragment or re.search(r"[\s\\]", value)):
        raise ValueError("请填写服务商提供的 API 地址，地址中不应包含密钥或查询参数。")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("远程 API 地址需要使用 HTTPS。本机服务可以用 HTTP。")
    return value


def settings_from(payload: dict, current: TranslationSettings, *, require_model: bool = True) -> TranslationSettings:
    engine = payload.get("engine", current.engine)
    if engine not in ("local", "api"):
        raise ValueError("请选择一个翻译方式。")
    profiles = current.api_profiles()
    if engine == "local":
        return TranslationSettings(engine="local", profiles=profiles)
    provider = payload.get("provider", current.provider)
    if not isinstance(provider, str) or provider not in API_PROVIDERS:
        raise ValueError("请选择一个 API 服务商。")
    _, default_url, default_model, _ = API_PROVIDERS[provider]
    profile = profiles.get(provider, {})
    base_url = _text(payload, "baseUrl", profile.get("base_url", default_url), 2048)
    model = _text(payload, "model", profile.get("model", default_model), 200)
    if base_url:
        base_url = _base_url(base_url)
    if not base_url:
        raise ValueError("请填写 API 地址。")
    if require_model and not model:
        raise ValueError("请填写 API 地址和模型名称。")

    supplied_key = _text(payload, "apiKey", "", 4096)
    if supplied_key and not re.fullmatch(r"[\x21-\x7e]+", supplied_key):
        raise ValueError("API Key 含有无效字符，请重新复制。")
    saved_key = profile.get("api_key", "") if base_url == profile.get("base_url") else ""
    key = "" if payload.get("clearKey") is True else supplied_key or saved_key
    if not key and provider != "custom" and payload.get("clearKey") is not True:
        raise ValueError("请填写这个服务商的 API Key。")
    profiles.pop(provider, None)
    return TranslationSettings(engine, base_url, model, key, provider, profiles)


def save_settings(payload: dict) -> TranslationSettings:
    with _lock:
        settings = settings_from(payload, load_settings())
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".settings-", dir=SETTINGS_PATH.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(asdict(settings), file, ensure_ascii=False, indent=2)
            os.replace(name, SETTINGS_PATH)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return settings
