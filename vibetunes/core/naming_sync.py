"""Non-destructive iPod file and directory alignment with Plex media conventions."""
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Callable, Dict, Tuple

from vibetunes.core.plex_client import (
    PlexManager, normalize_music_key, extract_base_album_title
)
from vibetunes.core.ipod_scanner import scan_ipod_music, iPodArtist, iPodAlbum
from vibetunes.core.naming import clean_fat32_name

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".wav", ".aac", ".alac", ".wma"}

@dataclass
class RenameProposal:
    current_path: Path
    target_path: Path
    is_dir: bool
    artist_name: str
    album_title: str
    item_count: int = 0
    description: str = ""

def is_album_match(t1: str, t2: str) -> bool:
    """Checks if two album titles match, considering editions, subtitles, and normalization."""
    k1 = normalize_music_key(t1)
    k2 = normalize_music_key(t2)
    if k1 == k2:
        return True
    b1 = normalize_music_key(extract_base_album_title(t1))
    b2 = normalize_music_key(extract_base_album_title(t2))
    if b1 == b2 and len(b1) >= 2:
        return True
    if len(b1) >= 4 and (k2.startswith(b1) or f" {b1} " in f" {k2} "):
        return True
    if len(b2) >= 4 and (k1.startswith(b2) or f" {b2} " in f" {k1} "):
        return True
    return False

def inspect_ipod_naming_alignment(
    ipod_mount: str,
    plex: PlexManager,
    library_name: str,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> List[RenameProposal]:
    """
    Scans the iPod and compares directory and file names against the Plex library's
    underlying file and folder structure. Returns a list of proposed non-destructive renames.
    """
    if not ipod_mount or not Path(ipod_mount).is_dir() or not plex.is_connected():
        return []

    # 1. Scan iPod music
    if progress_callback:
        progress_callback(5, "Scanning iPod music library...")
    ipod_artists = scan_ipod_music(ipod_mount)
    if not ipod_artists:
        return []

    # 2. Fetch Plex artists
    if progress_callback:
        progress_callback(15, "Fetching Plex catalog...")
    plex_artists = plex.get_artists(library_name)
    plex_artist_map = {normalize_music_key(a.name): a for a in plex_artists}

    proposals: List[RenameProposal] = []
    total_artists = len(ipod_artists)

    for idx, ip_art in enumerate(ipod_artists):
        pct = 15 + int((idx / max(1, total_artists)) * 75)
        if progress_callback:
            progress_callback(pct, f"Checking {ip_art.name}...")

        norm_art = normalize_music_key(ip_art.name)
        pl_art = plex_artist_map.get(norm_art)
        if not pl_art:
            # Try fuzzy artist match
            for k, a in plex_artist_map.items():
                if norm_art in k or k in norm_art:
                    pl_art = a
                    break
        if not pl_art:
            continue

        pl_albums = plex.get_artist_albums(pl_art.rating_key)
        for ip_alb in ip_art.albums:
            matched_pl_alb = None
            for a in pl_albums:
                if is_album_match(ip_alb.title, a.title):
                    matched_pl_alb = a
                    break

            if not matched_pl_alb:
                continue

            tracks = plex.get_album_tracks(matched_pl_alb.rating_key)
            if not tracks or not tracks[0].original_filename:
                continue

            fat32_rel = plex.get_fat32_media_path(tracks[0].original_filename)
            if not fat32_rel or len(fat32_rel.parts) < 2:
                continue

            target_artist_dir = fat32_rel.parts[0]
            target_album_dir = fat32_rel.parts[1]
            target_album_path = Path(ipod_mount) / target_artist_dir / target_album_dir

            # Check if album folder name differs
            if ip_alb.path.name != target_album_dir or ip_alb.path.parent.name != target_artist_dir:
                proposals.append(RenameProposal(
                    current_path=ip_alb.path,
                    target_path=target_album_path,
                    is_dir=True,
                    artist_name=ip_art.name,
                    album_title=matched_pl_alb.title,
                    item_count=ip_alb.track_count,
                    description=f"Rename folder: '{ip_alb.path.name}' ➜ '{target_album_dir}'"
                ))

    if progress_callback:
        progress_callback(100, "Alignment check complete.")

    return proposals

def apply_naming_alignment(
    proposals: List[RenameProposal],
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Tuple[int, List[str]]:
    """
    Executes in-place non-destructive renames.
    Strictly zero deletions: files are moved/renamed safely, never unlinked.
    """
    renamed_count = 0
    errors: List[str] = []
    total = len(proposals)

    for idx, prop in enumerate(proposals):
        if progress_callback:
            progress_callback(int(((idx + 1) / max(1, total)) * 100), f"Renaming {prop.current_path.name}...")

        if not prop.current_path.exists():
            continue

        if prop.current_path.resolve() == prop.target_path.resolve():
            continue

        try:
            prop.target_path.parent.mkdir(parents=True, exist_ok=True)

            if prop.target_path.exists():
                # Destination already exists: merge contents non-destructively
                if prop.is_dir:
                    for root, dirs, files in os.walk(prop.current_path):
                        rel_root = Path(root).relative_to(prop.current_path)
                        dest_sub = prop.target_path / rel_root
                        dest_sub.mkdir(parents=True, exist_ok=True)
                        for f in files:
                            src_file = Path(root) / f
                            dest_file = dest_sub / f
                            if not dest_file.exists():
                                shutil.move(str(src_file), str(dest_file))
                    # Clean empty residual directories if completely empty
                    _clean_empty_tree(prop.current_path)
                else:
                    # File conflict: do not overwrite
                    pass
            else:
                # Direct rename. Handle FAT32 case-only difference (e.g. "Abc" -> "abc")
                if prop.current_path.name.lower() == prop.target_path.name.lower():
                    temp_path = prop.current_path.parent / f"{prop.current_path.name}_vttmp"
                    shutil.move(str(prop.current_path), str(temp_path))
                    shutil.move(str(temp_path), str(prop.target_path))
                else:
                    shutil.move(str(prop.current_path), str(prop.target_path))

            renamed_count += 1
        except Exception as e:
            errors.append(f"Failed to rename {prop.current_path.name}: {e}")

    return renamed_count, errors

def _clean_empty_tree(dir_path: Path) -> None:
    """Removes empty directories only if they contain no files."""
    try:
        for root, dirs, files in os.walk(dir_path, topdown=False):
            if not files and not dirs:
                try:
                    os.rmdir(root)
                except OSError:
                    pass
    except Exception:
        pass
