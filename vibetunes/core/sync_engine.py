"""Multithreaded synchronization engine for transferring music from Plex to iPod."""
import os
import re
import time
import shutil
import threading
import subprocess
import requests
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable, Set, Union

from PySide6.QtCore import QObject, Signal

from vibetunes.core.plex_client import PlexManager, PlexAlbumSummary, PlexTrackDetail, normalize_music_key
from vibetunes.core.config import AppConfig

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".wav", ".aac", ".alac", ".wma"}

from vibetunes.core.naming import clean_fat32_name

def find_track_on_ipod(
    ipod_mount: Path,
    artist_name: str,
    album_title: str,
    track_title: str,
    track_number: int = 0,
    disc_number: int = 1,
) -> Optional[Path]:
    """
    Searches an iPod filesystem to locate an existing audio track.
    Matches across:
    - Release year in album folder names (e.g. 'Artist-1996-Album')
    - Differences in punctuation, curly vs straight quotes, casing, diacritics
    - Multi-disc folder structures ('CD 01', 'Disc 1', etc.)
    - Any supported audio container (.flac, .mp3, .m4a, .ogg, .wav, .aac, .alac, .wma)
    - Track number prefixes ('01 - Title.flac', '01. Title.mp3', 'Title.m4a')
    """
    ipod_path = Path(ipod_mount)
    if not ipod_path.is_dir():
        return None

    norm_artist = normalize_music_key(artist_name)
    norm_album = normalize_music_key(album_title)
    clean_art = clean_fat32_name(artist_name)
    norm_title = re.sub(r"[^\w]", "", track_title).casefold()

    # 1. Locate candidate artist directories
    artist_dirs: List[Path] = []
    exact_dir = ipod_path / clean_art
    if exact_dir.is_dir():
        artist_dirs.append(exact_dir)

    try:
        for entry in ipod_path.iterdir():
            if not entry.is_dir() or entry.name.startswith(".") or entry.name == "Playlists":
                continue
            if normalize_music_key(entry.name) == norm_artist and entry not in artist_dirs:
                artist_dirs.append(entry)
    except Exception:
        pass

    if not artist_dirs:
        for fallback in ["Various Artists", "Compilations", "Soundtracks"]:
            fb_dir = ipod_path / fallback
            if fb_dir.is_dir():
                artist_dirs.append(fb_dir)

    def file_matches(f: Path) -> bool:
        stem_norm = re.sub(r"[^\w]", "", f.stem).casefold()
        stem_without_num = re.sub(r"^\d+", "", stem_norm)

        num_match = False
        if track_number > 0:
            num_pattern = f"{track_number:02d}"
            if f.name.startswith(num_pattern) or f.name.startswith(f"{track_number} ") or f.name.startswith(f"{track_number}-"):
                num_match = True

        if num_match and (norm_title in stem_norm or stem_without_num == norm_title):
            return True
        if stem_without_num == norm_title or stem_norm == norm_title:
            return True
        if len(norm_title) >= 4 and norm_title in stem_without_num:
            return True
        return False

    def search_dir_for_track(search_dir: Path) -> Optional[Path]:
        try:
            for f in search_dir.iterdir():
                if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
                    if file_matches(f):
                        return f
        except Exception:
            pass
        return None

    for ad in artist_dirs:
        # 2. Check candidate album directories under artist
        album_dirs: List[Path] = []
        try:
            for d in ad.iterdir():
                if d.is_dir():
                    d_norm = normalize_music_key(d.name)
                    if norm_album in d_norm or d_norm in norm_album:
                        album_dirs.append(d)
        except Exception:
            pass

        for ald in album_dirs:
            if disc_number > 1:
                cd_dir = ald / f"CD {disc_number:02d}"
                if cd_dir.is_dir():
                    res = search_dir_for_track(cd_dir)
                    if res:
                        return res

            res = search_dir_for_track(ald)
            if res:
                return res

            try:
                for sub in ald.iterdir():
                    if sub.is_dir():
                        res = search_dir_for_track(sub)
                        if res:
                            return res
            except Exception:
                pass

        # 3. Fallback: Search all audio files under artist folder
        try:
            for f in ad.rglob("*"):
                if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
                    if file_matches(f):
                        return f
        except Exception:
            pass

    return None

@dataclass
class SyncTask:
    artist_name: str
    album_title: str
    album_key: str
    year: Optional[int] = None
    thumb_url: Optional[str] = None
    specific_track_keys: Optional[Set[str]] = None
    force_overwrite: bool = False

    @property
    def display_title(self) -> str:
        return f"{self.artist_name} - {self.album_title}"

    @property
    def item_type_label(self) -> str:
        if self.specific_track_keys:
            return "Selected Tracks"
        return "Album"

    @property
    def details_label(self) -> str:
        yr = f" ({self.year})" if self.year else ""
        if self.specific_track_keys:
            return f"{len(self.specific_track_keys)} track(s){yr}"
        return f"Full Album{yr}"

    @property
    def key_id(self) -> str:
        return f"album::{self.album_key}"

@dataclass
class SyncPlaylistTask:
    playlist_title: str
    playlist_key: str
    thumb_url: Optional[str] = None

    @property
    def display_title(self) -> str:
        return f"Playlist: {self.playlist_title}"

    @property
    def item_type_label(self) -> str:
        return "Playlist"

    @property
    def details_label(self) -> str:
        return "Plex Playlist"

    @property
    def key_id(self) -> str:
        return f"playlist::{self.playlist_key}"

@dataclass
class DeleteTask:
    artist_name: Optional[str] = None
    album_title: Optional[str] = None
    clean_trash_only: bool = False

    @property
    def display_title(self) -> str:
        if self.clean_trash_only:
            return "Clean Trash (.Trash-1000)"
        if self.album_title:
            return f"Delete: {self.artist_name} - {self.album_title}"
        return f"Delete Artist: {self.artist_name}"

    @property
    def item_type_label(self) -> str:
        return "Delete"

    @property
    def details_label(self) -> str:
        if self.clean_trash_only:
            return "Empty Trash"
        if self.album_title:
            return f"Album: {self.album_title}"
        return f"All albums by {self.artist_name}"

    @property
    def key_id(self) -> str:
        if self.clean_trash_only:
            return "delete::trash"
        if self.album_title:
            return f"delete::album::{self.artist_name}::{self.album_title}"
        return f"delete::artist::{self.artist_name}"

class SyncWorker(QObject):
    # Signals
    sync_started = Signal(int)  # total items
    album_started = Signal(str, str, int, int)  # artist, album, item_idx, total_items
    playlist_started = Signal(str, int, int)  # playlist_title, item_idx, total_items
    playlist_completed = Signal(str, int, int)  # playlist_title, tracks_synced, bytes_transferred
    delete_started = Signal(str, int, int)  # task_title, item_idx, total_items
    delete_completed = Signal(object, bool, int, str)  # task, success, freed_bytes, message
    track_started = Signal(str, int, int)  # track_title, track_idx, total_tracks
    track_progress = Signal(int, int, float)  # bytes_done, bytes_total, bytes_per_sec
    track_completed = Signal(str, bool, str)  # track_title, success, note
    album_completed = Signal(str, int, int)  # album_title, tracks_transferred, bytes_transferred
    sync_finished = Signal(int, int, list)  # total_tracks, total_bytes, errors
    queue_updated = Signal(int)  # remaining items in queue
    queue_changed = Signal(list)  # snapshot of upcoming queued items
    task_enqueued = Signal(object, int)  # task, position_1_indexed

    def __init__(self, plex: PlexManager, ipod_mount: str, config: AppConfig):
        super().__init__()
        self.plex = plex
        self.ipod_mount = Path(ipod_mount)
        self.config = config
        self._queue: List[Any] = []
        self._lock = threading.Lock()
        self._is_cancelled = False
        self.is_finished = False
        self.current_task: Optional[Any] = None
        self.completed_items_count: int = 0

        # Live snapshot fields for active transfer cards
        self.current_item_idx: int = 0
        self.total_items: int = 0
        self.current_track_title: Optional[str] = None
        self.current_track_idx: int = 0
        self.total_tracks: int = 0
        self.bytes_done: int = 0
        self.bytes_total: int = 0
        self.bytes_per_sec: float = 0.0

    def get_active_status(self) -> dict:
        """Thread-safe snapshot of the current active transfer state."""
        with self._lock:
            return {
                "task": self.current_task,
                "item_idx": self.current_item_idx,
                "total_items": self.total_items,
                "track_title": self.current_track_title,
                "track_idx": self.current_track_idx,
                "total_tracks": self.total_tracks,
                "bytes_done": self.bytes_done,
                "bytes_total": self.bytes_total,
                "speed": self.bytes_per_sec,
                "is_finished": self.is_finished,
            }

    def add_task(self, task: Any) -> int:
        """Thread-safe method to add any sync task to the queue."""
        with self._lock:
            self._queue.append(task)
            pos = len(self._queue)
            snapshot = list(self._queue)
        self.queue_updated.emit(pos)
        self.queue_changed.emit(snapshot)
        self.task_enqueued.emit(task, pos)
        return pos

    def add_album_task(self, task: SyncTask) -> int:
        return self.add_task(task)

    def add_playlist_task(self, task: SyncPlaylistTask) -> int:
        return self.add_task(task)

    def remove_task(self, index: int) -> Optional[Any]:
        """Thread-safe removal of a queued item by 0-based index."""
        with self._lock:
            if 0 <= index < len(self._queue):
                removed = self._queue.pop(index)
                snapshot = list(self._queue)
            else:
                return None
        self.queue_updated.emit(len(snapshot))
        self.queue_changed.emit(snapshot)
        return removed

    def clear_queue(self) -> int:
        """Thread-safe clearing of all upcoming queued tasks."""
        with self._lock:
            cleared_count = len(self._queue)
            self._queue.clear()
            snapshot = []
        self.queue_updated.emit(0)
        self.queue_changed.emit(snapshot)
        return cleared_count

    def get_queue_snapshot(self) -> tuple[Optional[Any], List[Any]]:
        """Returns (current_task, list_of_queued_tasks)."""
        with self._lock:
            return self.current_task, list(self._queue)

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        self._is_cancelled = False
        self.is_finished = False
        self.completed_items_count = 0

        with self._lock:
            total_items = len(self._queue)
            self.queue_changed.emit(list(self._queue))
        self.sync_started.emit(total_items)

        overall_tracks = 0
        overall_bytes = 0
        errors = []

        try:
            while not self._is_cancelled:
                with self._lock:
                    if not self._queue:
                        self.current_task = None
                        self.current_track_title = None
                        break
                    task = self._queue.pop(0)
                    self.current_task = task
                    current_queue_len = len(self._queue)
                    snapshot = list(self._queue)

                self.queue_updated.emit(current_queue_len)
                self.queue_changed.emit(snapshot)

                item_idx = self.completed_items_count + 1
                total_items = self.completed_items_count + 1 + current_queue_len
                self.current_item_idx = item_idx
                self.total_items = total_items
                self.bytes_done = 0
                self.bytes_total = 0
                self.bytes_per_sec = 0.0

                if isinstance(task, DeleteTask):
                    self.current_track_title = f"Deleting {task.display_title}"
                    self.current_track_idx = 1
                    self.total_tracks = 1
                    self.delete_started.emit(task.display_title, item_idx, total_items)
                    success, freed, msg = self._process_delete(task)
                    if success:
                        overall_bytes += freed
                    else:
                        errors.append(f"Delete '{task.display_title}': {msg}")
                    self.delete_completed.emit(task, success, freed, msg)
                elif isinstance(task, SyncPlaylistTask):
                    self.current_track_title = "Resolving playlist tracks..."
                    self.current_track_idx = 0
                    self.total_tracks = 0
                    self.playlist_started.emit(task.playlist_title, item_idx, total_items)
                    tracks_synced, new_bytes, errs = self._process_playlist(task)
                    overall_tracks += tracks_synced
                    overall_bytes += new_bytes
                    errors.extend(errs)
                    self.playlist_completed.emit(task.playlist_title, tracks_synced, new_bytes)
                else:
                    self.current_track_title = "Starting album transfer..."
                    self.current_track_idx = 0
                    self.total_tracks = 0
                    self.album_started.emit(task.artist_name, task.album_title, item_idx, total_items)
                    album_tracks_transferred, album_bytes, errs = self._process_album(task)
                    overall_tracks += album_tracks_transferred
                    overall_bytes += album_bytes
                    errors.extend(errs)
                    self.album_completed.emit(task.album_title, album_tracks_transferred, album_bytes)

                self.completed_items_count += 1
        finally:
            with self._lock:
                self.current_task = None
                self.current_track_title = None
                self.is_finished = True

        self.sync_finished.emit(overall_tracks, overall_bytes, errors)

    def _process_delete(self, task: DeleteTask) -> tuple[bool, int, str]:
        from vibetunes.core.ipod_scanner import (
            find_and_delete_ipod_album,
            find_and_delete_ipod_artist,
            clean_trash
        )
        mount_str = str(self.ipod_mount)
        if task.clean_trash_only:
            return clean_trash(mount_str)
        if task.album_title and task.artist_name:
            return find_and_delete_ipod_album(mount_str, task.artist_name, task.album_title)
        if task.artist_name:
            return find_and_delete_ipod_artist(mount_str, task.artist_name)
        return False, 0, "Invalid delete task"

    def _determine_album_folder(self, task: SyncTask, tracks: List[PlexTrackDetail]) -> Path:
        artist_clean = clean_fat32_name(task.artist_name)
        album_clean = clean_fat32_name(task.album_title)

        # 1. Determine target album directory
        fat32_rel = None
        if tracks and tracks[0].original_filename:
            fat32_rel = self.plex.get_fat32_media_path(tracks[0].original_filename)

        if self.config.naming_pattern == "plex_exact" and fat32_rel and len(fat32_rel.parts) >= 2:
            target_artist_dir = fat32_rel.parts[0]
            target_album_dir_name = fat32_rel.parts[1]
            target_album_dir = self.ipod_mount / target_artist_dir / target_album_dir_name
        elif self.config.naming_pattern == "rockbox_disc":
            if task.year:
                folder_name = f"{artist_clean}-{task.year}-{album_clean}"
            else:
                folder_name = f"{artist_clean}-{album_clean}"
            target_album_dir = self.ipod_mount / artist_clean / folder_name
        else:
            folder_name = album_clean
            target_album_dir = self.ipod_mount / artist_clean / folder_name

        # 2. Check if an album folder for this album already exists under artist directory
        from vibetunes.core.ipod_scanner import parse_album_folder_name
        from vibetunes.core.naming_sync import is_album_match, _clean_empty_tree
        norm_art = normalize_music_key(task.artist_name)

        artist_candidates = [self.ipod_mount / artist_clean]
        try:
            for entry in self.ipod_mount.iterdir():
                if entry.is_dir() and normalize_music_key(entry.name) == norm_art and entry not in artist_candidates:
                    artist_candidates.append(entry)
        except Exception:
            pass

        found_existing_dir: Optional[Path] = None
        for ad in artist_candidates:
            if not ad.is_dir():
                continue
            try:
                for d in ad.iterdir():
                    if not d.is_dir():
                        continue
                    has_audio = any(
                        f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
                        for f in d.rglob("*")
                    )
                    if not has_audio:
                        continue
                    clean_title, _ = parse_album_folder_name(d.name, task.artist_name)
                    if is_album_match(clean_title, task.album_title) or is_album_match(d.name, task.album_title):
                        found_existing_dir = d
                        break
            except Exception:
                pass
            if found_existing_dir:
                break

        # 3. If an existing directory was found, rename it in-place to target_album_dir if needed
        if found_existing_dir:
            if found_existing_dir.resolve() != target_album_dir.resolve():
                try:
                    target_album_dir.parent.mkdir(parents=True, exist_ok=True)
                    if target_album_dir.exists():
                        # Target already exists: merge files safely without deletion
                        for root, dirs, files in os.walk(found_existing_dir):
                            rel_root = Path(root).relative_to(found_existing_dir)
                            dest_sub = target_album_dir / rel_root
                            dest_sub.mkdir(parents=True, exist_ok=True)
                            for f in files:
                                src_f = Path(root) / f
                                dst_f = dest_sub / f
                                if not dst_f.exists():
                                    shutil.move(str(src_f), str(dst_f))
                        _clean_empty_tree(found_existing_dir)
                    else:
                        # Direct rename (handling FAT32 case-only difference safely)
                        if found_existing_dir.name.lower() == target_album_dir.name.lower():
                            tmp = found_existing_dir.parent / f"{found_existing_dir.name}_vttmp"
                            shutil.move(str(found_existing_dir), str(tmp))
                            shutil.move(str(tmp), str(target_album_dir))
                        else:
                            shutil.move(str(found_existing_dir), str(target_album_dir))
                    return target_album_dir
                except Exception:
                    return found_existing_dir
            return found_existing_dir

        return target_album_dir

    def _process_album(self, task: SyncTask) -> tuple[int, int, list[str]]:
        tracks = self.plex.get_album_tracks(task.album_key)
        if not tracks:
            return 0, 0, [f"No tracks found for album {task.album_title}"]

        if task.specific_track_keys:
            tracks = [t for t in tracks if t.rating_key in task.specific_track_keys]
            if not tracks:
                return 0, 0, [f"Selected tracks not found in album {task.album_title}"]

        album_dir = self._determine_album_folder(task, tracks)
        try:
            album_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return 0, 0, [f"Failed to create directory {album_dir}: {e}"]

        # Save album cover artwork for Rockbox
        if self.config.download_artwork and task.thumb_url:
            self._save_album_art(task.thumb_url, album_dir)

        # Check if multi-disc
        max_disc = max((t.disc_number for t in tracks), default=1)
        is_multidisc = max_disc > 1

        tracks_transferred = 0
        bytes_transferred = 0
        errors = []

        total_tracks = len(tracks)
        for i, track in enumerate(tracks):
            if self._is_cancelled:
                break

            self.current_track_title = track.title
            self.current_track_idx = i + 1
            self.total_tracks = total_tracks
            self.bytes_done = 0
            self.bytes_total = track.size_bytes or 0
            self.bytes_per_sec = 0.0
            self.track_started.emit(track.title, i + 1, total_tracks)

            # Determine destination track path
            fat32_rel_track = self.plex.get_fat32_media_path(track.original_filename) if track.original_filename else None
            if self.config.naming_pattern == "plex_exact" and fat32_rel_track and len(fat32_rel_track.parts) >= 2:
                sub_parts = fat32_rel_track.parts[2:]
                if len(sub_parts) > 1:
                    target_dir = album_dir / Path(*sub_parts[:-1])
                    dest_file = target_dir / sub_parts[-1]
                elif len(sub_parts) == 1:
                    target_dir = album_dir
                    dest_file = target_dir / sub_parts[0]
                else:
                    target_dir = album_dir
                    track_title_clean = clean_fat32_name(track.title)
                    ext = track.container or "flac"
                    dest_file = target_dir / f"{track.track_number:02d} - {track_title_clean}.{ext}"
                target_dir.mkdir(parents=True, exist_ok=True)
            else:
                if is_multidisc and self.config.naming_pattern == "rockbox_disc":
                    target_dir = album_dir / f"CD {track.disc_number:02d}"
                    target_dir.mkdir(exist_ok=True)
                else:
                    target_dir = album_dir
                track_title_clean = clean_fat32_name(track.title)
                ext = track.container or "flac"
                dest_file = target_dir / f"{track.track_number:02d} - {track_title_clean}.{ext}"

            # Check if file already exists on iPod (skip unless force_overwrite is requested)
            if not task.force_overwrite:
                existing_file = None
                if dest_file.exists() and dest_file.stat().st_size > 0:
                    existing_file = dest_file
                else:
                    existing_file = find_track_on_ipod(
                        ipod_mount=self.ipod_mount,
                        artist_name=task.artist_name,
                        album_title=task.album_title,
                        track_title=track.title,
                        track_number=track.track_number,
                        disc_number=track.disc_number,
                    )

                if existing_file and existing_file.exists() and existing_file.stat().st_size > 0:
                    # Rename existing file in-place to dest_file if naming differed
                    if existing_file.resolve() != dest_file.resolve() and not dest_file.exists():
                        try:
                            dest_file.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(existing_file), str(dest_file))
                        except Exception:
                            pass
                    self.track_completed.emit(track.title, True, "Already on iPod (skipped)")
                    tracks_transferred += 1
                    continue

            success, transferred, err_msg = self._download_track(track, dest_file)
            if success:
                tracks_transferred += 1
                bytes_transferred += transferred
                self.track_completed.emit(track.title, True, "OK")
            else:
                errors.append(f"{track.title}: {err_msg}")
                self.track_completed.emit(track.title, False, err_msg)

        return tracks_transferred, bytes_transferred, errors

    def _save_album_art(self, thumb_url: str, album_dir: Path) -> None:
        cover_path = album_dir / "cover.jpg"
        if cover_path.exists():
            return
        art_data = self.plex.download_artwork_bytes(thumb_url)
        if art_data:
            try:
                with open(cover_path, "wb") as f:
                    f.write(art_data)
            except Exception:
                pass

    def _download_track(self, track: PlexTrackDetail, dest_path: Path) -> tuple[bool, int, str]:
        temp_dest = dest_path.with_suffix(dest_path.suffix + ".part")
        stream_url = track.stream_url
        if not stream_url:
            return False, 0, "No stream URL"

        url_with_token = f"{stream_url}?X-Plex-Token={self.plex.token}" if "?" not in stream_url else f"{stream_url}&X-Plex-Token={self.plex.token}"

        try:
            with requests.get(url_with_token, stream=True, timeout=30) as r:
                if r.status_code != 200:
                    return False, 0, f"HTTP {r.status_code}"

                total_size = int(r.headers.get("content-length", track.size_bytes or 0))
                bytes_downloaded = 0
                start_time = time.time()
                last_update = start_time

                with open(temp_dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=128 * 1024):
                        if self._is_cancelled:
                            f.close()
                            if temp_dest.exists():
                                temp_dest.unlink()
                            return False, 0, "Cancelled"

                        if chunk:
                            f.write(chunk)
                            bytes_downloaded += len(chunk)

                            now = time.time()
                            if now - last_update >= 0.2:
                                elapsed = now - start_time
                                speed = bytes_downloaded / elapsed if elapsed > 0 else 0
                                self.bytes_done = bytes_downloaded
                                self.bytes_total = total_size
                                self.bytes_per_sec = speed
                                self.track_progress.emit(bytes_downloaded, total_size, speed)
                                last_update = now

            # Rename .part to final file
            if temp_dest.exists():
                temp_dest.replace(dest_path)
            return True, bytes_downloaded, ""

        except Exception as e:
            if temp_dest.exists():
                try:
                    temp_dest.unlink()
                except OSError:
                    pass
            return False, 0, str(e)

    def _process_playlist(self, task: SyncPlaylistTask) -> tuple[int, int, list[str]]:
        tracks = self.plex.get_playlist_tracks(task.playlist_key)
        if not tracks:
            return 0, 0, [f"No tracks found in playlist '{task.playlist_title}'"]

        pl_dir = self.ipod_mount / "Playlists"
        try:
            pl_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return 0, 0, [f"Could not create Playlists folder on iPod: {e}"]

        pl_filename = f"{clean_fat32_name(task.playlist_title)}.m3u8"
        pl_file = pl_dir / pl_filename

        playlist_lines: List[str] = []
        new_downloads = 0
        bytes_downloaded = 0
        errors = []

        total_tracks = len(tracks)
        for i, track in enumerate(tracks):
            if self._is_cancelled:
                break

            self.current_track_title = f"[{task.playlist_title}] {track.title}"
            self.current_track_idx = i + 1
            self.total_tracks = total_tracks
            self.bytes_done = 0
            self.bytes_total = track.size_bytes or 0
            self.bytes_per_sec = 0.0
            self.track_started.emit(f"[{task.playlist_title}] {track.title}", i + 1, total_tracks)

            # 1. Search if track already exists anywhere on iPod
            track_file = find_track_on_ipod(
                ipod_mount=self.ipod_mount,
                artist_name=track.artist_name,
                album_title=track.album_title,
                track_title=track.title,
                track_number=track.track_number,
                disc_number=track.disc_number,
            )

            if track_file and track_file.exists():
                self.track_completed.emit(track.title, True, "Already on iPod (skipped)")
            else:
                # 2. Track missing from iPod - download from Plex
                artist_clean = clean_fat32_name(track.artist_name)
                album_clean = clean_fat32_name(track.album_title)
                year_part = f"-{track.year}" if getattr(track, "year", None) else ""

                if self.config.naming_pattern == "rockbox_disc":
                    folder_name = f"{artist_clean}{year_part}-{album_clean}" if year_part else f"{artist_clean}-{album_clean}"
                else:
                    folder_name = album_clean

                album_dir = self.ipod_mount / artist_clean / folder_name
                if track.disc_number > 1 and self.config.naming_pattern == "rockbox_disc":
                    target_dir = album_dir / f"CD {track.disc_number:02d}"
                else:
                    target_dir = album_dir

                try:
                    target_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    errors.append(f"Cannot create folder {target_dir}: {e}")
                    self.track_completed.emit(track.title, False, str(e))
                    continue

                track_title_clean = clean_fat32_name(track.title)
                ext = track.container or "flac"
                expected_file = target_dir / f"{track.track_number:02d} - {track_title_clean}.{ext}"

                success, transferred, err_msg = self._download_track(track, expected_file)
                if success:
                    track_file = expected_file
                    new_downloads += 1
                    bytes_downloaded += transferred
                    self.track_completed.emit(track.title, True, "Downloaded for playlist")
                else:
                    errors.append(f"Playlist track '{track.title}': {err_msg}")
                    self.track_completed.emit(track.title, False, err_msg)
                    continue

            # Convert to Rockbox path format: /<HDD0>/Artist/...
            try:
                rel = track_file.relative_to(self.ipod_mount).as_posix()
                rockbox_path = f"/<HDD0>/{rel}"
                playlist_lines.append(rockbox_path)
            except Exception as e:
                errors.append(f"Failed to generate Rockbox path for {track_file}: {e}")

        # Write playlist file with UTF-8 BOM
        try:
            with open(pl_file, "w", encoding="utf-8-sig", newline="\n") as f:
                for line in playlist_lines:
                    f.write(line + "\n")
        except Exception as e:
            errors.append(f"Failed to save playlist file {pl_file}: {e}")

        return len(playlist_lines), bytes_downloaded, errors

