"""HTTP guards and the version check, against a real server on a free port (no dictionary or pipeline needed)."""
import json
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from ielts_study import server


@pytest.fixture(scope="module")
def base():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(SimpleNamespace(dic=None, pipeline=None)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def call(url, method="GET", data=None, headers=None):
    req = Request(url, method=method, data=data, headers=headers or {})
    try:
        with urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except HTTPError as e:
        return e.code, e.read()


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/vocab"), ("POST", "/api/import"), ("POST", "/api/restart"), ("POST", "/api/settings"),
    ("DELETE", "/api/vocab/word"), ("DELETE", "/api/video/some-video"), ("DELETE", "/api/reading/a000000000000"),
])
def test_writes_from_other_sites_are_refused(base, method, path):
    status, _ = call(base + path, method, b'{"en":"x"}', {"Origin": "http://evil.example", "Content-Type": "text/plain"})
    assert status == 403


def test_dns_rebinding_host_is_refused(base):
    port = base.rsplit(":", 1)[1]
    status, _ = call(base + "/api/video/some-video", "DELETE", headers={"Host": f"evil.example:{port}"})
    assert status == 403


def test_own_page_passes_the_guard(base):
    status, body = call(base + "/api/vocab", "POST", b'{"en":""}', {"Origin": base, "Content-Type": "application/json"})
    assert status == 400 and json.loads(body)["error"] == "empty"  # reached the handler


def test_version_reports_not_stale_right_after_start(base):
    status, body = call(base + "/api/version")
    info = json.loads(body)
    assert status == 200 and info["running"] == info["current"] and info["stale"] is False


def test_running_server_is_detected_when_library_fails(base, monkeypatch):
    def unavailable_library():
        raise ImportError("library requires updated code")

    monkeypatch.setattr(server, "list_library", unavailable_library)
    assert server._already_running(base + "/")


def test_fingerprint_is_stable_while_nothing_changes():
    first = server.code_fingerprint()
    assert first == server.code_fingerprint()
    assert len(first) == 12
