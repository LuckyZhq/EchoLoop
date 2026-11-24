"""Reading: paste an English article → sentences with key-point marks, word glosses and Chinese translation.

Articles live in ROOT/articles/<id>/data.json, apart from the video library. Each sentence is shaped like a
video cue ({"i", "p", "text", "zh", "marks", "notes", "gl", "seg"}) so annotation and translation are shared.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import traceback
import uuid

from .config import ARTICLES_DIR

MAX_CHARS = 40_000
ARTICLE_ID = re.compile(r"^a[0-9a-f]{12}$")


def new_id() -> str:
    return "a" + uuid.uuid4().hex[:12]


def split_sentences(text: str) -> list[dict]:
    """Paragraphs are separated by line breaks; spaCy splits each paragraph into sentences."""
    from .annotate import nlp

    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n|\r?\n", text)]
    paragraphs = [p for p in paragraphs if p]
    cues = []
    for p, doc in enumerate(nlp().pipe(paragraphs, batch_size=32)):
        for sent in doc.sents:
            s = sent.text.strip()
            if s:
                cues.append({"i": len(cues), "p": p, "text": s})
    return cues


def article_path(aid: str):
    return ARTICLES_DIR / aid / "data.json"


def load_article(aid: str) -> dict | None:
    if not ARTICLE_ID.match(aid):
        return None
    try:
        return json.loads(article_path(aid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_article(data: dict) -> None:
    f = article_path(data["id"])
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)


def delete_article(aid: str) -> bool:
    if not ARTICLE_ID.match(aid) or not (ARTICLES_DIR / aid).is_dir():
        return False
    shutil.rmtree(ARTICLES_DIR / aid)
    return True


def list_articles() -> list[dict]:
    items = []
    if not ARTICLES_DIR.exists():
        return items
    for d in ARTICLES_DIR.iterdir():
        data = load_article(d.name)
        if not data:
            continue
        cues = data.get("cues", [])
        items.append({
            "id": data["id"], "title": data.get("title") or "未命名文章", "created": data.get("created", 0),
            "sentenceCount": len(cues), "wordCount": sum(len(c["text"].split()) for c in cues),
            "preview": " ".join(c["text"] for c in cues[:2])[:160], "translator": data.get("translator"),
            "readAt": data.get("readAt", 0),
        })
    items.sort(key=lambda x: -x["created"])
    return items


def run_article_job(pipeline, job, text: str, title: str) -> None:
    """Runs on the pipeline's worker thread: split → translate → annotate → save."""
    from .annotate import ANNOTATION_VERSION, annotate_cues
    from .pipeline import friendly_error
    from .settings import load_settings
    from .translate import translate_cues

    def log(msg: str):
        msg = str(msg).strip()
        if msg:
            job.log.append(msg)

    with pipeline._run_lock:
        try:
            pipeline._set(job, "split")
            cues = split_sentences(text)
            if not cues:
                raise RuntimeError("没有找到英文句子。")
            job.title = title or (cues[0]["text"][:60] + ("…" if len(cues[0]["text"]) > 60 else ""))
            settings = load_settings()
            pipeline._set(job, "translate")
            log(f"使用{'API' if settings.engine == 'api' else '本地'}翻译 {len(cues)} 句…")
            translator = translate_cues(cues, lambda p: setattr(job, "percent", p), settings=settings, log=log)
            pipeline._set(job, "annotate")
            annotate_cues(cues, pipeline.dic, progress=lambda p: setattr(job, "percent", p))
            save_article({
                "id": job.video_id, "title": job.title, "created": int(time.time()), "translator": translator,
                "annotation": ANNOTATION_VERSION, "cues": cues,
            })
            pipeline._set(job, "done", 1.0)
            log("完成 ✓")
        except Exception as e:
            job.error = friendly_error(str(e))
            job.stage = "error"
            log(traceback.format_exc(limit=3))


def submit_article(pipeline, text: str, title: str):
    from .pipeline import Job

    job = Job(url="article")
    job.video_id = new_id()
    job.title = title or "新文章"
    with pipeline._jobs_lock:
        pipeline.jobs[job.id] = job
    threading.Thread(target=run_article_job, args=(pipeline, job, text, title), daemon=True).start()
    return job
