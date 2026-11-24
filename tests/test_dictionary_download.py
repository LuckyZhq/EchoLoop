"""First-run dictionary download: verified, and never left half-written."""
import hashlib

import pytest

from ielts_study import dictionary


def test_download_is_verified_and_moved_into_place(tmp_path, monkeypatch):
    source = tmp_path / "source.csv"
    source.write_text("word,phonetic,definition,translation\nhello,,greeting,你好\n", encoding="utf-8")
    good = hashlib.sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(dictionary, "CSV_PATH", tmp_path / "data" / "ecdict.csv")
    messages = []
    dictionary.download_ecdict(messages.append, url=source.as_uri(), sha256=good)
    assert dictionary.CSV_PATH.read_bytes() == source.read_bytes()
    assert not dictionary.CSV_PATH.with_suffix(".part").exists()
    assert messages and "ECDICT" in messages[0]


def test_a_corrupt_download_leaves_nothing_behind(tmp_path, monkeypatch):
    source = tmp_path / "source.csv"
    source.write_text("truncated", encoding="utf-8")
    monkeypatch.setattr(dictionary, "CSV_PATH", tmp_path / "data" / "ecdict.csv")
    with pytest.raises(RuntimeError):
        dictionary.download_ecdict(lambda m: None, url=source.as_uri(), sha256="0" * 64)
    assert not dictionary.CSV_PATH.exists() and not dictionary.CSV_PATH.with_suffix(".part").exists()
