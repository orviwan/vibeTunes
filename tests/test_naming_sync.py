"""Tests for Plex file/folder naming conventions and non-destructive rename synchronization."""
import tempfile
import shutil
from pathlib import Path
import pytest

from PySide6.QtWidgets import QLabel
from vibetunes.core.plex_client import PlexManager, PlexTrackDetail, PlexAlbumSummary, PlexArtistSummary
from vibetunes.core.naming_sync import (
    is_album_match, RenameProposal, inspect_ipod_naming_alignment, apply_naming_alignment
)
from vibetunes.core.sync_engine import SyncWorker, SyncTask
from vibetunes.core.config import AppConfig

def test_plex_media_path_resolution():
    plex = PlexManager("http://localhost:32400", "dummy")
    plex.library_locations["Music"] = ["/data/media/music"]

    orig = "/data/media/music/Pavement/1992-Slanted and Enchanted (Pavement)/Digital Media 01/01 - Summer Babe (Winter version).flac"
    rel = plex.get_relative_media_path(orig)
    assert rel == Path("Pavement/1992-Slanted and Enchanted (Pavement)/Digital Media 01/01 - Summer Babe (Winter version).flac")

    fat32_rel = plex.get_fat32_media_path(orig)
    assert fat32_rel == Path("Pavement/1992-Slanted and Enchanted (Pavement)/Digital Media 01/01 - Summer Babe (Winter version).flac")

    # Path with FAT32-invalid chars: colon, question mark, quotes
    orig_invalid = '/data/media/music/Artist: Name/2020-Album: Subtitle?/01 - Song "Title".mp3'
    fat32_clean = plex.get_fat32_media_path(orig_invalid)
    assert ":" not in str(fat32_clean)
    assert "?" not in str(fat32_clean)
    assert '"' not in str(fat32_clean)

def test_is_album_match():
    # Exact match
    assert is_album_match("AM", "AM") is True
    # Substring false positive guard for short strings
    assert is_album_match("AM", "Whatever People Say I Am, That’s What I’m Not") is False

    # Edition and subtitle matching
    assert is_album_match("Slanted and Enchanted", "Slanted & Enchanted: Luxe & Reduxe") is True
    assert is_album_match("Crooked Rain, Crooked Rain", "Crooked Rain, Crooked Rain: LA's Desert Origins") is True
    assert is_album_match("Wowee Zowee", "Wowee Zowee (Sordid Sentinels Edition)") is True

def test_naming_alignment_and_apply():
    with tempfile.TemporaryDirectory() as tmp_ipod:
        ipod_root = Path(tmp_ipod)

        # Create iPod album folder with legacy naming: "Pavement/Pavement-1992-Slanted and Enchanted"
        old_album_dir = ipod_root / "Pavement" / "Pavement-1992-Slanted and Enchanted"
        old_disc_dir = old_album_dir / "Digital Media 01"
        old_disc_dir.mkdir(parents=True, exist_ok=True)
        track_file = old_disc_dir / "01 - Summer Babe (Winter version).flac"
        track_file.write_bytes(b"dummy audio content 12345")

        target_dir = ipod_root / "Pavement" / "1992-Slanted and Enchanted (Pavement)"

        proposal = RenameProposal(
            current_path=old_album_dir,
            target_path=target_dir,
            is_dir=True,
            artist_name="Pavement",
            album_title="Slanted & Enchanted: Luxe & Reduxe",
            item_count=1,
            description="Rename to Plex convention",
        )

        renamed_cnt, errors = apply_naming_alignment([proposal])
        assert renamed_cnt == 1
        assert len(errors) == 0

        # Old folder should no longer exist; target folder must exist with all contents preserved
        assert not old_album_dir.exists()
        assert target_dir.exists()
        target_track = target_dir / "Digital Media 01" / "01 - Summer Babe (Winter version).flac"
        assert target_track.exists()
        assert target_track.read_bytes() == b"dummy audio content 12345"

def test_sync_engine_auto_rename_on_sync():
    with tempfile.TemporaryDirectory() as tmp_ipod:
        ipod_root = Path(tmp_ipod)

        # Create old iPod folder with an existing audio file
        old_album_dir = ipod_root / "Pavement" / "Pavement-1992-Slanted and Enchanted"
        old_album_dir.mkdir(parents=True, exist_ok=True)
        track_file = old_album_dir / "01 - Summer Babe.flac"
        track_file.write_bytes(b"audio content")

        cfg = AppConfig(naming_pattern="plex_exact")
        plex = PlexManager("http://localhost:32400", "dummy")
        plex.library_locations["Music"] = ["/data/media/music"]

        worker = SyncWorker(
            plex=plex,
            ipod_mount=str(ipod_root),
            config=cfg,
        )

        task = SyncTask(
            album_key="123",
            artist_name="Pavement",
            album_title="Slanted & Enchanted: Luxe & Reduxe",
            year=1992
        )

        dummy_track = PlexTrackDetail(
            rating_key="1",
            title="Summer Babe",
            artist_name="Pavement",
            album_title="Slanted & Enchanted: Luxe & Reduxe",
            track_number=1,
            original_filename="/data/media/music/Pavement/1992-Slanted and Enchanted (Pavement)/01 - Summer Babe.flac"
        )

        # When _determine_album_folder runs, it should rename old_album_dir to Plex target
        album_dir = worker._determine_album_folder(task, [dummy_track])
        expected_dir = ipod_root / "Pavement" / "1992-Slanted and Enchanted (Pavement)"
        assert album_dir == expected_dir
        assert expected_dir.exists()
        assert not old_album_dir.exists()
        # Track file inside preserved
        assert (expected_dir / "01 - Summer Babe.flac").exists()

def test_naming_sync_dialog_ui(qapp):
    from vibetunes.ui.widgets.naming_sync_dialog import NamingSyncDialog
    plex = PlexManager("http://localhost:32400", "dummy")
    dlg = NamingSyncDialog(ipod_mount="", plex=plex, library_name="Music", auto_scan=False)
    assert dlg.windowTitle() == "vibeTunes — Align iPod File & Folder Naming with Plex"
    dlg.close()
