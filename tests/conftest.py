import pytest

from echoloop import usage


@pytest.fixture(autouse=True)
def _usage_file(tmp_path, monkeypatch):
    """API usage from fake requests goes to a temporary file, never to data/api_usage.json."""
    monkeypatch.setattr(usage, "PATH", tmp_path / "api_usage.json")
