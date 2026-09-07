from __future__ import annotations

from pathlib import Path

from podplex.core.matcher import find_match
from podplex.core.naming import album_directory, track_filename
from podplex.core.plex_client import PlexTrack
from podplex.core.storage_analyzer import TrackFile
from podplex.core.sync_engine import SyncTrack


def to_rockbox_path(mount_path: Path, file_path: Path, drive_label: str = "HDD0") -> str:
    rel = file_path.relative_to(mount_path)
    return f"/<{drive_label}>/" + "/".join(rel.parts)


def resolve_playlist_tracks(
    tracks: list[PlexTrack],
    candidates: list[TrackFile],
    client,
    mount_path: Path,
    naming_pattern: str,
) -> tuple[list[Path], list[SyncTrack]]:
    """Returns (path per input track in order, tracks that still need downloading).

    Each resolved path is either a matched existing on-device file or the
    path the track will be downloaded to.
    """
    resolved_paths: list[Path] = []
    to_download: list[SyncTrack] = []
    for t in tracks:
        match = find_match(t, candidates)
        if match is not None:
            resolved_paths.append(match.path)
            continue
        disc = t.disc_number if naming_pattern == "rockbox_disc" else None
        year = str(t.year) if t.year else None
        dir_parts = album_directory(naming_pattern, t.artist, t.album, year, disc)
        ext = Path(t.file_path).suffix
        dest = mount_path.joinpath("Music", *dir_parts, track_filename(t.track_number, t.title, ext))
        resolved_paths.append(dest)
        to_download.append(
            SyncTrack(source_url=client.download_url(t), dest_path=dest, size_bytes=t.size_bytes, title=t.title)
        )
    return resolved_paths, to_download


def write_m3u8(playlist_name: str, mount_path: Path, resolved_paths: list[Path], drive_label: str = "HDD0") -> Path:
    playlists_dir = mount_path / "Playlists"
    playlists_dir.mkdir(parents=True, exist_ok=True)
    safe_name = playlist_name.replace("/", "_")
    out_path = playlists_dir / f"{safe_name}.m3u8"
    lines = [to_rockbox_path(mount_path, p, drive_label) for p in resolved_paths]
    content = "\ufeff" + "\n".join(lines) + "\n"
    out_path.write_bytes(content.encode("utf-8"))
    return out_path


def list_on_device_playlists(mount_path: Path) -> list[Path]:
    playlists_dir = mount_path / "Playlists"
    if not playlists_dir.is_dir():
        return []
    return sorted(playlists_dir.glob("*.m3u8"))


def delete_playlist(path: Path) -> None:
    if path.exists():
        path.unlink()
