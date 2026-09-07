from __future__ import annotations

import hashlib
from collections import OrderedDict
from pathlib import Path

from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4

CACHE_DIR = Path.home() / ".cache" / "podplex" / "thumbs"


def extract_embedded_art(path: Path) -> bytes | None:
    suffix = path.suffix.lower()
    try:
        if suffix == ".flac":
            audio = FLAC(path)
            return audio.pictures[0].data if audio.pictures else None
        if suffix in (".m4a", ".mp4", ".aac"):
            audio = MP4(path)
            covers = audio.tags.get("covr") if audio.tags else None
            return bytes(covers[0]) if covers else None
        if suffix == ".mp3":
            id3 = ID3(path)
            apics = id3.getall("APIC")
            return apics[0].data if apics else None
    except Exception:
        return None
    return None


class ThumbnailCache:
    def __init__(self, max_items: int = 200, cache_dir: Path = CACHE_DIR):
        self._max_items = max_items
        self._cache_dir = cache_dir
        self._memory: "OrderedDict[str, bytes]" = OrderedDict()

    def _cache_key(self, source_path: Path) -> str:
        try:
            mtime = source_path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        raw = f"{source_path}:{mtime}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def get(self, source_path: Path) -> bytes | None:
        key = self._cache_key(source_path)
        if key in self._memory:
            self._memory.move_to_end(key)
            return self._memory[key]
        disk_path = self._cache_dir / f"{key}.jpg"
        if disk_path.exists():
            data = disk_path.read_bytes()
            self._put_memory(key, data)
            return data
        return None

    def put(self, source_path: Path, data: bytes) -> None:
        key = self._cache_key(source_path)
        self._put_memory(key, data)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        (self._cache_dir / f"{key}.jpg").write_bytes(data)

    def _put_memory(self, key: str, data: bytes) -> None:
        self._memory[key] = data
        self._memory.move_to_end(key)
        while len(self._memory) > self._max_items:
            self._memory.popitem(last=False)

    def get_or_extract(self, source_path: Path) -> bytes | None:
        cached = self.get(source_path)
        if cached is not None:
            return cached
        data = extract_embedded_art(source_path)
        if data is not None:
            self.put(source_path, data)
        return data
