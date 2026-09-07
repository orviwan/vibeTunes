from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from podplex.core.naming import album_directory, track_filename
from podplex.core.plex_client import PlexTrack
from podplex.core.storage_analyzer import TrackFile

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav", ".alac"}


@dataclass(frozen=True)
class TrackStatus:
    track: PlexTrack
    on_device: bool
    dest_path: Path


@dataclass(frozen=True)
class AlbumStatus:
    tracks: list[TrackStatus]

    @property
    def synced_count(self) -> int:
        return sum(1 for t in self.tracks if t.on_device)

    @property
    def total_count(self) -> int:
        return len(self.tracks)

    @property
    def state(self) -> str:
        if self.total_count == 0 or self.synced_count == 0:
            return "MISSING"
        if self.synced_count == self.total_count:
            return "ON_IPOD"
        return "PARTIAL"


def album_directory_for(mount_path: Path, naming_pattern: str, first_track: PlexTrack) -> Path:
    disc = first_track.disc_number if naming_pattern == "rockbox_disc" else None
    year = str(first_track.year) if first_track.year else None
    parts = album_directory(naming_pattern, first_track.artist, first_track.album, year, disc)
    return mount_path.joinpath("Music", *parts)


def check_album_status(mount_path: Path, naming_pattern: str, tracks: list[PlexTrack]) -> AlbumStatus:
    if not tracks:
        return AlbumStatus(tracks=[])
    album_dir = album_directory_for(mount_path, naming_pattern, tracks[0])
    statuses = []
    for t in tracks:
        ext = Path(t.file_path).suffix
        filename = track_filename(t.track_number, t.title, ext)
        dest = album_dir / filename
        on_device = dest.exists() and (t.size_bytes == 0 or dest.stat().st_size == t.size_bytes)
        statuses.append(TrackStatus(track=t, on_device=on_device, dest_path=dest))
    return AlbumStatus(tracks=statuses)


def delete_album(mount_path: Path, naming_pattern: str, tracks: list[PlexTrack]) -> int:
    """Deletes the album's directory tree on the device. Returns bytes freed."""
    if not tracks:
        return 0
    album_dir = album_directory_for(mount_path, naming_pattern, tracks[0])
    if not album_dir.exists():
        return 0
    freed = sum(f.stat().st_size for f in album_dir.rglob("*") if f.is_file())
    shutil.rmtree(album_dir)
    return freed


def scan_music_tree(mount_path: Path) -> list[TrackFile]:
    """Walk Music/<Artist>/<Album...>/*.<ext> for storage-analyzer ranking."""
    music_root = mount_path / "Music"
    results: list[TrackFile] = []
    if not music_root.is_dir():
        return results
    for artist_dir in music_root.iterdir():
        if not artist_dir.is_dir():
            continue
        for f in artist_dir.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            rel = f.relative_to(artist_dir)
            album = rel.parts[0] if len(rel.parts) > 1 else artist_dir.name
            results.append(TrackFile(path=f, artist=artist_dir.name, album=album, size_bytes=size))
    return results
