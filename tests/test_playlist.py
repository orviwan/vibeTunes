from unittest.mock import MagicMock
from pathlib import Path
import tempfile

from vibetunes.core.config import AppConfig
from vibetunes.core.plex_client import PlexTrackDetail
from vibetunes.core.sync_engine import SyncWorker, SyncPlaylistTask, find_track_on_ipod
from vibetunes.core.ipod_scanner import scan_ipod_playlists, delete_playlist, iPodPlaylist

def test_playlist_m3u8_format():
    # Test Rockbox path formatting and UTF-8 BOM encoding
    with tempfile.TemporaryDirectory() as tmpdir:
        pl_dir = Path(tmpdir) / "Playlists"
        pl_dir.mkdir()
        pl_file = pl_dir / "Rockbox Favorites.m3u8"

        lines = [
            "/<HDD0>/Radiohead/Radiohead-1997-OK Computer/CD 01/01 - Airbag.flac",
            "/<HDD0>/Blur/Blur-1994-Parklife/03 - End of a Century.flac"
        ]

        with open(pl_file, "w", encoding="utf-8-sig", newline="\n") as f:
            for line in lines:
                f.write(line + "\n")

        # Read back raw bytes to verify UTF-8 BOM
        raw = pl_file.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf/<HDD0>/")

        # Verify scanning
        pls = scan_ipod_playlists(tmpdir)
        assert len(pls) == 1
        assert pls[0].name == "Rockbox Favorites"
        assert pls[0].track_count == 2

        # Verify deletion
        ok, msg = delete_playlist(pls[0])
        assert ok is True
        assert not pl_file.exists()

def test_find_track_on_ipod():
    with tempfile.TemporaryDirectory() as tmpdir:
        ipod_root = Path(tmpdir)

        # Structure on iPod:
        # Ash/Ash-1996-1977/01 - Lose Control.flac
        # Ash/Ash-1996-1977/04 - I’d Give You Anything.flac
        # Radiohead/Radiohead-1997-OK Computer/CD 01/01 - Airbag.flac
        # Blur/Parklife/03 - End of a Century.mp3
        ash_album = ipod_root / "Ash" / "Ash-1996-1977"
        ash_album.mkdir(parents=True)
        (ash_album / "01 - Lose Control.flac").write_bytes(b"dummy")
        (ash_album / "04 - I’d Give You Anything.flac").write_bytes(b"dummy")

        rh_cd1 = ipod_root / "Radiohead" / "Radiohead-1997-OK Computer" / "CD 01"
        rh_cd1.mkdir(parents=True)
        (rh_cd1 / "01 - Airbag.flac").write_bytes(b"dummy")

        blur_album = ipod_root / "Blur" / "Parklife"
        blur_album.mkdir(parents=True)
        (blur_album / "03 - End of a Century.mp3").write_bytes(b"dummy")

        # 1. Match track when folder includes release year
        res = find_track_on_ipod(ipod_root, "Ash", "1977", "Lose Control", 1)
        assert res is not None
        assert res.name == "01 - Lose Control.flac"

        # 2. Match track with curly quote in filename
        res = find_track_on_ipod(ipod_root, "Ash", "1977", "I'd Give You Anything", 4)
        assert res is not None
        assert res.name == "04 - I’d Give You Anything.flac"

        # 3. Match track in multi-disc folder
        res = find_track_on_ipod(ipod_root, "Radiohead", "OK Computer", "Airbag", 1, disc_number=1)
        assert res is not None
        assert "CD 01" in str(res)

        # 4. Match track with different audio extension (.mp3 on iPod)
        res = find_track_on_ipod(ipod_root, "Blur", "Parklife", "End of a Century", 3)
        assert res is not None
        assert res.name == "03 - End of a Century.mp3"

        # 5. Non-existent track returns None
        res = find_track_on_ipod(ipod_root, "Ash", "1977", "Nonexistent Track", 99)
        assert res is None

def test_sync_playlist_skips_existing_tracks():
    with tempfile.TemporaryDirectory() as tmpdir:
        ipod_root = Path(tmpdir)

        # Create an existing track on the iPod
        ash_album = ipod_root / "Ash" / "Ash-1996-1977"
        ash_album.mkdir(parents=True)
        existing_file = ash_album / "01 - Lose Control.flac"
        existing_file.write_bytes(b"existing_audio_data")

        # Set up a mock Plex manager
        mock_plex = MagicMock()
        mock_tracks = [
            PlexTrackDetail(
                rating_key="101",
                title="Lose Control",
                artist_name="Ash",
                album_title="1977",
                track_number=1,
                disc_number=1,
                duration_ms=180000,
                size_bytes=len(b"existing_audio_data"),
                container="flac",
                stream_url="http://mock/stream1",
                year=1996,
            ),
            PlexTrackDetail(
                rating_key="102",
                title="Goldfinger",
                artist_name="Ash",
                album_title="1977",
                track_number=2,
                disc_number=1,
                duration_ms=200000,
                size_bytes=1000,
                container="flac",
                stream_url="http://mock/stream2",
                year=1996,
            ),
        ]
        mock_plex.get_playlist_tracks.return_value = mock_tracks

        config = AppConfig(naming_pattern="rockbox_disc")
        worker = SyncWorker(mock_plex, str(ipod_root), config)

        # Mock _download_track so it creates the file for missing track 2
        def fake_download(track, dest_path):
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(b"downloaded_track_2")
            return True, len(b"downloaded_track_2"), ""

        worker._download_track = MagicMock(side_effect=fake_download)

        task = SyncPlaylistTask(playlist_title="Ash Best Of", playlist_key="999")
        worker.add_playlist_task(task)

        # Run sync
        worker.run()

        # Verify: _download_track was only called for track 2 (Goldfinger), NOT for track 1 (Lose Control)
        assert worker._download_track.call_count == 1
        called_track = worker._download_track.call_args[0][0]
        assert called_track.title == "Goldfinger"

        # Verify playlist file was created
        pl_file = ipod_root / "Playlists" / "Ash Best Of.m3u8"
        assert pl_file.exists()

        content = pl_file.read_text(encoding="utf-8-sig")
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        assert len(lines) == 2
        assert lines[0] == "/<HDD0>/Ash/Ash-1996-1977/01 - Lose Control.flac"
        assert lines[1] == "/<HDD0>/Ash/Ash-1996-1977/02 - Goldfinger.flac"

