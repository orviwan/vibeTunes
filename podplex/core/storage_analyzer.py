from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrackFile:
    path: Path
    artist: str
    album: str
    size_bytes: int


@dataclass
class StorageBreakdown:
    total_bytes: int
    free_bytes: int
    music_bytes: int
    rockbox_bytes: int
    other_bytes: int


def compute_storage_bar(mount_path: Path) -> StorageBreakdown:
    stat = os.statvfs(mount_path)
    total = stat.f_frsize * stat.f_blocks
    free = stat.f_frsize * stat.f_bavail
    used = total - free
    music_bytes = _dir_size(mount_path / "Music") if (mount_path / "Music").is_dir() else 0
    rockbox_bytes = _dir_size(mount_path / ".rockbox") if (mount_path / ".rockbox").is_dir() else 0
    other_bytes = max(used - music_bytes - rockbox_bytes, 0)
    return StorageBreakdown(total, free, music_bytes, rockbox_bytes, other_bytes)


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


@dataclass(frozen=True)
class AlbumSize:
    artist: str
    album: str
    total_bytes: int
    track_count: int


@dataclass(frozen=True)
class ArtistSize:
    artist: str
    total_bytes: int


def largest_albums(tracks: list[TrackFile], limit: int = 50) -> list[AlbumSize]:
    grouped: dict[tuple[str, str], list[TrackFile]] = {}
    for t in tracks:
        grouped.setdefault((t.artist, t.album), []).append(t)
    albums = [
        AlbumSize(artist=a, album=al, total_bytes=sum(t.size_bytes for t in ts), track_count=len(ts))
        for (a, al), ts in grouped.items()
    ]
    albums.sort(key=lambda x: x.total_bytes, reverse=True)
    return albums[:limit]


def largest_files(tracks: list[TrackFile], limit: int = 50) -> list[TrackFile]:
    return sorted(tracks, key=lambda t: t.size_bytes, reverse=True)[:limit]


def largest_artists(tracks: list[TrackFile], limit: int = 50) -> list[ArtistSize]:
    grouped: dict[str, int] = {}
    for t in tracks:
        grouped[t.artist] = grouped.get(t.artist, 0) + t.size_bytes
    artists = [ArtistSize(artist=a, total_bytes=b) for a, b in grouped.items()]
    artists.sort(key=lambda x: x.total_bytes, reverse=True)
    return artists[:limit]
