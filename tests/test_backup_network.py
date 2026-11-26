"""Backups (export, restore, folder backups) and phone access over the LAN (the access key gate)."""
import json
import threading
import time
import zipfile
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from echoloop import backup, network, server


@pytest.fixture
def roots(tmp_path, monkeypatch):
    lib, arts = tmp_path / "library", tmp_path / "articles"
    (lib / "youtube-abc").mkdir(parents=True)
    (lib / "youtube-abc" / "data.json").write_text('{"id": "youtube-abc"}')
    (lib / "youtube-abc" / "video.mp4").write_bytes(b"\0" * 1000)
    (lib / "vocab.json").write_text('[{"en": "notice"}]')
    (arts / "a1").mkdir(parents=True)
    (arts / "a1" / "data.json").write_text("{}")
    monkeypatch.setattr(backup, "ROOTS", {"library": lib, "articles": arts})
    monkeypatch.setattr(backup, "RESTORE_DIR", tmp_path / "aside")
    monkeypatch.setattr(backup, "BACKUP_SETTINGS", tmp_path / "backup.json")
    return lib, arts


def test_export_leaves_out_videos(roots, tmp_path):
    info = backup.write_zip(tmp_path / "b.zip")
    names = zipfile.ZipFile(tmp_path / "b.zip").namelist()
    assert "library/vocab.json" in names and "articles/a1/data.json" in names and "manifest.json" in names
    assert "library/youtube-abc/video.mp4" not in names and info["files"] == 3
    backup.write_zip(tmp_path / "v.zip", include_videos=True)
    assert "library/youtube-abc/video.mp4" in zipfile.ZipFile(tmp_path / "v.zip").namelist()


def test_restore_keeps_replaced_files(roots, tmp_path):
    lib, _ = roots
    backup.write_zip(tmp_path / "b.zip")
    (lib / "vocab.json").write_text("[]")
    out = backup.restore(tmp_path / "b.zip")
    assert json.loads((lib / "vocab.json").read_text()) == [{"en": "notice"}]
    assert out["keptAside"] == 1  # only the changed file was set aside; identical ones were skipped
    aside = next((tmp_path / "aside").iterdir())
    assert (aside / "library" / "vocab.json").read_text() == "[]"


def test_restore_rejects_foreign_and_unsafe_zips(roots, tmp_path):
    with zipfile.ZipFile(tmp_path / "x.zip", "w") as z:
        z.writestr("vocab.json", "[]")
    with pytest.raises(ValueError):
        backup.restore(tmp_path / "x.zip")
    with zipfile.ZipFile(tmp_path / "y.zip", "w") as z:
        z.writestr("manifest.json", json.dumps({"app": "echoloop"}))
        z.writestr("library/../../evil.txt", "x")
    with pytest.raises(ValueError):
        backup.restore(tmp_path / "y.zip")
    assert not (tmp_path / "evil.txt").exists()


def test_restore_accepts_legacy_ielts_study_backup(roots, tmp_path):
    lib, _ = roots
    backup.write_zip(tmp_path / "b.zip")
    legacy = tmp_path / "legacy.zip"
    with zipfile.ZipFile(tmp_path / "b.zip") as src, zipfile.ZipFile(legacy, "w") as dst:
        for info in src.infolist():
            if info.filename == "manifest.json":
                m = json.loads(src.read(info))
                m["app"] = "ielts-study"
                dst.writestr("manifest.json", json.dumps(m))
            else:
                dst.writestr(info, src.read(info))
    (lib / "vocab.json").write_text("[]")
    out = backup.restore(legacy)
    assert out["restored"] == 1 and json.loads((lib / "vocab.json").read_text()) == [{"en": "notice"}]


def test_folder_backups_keep_the_newest(roots, tmp_path, monkeypatch):
    folder = tmp_path / "cloud"
    folder.mkdir()
    backup.set_folder(str(folder), keep=2)
    names = iter(f"EchoLoop-backup-20260101-00000{i}.zip" for i in range(5))
    monkeypatch.setattr(backup, "file_name", lambda: next(names))
    for _ in range(3):
        backup.backup_now()
    assert sorted(p.name for p in folder.iterdir()) == ["EchoLoop-backup-20260101-000001.zip",
                                                         "EchoLoop-backup-20260101-000002.zip"]
    with pytest.raises(ValueError):
        backup.set_folder(str(tmp_path / "missing"))
    with pytest.raises(ValueError):
        backup.set_folder(str(roots[0]))  # not inside the library itself


def test_lan_addresses_skip_vpn_tunnels():
    assert network._usable("192.168.1.84") and network._usable("10.0.0.5")
    assert not network._usable("198.18.0.1")  # Clash / Surge tunnel
    assert not network._usable("100.101.1.2") and not network._usable("8.8.8.8") and not network._usable("127.0.0.1")
    assert network.private_host("192.168.1.84:8765") and not network.private_host("evil.example:8765")
    assert not network.private_host("127.0.0.1:8765")


@pytest.fixture
def lan_server(tmp_path, monkeypatch):
    monkeypatch.setattr(network, "NETWORK_PATH", tmp_path / "network.json")
    data = network.save(True)
    monkeypatch.setattr(network, "STARTED", data)
    handler = server.make_handler(SimpleNamespace(dic=None, pipeline=None))
    monkeypatch.setattr(handler, "_loopback_client", lambda self: False)  # as if from a phone
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", httpd.server_port, data["token"]
    httpd.shutdown()


def call(url, method="GET", headers=None, data=None):
    try:
        with urlopen(Request(url, method=method, headers=headers or {}, data=data), timeout=5) as r:
            return r.status, r.headers, r.read()
    except HTTPError as error:
        return error.code, error.headers, error.read()


def test_phone_needs_the_key(lan_server):
    base, port, token = lan_server
    host = {"Host": f"192.168.1.84:{port}"}
    assert call(base + "/api/sidebar", headers=host)[0] == 403
    assert call(base + f"/vocab?key=wrong", headers=host)[0] == 403
    with_cookie = {**host, "Cookie": f"echoloop_key={token}"}
    assert call(base + "/api/settings", headers=with_cookie)[0] == 403  # API keys stay on the computer
    status, _, _ = call(base + "/api/shutdown", "POST", {**with_cookie, "Origin": f"http://192.168.1.84:{port}"}, b"{}")
    assert status == 403
    status, _, _ = call(base + "/api/language", "POST", {**with_cookie, "Origin": "http://evil.example"}, b"{}")
    assert status == 403
    # without LAN mode the same request is refused
    network.STARTED["lan"] = False
    assert call(base + "/api/language", headers=with_cookie)[0] == 403


def test_key_link_sets_the_cookie(lan_server):
    from urllib.request import HTTPRedirectHandler, build_opener

    class Stop(HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    base, port, token = lan_server
    try:
        build_opener(Stop()).open(Request(base + f"/player/x?t=12&key={token}", headers={"Host": f"192.168.1.84:{port}"}))
        pytest.fail("expected a redirect")
    except HTTPError as error:
        assert error.code == 303
        assert error.headers["Location"] == "/player/x?t=12"
        assert f"echoloop_key={token}" in error.headers["Set-Cookie"] and "HttpOnly" in error.headers["Set-Cookie"]
