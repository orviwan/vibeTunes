"""Unit tests for SyncWorker queue management, SyncDrawerWidget, and SyncQueueDialog."""
import pytest
from pathlib import Path
from PySide6.QtCore import Qt

from vibestunes.core.plex_client import PlexManager, PlexAlbumSummary, PlexTrackDetail
from vibestunes.core.config import AppConfig
from vibestunes.core.sync_engine import SyncWorker, SyncTask, SyncPlaylistTask
from vibestunes.ui.widgets.sync_drawer import SyncDrawerWidget
from vibestunes.ui.widgets.queue_dialog import SyncQueueDialog
from vibestunes.ui.widgets.plex_browser import PlexBrowserWidget

def test_sync_task_properties():
    t1 = SyncTask(
        artist_name="Radiohead",
        album_title="OK Computer",
        album_key="101",
        year=1997,
        thumb_url=None,
    )
    assert t1.display_title == "Radiohead - OK Computer"
    assert t1.item_type_label == "Album"
    assert "Full Album (1997)" in t1.details_label
    assert t1.key_id == "album::101"

    t2 = SyncTask(
        artist_name="Radiohead",
        album_title="OK Computer",
        album_key="101",
        year=1997,
        thumb_url=None,
        specific_track_keys={"1", "2"},
    )
    assert t2.item_type_label == "Selected Tracks"
    assert "2 track(s)" in t2.details_label

    pl = SyncPlaylistTask(
        playlist_title="Best of 90s",
        playlist_key="500",
    )
    assert pl.display_title == "Playlist: Best of 90s"
    assert pl.item_type_label == "Playlist"
    assert pl.key_id == "playlist::500"

def test_sync_worker_thread_safe_queue(tmp_path):
    plex = PlexManager()
    config = AppConfig()
    worker = SyncWorker(plex, str(tmp_path), config)

    t1 = SyncTask(artist_name="Ash", album_title="1977", album_key="1", year=1996, thumb_url=None)
    t2 = SyncTask(artist_name="Blur", album_title="Parklife", album_key="2", year=1994, thumb_url=None)
    t3 = SyncPlaylistTask(playlist_title="Indie", playlist_key="3")

    enqueued_events = []
    queue_changed_events = []
    worker.task_enqueued.connect(lambda task, pos: enqueued_events.append((task, pos)))
    worker.queue_changed.connect(lambda q: queue_changed_events.append(list(q)))

    # Add tasks
    pos1 = worker.add_task(t1)
    assert pos1 == 1
    assert len(enqueued_events) == 1
    assert enqueued_events[-1][1] == 1

    pos2 = worker.add_album_task(t2)
    assert pos2 == 2
    assert len(enqueued_events) == 2

    pos3 = worker.add_playlist_task(t3)
    assert pos3 == 3
    assert len(enqueued_events) == 3

    curr, queued = worker.get_queue_snapshot()
    assert curr is None
    assert len(queued) == 3
    assert queued[0] == t1
    assert queued[1] == t2
    assert queued[2] == t3

    # Remove task at index 1 (t2)
    removed = worker.remove_task(1)
    assert removed == t2
    curr, queued = worker.get_queue_snapshot()
    assert len(queued) == 2
    assert queued[0] == t1
    assert queued[1] == t3

    # Clear queue
    cleared = worker.clear_queue()
    assert cleared == 2
    curr, queued = worker.get_queue_snapshot()
    assert len(queued) == 0

def test_sync_drawer_view_queue_button(qapp):
    drawer = SyncDrawerWidget()
    drawer.set_sync_active(True)
    assert drawer.isVisible()

    view_queue_called = []
    drawer.view_queue_requested.connect(lambda: view_queue_called.append(True))

    drawer.set_queue_status(3)
    assert "View Queue (3)" in drawer.view_queue_btn.text()
    assert "3 items waiting in queue" in drawer.queue_label.text()

    # Click view queue button
    drawer.view_queue_btn.click()
    assert len(view_queue_called) == 1

    # Test enqueue notice
    drawer.show_enqueue_notice("OK Computer", 2)
    assert "OK Computer" in drawer.notice_label.text()
    assert "#2" in drawer.notice_label.text()

def test_sync_queue_dialog(qapp):
    dialog = SyncQueueDialog()
    assert dialog.windowTitle() == "Sync Queue - vibesTunes"

    # Initially empty
    assert dialog.queue_table.isHidden()
    assert not dialog.empty_label.isHidden()

    t1 = SyncTask(artist_name="Ash", album_title="1977", album_key="1", year=1996, thumb_url=None)
    t2 = SyncPlaylistTask(playlist_title="Britpop", playlist_key="2")

    # Update queue with 2 tasks
    dialog.update_queue([t1, t2])
    assert not dialog.queue_table.isHidden()
    assert dialog.empty_label.isHidden()
    assert dialog.queue_table.rowCount() == 2

    # Check row 0
    assert dialog.queue_table.item(0, 0).text() == "#1"
    assert dialog.queue_table.item(0, 1).text() == "Album"
    assert "Ash - 1977" in dialog.queue_table.item(0, 2).text()

    # Check row 1
    assert dialog.queue_table.item(1, 0).text() == "#2"
    assert dialog.queue_table.item(1, 1).text() == "Playlist"
    assert "Playlist: Britpop" in dialog.queue_table.item(1, 2).text()

    # Test remove signal
    removed_indices = []
    dialog.remove_task_requested.connect(lambda idx: removed_indices.append(idx))

    remove_btn = dialog.queue_table.cellWidget(0, 4)
    assert remove_btn is not None
    remove_btn.click()
    assert removed_indices == [0]

    # Test active task card updates
    dialog.set_active_album("Radiohead", "The Bends", 1, 3)
    assert "Radiohead - The Bends (1/3)" in dialog.active_title_label.text()

    dialog.set_track_started("High and Dry", 3, 12)
    assert "Track 3/12: High and Dry" in dialog.active_track_label.text()

    dialog.set_track_progress(1000, 2000, 500000)
    assert dialog.active_progress.value() == 50

    # Finished
    dialog.set_sync_finished()
    assert "Idle" in dialog.active_title_label.text()
    assert dialog.queue_table.rowCount() == 0

def test_plex_browser_queued_status_indicator(qapp):
    plex = PlexManager()
    browser = PlexBrowserWidget(plex)

    alb = PlexAlbumSummary(rating_key="100", title="1977", artist_name="Ash", year=1996, track_count=12)
    browser.current_albums = [alb]
    browser.displayed_albums = [alb]
    browser.selected_album = alb

    # Initially not queued
    browser._update_album_actions()
    assert browser.sync_album_btn.text() == "+ Add to iPod"

    # Mark as queued
    browser.update_sync_queue_keys({"100"}, None)
    assert browser.sync_album_btn.text() == "⏱ In Sync Queue"
    assert not browser.sync_album_btn.isEnabled()

    # Mark as active sync
    browser.update_sync_queue_keys(set(), "100")
    assert browser.sync_album_btn.text() == "● Syncing Now..."
    assert not browser.sync_album_btn.isEnabled()

    # Finish sync
    browser.update_sync_queue_keys(set(), None)
    assert browser.sync_album_btn.text() == "+ Add to iPod"
    assert browser.sync_album_btn.isEnabled()

def test_main_window_queue_dialog_connection(qapp, tmp_path):
    from vibestunes.ui.main_window import MainWindow
    from vibestunes.core.device import iPodDevice, StorageBreakdown

    window = MainWindow()
    window.queue_dialog = SyncQueueDialog(window)

    plex = PlexManager()
    config = AppConfig()
    worker = SyncWorker(plex, str(tmp_path), config)

    # Connecting worker to queue dialog must not raise TypeError (ConnectionType bitwise OR)
    window._connect_worker_to_queue_dialog(worker)
    assert getattr(worker, "_queue_dialog_connected", False) is True

    # Calling it again should be idempotent
    window._connect_worker_to_queue_dialog(worker)

    # Emitting worker signals updates the dialog
    worker.album_started.emit("Oasis", "Definitely Maybe", 1, 2)
    qapp.processEvents()
    assert "Oasis - Definitely Maybe (1/2)" in window.queue_dialog.active_title_label.text()

    worker.track_started.emit("Rock 'n' Roll Star", 1, 11)
    qapp.processEvents()
    assert "Rock 'n' Roll Star" in window.queue_dialog.active_track_label.text()

    window.close()

def test_main_window_background_scans(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("vibestunes.ui.main_window.detect_ipod", lambda *args, **kwargs: None)
    from vibestunes.ui.main_window import MainWindow
    from vibestunes.core.device import iPodDevice, StorageBreakdown
    import time

    window = MainWindow()
    music_dir = tmp_path / "Ash" / "1977"
    music_dir.mkdir(parents=True)
    (music_dir / "01 - Girl From Mars.mp3").write_bytes(b"dummy")

    device = iPodDevice(
        mount_point=str(tmp_path),
        model_name="iPod Classic",
        storage=StorageBreakdown(1000000, 500000, 200000, 100000, 200000),
    )
    window.device = device

    # Start scans
    window._refresh_storage()
    window._start_ipod_scan()

    # Wait for daemon threads to finish
    if window._storage_scan_thread:
        window._storage_scan_thread.join(timeout=3.0)
    if window._ipod_scan_thread:
        window._ipod_scan_thread.join(timeout=3.0)

    qapp.processEvents()
    assert len(window.ipod_artists) >= 1
    assert window.ipod_artists[0].name == "Ash"
    window.close()
