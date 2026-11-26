"""API usage: the tokens of every request, kept per day and purpose in data/api_usage.json.

Shown in each import's log ("API 用量：…") and in Settings → Models and services. Requests to DeepSeek also get an
estimated cost from its published price list; other providers are counted in tokens only. A request that timed out
is counted separately: the provider may have billed it even though no reply arrived.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

from .config import DATA_DIR

PATH = DATA_DIR / "api_usage.json"
_lock = threading.Lock()
FIELDS = ("requests", "input", "cached", "output", "reasoning", "timeouts", "unpriced")

# CNY per million tokens at peak: (input, cache hit; input, cache miss; output). DeepSeek's price page, November
# 2026 (api-docs.deepseek.com/zh-cn/quick_start/pricing). Reasoning tokens are part of the output. The old model names
# are billed at Flash prices.
_FLASH = (0.04, 2.0, 8.0)
DEEPSEEK_PRICES = {"deepseek-flash": _FLASH, "deepseek-v4-flash": _FLASH, "deepseek-v4-flash-vision-exp": _FLASH,
                   "deepseek-v4-pro": (0.30, 9.0, 27.0)}
BEIJING = timezone(timedelta(hours=8))

PURPOSES = ("subtitles", "meanings", "examples", "article", "writing", "speaking", "interface", "other")

_running = dict.fromkeys(FIELDS, 0) | {"cost": 0.0}  # since the app started: an import's log shows the difference


def _peak(now: datetime) -> bool:
    """DeepSeek's peak hours: Beijing time, Monday to Friday, 9–12 and 14–18 (public holidays are off-peak, but
    not known here, so they count as peak and the estimate is a little high)."""
    t = now.astimezone(BEIJING)
    return t.weekday() < 5 and (9 <= t.hour < 12 or 14 <= t.hour < 18)


def _prices(settings):
    deepseek = settings.provider == "deepseek" or "deepseek.com" in (settings.base_url or "")
    return DEEPSEEK_PRICES.get((settings.model or "").lower()) if deepseek else None


def _counts(usage: dict) -> tuple[int, int, int, int]:
    """(input, cached input, output, reasoning) from an OpenAI-style or Responses-style usage object."""
    def number(*values):
        return next((int(v) for v in values if isinstance(v, (int, float))), 0)

    details_in = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    details_out = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
    prompt = number(usage.get("prompt_tokens"), usage.get("input_tokens"))
    cached = number(usage.get("prompt_cache_hit_tokens"), details_in.get("cached_tokens"))
    output = number(usage.get("completion_tokens"), usage.get("output_tokens"))
    reasoning = number(details_out.get("reasoning_tokens"))
    return prompt, min(cached, prompt), output, reasoning


def _load() -> dict:
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("days"), dict) else {"days": {}}
    except (OSError, ValueError):
        return {"days": {}}


def _add(row: dict, delta: dict) -> None:
    for field in FIELDS:
        row[field] = row.get(field, 0) + delta.get(field, 0)
    row["cost"] = round(row.get("cost", 0.0) + delta.get("cost", 0.0), 6)


def _save(delta: dict, purpose: str, now: datetime) -> None:
    with _lock:
        _add(_running, delta)
        data = _load()
        day = data["days"].setdefault(now.astimezone().strftime("%Y-%m-%d"), {})
        _add(day.setdefault(purpose if purpose in PURPOSES else "other", {}), delta)
        try:
            PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(PATH)
        except OSError:
            pass  # usage is a convenience: never fail a translation over it


def record(settings, purpose: str, usage, now: datetime | None = None) -> None:
    """Count one answered request."""
    now = now or datetime.now(timezone.utc)
    prompt, cached, output, reasoning = _counts(usage if isinstance(usage, dict) else {})
    delta = {"requests": 1, "input": prompt, "cached": cached, "output": output, "reasoning": reasoning}
    prices = _prices(settings)
    if prices and isinstance(usage, dict):
        hit, miss, out = prices
        cost = (cached * hit + (prompt - cached) * miss + output * out) / 1e6
        delta["cost"] = cost if _peak(now) else cost / 2
    else:
        delta["unpriced"] = 1
    _save(delta, purpose, now)


def record_timeout(settings, purpose: str, now: datetime | None = None) -> None:
    """A request that got no reply in time. The provider may still have billed it; its tokens are unknown."""
    _save({"requests": 1, "timeouts": 1, "unpriced": 1}, purpose, now or datetime.now(timezone.utc))


def snapshot() -> dict:
    with _lock:
        return dict(_running)


def since(before: dict) -> dict:
    now = snapshot()
    return {k: now[k] - before.get(k, 0) for k in now}


def yuan(cost: float) -> str:
    return f"约 ¥{cost:.2f}" if cost >= 0.01 else "不到 ¥0.01"


def describe(delta: dict) -> str:
    """One log line for an import: '' when no API request was made."""
    if not delta.get("requests"):
        return ""
    line = f"API 用量：{delta['requests']} 次请求 · 输入 {delta['input']:,} token · 输出 {delta['output']:,} token"
    if delta.get("reasoning"):
        line += f" · 其中思考 {delta['reasoning']:,} token"
    if delta.get("cost"):
        line += (" · " if not delta.get("unpriced") else " · 可估价部分") + yuan(delta["cost"])
    if delta.get("timeouts"):
        line += f" · {delta['timeouts']} 次超时（可能已计费）"
    return line


def summary(now: datetime | None = None) -> dict:
    """Today, this month and all time, plus this month by purpose, for Settings."""
    now = (now or datetime.now(timezone.utc)).astimezone()
    today, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
    with _lock:
        days = _load()["days"]
    totals = {name: dict.fromkeys(FIELDS, 0) | {"cost": 0.0} for name in ("today", "month", "all")}
    by_purpose: dict[str, dict] = {}
    for day, purposes in days.items():
        if not isinstance(purposes, dict):
            continue
        for purpose, row in purposes.items():
            if not isinstance(row, dict):
                continue
            _add(totals["all"], row)
            if day.startswith(month):
                _add(totals["month"], row)
                _add(by_purpose.setdefault(purpose, dict.fromkeys(FIELDS, 0) | {"cost": 0.0}), row)
            if day == today:
                _add(totals["today"], row)
    return {**totals, "byPurpose": by_purpose, "since": min(days) if days else ""}
