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

def test_repair_ipod_playlists():
    from vibetunes.core.naming_sync import repair_ipod_playlists
    with tempfile.TemporaryDirectory() as tmpdir:
        ipod_root = Path(tmpdir)
        pl_dir = ipod_root / "Playlists"
        pl_dir.mkdir(parents=True)

        # Create actual music files under Plex-aligned names
        ash_album = ipod_root / "Ash" / "1994-Trailer (Ash)"
        ash_album.mkdir(parents=True)
        (ash_album / "02 - Jack Names the Planets.flac").write_bytes(b"audio1")

        blur_album = ipod_root / "Blur" / "1994-Parklife (Blur)"
        blur_album.mkdir(parents=True)
        (blur_album / "03 - End of a Century.mp3").write_bytes(b"audio2")

        # Create playlist with old broken paths
        test_pl = pl_dir / "Favorites.m3u8"
        broken_lines = [
            "/<HDD0>/Ash/Ash-1994-Trailer/02 - Jack Names the Planets.flac",
            "/<HDD0>/Blur/Blur-Parklife/03 - End of a Century.mp3",
        ]
        test_pl.write_text("\n".join(broken_lines) + "\n", encoding="utf-8-sig")

        # Run repair
        repaired_pls, repaired_tracks, unresolved = repair_ipod_playlists(ipod_root)
        assert repaired_pls == 1
        assert repaired_tracks == 2
        assert len(unresolved) == 0

        # Verify repaired playlist content
        repaired_lines = [l.strip() for l in test_pl.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
        assert len(repaired_lines) == 2
        assert repaired_lines[0] == "/<HDD0>/Ash/1994-Trailer (Ash)/02 - Jack Names the Planets.flac"
        assert repaired_lines[1] == "/<HDD0>/Blur/1994-Parklife (Blur)/03 - End of a Century.mp3"

def test_find_track_on_ipod_plex_exact_and_cross_album_guard():
    from vibetunes.core.plex_client import PlexManager
    with tempfile.TemporaryDirectory() as tmpdir:
        ipod_root = Path(tmpdir)

        # 1. Pavement album in Plex-exact layout
        pav_album = ipod_root / "Pavement" / "1992-Slanted and Enchanted (Pavement)"
        pav_album.mkdir(parents=True)
        track1 = pav_album / "01 - Summer Babe (Winter version).flac"
        track1.write_bytes(b"audio")

        plex = PlexManager("http://localhost:32400", "dummy")
        plex.library_locations["Music"] = ["/data/media/music"]

        # Fast path with original_filename
        res = find_track_on_ipod(
            ipod_mount=ipod_root,
            artist_name="Pavement",
            album_title="Slanted & Enchanted: Luxe & Reduxe",
            track_title="Summer Babe (Winter version)",
            track_number=1,
            original_filename="/data/media/music/Pavement/1992-Slanted and Enchanted (Pavement)/01 - Summer Babe (Winter version).flac",
            plex=plex
        )
        assert res == track1

        # Match via is_album_match when original_filename is omitted
        res2 = find_track_on_ipod(
            ipod_mount=ipod_root,
            artist_name="Pavement",
            album_title="Slanted & Enchanted: Luxe & Reduxe",
            track_title="Summer Babe",
            track_number=1
        )
        assert res2 == track1

        # 2. Cross-album guard test:
        # Create Guns N' Roses Appetite for Destruction CD 2 with bonus track "Patience"
        gnr_appetite = ipod_root / "Guns N' Roses" / "1987-Appetite for Destruction (Guns N' Roses)" / "CD 02"
        gnr_appetite.mkdir(parents=True)
        (gnr_appetite / "07 - Patience.flac").write_bytes(b"bonus_audio")

        # Now search for track "Patience" from album "G N' R Lies"
        # It must NOT return the Appetite for Destruction bonus track!
        res_cross = find_track_on_ipod(
            ipod_mount=ipod_root,
            artist_name="Guns N' Roses",
            album_title="G N' R Lies",
            track_title="Patience",
            track_number=5,
            disc_number=1
        )
        assert res_cross is None

def test_sync_playlist_plex_exact_naming():
    with tempfile.TemporaryDirectory() as tmpdir:
        ipod_root = Path(tmpdir)

        mock_plex = MagicMock()
        mock_plex.library_locations = {"Music": ["/data/media/music"]}
        mock_plex.get_fat32_media_path.side_effect = lambda orig: Path("Ash/1996-1977 (Ash)/02 - Goldfinger.flac")

        missing_track = PlexTrackDetail(
            rating_key="202",
            title="Goldfinger",
            artist_name="Ash",
            album_title="1977",
            track_number=2,
            disc_number=1,
            duration_ms=200000,
            size_bytes=1000,
            container="flac",
            stream_url="http://mock/stream2",
            original_filename="/data/media/music/Ash/1996-1977 (Ash)/02 - Goldfinger.flac",
            year=1996,
        )
        mock_plex.get_playlist_tracks.return_value = [missing_track]

        cfg = AppConfig(naming_pattern="plex_exact")
        worker = SyncWorker(mock_plex, str(ipod_root), cfg)

        def fake_download(track, dest_path):
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(b"downloaded")
            return True, len(b"downloaded"), ""

        worker._download_track = MagicMock(side_effect=fake_download)

        task = SyncPlaylistTask(playlist_title="Ash Best Of", playlist_key="999")
        worker.add_playlist_task(task)
        worker.run()

        # Verify missing track downloaded into Plex layout
        expected_file = ipod_root / "Ash" / "1996-1977 (Ash)" / "02 - Goldfinger.flac"
        assert expected_file.exists()

        # Verify playlist path matches Plex layout
        pl_file = ipod_root / "Playlists" / "Ash Best Of.m3u8"
        assert pl_file.exists()
        content = pl_file.read_text(encoding="utf-8-sig")
        assert "/<HDD0>/Ash/1996-1977 (Ash)/02 - Goldfinger.flac" in content


