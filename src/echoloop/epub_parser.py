"""Parse EPUB files without accessing the library, dictionary, or translation services."""
from __future__ import annotations

import logging
import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

log = logging.getLogger(__name__)
BLOCKS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote", "li", "div"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
IGNORED = {"script", "style"}
NON_BODY = re.compile(r"\b(?:cover|title[\s_-]*page|table[\s_-]*of[\s_-]*contents|contents|toc|nav|"
                      r"copyright|colophon|acknowledg(?:e)?ments)\b", re.I)
NON_BODY_TITLE = re.compile(r"^\s*(?:cover(?:\s+page)?|title\s*page|table\s+of\s+contents|contents|"
                            r"copyright|colophon|acknowledg(?:e)?ments)\s*[:.\-]*\s*$", re.I)
CHAPTER = re.compile(r"^(?:chapter|book|part|letter|prologue|epilogue)\b", re.I)
WORDS = re.compile(r"\b[A-Za-z]+(?:['’][A-Za-z]+)*\b")
ABBREVIATION = re.compile(
    r"(?i)(?:\b(?:mr|mrs|ms|miss|dr|prof|st|sr|jr|rev|gen|col|capt|lt|hon|vs|etc|no|vol|ch)\."
    r"|\b(?:e\.g|i\.e|a\.m|p\.m)\.|(?:\b[a-z]\.){2,})$"
)
SENTENCE_END = re.compile(r"""(?:[.!?]+|…+)[\"”'’)\]]*""")
START = re.compile(r"\*{3}\s*START OF (?:THE |THIS )?PROJECT GUTENBERG", re.I)
END = re.compile(r"\*{3}\s*END OF (?:THE |THIS )?PROJECT GUTENBERG", re.I)


class EncryptedContentError(ValueError):
    """A spine document cannot be decoded as readable UTF-8 XHTML."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _path(base: str, href: str) -> tuple[str, str]:
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        return "", ""
    path = posixpath.join(posixpath.dirname(base), unquote(parts.path)) if parts.path else base
    return posixpath.normpath(path), unquote(parts.fragment)


class _Node:
    def __init__(self, tag="", attrs=()):
        self.tag = tag.lower()
        self.attrs = dict(attrs)
        self.children = []


class _HTML(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.stack = [self.root]
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag.lower() not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
                               "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, attrs))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag.lower():
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _nodes(node):
    yield node
    for child in node.children:
        if isinstance(child, _Node):
            yield from _nodes(child)


def _text(node):
    if node.tag in IGNORED:
        return ""
    if node.tag == "br":
        return " "
    value = "".join(_text(child) if isinstance(child, _Node) else child for child in node.children)
    if node.tag == "sup" and re.fullmatch(r"\s*\[?\d+\]?\s*", value):
        return ""
    return value


def _clean(text):
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    if not text or re.fullmatch(r"\d+|[\s*_\-—–·•~]+", text):
        return ""
    return text


def _blocks(text):
    tree = _HTML(text).root
    body = next((node for node in _nodes(tree) if node.tag == "body"), tree)
    blocks, anchors, pending = [], {}, []

    def visit(node):
        if node.tag in IGNORED:
            return
        identifier = node.attrs.get("id") or node.attrs.get("name")
        if identifier:
            pending.append(identifier)
        nested = any(child.tag in BLOCKS for child in _nodes(node) if child is not node)
        if node.tag in BLOCKS and not nested:
            value = _clean(_text(node))
            if value:
                for child in _nodes(node):
                    if child is not node:
                        identifier = child.attrs.get("id") or child.attrs.get("name")
                        if identifier:
                            pending.append(identifier)
                for identifier in pending:
                    anchors.setdefault(identifier, len(blocks))
                pending.clear()
                blocks.append({"text": value, "tag": node.tag})
            else:
                for child in _nodes(node):
                    if child is not node:
                        identifier = child.attrs.get("id") or child.attrs.get("name")
                        if identifier:
                            pending.append(identifier)
            return
        for child in node.children:
            if isinstance(child, _Node):
                visit(child)

    visit(body)
    return blocks, anchors


def split_sentences(text: str) -> list[str]:
    text = _clean(text)
    if not text:
        return []
    result, start = [], 0
    for match in SENTENCE_END.finditer(text):
        end = match.end()
        if end < len(text) and not text[end].isspace():
            continue
        fragment = text[start:end].strip()
        bare = re.sub(r"""[\"”'’)\]]+$""", "", fragment)
        if bare.endswith(".") and ABBREVIATION.search(bare):
            continue
        if (bare.endswith("...") or bare.endswith("…")) and text[end:].lstrip()[:1].islower():
            continue
        if fragment:
            result.append(fragment)
        start = end
    tail = text[start:].strip()
    if tail:
        result.append(tail)
    return result


def _read_xhtml(archive, path):
    try:
        raw = archive.read(path)
    except KeyError:
        log.warning("EPUB document missing: %s", path)
        return None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise EncryptedContentError(f"EPUB content is not UTF-8: {path}") from error
    bad = sum(ord(char) < 32 and char not in "\n\r\t" for char in text)
    if "\x00" in text or (text and bad / len(text) > 0.02):
        raise EncryptedContentError(f"EPUB content is binary: {path}")
    return text


def _toc(archive, manifest):
    nav = next((item for item in manifest if "nav" in item["properties"].split()), None)
    if not nav:
        nav = next((item for item in manifest
                    if posixpath.basename(item["path"]).lower() in ("toc.xhtml", "nav.xhtml")), None)
    if nav:
        try:
            text = archive.read(nav["path"]).decode("utf-8-sig")
            tree = _HTML(text).root
            element = next((node for node in _nodes(tree) if node.tag == "nav" and
                            "toc" in (node.attrs.get("epub:type") or node.attrs.get("role") or "").split()), None)
            if element:
                entries = []
                for node in _nodes(element):
                    if node.tag == "a" and node.attrs.get("href"):
                        path, anchor = _path(nav["path"], node.attrs["href"])
                        title = _clean(_text(node))
                        if title and path and not NON_BODY_TITLE.match(title):
                            entries.append({"title": title, "href_path": path, "anchor_id": anchor})
                if entries:
                    return entries
        except (KeyError, UnicodeError, ValueError) as error:
            log.warning("Cannot read EPUB navigation: %s", error)
    ncx = next((item for item in manifest if item["media"] == "application/x-dtbncx+xml"
                or item["path"].lower().endswith(".ncx")), None)
    if not ncx:
        return []
    try:
        root = ElementTree.fromstring(archive.read(ncx["path"]))
        entries = []
        for point in root.iter():
            if _local(point.tag) != "navpoint":
                continue
            label = next((child for child in point if _local(child.tag) == "navlabel"), None)
            content = next((child for child in point if _local(child.tag) == "content"), None)
            title = _clean("".join(label.itertext())) if label is not None else ""
            if title and content is not None and content.get("src") and not NON_BODY_TITLE.match(title):
                path, anchor = _path(ncx["path"], content.get("src"))
                if path:
                    entries.append({"title": title, "href_path": path, "anchor_id": anchor})
        return entries
    except (KeyError, ElementTree.ParseError, UnicodeError) as error:
        log.warning("Cannot read EPUB NCX: %s", error)
        return []


def _cover(archive, manifest, cover_id):
    images = [item for item in manifest if item["path"].lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    candidates = ([item for item in images if "cover-image" in item["properties"].split()] +
                  [item for item in images if item["id"] == cover_id] +
                  [item for item in images if "cover" in (item["id"] + item["path"]).lower()])
    for page in manifest:
        if posixpath.basename(page["path"]).lower() not in ("cover.xhtml", "cover.html"):
            continue
        try:
            tree = _HTML(archive.read(page["path"]).decode("utf-8-sig")).root
            image = next((node for node in _nodes(tree) if node.tag in ("img", "image")), None)
            if image:
                href = image.attrs.get("src") or image.attrs.get("href") or image.attrs.get("xlink:href")
                if href:
                    path, _ = _path(page["path"], href)
                    candidates.extend(item for item in images if item["path"] == path)
                    if path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        candidates.append({"path": path})
        except (KeyError, UnicodeError, ValueError) as error:
            log.warning("Cannot read EPUB cover page: %s", error)
    for item in candidates:
        try:
            return {"data": archive.read(item["path"]), "extension": posixpath.splitext(item["path"])[1].lower()}
        except KeyError:
            log.warning("EPUB cover missing: %s", item["path"])
    return None


def _chapter(title, blocks):
    paragraphs = [block["text"] for block in blocks]
    normalized = lambda text: re.sub(r"\W+", "", text, flags=re.UNICODE).casefold()
    target = normalized(title)
    for index in reversed(range(min(2, len(paragraphs)))):
        value = normalized(paragraphs[index])
        if value and target and (
            value == target
            or (len(paragraphs[index]) < 80 and (target.startswith(value) or value.startswith(target)))
        ):
            paragraphs.pop(index)
    sentences = [{"p": index, "text": sentence} for index, paragraph in enumerate(paragraphs)
                 for sentence in split_sentences(paragraph)]
    return {"title": title, "paragraphs": paragraphs, "sentences": sentences,
            "word_count": sum(len(WORDS.findall(paragraph)) for paragraph in paragraphs)}


def parse_epub(source):
    """Return metadata, cover bytes, and ordered chapter paragraphs and sentences."""
    filename = Path(source).stem if isinstance(source, (str, Path)) else "Untitled"
    with zipfile.ZipFile(source) as archive:
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        rootfile = next((node.get("full-path") for node in container.iter()
                         if _local(node.tag) == "rootfile" and node.get("full-path")), None)
        if not rootfile:
            raise ValueError("EPUB container has no rootfile")
        opf = posixpath.normpath(unquote(rootfile))
        root = ElementTree.fromstring(archive.read(opf))
        metadata = next((node for node in root.iter() if _local(node.tag) == "metadata"), None)
        values = {}
        if metadata is not None:
            for node in metadata:
                name = _local(node.tag)
                if name in ("title", "creator", "language", "description"):
                    value = _clean("".join(node.itertext()))
                    if value:
                        values.setdefault(name, []).append(value)
        cover_id = next((node.get("content") for node in (metadata if metadata is not None else [])
                         if _local(node.tag) == "meta" and node.get("name", "").lower() == "cover"), "")
        manifest_node = next((node for node in root.iter() if _local(node.tag) == "manifest"), None)
        manifest = []
        for node in (manifest_node if manifest_node is not None else []):
            if _local(node.tag) == "item" and node.get("href"):
                path, _ = _path(opf, node.get("href"))
                manifest.append({"id": node.get("id", ""), "path": path, "media": node.get("media-type", ""),
                                 "properties": node.get("properties", "")})
        by_id = {item["id"]: item for item in manifest}
        spine_node = next((node for node in root.iter() if _local(node.tag) == "spine"), None)
        spine = [by_id[node.get("idref")] for node in (spine_node if spine_node is not None else [])
                 if node.get("idref") in by_id and node.get("linear", "yes") != "no"]
        toc = _toc(archive, manifest)
        book_title = (values.get("title") or [filename])[0]
        if any(CHAPTER.match(entry["title"]) for entry in toc):
            toc = [entry for entry in toc if entry["title"].casefold() != book_title.casefold()]
        cover = _cover(archive, manifest, cover_id)
        files = [item for item in spine if (item["media"] in ("application/xhtml+xml", "text/html")
                 or item["path"].lower().endswith((".xhtml", ".html", ".htm")))
                 and "nav" not in item["properties"].split()
                 and not NON_BODY.search(posixpath.basename(item["path"]))]
        docs = []
        for item in files:
            text = _read_xhtml(archive, item["path"])
            if text is not None:
                try:
                    blocks, anchors = _blocks(text)
                    if blocks:
                        docs.append((item["path"], blocks, anchors))
                    else:
                        log.warning("Skipping empty EPUB document: %s", item["path"])
                except (ValueError, RecursionError) as error:
                    log.warning("Skipping malformed EPUB document %s: %s", item["path"], error)
        all_blocks = [block for _, blocks, _ in docs for block in blocks]
        start = next((index for index, block in enumerate(all_blocks) if START.search(block["text"])), None)
        end = next((index for index, block in enumerate(all_blocks) if END.search(block["text"])), None)
        lower = start + 1 if start is not None else 0
        upper = end if end is not None else len(all_blocks)
        chapters, offset = [], 0
        anchor_mode = any(len({entry["anchor_id"] for entry in toc if entry["href_path"] == path
                               and entry["anchor_id"]}) >= 2 for path, _, _ in docs)
        for path, blocks, anchors in docs:
            entries = [entry for entry in toc if entry["href_path"] == path]
            starts_by_index = {}
            if anchor_mode:
                for entry in entries:
                    if entry["anchor_id"] in anchors:
                        starts_by_index.setdefault(anchors[entry["anchor_id"]], entry["title"])
            starts = sorted(starts_by_index.items())
            if starts:
                spans = [(index, starts[pos + 1][0] if pos + 1 < len(starts) else len(blocks), title)
                         for pos, (index, title) in enumerate(starts)]
            elif len(docs) >= 2:
                title = next((entry["title"] for entry in entries), None)
                title = title or next((block["text"] for block in blocks if block["tag"] in HEADINGS), None)
                spans = [(0, len(blocks), title or f"Chapter {len(chapters) + 1}")]
            else:
                headings = [(index, block["text"]) for index, block in enumerate(blocks)
                            if (len(block["text"]) < 80 and CHAPTER.match(block["text"]))
                            or block["tag"] in ("h1", "h2")]
                spans = [(index, headings[pos + 1][0] if pos + 1 < len(headings) else len(blocks), title)
                         for pos, (index, title) in enumerate(headings)]
                if not spans:
                    spans = [(0, len(blocks), f"Chapter {len(chapters) + 1}")]
            for first, last, title in spans:
                selected = [block for index, block in enumerate(blocks[first:last], first)
                            if lower <= offset + index < upper]
                chapter = _chapter(title, selected)
                if chapter["sentences"]:
                    chapters.append(chapter)
                else:
                    log.warning("Skipping empty EPUB chapter: %s", title)
            offset += len(blocks)
        return {"title": book_title,
                "author": ", ".join(values.get("creator") or ["Unknown"]),
                "language": (values.get("language") or ["en"])[0].lower().replace("_", "-").split("-")[0],
                "description": (values.get("description") or [""])[0],
                "cover": cover, "chapters": chapters, "total_chapters": len(chapters),
                "total_words": sum(chapter["word_count"] for chapter in chapters)}
