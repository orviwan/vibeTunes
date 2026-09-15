import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from vibestunes.core.demo_data import (
    DEMO_CATALOG,
    DEMO_PLAYLISTS,
    DemoPlexManager,
    DemoSyncWorker,
    generate_demo_art,
    get_demo_device,
    get_demo_ipod_state,
)
from vibestunes.core.sync_engine import DeleteTask, SyncTask


def test_demo_catalog_and_procedural_art(qapp):
    assert len(DEMO_CATALOG) >= 6
    artist_names = [e["artist"] for e in DEMO_CATALOG]
    assert "The Solar Echoes" in artist_names
    assert "Subatomic Pulse" in artist_names

    # Check that procedural art generates a valid pixmap
    pix = generate_demo_art("demo://album/The Solar Echoes/Celestial Drifter", size=300)
    assert isinstance(pix, QPixmap)
    assert not pix.isNull()
    assert pix.width() == 300
    assert pix.height() == 300

    # Test playlist cover art
    pl_pix = generate_demo_art("demo://playlist/Focus & Coding", size=300)
    assert isinstance(pl_pix, QPixmap)
    assert not pl_pix.isNull()


def test_demo_plex_manager(qapp):
    plex = DemoPlexManager()
    success, msg = plex.connect()
    assert success is True
    assert plex.is_connected() is True

    libs = plex.get_music_libraries()
    assert len(libs) > 0
    assert "Lossless Music (Demo)" in libs

    artists = plex.get_artists()
    assert len(artists) == len(DEMO_CATALOG)
    first_art = artists[0]
    assert first_art.rating_key == "art_1"

    albums = plex.get_artist_albums("art_1")
    assert len(albums) == len(DEMO_CATALOG[0]["albums"])
    first_alb = albums[0]
    assert first_alb.rating_key == "alb_1_1"

    tracks = plex.get_album_tracks("alb_1_1")
    assert len(tracks) == len(DEMO_CATALOG[0]["albums"][0]["tracks"])
    assert tracks[0].container == "flac"
    assert tracks[0].bitrate == 1411

    playlists = plex.get_all_playlists()
    assert len(playlists) == len(DEMO_PLAYLISTS)

    pl_tracks = plex.get_playlist_tracks(playlists[0].rating_key)
    assert len(pl_tracks) > 0

    art_bytes = plex.download_artwork_bytes("demo://album/Subatomic Pulse/Quantum Resonance")
    assert art_bytes is not None
    assert len(art_bytes) > 100


def test_demo_device_and_ipod_state():
    device = get_demo_device()
    assert device is not None
    assert "iPod" in device.model_name
    assert device.storage.total > 100 * 1000 * 1000 * 1000  # ~160GB
    assert device.storage.free > 0
    assert device.storage.music > 0

    on_ipod_albums, ipod_album_data, ipod_artist_album_counts, ipod_artists = get_demo_ipod_state()
    assert len(on_ipod_albums) > 0
    assert len(ipod_album_data) > 0
    assert len(ipod_artist_album_counts) > 0
    assert len(ipod_artists) > 0

    # Check partial album status exists in demo state
    has_partial = False
    for k, data in ipod_album_data.items():
        if "subatomic pulse" in k.lower():
            has_partial = True
            assert data["track_count"] < 10
    assert has_partial is True


def test_demo_sync_worker_execution(qapp):
    sync_task = SyncTask(
        artist_name="Neon Mirage",
        album_title="Prism Frequency",
        album_key="alb_2_1",
        year=2024,
        thumb_url="demo://album/Neon Mirage/Prism Frequency",
        specific_track_keys=["trk_1", "trk_2"]
    )
    del_task = DeleteTask(
        artist_name="The Paper Birds",
        album_title="North & Byways"
    )

    worker = DemoSyncWorker([sync_task, del_task])

    completed_albums = []
    completed_deletes = []
    finished_summary = []

    worker.album_completed.connect(lambda title, count, b: completed_albums.append(title))
    worker.delete_completed.connect(lambda t, ok, freed, msg: completed_deletes.append((t.display_title, ok)))
    worker.sync_finished.connect(lambda tracks, bytes_done, errs: finished_summary.append((tracks, bytes_done)))

    # Execute simulation
    worker.run()

    assert len(completed_albums) == 1
    assert completed_albums[0] == "Prism Frequency"
    assert len(completed_deletes) == 1
    assert completed_deletes[0][1] is True
    assert len(finished_summary) == 1
    assert finished_summary[0][0] > 0  # tracks synced


def test_main_window_demo_mode(qapp):
    from vibestunes.ui.main_window import MainWindow

    win = MainWindow(demo_mode=True)
    assert win.is_demo_mode is True
    assert not hasattr(win, "demo_btn")
    assert "[Demo Mode]" in win.windowTitle()
    assert win.device is not None
    assert isinstance(win.plex, DemoPlexManager)
    assert len(win.ipod_artists) > 0

    # Ensure demo mode can start demo sync worker without real hardware
    task = SyncTask(
        artist_name="Subatomic Pulse",
        album_title="Particle Shift",
        album_key="alb_4_2",
        year=2022,
        thumb_url=""
    )
    win._start_sync([task])
    assert win.sync_worker is not None
    assert isinstance(win.sync_worker, DemoSyncWorker)

    # Clean up worker thread if still running
    if win.sync_worker:
        win.sync_worker.cancel()
    if win.sync_thread and win.sync_thread.is_alive():
        win.sync_thread.join(timeout=1.0)
    win.close()
