from podplex.core import downloader as dl
from podplex.core.downloader import HttpDownloader


class FakeResponse:
    def __init__(self, chunks, total):
        self._chunks = chunks
        self.headers = {"Content-Length": str(total)}

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_http_downloader_writes_file_and_reports_progress(tmp_path, monkeypatch):
    chunks = [b"hell", b"o wo", b"rld!"]
    total = sum(len(c) for c in chunks)

    def fake_get(url, stream, timeout):
        assert url == "http://example/track.mp3"
        return FakeResponse(chunks, total)

    monkeypatch.setattr(dl.requests, "get", fake_get)
    progress_calls = []
    dest = tmp_path / "out.mp3"
    HttpDownloader().download(
        "http://example/track.mp3",
        dest,
        on_progress=lambda w, t: progress_calls.append((w, t)),
        should_cancel=lambda: False,
    )
    assert dest.read_bytes() == b"hello world!"
    assert progress_calls[-1] == (12, 12)


def test_http_downloader_stops_when_cancelled(tmp_path, monkeypatch):
    chunks = [b"aa", b"bb", b"cc"]

    def fake_get(url, stream, timeout):
        return FakeResponse(chunks, 6)

    monkeypatch.setattr(dl.requests, "get", fake_get)
    dest = tmp_path / "out.mp3"
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > 1

    HttpDownloader().download("http://x", dest, on_progress=lambda w, t: None, should_cancel=should_cancel)
    assert dest.read_bytes() == b"aa"
