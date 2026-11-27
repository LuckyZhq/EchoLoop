"""Periodicals: two-stage lazy-loaded RSS/Atom news & magazine articles with local .webp image caching."""
from __future__ import annotations

import calendar
import hashlib
import json
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import trafilatura
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
from PIL import Image

from . import reading, usage
from .config import DATA_DIR

SOURCES: list[dict[str, Any]] = [
    {
        "id": "guardian_tech",
        "source_name": "The Guardian",
        "category": "科技与生活",
        "feed_url": "https://www.theguardian.com/uk/technology/rss",
        "strategy": "trafilatura",
    },
    {
        "id": "guardian_env",
        "source_name": "The Guardian",
        "category": "消费与环境",
        "feed_url": "https://www.theguardian.com/uk/environment/rss",
        "strategy": "trafilatura",
    },
    {
        "id": "guardian_biz",
        "source_name": "The Guardian",
        "category": "商业与职场",
        "feed_url": "https://www.theguardian.com/uk/business/rss",
        "strategy": "trafilatura",
    },
    {
        "id": "time",
        "source_name": "Time",
        "category": "社会与文化",
        "feed_url": "https://time.com/feed/",
        "strategy": "rss_prefer",
    },
    {
        "id": "conversation",
        "source_name": "The Conversation",
        "category": "深度与社评",
        "feed_url": "https://theconversation.com/global/articles.atom",
        "strategy": "rss_prefer",
        "clean_conversation": True,
    },
    {
        "id": "psychology_today",
        "source_name": "Psychology Today",
        "category": "心理与健康",
        "feed_url": "https://www.psychologytoday.com/us/front/feed",
        "strategy": "trafilatura",
        "clean_psychology_today": True,
    },
    {
        "id": "npr",
        "source_name": "NPR",
        "category": "国际与时政",
        "feed_url": "https://feeds.npr.org/1001/rss.xml",
        "strategy": "trafilatura",
        "skip_keywords": ["newsletter", "up-first", "podcast", "video"],
        "clean_npr": True,
    },
]

CATEGORY_ORDER = [
    "科技与生活",
    "消费与环境",
    "商业与职场",
    "社会与文化",
    "深度与社评",
    "心理与健康",
    "国际与时政",
]

DEFAULT_PER_SOURCE = 8
MAX_UNCACHED_PER_SOURCE = 30
SYNC_COOLDOWN_SEC = 15
PAGE_TIMEOUT = 15
IMAGE_TIMEOUT = 10
MAX_IMAGE_WIDTH = 1200
WEBP_QUALITY = 80
SAFE_IMG_NAME = re.compile(r"^[a-zA-Z0-9_-]+\.webp$")

NON_ARTICLE_PATTERNS = (
    "/video/",
    "/videos/",
    "/gallery/",
    "/galleries/",
    "/picture/",
    "/pictures/",
    "/audio/",
    "/podcast/",
    "/podcasts/",
    "/live/",
    "/av/",
    "/multimedia/",
    "/interactive/",
    "/slideshow/",
)

IMAGE_SKIP_KEYWORDS = (
    "icon",
    "logo",
    "avatar",
    "pixel",
    "tracker",
    "doubleclick",
    "beacon",
    "spacer",
    "1x1",
    "favicon",
    "badge",
    "sprite",
    "adservice",
)

NPR_FOOTER_PATTERNS = (
    re.compile(r"^This newsletter was edited by.*$", re.IGNORECASE),
    re.compile(r"^Copyright\s+\d{4}\s+NPR.*$", re.IGNORECASE),
    re.compile(r"^NPR thanks its sponsors.*$", re.IGNORECASE),
    re.compile(r"^Sponsor Message.*$", re.IGNORECASE),
    re.compile(r"^Subscribe to the .* newsletter.*$", re.IGNORECASE),
)

CONVERSATION_FOOTER_PATTERNS = (
    re.compile(r"\breceives funding from\b", re.IGNORECASE),
    re.compile(r"\bworks for,\s*consults,\s*shares ownership\b", re.IGNORECASE),
    re.compile(r"\bprovides funding as a member of The Conversation\b", re.IGNORECASE),
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_index_lock = threading.Lock()
_sync_lock = threading.Lock()
_fetch_locks_guard = threading.Lock()
_fetch_locks: dict[str, threading.Lock] = {}
_last_sync_at = 0.0
_sync_in_progress = False
_startup_started = False


def _index_path() -> Path:
    return reading.ARTICLES_DIR / "_periodicals.json"


def _images_root() -> Path:
    return DATA_DIR / "article_images"


def image_file_path(aid: str, filename: str) -> Path | None:
    if not reading.ARTICLE_ID.match(aid) or not SAFE_IMG_NAME.match(filename):
        return None
    p = _images_root() / aid / filename
    return p if p.is_file() else None


def _get_fetch_lock(aid: str) -> threading.Lock:
    with _fetch_locks_guard:
        if aid not in _fetch_locks:
            _fetch_locks[aid] = threading.Lock()
        return _fetch_locks[aid]


def _proxies() -> dict[str, str] | None:
    http_p = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https_p = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not http_p and not https_p:
        return None
    out: dict[str, str] = {}
    if http_p:
        out["http"] = http_p
    if https_p:
        out["https"] = https_p
    return out


def _cffi_get(url: str, timeout: int = PAGE_TIMEOUT, headers: dict[str, str] | None = None):
    return cffi_requests.get(
        url,
        headers=headers or HEADERS,
        proxies=_proxies(),
        timeout=timeout,
        impersonate="chrome",
        allow_redirects=True,
    )


def article_id_for_url(source_url: str) -> str:
    digest = hashlib.sha256(source_url.strip().encode("utf-8")).hexdigest()[:12]
    return f"a{digest}"


def _load_index() -> dict[str, dict[str, Any]]:
    path = _index_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except (OSError, ValueError):
        pass
    return {}


def _save_index(items: dict[str, dict[str, Any]]) -> None:
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def cleanup_legacy_graded() -> int:
    """Remove the 20 legacy built-in graded seed articles from ARTICLES_DIR without touching classics or custom."""
    if not reading.ARTICLES_DIR.is_dir():
        return 0
    removed = 0
    for d in list(reading.ARTICLES_DIR.iterdir()):
        if not d.is_dir() or not reading.ARTICLE_ID.match(d.name):
            continue
        f = d / "data.json"
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("graded") and not data.get("classicManaged") and data.get("section") != "classic":
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed


def _parse_published(entry: Any) -> tuple[str, int]:
    for attr in ("published_parsed", "updated_parsed"):
        st = getattr(entry, attr, None)
        if st:
            try:
                ts = int(calendar.timegm(st))
                return time.strftime("%Y-%m-%d", st), ts
            except (TypeError, ValueError, OverflowError):
                pass
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, "") or ""
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                return dt.strftime("%Y-%m-%d"), int(dt.timestamp())
            except (TypeError, ValueError):
                pass
    now = int(time.time())
    return time.strftime("%Y-%m-%d", time.localtime(now)), now


def _clean_summary(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    text = re.sub(r'\s+([.,;:!?\'"\)\]])', r"\1", text)
    if len(text) > 220:
        text = text[:217].rstrip() + "…"
    return text


def _is_valid_image_url(url: str, width_attr: str | None = None, height_attr: str | None = None) -> bool:
    if not url or url.startswith("data:"):
        return False
    lower = url.lower()
    if lower.endswith(".svg") or ".svg?" in lower:
        return False
    if any(kw in lower for kw in IMAGE_SKIP_KEYWORDS):
        return False
    for dim in (width_attr, height_attr):
        if dim and dim.isdigit() and int(dim) < 100:
            return False
    return True


def _extract_rss_cover(entry: Any) -> str:
    for mc in getattr(entry, "media_content", None) or []:
        url = (mc.get("url") or "").strip()
        mtype = (mc.get("type") or "").lower()
        medium = (mc.get("medium") or "").lower()
        if url and (not mtype or mtype.startswith("image/") or medium == "image"):
            if _is_valid_image_url(url):
                return url
    for mt in getattr(entry, "media_thumbnail", None) or []:
        url = (mt.get("url") or "").strip()
        if url and _is_valid_image_url(url):
            return url
    for enc in getattr(entry, "enclosures", None) or []:
        url = (enc.get("href") or enc.get("url") or "").strip()
        etype = (enc.get("type") or "").lower()
        if url and etype.startswith("image/") and _is_valid_image_url(url):
            return url
    return ""


def _get_rss_entry_html(entry: Any) -> str:
    content_list = getattr(entry, "content", None) or []
    best = ""
    for item in content_list:
        val = item.get("value", "") if isinstance(item, dict) else getattr(item, "value", "")
        if len(val) > len(best):
            best = val
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    if len(summary) > len(best):
        best = summary
    return best


def _is_non_article_entry(entry: Any, skip_keywords: list[str] | None = None) -> bool:
    link = (getattr(entry, "link", "") or "").lower()
    title = (getattr(entry, "title", "") or "").lower()
    path = urlparse(link).path.lower()
    if any(pat in path for pat in NON_ARTICLE_PATTERNS):
        return True
    if title.startswith("video:") or title.startswith("watch:") or "[video]" in title:
        return True
    if skip_keywords and any(kw in link or kw in title for kw in skip_keywords):
        return True
    return False


def _fetch_single_feed(source: dict[str, Any], limit: int) -> tuple[list[dict[str, Any]], str | None]:
    try:
        resp = _cffi_get(source["feed_url"], timeout=PAGE_TIMEOUT)
        if resp.status_code >= 400 or not resp.text:
            return [], f"{source['source_name']} ({source['category']}): HTTP {resp.status_code}"
        parsed = feedparser.parse(resp.text)
        entries = getattr(parsed, "entries", []) or []
    except Exception as exc:  # noqa: BLE001
        return [], f"{source['source_name']} ({source['category']}): {type(exc).__name__}"

    skip_kws = source.get("skip_keywords")
    results: list[dict[str, Any]] = []
    for entry in entries:
        link = (getattr(entry, "link", "") or "").strip()
        if not link or _is_non_article_entry(entry, skip_kws):
            continue
        title = re.sub(r"\s+", " ", (getattr(entry, "title", "") or "").strip())
        if not title:
            continue
        pub_date, pub_ts = _parse_published(entry)
        raw_summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        rss_html = _get_rss_entry_html(entry) if source.get("strategy") == "rss_prefer" else ""
        results.append({
            "id": article_id_for_url(link),
            "source_id": source["id"],
            "title": title,
            "source_name": source["source_name"],
            "category": source["category"],
            "source_url": link,
            "published_at": pub_date,
            "published_ts": pub_ts,
            "summary": _clean_summary(raw_summary),
            "cover_image_url": _extract_rss_cover(entry),
            "cover_image_local": None,
            "content_cached": False,
            "word_count": 0,
            "inline_images": [],
            "fetch_status": "meta_only",
            "last_error": "",
            "rss_content_html": rss_html,
        })
        if len(results) >= limit:
            break
    return results, None


def sync_feeds(per_source_limit: int = DEFAULT_PER_SOURCE, force: bool = False) -> dict[str, Any]:
    """Stage 1: fetch RSS/Atom metadata only (no article HTML or image downloads)."""
    global _last_sync_at, _sync_in_progress
    with _sync_lock:
        now = time.time()
        existing = _load_index()
        if not force and existing and (now - _last_sync_at) < SYNC_COOLDOWN_SEC:
            wait_sec = max(1, int(SYNC_COOLDOWN_SEC - (now - _last_sync_at)))
            return {"added": 0, "total": len(existing), "cooldown": True, "waitSec": wait_sec, "errors": []}

        _sync_in_progress = True
        try:
            cleanup_legacy_graded()
            fetched: list[dict[str, Any]] = []
            errors: list[str] = []
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(_fetch_single_feed, src, per_source_limit): src for src in SOURCES}
                for fut in as_completed(futures):
                    items, err = fut.result()
                    if err:
                        errors.append(err)
                    fetched.extend(items)

            added = 0
            with _index_lock:
                items = _load_index()
                seen_urls = {v.get("source_url") for v in items.values() if v.get("source_url")}
                for item in fetched:
                    if item["source_url"] in seen_urls or item["id"] in items:
                        continue
                    items[item["id"]] = item
                    seen_urls.add(item["source_url"])
                    added += 1
                items = _trim_uncached_per_source(items)
                _save_index(items)
                total = len(items)
            _last_sync_at = time.time()
            return {"added": added, "total": total, "cooldown": False, "errors": errors}
        finally:
            _sync_in_progress = False


def ensure_seeded_async() -> None:
    """On startup: remove legacy test articles and, if periodicals index is empty, sync feeds in background."""
    global _startup_started
    if _startup_started:
        return
    _startup_started = True
    cleanup_legacy_graded()
    if _load_index():
        return

    def _bg():
        try:
            sync_feeds(force=True)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_bg, daemon=True).start()


def _public_item(meta: dict[str, Any], saved_articles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    aid = meta["id"]
    saved = saved_articles.get(aid)
    cached = bool(meta.get("content_cached") and saved)
    return {
        "id": aid,
        "section": "periodical",
        "title": meta["title"],
        "sourceName": meta["source_name"],
        "category": meta["category"],
        "topic": meta["category"],
        "sourceUrl": meta["source_url"],
        "publishedAt": meta.get("published_at", ""),
        "publishedTs": meta.get("published_ts", 0),
        "summary": meta.get("summary", ""),
        "coverImageUrl": meta.get("cover_image_url") or "",
        "coverImageLocal": meta.get("cover_image_local") or "",
        "contentCached": cached,
        "wordCount": saved["wordCount"] if saved else (meta.get("word_count") or 0),
        "articleId": aid if cached else None,
        "readAt": saved.get("readAt", 0) if saved else 0,
        "fetchStatus": "cached" if cached else meta.get("fetch_status", "meta_only"),
    }


def overview() -> dict[str, Any]:
    items = _load_index()
    saved_map = {a["id"]: a for a in reading.list_articles(include_managed=False) if a.get("section") == "periodical"}
    periodicals = [_public_item(meta, saved_map) for meta in items.values()]
    periodicals.sort(key=lambda x: (-x.get("publishedTs", 0), x["title"]))
    present_cats = {p["category"] for p in periodicals if p.get("category")}
    categories = [c for c in CATEGORY_ORDER if c in present_cats]
    for c in sorted(present_cats):
        if c not in categories:
            categories.append(c)
    return {
        "categories": categories,
        "periodicals": periodicals,
        "total": len(periodicals),
        "syncing": _sync_in_progress,
    }


def get_meta(aid: str) -> dict[str, Any] | None:
    return _load_index().get(aid)


def uncached_stub(aid: str) -> dict[str, Any] | None:
    meta = get_meta(aid)
    if not meta:
        return None
    return {
        "id": aid,
        "title": meta["title"],
        "section": "periodical",
        "sourceName": meta["source_name"],
        "category": meta["category"],
        "sourceUrl": meta["source_url"],
        "publishedAt": meta.get("published_at", ""),
        "contentCached": False,
        "fetchStatus": meta.get("fetch_status", "meta_only"),
        "lastError": meta.get("last_error", ""),
    }


# ------------------------------------------------------------------ Stage 2: extraction, cleaning & image caching

def _fix_punctuation_spacing(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r'\s+([.,;:!?\'"\)\]])', r"\1", text)


def _count_words(paragraphs: list[str]) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*", " ".join(paragraphs)))


def _norm_url_key(url: str) -> str:
    p = urlparse(url)
    return f"{p.netloc.lower()}{p.path}"


def _extract_meta_cover_image(html: str, base_url: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for attr_name, attr_val in (("property", "og:image"), ("name", "twitter:image"), ("property", "twitter:image")):
        tag = soup.find("meta", attrs={attr_name: attr_val})
        if tag and tag.get("content"):
            url = urljoin(base_url, str(tag["content"]).strip())
            if _is_valid_image_url(url):
                return url
    return ""


def _parse_img_tag(img: Any, base_url: str) -> dict[str, str] | None:
    src = (img.get("src") or img.get("data-src") or "").strip()
    if not src and img.get("srcset"):
        src = str(img["srcset"]).split(",")[0].strip().split(" ")[0]
    if not src:
        return None
    src = urljoin(base_url, src)
    w = str(img.get("width") or "")
    h = str(img.get("height") or "")
    if not _is_valid_image_url(src, w, h):
        return None
    alt = re.sub(r"\s+", " ", (img.get("alt") or "").strip())
    caption = ""
    fig = img.find_parent("figure")
    if fig:
        fc = fig.find("figcaption")
        if fc:
            caption = _fix_punctuation_spacing(fc.get_text(" ", strip=True))
    return {"url": src, "alt": alt, "caption": caption}


def _extract_from_rss_html(rss_html: str, base_url: str) -> tuple[list[str], list[dict[str, Any]]]:
    if not rss_html:
        return [], []
    soup = BeautifulSoup(rss_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()
    paragraphs: list[str] = []
    inline_images: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for el in soup.find_all(["p", "h2", "h3", "blockquote", "li", "figure", "img"]):
        if el.name == "img":
            if el.find_parent("figure") or el.find_parent(["p", "h2", "h3", "blockquote", "li"]):
                continue
            parsed = _parse_img_tag(el, base_url)
            if parsed and parsed["url"] not in seen_urls and paragraphs:
                seen_urls.add(parsed["url"])
                inline_images.append({**parsed, "after_paragraph_index": len(paragraphs) - 1})
        elif el.name == "figure":
            img = el.find("img")
            if img:
                parsed = _parse_img_tag(img, base_url)
                if parsed and parsed["url"] not in seen_urls and paragraphs:
                    seen_urls.add(parsed["url"])
                    inline_images.append({**parsed, "after_paragraph_index": len(paragraphs) - 1})
        else:
            for img in el.find_all("img"):
                parsed = _parse_img_tag(img, base_url)
                if parsed and parsed["url"] not in seen_urls and paragraphs:
                    seen_urls.add(parsed["url"])
                    inline_images.append({**parsed, "after_paragraph_index": len(paragraphs) - 1})
            txt = _fix_punctuation_spacing(el.get_text(" ", strip=True))
            if txt and len(txt) > 1:
                paragraphs.append(txt)

    return paragraphs, inline_images


def _extract_inline_images_mapped(html: str, base_url: str, paragraphs: list[str]) -> list[dict[str, Any]]:
    if not html or not paragraphs:
        return []
    soup = BeautifulSoup(html, "html.parser")
    area = soup.find("article") or soup.find("main") or soup
    inline_images: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    para_idx = -1
    para_norms = [re.sub(r"\W+", "", p.lower())[:60] for p in paragraphs]

    for el in area.find_all(["p", "h2", "h3", "blockquote", "figure", "img"]):
        if el.name in ("p", "h2", "h3", "blockquote"):
            txt = re.sub(r"\W+", "", el.get_text(" ", strip=True).lower())[:60]
            if len(txt) >= 12:
                for idx in range(max(0, para_idx + 1), len(para_norms)):
                    if txt[:30] in para_norms[idx] or para_norms[idx][:30] in txt:
                        para_idx = idx
                        break
            for img in el.find_all("img"):
                parsed = _parse_img_tag(img, base_url)
                if parsed and parsed["url"] not in seen_urls and para_idx >= 0:
                    seen_urls.add(parsed["url"])
                    inline_images.append({**parsed, "after_paragraph_index": para_idx})
        elif el.name == "figure":
            img = el.find("img")
            if img:
                parsed = _parse_img_tag(img, base_url)
                if parsed and parsed["url"] not in seen_urls and para_idx >= 0:
                    seen_urls.add(parsed["url"])
                    inline_images.append({**parsed, "after_paragraph_index": para_idx})
        elif el.name == "img":
            if el.find_parent("figure") or el.find_parent(["p", "h2", "h3", "blockquote"]):
                continue
            parsed = _parse_img_tag(el, base_url)
            if parsed and parsed["url"] not in seen_urls and para_idx >= 0:
                seen_urls.add(parsed["url"])
                inline_images.append({**parsed, "after_paragraph_index": para_idx})
    return inline_images


def _trim_uncached_per_source(items: dict[str, dict[str, Any]], limit: int = MAX_UNCACHED_PER_SOURCE) -> dict[str, dict[str, Any]]:
    """Keep all cached articles and at most `limit` newest uncached items per source_id."""
    by_source: dict[str, list[dict[str, Any]]] = {}
    kept: dict[str, dict[str, Any]] = {}
    for aid, item in items.items():
        item.pop("content_paragraphs", None)
        if item.get("content_cached"):
            item["rss_content_html"] = ""
            kept[aid] = item
        else:
            by_source.setdefault(item.get("source_id") or "", []).append(item)
    for group in by_source.values():
        group.sort(key=lambda x: (-x.get("published_ts", 0), x.get("id", "")))
        for item in group[:limit]:
            kept[item["id"]] = item
    return kept


def _clean_paragraphs(paragraphs: list[str], title: str, source: dict[str, Any]) -> tuple[list[str], int]:
    cleaned = [_fix_punctuation_spacing(p) for p in paragraphs if p and p.strip()]
    title_norm = re.sub(r"\W+", "", title.lower())
    removed_head = 0

    # 1. Remove leading title duplication or short category tag (e.g. Psychology Today "Anxiety")
    for _ in range(2):
        if not cleaned:
            break
        first = cleaned[0]
        first_norm = re.sub(r"\W+", "", first.lower())
        is_title_dup = bool(title_norm) and (first_norm == title_norm or (len(first_norm) > 12 and (first_norm in title_norm or title_norm in first_norm)))
        is_short_tag = len(first.split()) <= 3 and not first.endswith((".", "!", "?", '"', "”", "'"))
        if is_title_dup or is_short_tag:
            cleaned.pop(0)
            removed_head += 1
        else:
            break

    # 2. Source-specific footer cleanup
    if source.get("clean_npr"):
        cleaned = [p for p in cleaned if not any(pat.match(p) for pat in NPR_FOOTER_PATTERNS)]

    if source.get("clean_conversation"):
        while cleaned and any(pat.search(cleaned[-1]) for pat in CONVERSATION_FOOTER_PATTERNS):
            cleaned.pop()

    if source.get("clean_psychology_today"):
        cutoff = max(1, int(len(cleaned) * 0.55))
        for idx in range(cutoff, len(cleaned)):
            if re.match(r"^References?:?$", cleaned[idx], re.IGNORECASE):
                cleaned = cleaned[:idx]
                break

    return [p for p in cleaned if p], removed_head


def _download_and_compress_webp(url: str, target_path: Path) -> bool:
    if not url:
        return False
    try:
        headers = {
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        resp = _cffi_get(url, timeout=IMAGE_TIMEOUT, headers=headers)
        if resp.status_code != 200 or not resp.content or len(resp.content) < 2048:
            return False
        ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        if ctype and not ctype.startswith("image/"):
            return False
        with Image.open(BytesIO(resp.content)) as img:
            w, h = img.size
            if w < 80 or h < 80:
                return False
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            if w > MAX_IMAGE_WIDTH:
                new_h = max(1, int(h * (MAX_IMAGE_WIDTH / w)))
                img = img.resize((MAX_IMAGE_WIDTH, new_h), Image.Resampling.LANCZOS)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = target_path.with_suffix(".tmp.webp")
            img.save(tmp, format="WEBP", quality=WEBP_QUALITY, method=4)
            tmp.replace(target_path)
            return True
    except Exception:  # noqa: BLE001
        return False


def fetch_and_cache_article(aid: str, dic, force: bool = False) -> dict[str, Any]:
    """Stage 2: on-demand fetch, clean, compress images to .webp, split/translate/annotate, and persist."""
    lock = _get_fetch_lock(aid)
    with lock:
        meta = get_meta(aid)
        if not meta:
            raise LookupError("未找到该外刊文章")

        if not force and meta.get("content_cached"):
            existing = reading.load_article(aid)
            if existing:
                return reading.ensure_article_annotation(existing, dic)

        source = next((s for s in SOURCES if s["id"] == meta.get("source_id")), {})
        url = meta["source_url"]
        cover_url = meta.get("cover_image_url") or ""
        paragraphs: list[str] = []
        inline_images: list[dict[str, Any]] = []
        web_html = ""

        try:
            used_web_body = False
            if source.get("strategy") == "rss_prefer" and meta.get("rss_content_html"):
                paragraphs, inline_images = _extract_from_rss_html(meta["rss_content_html"], url)

            need_web = (
                source.get("strategy") != "rss_prefer"
                or len(paragraphs) < 3
                or _count_words(paragraphs) < 200
                or not cover_url
            )

            if need_web:
                resp = _cffi_get(url, timeout=PAGE_TIMEOUT)
                if resp.status_code >= 400 or not resp.text:
                    if not paragraphs:
                        raise RuntimeError(f"获取原文失败 (HTTP {resp.status_code})")
                else:
                    web_html = resp.text
                    og_cover = _extract_meta_cover_image(web_html, url)
                    if og_cover:
                        cover_url = og_cover

                    if source.get("strategy") != "rss_prefer" or len(paragraphs) < 3 or _count_words(paragraphs) < 200:
                        raw_json = trafilatura.extract(
                            web_html,
                            url=url,
                            output_format="json",
                            with_metadata=True,
                            include_comments=False,
                            include_links=False,
                        )
                        extracted_text = ""
                        if raw_json:
                            try:
                                extracted_text = (json.loads(raw_json).get("text") or "").strip()
                            except json.JSONDecodeError:
                                pass
                        paragraphs = [p.strip() for p in re.split(r"\n+", extracted_text) if p.strip()]
                        used_web_body = True

            paragraphs, removed_head = _clean_paragraphs(paragraphs, meta["title"], source)
            word_count = _count_words(paragraphs)
            if len(paragraphs) < 3 or word_count < 100:
                raise RuntimeError("提取的正文内容过少，可能受到目标站点访问限制")

            if used_web_body:
                inline_images = _extract_inline_images_mapped(web_html, url, paragraphs)
            elif removed_head:
                inline_images = [
                    {**img, "after_paragraph_index": max(0, int(img.get("after_paragraph_index", 0)) - removed_head)}
                    for img in inline_images
                ]

            if not cover_url and inline_images:
                cover_url = inline_images[0]["url"]

            # Deduplicate inline images against cover_url and clamp paragraph index
            cover_key = _norm_url_key(cover_url) if cover_url else ""
            filtered_inline: list[dict[str, Any]] = []
            max_p = len(paragraphs) - 1
            for img in inline_images:
                if cover_key and _norm_url_key(img["url"]) == cover_key:
                    continue
                idx = min(max(0, int(img.get("after_paragraph_index", 0))), max_p)
                filtered_inline.append({**img, "after_paragraph_index": idx})

            # Download and compress cover + inline images concurrently to local .webp
            img_dir = _images_root() / aid
            cover_local = ""
            cached_inline: list[dict[str, Any]] = []
            inline_batch = filtered_inline[:8]
            with ThreadPoolExecutor(max_workers=4) as img_pool:
                cover_fut = (
                    img_pool.submit(_download_and_compress_webp, cover_url, img_dir / "cover.webp")
                    if cover_url
                    else None
                )
                inline_futs = [
                    (idx, img, f"img_{idx}.webp", img_pool.submit(_download_and_compress_webp, img["url"], img_dir / f"img_{idx}.webp"))
                    for idx, img in enumerate(inline_batch)
                ]
                if cover_fut and cover_fut.result():
                    cover_local = f"/api/periodicals/images/{aid}/cover.webp"
                for _, img, fname, fut in inline_futs:
                    if fut.result():
                        cached_inline.append({
                            "localUrl": f"/api/periodicals/images/{aid}/{fname}",
                            "alt": img.get("alt", ""),
                            "caption": img.get("caption", ""),
                            "afterParagraphIndex": img["after_paragraph_index"],
                        })

            # Split, translate, and annotate using existing reading pipeline
            from .annotate import ANNOTATION_VERSION, annotate_cues
            from . import meanings
            from .pipeline import learner_language
            from .settings import load_settings
            from .translate import translate_cues

            full_text = "\n\n".join(paragraphs)[:reading.MAX_CHARS]
            cues = reading.split_sentences(full_text)
            if not cues:
                raise RuntimeError("未能在正文中切分出有效英文句子")

            settings = load_settings()
            lang = learner_language()
            spent = usage.snapshot()
            translator = translate_cues(cues, lambda _p: None, settings=settings, log=lambda _m: None, lang=lang)
            annotate_cues(cues, dic, progress=lambda _p: None, lang=lang)
            meanings.fill_notes(cues, lang, settings, lambda _m: None)
            usage.since(spent)

            article_data = {
                "id": aid,
                "title": meta["title"],
                "created": int(time.time()),
                "translator": translator,
                "translatorModel": settings.model if translator != "local" else "",
                "annotation": ANNOTATION_VERSION,
                "lang": lang,
                "cues": cues,
                "section": "periodical",
                "sourceName": meta["source_name"],
                "category": meta["category"],
                "sourceUrl": url,
                "publishedAt": meta.get("published_at", ""),
                "coverImageLocal": cover_local,
                "inlineImages": cached_inline,
                "wordCount": word_count,
            }
            reading.save_article(article_data)

            with _index_lock:
                items = _load_index()
                if aid in items:
                    items[aid].pop("content_paragraphs", None)
                    items[aid].update({
                        "cover_image_url": cover_url,
                        "cover_image_local": cover_local or None,
                        "content_cached": True,
                        "word_count": word_count,
                        "inline_images": cached_inline,
                        "fetch_status": "cached",
                        "last_error": "",
                        "rss_content_html": "",
                    })
                    _save_index(items)

            return reading.ensure_article_annotation(article_data, dic)
        except Exception as exc:  # noqa: BLE001
            with _index_lock:
                items = _load_index()
                if aid in items:
                    items[aid].update({
                        "content_cached": False,
                        "fetch_status": "failed",
                        "last_error": str(exc),
                    })
                    _save_index(items)
            raise
