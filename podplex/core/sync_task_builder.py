from __future__ import annotations

from pathlib import Path

from podplex.core.naming import album_directory, track_filename
from podplex.core.plex_client import PlexTrack
from podplex.core.sync_engine import SyncTask, SyncTrack


def build_album_sync_task(
    client,
    tracks: list[PlexTrack],
    mount_path: Path,
    naming_pattern: str,
    task_id: str,
) -> SyncTask:
    if not tracks:
        raise ValueError("cannot build a sync task with no tracks")
    first = tracks[0]
    disc = first.disc_number if naming_pattern == "rockbox_disc" else None
    year = str(first.year) if first.year else None
    dir_parts = album_directory(naming_pattern, first.artist, first.album, year, disc)
    album_dir = mount_path.joinpath("Music", *dir_parts)

    sync_tracks = []
    for t in tracks:
        ext = Path(t.file_path).suffix
        filename = track_filename(t.track_number, t.title, ext)
        dest = album_dir / filename
        sync_tracks.append(
            SyncTrack(source_url=client.download_url(t), dest_path=dest, size_bytes=t.size_bytes, title=t.title)
        )
    name = f"{first.artist} - {first.album}"
    return SyncTask(name=name, tracks=sync_tracks, task_id=task_id)
