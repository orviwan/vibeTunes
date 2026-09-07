from pathlib import Path

from podplex.core import artwork as aw
from podplex.core.artwork import ThumbnailCache, extract_embedded_art


class FakePicture:
    def __init__(self, data):
        self.data = data


class FakeFLAC:
    def __init__(self, path):
        self.pictures = [FakePicture(b"flacart")]


class FakeFLACNoArt:
    def __init__(self, path):
        self.pictures = []


class FakeAPIC:
    def __init__(self, data):
        self.data = data


class FakeID3:
    def __init__(self, path):
        self._apics = [FakeAPIC(b"id3art")]

    def getall(self, key):
        return self._apics if key == "APIC" else []


class FakeMP4:
    def __init__(self, path):
        self.tags = {"covr": [b"mp4art"]}


def test_extract_embedded_art_flac(monkeypatch):
    monkeypatch.setattr(aw, "FLAC", FakeFLAC)
    assert extract_embedded_art(Path("song.flac")) == b"flacart"


def test_extract_embedded_art_flac_no_art(monkeypatch):
    monkeypatch.setattr(aw, "FLAC", FakeFLACNoArt)
    assert extract_embedded_art(Path("song.flac")) is None


def test_extract_embedded_art_mp3(monkeypatch):
    monkeypatch.setattr(aw, "ID3", FakeID3)
    assert extract_embedded_art(Path("song.mp3")) == b"id3art"


def test_extract_embedded_art_mp4(monkeypatch):
    monkeypatch.setattr(aw, "MP4", FakeMP4)
    assert extract_embedded_art(Path("song.m4a")) == b"mp4art"


def test_extract_embedded_art_unsupported_extension_returns_none():
    assert extract_embedded_art(Path("song.ogg")) is None


def test_extract_embedded_art_handles_exceptions(monkeypatch):
    class Boom:
        def __init__(self, path):
            raise ValueError("bad file")

    monkeypatch.setattr(aw, "FLAC", Boom)
    assert extract_embedded_art(Path("song.flac")) is None


def test_thumbnail_cache_put_and_get_from_memory(tmp_path):
    cache = ThumbnailCache(cache_dir=tmp_path)
    source = tmp_path / "song.flac"
    source.write_bytes(b"audio")
    cache.put(source, b"thumbdata")
    assert cache.get(source) == b"thumbdata"


def test_thumbnail_cache_persists_to_disk_and_reloads(tmp_path):
    source = tmp_path / "song.flac"
    source.write_bytes(b"audio")
    cache_dir = tmp_path / "cache"
    cache1 = ThumbnailCache(cache_dir=cache_dir)
    cache1.put(source, b"thumbdata")

    cache2 = ThumbnailCache(cache_dir=cache_dir)
    assert cache2.get(source) == b"thumbdata"


def test_thumbnail_cache_get_missing_returns_none(tmp_path):
    cache = ThumbnailCache(cache_dir=tmp_path)
    assert cache.get(tmp_path / "nope.flac") is None


def test_thumbnail_cache_evicts_oldest_when_over_capacity(tmp_path):
    cache = ThumbnailCache(max_items=2, cache_dir=tmp_path)
    s1 = tmp_path / "a.flac"
    s1.write_bytes(b"1")
    s2 = tmp_path / "b.flac"
    s2.write_bytes(b"2")
    s3 = tmp_path / "c.flac"
    s3.write_bytes(b"3")
    cache.put(s1, b"A")
    cache.put(s2, b"B")
    cache.put(s3, b"C")
    assert len(cache._memory) == 2
    assert cache._cache_key(s1) not in cache._memory


def test_thumbnail_cache_get_or_extract_uses_extraction_when_not_cached(tmp_path, monkeypatch):
    cache = ThumbnailCache(cache_dir=tmp_path)
    source = tmp_path / "song.flac"
    source.write_bytes(b"audio")
    monkeypatch.setattr("podplex.core.artwork.extract_embedded_art", lambda p: b"extracted")
    result = cache.get_or_extract(source)
    assert result == b"extracted"
    assert cache.get(source) == b"extracted"


def test_thumbnail_cache_get_or_extract_returns_none_when_no_art(tmp_path, monkeypatch):
    cache = ThumbnailCache(cache_dir=tmp_path)
    source = tmp_path / "song.flac"
    source.write_bytes(b"audio")
    monkeypatch.setattr("podplex.core.artwork.extract_embedded_art", lambda p: None)
    assert cache.get_or_extract(source) is None
