"""Import job: link → video + English cues → Chinese translation → key-point marks → data.json."""
from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from .config import LIBRARY_DIR
from .settings import load_settings


def learner_language() -> str:
    """The stored language new translations are made in (Traditional Chinese is stored as Simplified)."""
    from . import i18n, languages

    return languages.stored(i18n.load()["native"])

STAGES = [
    ("probe", "读取视频信息"),
    ("download", "下载视频"),
    ("transcribe", "获取英文字幕"),
    ("translate", "翻译字幕"),
    ("annotate", "标注重点"),
    ("done", "完成"),
]
STAGE_LABEL = {**dict(STAGES), "queued": "排队中", "error": "处理失败", "split": "拆分句子", "compress": "压缩视频"}


@dataclass
class Job:
    url: str
    quality: str = "720"
    overwrite: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    stage: str = "queued"
    percent: float = 0.0
    log: list[str] = field(default_factory=list)
    video_id: str | None = None
    title: str | None = None
    error: str | None = None
    exists: bool = False
    result: dict | None = None  # e.g. {"before": bytes, "after": bytes} for a shrink job

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "stage": self.stage,
            "stageLabel": STAGE_LABEL.get(self.stage, "排队中"),
            "stageIndex": next((i for i, (k, _) in enumerate(STAGES) if k == self.stage), -1),
            "stageCount": len(STAGES),
            "percent": round(self.percent * 100, 1),
            "log": self.log[-30:],
            "videoId": self.video_id,
            "title": self.title,
            "error": self.error,
            "exists": self.exists,
            "result": self.result,
        }


class Pipeline:
    def __init__(self, dictionary):
        self.dic = dictionary
        self.jobs: dict[str, Job] = {}
        self._jobs_lock = threading.Lock()
        self._run_lock = threading.Lock()  # one heavy job at a time

    def submit(self, url: str, quality: str = "720", overwrite: bool = False) -> Job:
        url = url.strip()
        with self._jobs_lock:
            for job in self.jobs.values():
                if job.stage not in ("done", "error") and (job.url, job.quality, job.overwrite) == (url, quality, overwrite):
                    return job
            job = Job(url=url, quality=quality, overwrite=overwrite)
            self.jobs[job.id] = job
            threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def retranslate(self, vid: str) -> Job:
        """Translate an existing video again with the current settings (no download / transcription)."""
        key = f"retranslate:{vid}"
        with self._jobs_lock:
            for job in self.jobs.values():
                if job.url == key and job.stage not in ("done", "error"):
                    return job
            job = Job(url=key)
            job.video_id = vid
            self.jobs[job.id] = job
            threading.Thread(target=self._retranslate, args=(job,), daemon=True).start()
        return job

    def _retranslate(self, job: Job):
        from . import meanings
        from .annotate import ANNOTATION_VERSION, annotate_cues
        from .translate import translate_cues

        def log(msg: str):
            msg = str(msg).strip()
            if msg:
                job.log.append(msg)

        with self._run_lock:
            try:
                f = LIBRARY_DIR / job.video_id / "data.json"
                data = json.loads(f.read_text(encoding="utf-8"))
                job.title = data.get("title") or job.video_id
                settings = load_settings()
                lang = learner_language()
                cues = data["cues"]
                if data.get("lang", "zh-CN") != lang:  # meanings and glosses follow the language too
                    self._set(job, "annotate")
                    annotate_cues(cues, self.dic, lambda p: setattr(job, "percent", p), lang=lang)
                    data["annotation"] = ANNOTATION_VERSION
                self._set(job, "translate")
                engine = "API" if settings.engine == "api" else "本地"
                log(f"使用{engine}翻译 {len(cues)} 句字幕…")
                data["translator"] = translate_cues(cues, lambda p: setattr(job, "percent", p), settings=settings,
                                                    log=log, lang=lang)
                data["translatorModel"] = settings.model if data["translator"] in ("api", "api+local") else ""
                meanings.fill_notes(cues, lang, settings, log)
                data["lang"] = lang
                tmp = f.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                tmp.replace(f)
                self._set(job, "done", 1.0)
                log("完成 ✓")
            except Exception as e:
                job.error = friendly_error(str(e))
                job.stage = "error"
                log(traceback.format_exc(limit=3))

    def shrink(self, vid: str, mode: str) -> Job:
        """Make a video smaller (720p / 480p / audio only). Runs like an import: one heavy job at a time."""
        key = f"shrink:{vid}"
        with self._jobs_lock:
            for job in self.jobs.values():
                if job.url == key and job.stage not in ("done", "error"):
                    return job
            job = Job(url=key, quality=mode)
            job.video_id = vid
            self.jobs[job.id] = job
            threading.Thread(target=self._shrink, args=(job,), daemon=True).start()
        return job

    def _shrink(self, job: Job):
        from .storage import shrink

        with self._run_lock:
            try:
                self._set(job, "compress")
                result = shrink(LIBRARY_DIR / job.video_id, job.quality,
                                progress=lambda p: setattr(job, "percent", p), log=job.log.append)
                job.result = result
                self._set(job, "done", 1.0)
            except Exception as e:
                job.error = str(e)
                job.stage = "error"

    def _set(self, job: Job, stage: str, pct: float = 0.0):
        job.stage, job.percent = stage, pct

    def _run(self, job: Job):
        from . import meanings, media
        from .annotate import ANNOTATION_VERSION, annotate_cues
        from .translate import translate_cues

        def log(msg: str):
            msg = str(msg).strip()
            if msg:
                job.log.append(msg)

        with self._run_lock, ExitStack() as stack:
            try:
                self._set(job, "probe")
                info = media.probe(job.url, log)
                vid = media.video_key(info)
                job.video_id, job.title = vid, info.get("title") or vid
                vdir = LIBRARY_DIR / vid
                if (vdir / "data.json").exists() and not job.overwrite:
                    job.exists = True
                    self._set(job, "done", 1.0)
                    log("这个视频已经在资料库里了，直接打开")
                    return
                settings = load_settings()
                LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
                staging = Path(stack.enter_context(TemporaryDirectory(prefix=".import-", dir=LIBRARY_DIR)))
                staged_video = staging / "ready"

                self._set(job, "download")
                video, sub = media.download(job.url, staged_video, job.quality, log, lambda p: setattr(job, "percent", p))

                self._set(job, "transcribe")
                cues, source = media.get_cues(video, sub, log, lambda p: setattr(job, "percent", p))
                if not cues:
                    raise RuntimeError("没有识别到英文语音或字幕")

                self._set(job, "translate")
                engine = "API" if settings.engine == "api" else "本地"
                log(f"使用{engine}翻译 {len(cues)} 句字幕…")
                lang = learner_language()
                translator = translate_cues(cues, lambda p: setattr(job, "percent", p), settings=settings, log=log,
                                            lang=lang)

                self._set(job, "annotate")
                annotate_cues(cues, self.dic, progress=lambda p: setattr(job, "percent", p), lang=lang)
                meanings.fill_notes(cues, lang, settings, log)

                for i, c in enumerate(cues):
                    c["i"] = i
                    c["start"], c["end"] = round(c["start"], 3), round(c["end"], 3)
                data = {
                    "id": vid,
                    "title": job.title,
                    "url": info.get("webpage_url") or job.url,
                    "uploader": info.get("uploader") or info.get("channel") or "",
                    "duration": info.get("duration") or (cues[-1]["end"] if cues else 0),
                    "thumbnail": info.get("thumbnail") or "",
                    "video": video.name,
                    "subtitleSource": source,
                    "translator": translator,
                    "translatorModel": settings.model if translator != "local" else "",  # which API model
                    "annotation": ANNOTATION_VERSION,
                    "lang": lang,  # the language the translations and meanings are in
                    "created": int(time.time()),
                    "cues": cues,
                }
                media.save_thumbnail(data["thumbnail"], staged_video)  # so the library shows covers offline
                (staged_video / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                previous = staging / "previous"
                if vdir.exists():
                    vdir.rename(previous)
                try:
                    staged_video.rename(vdir)
                except OSError:
                    if previous.exists():
                        previous.rename(vdir)
                    raise
                self._set(job, "done", 1.0)
                log("完成 ✓")
            except Exception as e:  # surface any failure to the UI
                job.error = friendly_error(str(e))
                job.stage = "error"
                log(traceback.format_exc(limit=3))


_reannotate_lock = threading.Lock()


def ensure_annotation(vdir: Path, data: dict, dic) -> dict:
    """Re-run key-point marking for videos imported before the current annotation format."""
    from .annotate import ANNOTATION_VERSION, annotate_cues

    if data.get("annotation") == ANNOTATION_VERSION:
        return data
    with _reannotate_lock:
        f = vdir / "data.json"
        data = json.loads(f.read_text(encoding="utf-8"))  # another request may have upgraded it already
        if data.get("annotation") != ANNOTATION_VERSION:
            annotate_cues(data["cues"], dic, lang=data.get("lang", "zh-CN"))
            data["annotation"] = ANNOTATION_VERSION
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(f)
    return data


def friendly_error(msg: str) -> str:
    low = msg.lower()
    hints = [
        ("sign in to confirm", "YouTube 要求登录验证（疑似被识别为机器人）。稍后重试，或换一个网络。"),
        ("private video", "这是私人视频，无法下载。"),
        ("unsupported url", "不支持这个链接，请确认是视频页面的地址。"),
        ("requested format is not available", "视频源没有提供符合当前清晰度上限的格式。可以提高上限或选择「最高可用」后重试。"),
        ("http error 403", "下载被拒绝（403）。可以稍后再试，或先更新 yt-dlp：uv lock --upgrade-package yt-dlp。"),
        ("unable to download", "网络连接失败，请检查网络或代理。"),
        ("huggingface", "Whisper 模型下载中断。再点一次「开始」会从断点继续下载。"),
        ("timed out", "网络超时，请检查网络或代理。再试一次通常就好。"),
    ]
    for key, hint in hints:
        if key in low:
            return f"{hint}\n\n原始错误：{msg}"
    return msg


_thumb_fetching: set[str] = set()


def _thumbnail_url(vdir: Path, data: dict) -> str:
    """The local copy of the cover when there is one. Videos imported before covers were saved locally
    fetch theirs once in the background; until then the remote address is used."""
    from .media import local_thumbnail, save_thumbnail

    local = local_thumbnail(vdir)
    if local:
        return f"/media/{vdir.name}/{local.name}"
    remote = data.get("thumbnail") or ""
    if remote and vdir.name not in _thumb_fetching:
        _thumb_fetching.add(vdir.name)
        threading.Thread(target=save_thumbnail, args=(remote, vdir), daemon=True).start()
    return remote


def _file_size(f: Path) -> int:
    try:
        return f.stat().st_size if f.is_file() else 0
    except OSError:
        return 0


def list_library() -> list[dict]:
    items = []
    if not LIBRARY_DIR.exists():
        return items
    for d in LIBRARY_DIR.iterdir():
        f = d / "data.json"
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        cues = data.get("cues", [])
        items.append(
            {
                "id": data["id"],
                "title": data.get("title"),
                "uploader": data.get("uploader"),
                "duration": data.get("duration"),
                "thumbnail": _thumbnail_url(d, data),
                "created": data.get("created", 0),
                "cueCount": len(cues),
                "phraseCount": sum(1 for c in cues if any(m["type"] == "phrase" for m in c.get("marks", []))),
                "subtitleSource": data.get("subtitleSource"),
                # videos imported before this field existed were all translated locally
                "translator": data.get("translator") or "local",
                "translatorModel": data.get("translatorModel") or "",
                "lang": data.get("lang", "zh-CN"),
                "aligned": any(c.get("seg") for c in cues),
                "bytes": _file_size(d / (data.get("video") or "")),
            }
        )
    items.sort(key=lambda x: -x["created"])
    return items
