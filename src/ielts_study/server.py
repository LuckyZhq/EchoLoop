"""Tiny local web server: paste-link page, library, player, dictionary lookup, vocab book."""
from __future__ import annotations

import errno
import json
import mimetypes
import re
import shutil
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

from .config import HOST, LIBRARY_DIR, PORT, STATIC_DIR
from .dictionary import Dictionary
from .pipeline import Pipeline, ensure_annotation, list_library
from . import reading
from .settings import load_settings, save_settings, settings_from

VOCAB_PATH = LIBRARY_DIR / "vocab.json"
_vocab_lock = threading.Lock()
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
SETTINGS_PATHS = {"/settings", "/settings/appearance", "/settings/download",
                  "/settings/playback", "/settings/study", "/settings/translation"}


def load_vocab() -> list[dict]:
    try:
        return json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_vocab(items: list[dict]) -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    tmp = VOCAB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(VOCAB_PATH)


_dictation_lock = threading.Lock()


def load_dictation(vid: str) -> dict:
    try:
        data = json.loads((LIBRARY_DIR / vid / "dictation.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_json(path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


RECENT_PATH = LIBRARY_DIR / "recent.json"
_recent_lock = threading.Lock()
DICT_PASS = 0.9  # same threshold as the player's "练错句"


def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_recent() -> list[dict]:
    items = _read_json(RECENT_PATH, [])
    return items if isinstance(items, list) else []


def touch_recent(vid: str, t: float) -> None:
    with _recent_lock:
        items = [r for r in load_recent() if r.get("videoId") != vid]
        items.insert(0, {"videoId": vid, "time": round(max(0.0, t), 1), "at": int(time.time())})
        save_json(RECENT_PATH, items[:10])


def list_mistakes() -> list[dict]:
    """Every dictated sentence whose latest score is below the pass mark, across the library."""
    out = []
    if not LIBRARY_DIR.exists():
        return out
    for d in LIBRARY_DIR.iterdir():
        records = _read_json(d / "dictation.json", {})
        wrong = {i: r for i, r in records.items() if isinstance(r, dict) and r.get("score", 1) < DICT_PASS}
        if not wrong:
            continue
        data = _read_json(d / "data.json", None)
        if not data:
            continue
        cues = data.get("cues", [])
        for i, r in wrong.items():
            if not i.isdigit() or int(i) >= len(cues):
                continue
            c = cues[int(i)]
            out.append({
                "videoId": d.name, "title": data.get("title") or d.name, "i": int(i),
                "text": c["text"], "zh": c.get("zh", ""), "start": c["start"],
                "score": r.get("score", 0), "best": r.get("best", 0), "tries": r.get("tries", 1),
                "typed": r.get("typed", ""), "at": r.get("at", 0),
            })
    out.sort(key=lambda m: -m["at"])
    return out


def sidebar() -> dict:
    recent = []
    for r in load_recent():
        vid = r.get("videoId", "")
        data = _read_json(LIBRARY_DIR / vid / "data.json", None) if SAFE_ID.match(vid) else None
        if not data:
            continue  # deleted video
        records = _read_json(LIBRARY_DIR / vid / "dictation.json", {})
        recent.append({
            "id": vid, "title": data.get("title") or vid, "time": r.get("time", 0),
            "duration": data.get("duration") or 0, "cueCount": len(data.get("cues", [])), "dictated": len(records),
        })
        if len(recent) == 3:
            break
    return {"mistakes": len(list_mistakes()), "recent": recent}


def home_stats() -> dict:
    """Numbers for the home page: what is in each section and what was practised today."""
    today = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
    dictated = dictated_today = 0
    if LIBRARY_DIR.exists():
        for d in LIBRARY_DIR.iterdir():
            records = _read_json(d / "dictation.json", {})
            if isinstance(records, dict):
                dictated += len(records)
                dictated_today += sum(1 for r in records.values() if isinstance(r, dict) and r.get("at", 0) >= today)
    vocab = load_vocab()
    articles = reading.list_articles()
    info = sidebar()
    return {
        "videos": len(list_library()), "articles": len(articles), "latestArticle": articles[0] if articles else None,
        "words": sum(1 for v in vocab if v.get("type") != "phrase"), "phrases": sum(1 for v in vocab if v.get("type") == "phrase"),
        "savedToday": sum(1 for v in vocab if v.get("added", 0) >= today),
        "dictated": dictated, "dictatedToday": dictated_today, "mistakes": info["mistakes"], "recent": info["recent"],
    }


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


class App:
    def __init__(self):
        self.dic = Dictionary()
        self.pipeline = Pipeline(self.dic)


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ielts-study"

        def log_message(self, fmt, *args):  # keep the terminal quiet
            pass

        # ------------------------------------------------------------ helpers
        def _json(self, obj, status=200):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                body = json.loads(self.rfile.read(n))
                return body if isinstance(body, dict) else {}
            except ValueError:
                return {}

        def _local_request(self) -> bool:
            host = self.headers.get("Host", "")
            port = self.server.server_port
            origin = self.headers.get("Origin")
            return host in (f"127.0.0.1:{port}", f"localhost:{port}") and origin in (None, f"http://{host}")

        def _file(self, path, ctype=None, download_name=None):
            if not path.exists() or not path.is_file():
                return self._json({"error": "not found"}, 404)
            size = path.stat().st_size
            ctype = ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            rng = self.headers.get("Range")
            start, end = 0, size - 1
            status = HTTPStatus.OK
            if rng:
                m = re.match(r"bytes=(\d*)-(\d*)", rng)
                if m:
                    if m.group(1):
                        start = int(m.group(1))
                        end = int(m.group(2)) if m.group(2) else size - 1
                    elif m.group(2):
                        start = max(0, size - int(m.group(2)))
                    end = min(end, size - 1)
                    if start > end:
                        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.end_headers()
                        return
                    status = HTTPStatus.PARTIAL_CONTENT
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            if download_name:
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(download_name)}")
            self.end_headers()
            try:
                with path.open("rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(1 << 20, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _video_data(self, vid):
            if not SAFE_ID.match(vid):
                return None
            f = LIBRARY_DIR / vid / "data.json"
            if not f.exists():
                return None
            return json.loads(f.read_text(encoding="utf-8"))

        # ------------------------------------------------------------ routes
        def do_GET(self):
            u = urlparse(self.path)
            p = unquote(u.path)
            q = parse_qs(u.query)
            if p == "/":
                return self._file(STATIC_DIR / "home.html", "text/html; charset=utf-8")
            if p in ("/listening", "/index.html"):
                return self._file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            if p == "/reading":
                return self._file(STATIC_DIR / "reading.html", "text/html; charset=utf-8")
            if p.startswith("/reading/"):
                return self._file(STATIC_DIR / "article.html", "text/html; charset=utf-8")
            if p == "/api/home":
                return self._json(home_stats())
            if p == "/api/reading":
                return self._json(reading.list_articles())
            if p.startswith("/api/reading/"):
                data = reading.load_article(p.rsplit("/", 1)[1])
                return self._json(data) if data else self._json({"error": "not found"}, 404)
            if p.startswith("/player/"):
                return self._file(STATIC_DIR / "player.html", "text/html; charset=utf-8")
            if p == "/mistakes":
                return self._file(STATIC_DIR / "mistakes.html", "text/html; charset=utf-8")
            if p == "/api/mistakes":
                return self._json(list_mistakes())
            if p == "/api/sidebar":
                return self._json(sidebar())
            if p == "/vocab":
                return self._file(STATIC_DIR / "vocab.html", "text/html; charset=utf-8")
            if p.rstrip("/") in SETTINGS_PATHS:
                return self._file(STATIC_DIR / "settings.html", "text/html; charset=utf-8")
            if p.startswith("/static/"):
                target = (STATIC_DIR / p[len("/static/") :]).resolve()
                if STATIC_DIR.resolve() not in target.parents:
                    return self._json({"error": "forbidden"}, 403)
                return self._file(target)
            if p == "/api/library":
                return self._json(list_library())
            if p == "/api/settings":
                if not self._local_request():
                    return self._json({"error": "请从本机页面打开设置。"}, 403)
                try:
                    return self._json(load_settings().public())
                except ValueError as error:
                    return self._json({"error": str(error)}, 500)
            if p.startswith("/api/video/"):
                vid = p.rsplit("/", 1)[1]
                data = self._video_data(vid)
                if not data:
                    return self._json({"error": "not found"}, 404)
                return self._json(ensure_annotation(LIBRARY_DIR / vid, data, app.dic))
            if p.startswith("/api/dictation/"):
                vid = p.rsplit("/", 1)[1]
                if not SAFE_ID.match(vid):
                    return self._json({"error": "not found"}, 404)
                return self._json(load_dictation(vid))
            if p.startswith("/media/"):
                parts = p.split("/")
                if len(parts) == 4 and SAFE_ID.match(parts[2]) and re.match(r"^video\.\w+$", parts[3]):
                    return self._file(LIBRARY_DIR / parts[2] / parts[3])
                return self._json({"error": "not found"}, 404)
            if p.startswith("/api/jobs/"):
                job = app.pipeline.jobs.get(p.rsplit("/", 1)[1])
                return self._json(job.to_json()) if job else self._json({"error": "not found"}, 404)
            if p == "/api/lookup":
                w = (q.get("w") or [""])[0].strip().lower()
                w = re.sub(r"[^a-z'-]", "", w)
                info = app.dic.lookup(w) if w else None
                return self._json(info or {"en": w, "zh": "", "phonetic": ""})
            if p == "/api/vocab":
                return self._json(load_vocab())
            if p.startswith("/api/export/"):
                vid = p.rsplit("/", 1)[1].removesuffix(".srt")
                data = self._video_data(vid)
                if not data:
                    return self._json({"error": "not found"}, 404)
                mode = (q.get("mode") or ["bilingual"])[0]
                lines = []
                for n, c in enumerate(data["cues"], 1):
                    text = c["text"] if mode == "en" else (c.get("zh", "") if mode == "zh" else f'{c["text"]}\n{c.get("zh", "")}')
                    lines.append(f"{n}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{text}\n")
                body = "\n".join(lines).encode("utf-8")
                name = re.sub(r'[\\/:*?"<>|]+', "_", data.get("title") or vid)[:80] + ".srt"
                self.send_response(200)
                self.send_header("Content-Type", "application/x-subrip; charset=utf-8")
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name)}")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return self._json({"error": "not found"}, 404)

        def do_POST(self):
            p = urlparse(self.path).path
            settings_routes = ("/api/settings", "/api/settings/test", "/api/settings/models")
            if (p == "/api/import" or p in settings_routes) and not self._local_request():
                return self._json({"error": "请求需要来自本机页面。"}, 403)
            body = self._body()
            if p in settings_routes:
                if not body:
                    return self._json({"error": "请提交有效的设置。"}, 400)
                try:
                    if p == "/api/settings":
                        return self._json(save_settings(body).public())
                    from .translate import list_models, translate_batch

                    discover = p == "/api/settings/models"
                    settings = settings_from({**body, "engine": "api"}, load_settings(), require_model=not discover)
                    if discover:
                        return self._json({"models": list_models(settings)})
                    translate_batch(["The subtitles are ready."], settings)
                    return self._json({"ok": True})
                except ValueError as error:
                    return self._json({"error": str(error)}, 400)
                except RuntimeError as error:
                    return self._json({"error": str(error)}, 502)
                except OSError:
                    return self._json({"error": "无法保存本机设置。"}, 500)
            if p == "/api/import":
                url = (body.get("url") or "").strip()
                if not re.match(r"^https?://", url):
                    return self._json({"error": "请粘贴以 http(s):// 开头的视频链接"}, 400)
                job = app.pipeline.submit(url, str(body.get("quality") or "720"), bool(body.get("overwrite")))
                return self._json(job.to_json())
            if p == "/api/reading":
                if not self._local_request():
                    return self._json({"error": "请求需要来自本机页面。"}, 403)
                text = str(body.get("text") or "").strip()
                if len(re.findall(r"[A-Za-z]+", text)) < 3:
                    return self._json({"error": "请粘贴一段英文文章。"}, 400)
                if len(text) > reading.MAX_CHARS:
                    return self._json({"error": f"文章太长了，请控制在 {reading.MAX_CHARS // 1000}k 字符以内，或分几次粘贴。"}, 400)
                title = re.sub(r"\s+", " ", str(body.get("title") or "")).strip()[:120]
                return self._json(reading.submit_article(app.pipeline, text, title).to_json())
            if p.startswith("/api/video/") and p.endswith("/retranslate"):
                if not self._local_request():
                    return self._json({"error": "请求需要来自本机页面。"}, 403)
                vid = p.split("/")[3]
                if not SAFE_ID.match(vid) or not (LIBRARY_DIR / vid / "data.json").exists():
                    return self._json({"error": "not found"}, 404)
                return self._json(app.pipeline.retranslate(vid).to_json())
            if p == "/api/recent":
                if not self._local_request():
                    return self._json({"error": "请求需要来自本机页面。"}, 403)
                vid = str(body.get("videoId") or "")
                if not SAFE_ID.match(vid) or not (LIBRARY_DIR / vid / "data.json").exists():
                    return self._json({"error": "not found"}, 404)
                try:
                    t = float(body.get("time") or 0)
                except (TypeError, ValueError):
                    t = 0.0
                touch_recent(vid, t)
                return self._json({"ok": True})
            if p.startswith("/api/dictation/"):
                if not self._local_request():
                    return self._json({"error": "请求需要来自本机页面。"}, 403)
                vid = p.rsplit("/", 1)[1]
                if not SAFE_ID.match(vid) or not (LIBRARY_DIR / vid / "data.json").exists():
                    return self._json({"error": "not found"}, 404)
                try:
                    i = int(body.get("i"))
                    score = min(1.0, max(0.0, float(body.get("score"))))
                except (TypeError, ValueError):
                    return self._json({"error": "bad request"}, 400)
                with _dictation_lock:
                    records = load_dictation(vid)
                    prev = records.get(str(i), {})
                    records[str(i)] = {
                        "score": round(score, 3),
                        "best": round(max(score, prev.get("best", 0)), 3),
                        "tries": prev.get("tries", 0) + 1,
                        "typed": str(body.get("typed") or "")[:1000],
                        "at": int(time.time()),
                    }
                    save_json(LIBRARY_DIR / vid / "dictation.json", records)
                return self._json(records[str(i)])
            if p == "/api/vocab":
                item = {
                    "key": str(body.get("key") or "")[:200],
                    "type": body.get("type") if body.get("type") in ("word", "phrase") else "word",
                    "en": str(body.get("en") or "")[:200],
                    "zh": str(body.get("zh") or "")[:500],
                    "note": str(body.get("note") or "")[:500],
                    "phonetic": str(body.get("phonetic") or "")[:100],
                    "sentence": str(body.get("sentence") or "")[:500],
                    "sentenceZh": str(body.get("sentenceZh") or "")[:500],
                    "videoId": str(body.get("videoId") or "")[:80],
                    "articleId": str(body.get("articleId") or "")[:40],
                    "sentenceIndex": int(body.get("sentenceIndex") or 0),
                    "time": float(body.get("time") or 0),
                    "added": int(time.time()),
                }
                if not item["en"]:
                    return self._json({"error": "empty"}, 400)
                with _vocab_lock:
                    items = [v for v in load_vocab() if v.get("en", "").lower() != item["en"].lower()]
                    items.insert(0, item)
                    save_vocab(items)
                return self._json({"ok": True, "count": len(items)})
            return self._json({"error": "not found"}, 404)

        def do_DELETE(self):
            p = unquote(urlparse(self.path).path)
            if p.startswith("/api/vocab/"):
                en = p[len("/api/vocab/") :].lower()
                with _vocab_lock:
                    items = [v for v in load_vocab() if v.get("en", "").lower() != en]
                    save_vocab(items)
                return self._json({"ok": True})
            if p.startswith("/api/reading/"):
                if not self._local_request():
                    return self._json({"error": "请求需要来自本机页面。"}, 403)
                ok = reading.delete_article(p.rsplit("/", 1)[1])
                return self._json({"ok": True}) if ok else self._json({"error": "not found"}, 404)
            if p.startswith("/api/video/"):
                vid = p.rsplit("/", 1)[1]
                if SAFE_ID.match(vid) and (LIBRARY_DIR / vid).is_dir():
                    shutil.rmtree(LIBRARY_DIR / vid)
                    return self._json({"ok": True})
                return self._json({"error": "not found"}, 404)
            return self._json({"error": "not found"}, 404)

    return Handler


def _already_running(url: str) -> bool:
    from urllib.request import urlopen

    try:
        with urlopen(url + "api/library", timeout=2) as response:
            return response.headers.get("Server", "").startswith(("ielts-study", "whatsub-lite"))  # also the pre-rename build
    except OSError:
        return False


def _stop_running_instance() -> bool:
    """Stop the IELTS Study server listening on PORT (only if it really is ours, including the old whatsub-lite build)."""
    import os
    import signal
    import subprocess

    try:
        pids = subprocess.run(["lsof", "-nP", f"-iTCP:{PORT}", "-sTCP:LISTEN", "-t"],
                              capture_output=True, text=True, timeout=5).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return False
    stopped = False
    for pid in map(int, pids):
        command = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
        if ("ielts-study" in command or "whatsub-lite" in command) and pid != os.getpid():
            os.kill(pid, signal.SIGTERM)
            stopped = True
    if stopped:
        for _ in range(50):  # wait up to 5 s for the port to be released
            if not _already_running(f"http://{HOST}:{PORT}/"):
                break
            time.sleep(0.1)
    return stopped


def stop() -> int:
    """`ielts-study --stop`: quit the server that is running in the background (e.g. started by the desktop app)."""
    url = f"http://{HOST}:{PORT}/"
    if not _already_running(url):
        print("IELTS Study 没有在运行。")
        return 0
    if _stop_running_instance():
        print("已停止 IELTS Study。")
        return 0
    print("没能停止 IELTS Study。")
    return 1


def main(open_browser: bool = True, restart: bool = False):
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    print("IELTS Study 启动中…")
    url = f"http://{HOST}:{PORT}/"
    if restart and _already_running(url) and _stop_running_instance():
        print("已停止旧的 IELTS Study，正在用最新代码重新启动…")
    try:
        httpd = ThreadingHTTPServer((HOST, PORT), make_handler(App()))
    except OSError as error:
        if error.errno != errno.EADDRINUSE:
            raise
        if _already_running(url):
            print(f"IELTS Study 已经在运行：{url}")
            print("如果改了代码要重启：uv run ielts-study --restart")
            if open_browser:
                webbrowser.open(url)
            raise SystemExit(0) from None  # not an error: the page is open
        print(f"端口 {PORT} 被其他程序占用。可以换一个端口启动，例如：IELTS_PORT=8766 uv run ielts-study")
        raise SystemExit(1) from None
    print(f"已启动：{url}  （按 Ctrl+C 退出）")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
