"""Non-destructive iPod file and directory alignment with Plex media conventions."""
import os
import re
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
    ipod_mount: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Tuple[int, List[str]]:
    """
    Executes in-place non-destructive renames.
    Strictly zero deletions: files are moved/renamed safely, never unlinked.
    """
    renamed_count = 0
    errors: List[str] = []
    total = len(proposals)

    # Derive ipod_mount if not provided
    if ipod_mount is None and proposals:
        curr = proposals[0].current_path
        # Traverse upwards to find mount root
        for parent in curr.parents:
            if (parent / "Playlists").is_dir() or (parent / "playlists").is_dir():
                ipod_mount = parent
                break
        if ipod_mount is None and len(curr.parents) >= 2:
            ipod_mount = curr.parents[1]

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

    # Synchronize all playlists on iPod to reflect renamed paths
    if ipod_mount:
        try:
            repair_ipod_playlists(Path(ipod_mount))
        except Exception as e:
            errors.append(f"Playlist alignment warning: {e}")

    return renamed_count, errors

def resolve_track_on_ipod(ipod_mount: Path, old_rel_path: str) -> Optional[Path]:
    """
    Given a broken relative path from a playlist (e.g. 'Ash/Ash-1994-Trailer/02 - Jack Names the Planets.flac'),
    locates the actual audio file on the iPod under newly renamed directory conventions.
    """
    parts = Path(old_rel_path).parts
    if len(parts) < 2:
        return None

    artist_name = parts[0]
    album_folder = parts[1] if len(parts) >= 3 else ""
    filename = parts[-1]

    artist_dir = ipod_mount / artist_name
    if not artist_dir.is_dir():
        for ad in ipod_mount.iterdir():
            if ad.is_dir() and normalize_music_key(ad.name) == normalize_music_key(artist_name):
                artist_dir = ad
                break

    if not artist_dir.is_dir():
        return None

    stem = Path(filename).stem
    stem_norm = re.sub(r"[^\w]", "", stem).casefold()
    stem_no_num = re.sub(r"[^\w]", "", re.sub(r"^\d+[\s\.\-_]*", "", stem)).casefold()

    # 1. Search matching candidate album folders first
    if album_folder:
        clean_alb_folder = re.sub(rf"^{re.escape(artist_name)}\s*[-_]\s*", "", album_folder, flags=re.IGNORECASE)
        for d in artist_dir.iterdir():
            if not d.is_dir():
                continue
            if is_album_match(album_folder, d.name) or is_album_match(clean_alb_folder, d.name):
                for f in d.rglob("*"):
                    if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
                        f_norm = re.sub(r"[^\w]", "", f.stem).casefold()
                        f_no_num = re.sub(r"[^\w]", "", re.sub(r"^\d+[\s\.\-_]*", "", f.stem)).casefold()
                        if stem_norm == f_norm or stem_no_num == f_no_num:
                            return f

    # 2. Fallback: Search all audio files under artist folder with length guard
    for f in artist_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            f_norm = re.sub(r"[^\w]", "", f.stem).casefold()
            f_no_num = re.sub(r"[^\w]", "", re.sub(r"^\d+[\s\.\-_]*", "", f.stem)).casefold()
            if stem_norm == f_norm or (len(stem_no_num) >= 4 and stem_no_num == f_no_num):
                return f

    return None

def repair_ipod_playlists(
    ipod_mount: Path,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    dry_run: bool = False,
) -> Tuple[int, int, List[str]]:
    """
    Scans all .m3u and .m3u8 playlist files in the iPod's Playlists folder,
    detects dead paths caused by folder/track renaming, and repairs them in-place.
    Returns: (repaired_playlists_count, repaired_tracks_count, unresolvable_entries)
    """
    pl_dir = Path(ipod_mount) / "Playlists"
    if not pl_dir.is_dir():
        pl_dir = Path(ipod_mount) / "playlists"
    if not pl_dir.is_dir():
        return 0, 0, []

    playlist_files = sorted([f for f in pl_dir.iterdir() if f.is_file() and f.suffix.lower() in (".m3u", ".m3u8")])
    if not playlist_files:
        return 0, 0, []

    repaired_playlists = 0
    total_repaired_tracks = 0
    unresolved: List[str] = []

    for idx, pl_path in enumerate(playlist_files):
        if progress_callback:
            pct = int((idx / len(playlist_files)) * 100)
            progress_callback(pct, f"Checking playlist {pl_path.name}...")

        try:
            content = pl_path.read_text(encoding="utf-8-sig", errors="ignore")
        except Exception:
            continue

        lines = content.splitlines()
        new_lines: List[str] = []
        file_modified = False

        for line in lines:
            trimmed = line.strip()
            if not trimmed or trimmed.startswith("#"):
                new_lines.append(line)
                continue

            rel = trimmed
            if rel.startswith("/<HDD0>/"):
                rel = rel[len("/<HDD0>/"):]
            elif rel.startswith("/"):
                rel = rel[1:]

            target_file = Path(ipod_mount) / rel
            if target_file.is_file():
                new_lines.append(line)
                continue

            # Dead path: attempt to resolve against current disk layout
            resolved = resolve_track_on_ipod(Path(ipod_mount), rel)
            if resolved and resolved.is_file():
                resolved_rel = resolved.relative_to(ipod_mount).as_posix()
                new_lines.append(f"/<HDD0>/{resolved_rel}")
                file_modified = True
                total_repaired_tracks += 1
            else:
                new_lines.append(line)
                unresolved.append(f"{pl_path.name}: {trimmed}")

        if file_modified:
            repaired_playlists += 1
            if not dry_run:
                try:
                    with open(pl_path, "w", encoding="utf-8-sig", newline="\n") as f:
                        for l in new_lines:
                            f.write(l + "\n")
                except Exception as e:
                    unresolved.append(f"Could not save {pl_path.name}: {e}")

    if progress_callback:
        progress_callback(100, "Playlist verification complete.")

    return repaired_playlists, total_repaired_tracks, unresolved

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
