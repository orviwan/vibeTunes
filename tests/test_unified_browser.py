import os
import pytest
from PySide6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_unified_browser_filtering_and_actions(qapp):
    from vibetunes.core.plex_client import PlexManager, PlexArtistSummary, PlexAlbumSummary, normalize_music_key
    from vibetunes.ui.widgets.plex_browser import PlexBrowserWidget

    plex = PlexManager()
    browser = PlexBrowserWidget(plex)

    # Mock artists
    a1 = PlexArtistSummary(rating_key="1", name="Radiohead", album_count=2, thumb_url="")
    a2 = PlexArtistSummary(rating_key="2", name="Portishead", album_count=1, thumb_url="")
    browser.artists = [a1, a2]

    # Mock albums for Radiohead
    alb1 = PlexAlbumSummary(rating_key="101", title="OK Computer", artist_name="Radiohead", year=1997, track_count=12, thumb_url="")
    alb2 = PlexAlbumSummary(rating_key="102", title="Kid A", artist_name="Radiohead", year=2000, track_count=10, thumb_url="")
    browser.current_albums = [alb1, alb2]

    # Initially neither is on iPod
    browser.update_ipod_known_albums(set(), {})
    assert len(browser.filtered_artists) == 2
    assert "All Music (2)" in browser.filter_all_btn.text()
    assert "✓ Synced (0)" in browser.filter_ipod_btn.text()
    assert "Not Synced (2)" in browser.filter_missing_btn.text()

    # Now simulate Radiohead OK Computer being on iPod
    ok_computer_key = normalize_music_key("Radiohead", "OK Computer")
    known = {ok_computer_key}
    artist_counts = {normalize_music_key("Radiohead"): 1}
    browser.update_ipod_known_albums(known, artist_counts)

    assert "✓ Synced (1)" in browser.filter_ipod_btn.text()

    # Select Radiohead
    browser.selected_artist = a1
    browser._refresh_album_list_badges()

    # In "all" mode, 2 albums displayed
    assert len(browser.displayed_albums) == 2
    assert not browser.delete_artist_btn.isHidden()
    assert browser.delete_artist_btn.isEnabled() is True
    assert "Remove Artist (1)" in browser.delete_artist_btn.text()
    assert "+ Add Missing (1)" in browser.sync_artist_btn.text()

    # Select OK Computer (on iPod)
    browser._on_album_selected(0)
    assert browser.selected_album == alb1
    assert browser.sync_album_btn.isHidden()
    assert not browser.resync_album_btn.isHidden()
    assert not browser.delete_album_btn.isHidden()
    assert browser.delete_album_btn.isEnabled() is True

    # Select Kid A (not on iPod)
    browser._on_album_selected(1)
    assert browser.selected_album == alb2
    assert not browser.sync_album_btn.isHidden()
    assert browser.sync_album_btn.isEnabled() is True
    assert browser.resync_album_btn.isHidden()
    assert browser.delete_album_btn.isHidden()

    # Switch filter to "on_ipod"
    browser._set_filter_mode("on_ipod")
    # Only Radiohead is in artist list
    assert len(browser.filtered_artists) == 1
    assert browser.filtered_artists[0].name == "Radiohead"
    # Only OK Computer is displayed
    assert len(browser.displayed_albums) == 1
    assert browser.displayed_albums[0].title == "OK Computer"

    # Switch filter to "not_on_ipod"
    browser._set_filter_mode("not_on_ipod")
    # Both Radiohead (missing Kid A) and Portishead (missing all) should be shown
    assert len(browser.filtered_artists) == 2
    # For Radiohead, only Kid A displayed
    assert len(browser.displayed_albums) == 1
    assert browser.displayed_albums[0].title == "Kid A"

def test_main_window_tabs_unified(qapp, monkeypatch):
    monkeypatch.setattr("vibetunes.ui.main_window.detect_ipod", lambda *args, **kwargs: None)
    monkeypatch.setattr("vibetunes.ui.main_window.MainWindow._init_plex_connection", lambda self: None)
    from vibetunes.ui.main_window import MainWindow

    win = MainWindow()
    try:
        # Ensure there are only 2 tabs: Music Library and Playlists
        assert win.tabs.count() == 2
        assert win.tabs.tabText(0) == "Music Library"
        assert win.tabs.tabText(1) == "Playlists"
        # Ensure ipod_browser is not present
        assert not hasattr(win, "ipod_browser")
    finally:
        win.close()

def test_partial_album_and_track_status(qapp):
    from pathlib import Path
    from vibetunes.core.plex_client import PlexManager, PlexArtistSummary, PlexAlbumSummary, PlexTrackDetail, normalize_music_key
    from vibetunes.core.ipod_scanner import iPodTrack, is_plex_track_on_ipod
    from vibetunes.ui.widgets.plex_browser import PlexBrowserWidget

    plex = PlexManager()
    browser = PlexBrowserWidget(plex)

    # 1. Unit test is_plex_track_on_ipod
    ipod_tracks = [
        iPodTrack(filename="01 - Lose Control.flac", path=Path("/fake/01.flac"), size_bytes=1000, title="Lose Control", track_number=1),
        iPodTrack(filename="04 - I’d Give You Anything.flac", path=Path("/fake/04.flac"), size_bytes=1000, title="I’d Give You Anything", track_number=4),
    ]

    t1 = PlexTrackDetail(rating_key="1", title="Lose Control", artist_name="Ash", album_title="1977", track_number=1)
    t2 = PlexTrackDetail(rating_key="2", title="Goldfinger", artist_name="Ash", album_title="1977", track_number=2)
    t4 = PlexTrackDetail(rating_key="4", title="I'd Give You Anything", artist_name="Ash", album_title="1977", track_number=4)

    assert is_plex_track_on_ipod(t1, ipod_tracks) is True
    assert is_plex_track_on_ipod(t2, ipod_tracks) is False
    assert is_plex_track_on_ipod(t4, ipod_tracks) is True

    # 2. Test partial album badging in browser
    art = PlexArtistSummary(rating_key="10", name="Ash", album_count=1)
    alb = PlexAlbumSummary(rating_key="100", title="1977", artist_name="Ash", year=1996, track_count=12)
    browser.artists = [art]
    browser.current_albums = [alb]

    ash_1977_key = normalize_music_key("Ash", "1977")
    ipod_data = {
        ash_1977_key: {
            "track_count": 2,
            "tracks": ipod_tracks,
        }
    }
    browser.update_ipod_known_albums({ash_1977_key}, {normalize_music_key("Ash"): 1}, ipod_data)

    status, on_cnt, miss_cnt = browser.get_album_ipod_status("Ash", "1977", 12)
    assert status == "partial"
    assert on_cnt == 2
    assert miss_cnt == 10

    # Select Ash and test album display
    browser.selected_artist = art
    browser._refresh_album_list_badges()
    assert len(browser.displayed_albums) == 1

    item = browser.album_list.item(0)
    assert "◐ 2/12" in item.text()

    # Select the album
    browser._on_album_selected(0)
    assert browser.selected_album == alb
    # Check album action buttons for partial album
    assert not browser.sync_album_btn.isHidden()
    assert "+ Add Missing (10 tracks)" in browser.sync_album_btn.text()
    assert not browser.resync_album_btn.isHidden()
    assert "Re-sync Full Album" in browser.resync_album_btn.text()
    assert not browser.delete_album_btn.isHidden()
    assert "Remove from iPod (2)" in browser.delete_album_btn.text()

    # 3. Test track table population with status column
    plex_tracks = [t1, t2, t4]
    browser._on_tracks_loaded("100", plex_tracks)

    assert browser.track_table.rowCount() == 3
    assert browser.track_table.columnCount() == 6
    assert "◐ 2/3" in browser.track_header.text()

    # Row 0: Lose Control -> On iPod (visual icon, no text)
    assert browser.track_table.item(0, 1).text() == "Lose Control"
    assert browser.track_table.item(0, 2).text() == ""
    assert browser.track_table.item(0, 2).toolTip() == "Synced"
    assert not browser.track_table.item(0, 2).icon().isNull()

    # Row 1: Goldfinger -> Missing (visual missing icon, no text)
    assert browser.track_table.item(1, 1).text() == "Goldfinger"
    assert browser.track_table.item(1, 2).text() == ""
    assert browser.track_table.item(1, 2).toolTip() == "Not Synced"
    assert not browser.track_table.item(1, 2).icon().isNull()

    # Row 2: I'd Give You Anything -> On iPod (visual icon, no text)
    assert browser.track_table.item(2, 1).text() == "I'd Give You Anything"
    assert browser.track_table.item(2, 2).text() == ""
    assert browser.track_table.item(2, 2).toolTip() == "Synced"
    assert not browser.track_table.item(2, 2).icon().isNull()

    # 4. Test clicking Add Missing on partial album emits SyncTask for only missing tracks
    received_tasks = []
    browser.sync_album_requested.connect(lambda task: received_tasks.append(task))

    browser._on_sync_album()
    assert len(received_tasks) == 1
    task = received_tasks[0]
    assert task.album_title == "1977"
    assert task.specific_track_keys == {"2"}  # Only Goldfinger is missing!
    assert task.force_overwrite is False

    # 5. Test Re-sync Album emits SyncTask with specific_track_keys=None and force_overwrite=True
    browser._on_resync_album()
    assert len(received_tasks) == 2
    resync_task = received_tasks[1]
    assert resync_task.album_title == "1977"
    assert resync_task.specific_track_keys is None
    assert resync_task.force_overwrite is True

    # 6. Test specific track sync
    browser._sync_specific_tracks([t1], force_overwrite=True)
    assert len(received_tasks) == 3
    t1_task = received_tasks[2]
    assert t1_task.specific_track_keys == {"1"}
    assert t1_task.force_overwrite is True


def test_sync_worker_skips_existing_tracks(tmp_path):
    from vibetunes.core.plex_client import PlexManager, PlexTrackDetail
    from vibetunes.core.sync_engine import SyncWorker, SyncTask
    from vibetunes.core.config import AppConfig

    mount_dir = tmp_path / "ipod"
    mount_dir.mkdir()

    # Pre-create track 1 on disk under Ash/Ash-1996-1977/
    album_dir = mount_dir / "Ash" / "Ash-1996-1977"
    album_dir.mkdir(parents=True)
    existing_file = album_dir / "01 - Lose Control.flac"
    existing_file.write_bytes(b"EXISTING_AUDIO_CONTENT")

    config = AppConfig(naming_pattern="rockbox_disc", download_artwork=False)
    plex = PlexManager()

    t1 = PlexTrackDetail(rating_key="1", title="Lose Control", artist_name="Ash", album_title="1977", track_number=1, size_bytes=100)
    t2 = PlexTrackDetail(rating_key="2", title="Goldfinger", artist_name="Ash", album_title="1977", track_number=2, size_bytes=200, stream_url="/fake/stream")

    # Mock plex.get_album_tracks
    plex.get_album_tracks = lambda key: [t1, t2]

    worker = SyncWorker(plex, str(mount_dir), config)

    # Mock _download_track so it doesn't actually make network calls
    downloaded_files = []
    def mock_download(track, dest_path):
        dest_path.write_bytes(b"DOWNLOADED_DATA")
        downloaded_files.append(dest_path.name)
        return True, 200, ""

    worker._download_track = mock_download

    # Run _process_album without force_overwrite -> t1 should be skipped, t2 downloaded
    task = SyncTask(
        artist_name="Ash",
        album_title="1977",
        album_key="100",
        year=1996,
        thumb_url=None,
        specific_track_keys=None,
        force_overwrite=False,
    )

    transferred, bytes_done, errs = worker._process_album(task)
    assert len(errs) == 0
    assert transferred == 2  # 1 skipped + 1 downloaded
    assert downloaded_files == ["02 - Goldfinger.flac"]
    assert existing_file.read_bytes() == b"EXISTING_AUDIO_CONTENT"

    # Now run with force_overwrite=True -> both should be downloaded
    downloaded_files.clear()
    task.force_overwrite = True
    transferred, bytes_done, errs = worker._process_album(task)
    assert len(errs) == 0
    assert transferred == 2
    assert "01 - Lose Control.flac" in downloaded_files
    assert "02 - Goldfinger.flac" in downloaded_files


def test_playlist_browser_visual_status(qapp):
    from pathlib import Path
    from vibetunes.core.plex_client import PlexManager, PlexTrackDetail, normalize_music_key
    from vibetunes.core.ipod_scanner import iPodTrack
    from vibetunes.ui.widgets.playlist_browser import PlaylistBrowserWidget

    plex = PlexManager()
    browser = PlaylistBrowserWidget(plex)

    t1 = PlexTrackDetail(rating_key="1", title="Lose Control", artist_name="Ash", album_title="1977", track_number=1)
    t2 = PlexTrackDetail(rating_key="2", title="Karma Police", artist_name="Radiohead", album_title="OK Computer", track_number=6)

    ipod_artist_tracks = {
        normalize_music_key("Ash"): [
            iPodTrack(filename="01 - Lose Control.flac", path=Path("/fake/01.flac"), size_bytes=1000, title="Lose Control", track_number=1)
        ]
    }
    browser.update_ipod_tracks(ipod_artist_tracks)
    browser._on_tracks_loaded([t1, t2])

    assert browser.track_table.rowCount() == 2
    assert browser.track_table.columnCount() == 6
    assert "◐ 1/2" in browser.track_header.text()

    # Track 1 (Ash - Lose Control) -> on iPod
    assert browser.track_table.item(0, 1).text() == "Lose Control"
    assert browser.track_table.item(0, 2).text() == ""
    assert browser.track_table.item(0, 2).toolTip() == "Synced"
    assert not browser.track_table.item(0, 2).icon().isNull()

    # Track 2 (Radiohead - Karma Police) -> missing
    assert browser.track_table.item(1, 1).text() == "Karma Police"
    assert browser.track_table.item(1, 2).text() == ""
    assert browser.track_table.item(1, 2).toolTip() == "Not Synced"
    assert not browser.track_table.item(1, 2).icon().isNull()


def test_multivolume_album_browser_status(qapp):
    from pathlib import Path
    from vibetunes.core.plex_client import (
        PlexManager, PlexArtistSummary, PlexAlbumSummary, PlexTrackDetail, normalize_music_key
    )
    from vibetunes.core.ipod_scanner import iPodTrack
    from vibetunes.ui.widgets.plex_browser import PlexBrowserWidget

    plex = PlexManager()
    browser = PlexBrowserWidget(plex)

    artist = PlexArtistSummary(rating_key="1", name="The Wedding Present", album_count=2, thumb_url="")
    browser.artists = [artist]

    alb1 = PlexAlbumSummary(
        rating_key="101", title="Locked Down and Stripped Back", artist_name="The Wedding Present", year=2021, track_count=12
    )
    alb2 = PlexAlbumSummary(
        rating_key="102", title="Locked Down and Stripped Back, Volume 2", artist_name="The Wedding Present", year=2022, track_count=12
    )
    browser.current_albums = [alb1, alb2]

    # iPod has only Volume 1 (12 tracks)
    norm_art = normalize_music_key("The Wedding Present")
    v1_key = normalize_music_key("The Wedding Present", "Locked Down and Stripped Back")
    known = {v1_key}
    artist_counts = {norm_art: 1}
    v1_tracks = [
        iPodTrack(filename=f"0{i} - Track.mp3", path=Path(f"/ipod/v1/0{i}.mp3"), size_bytes=1000, title=f"Track {i}", track_number=i)
        for i in range(1, 13)
    ]
    # Simulate an older album on iPod having "Brassneck"
    bizarro_tracks = [
        iPodTrack(filename="01 - Brassneck.mp3", path=Path("/ipod/bizarro/01.mp3"), size_bytes=1000, title="Brassneck", track_number=1)
    ]
    ipod_album_data = {
        v1_key: {"track_count": 12, "tracks": v1_tracks}
    }
    ipod_artist_tracks = {
        norm_art: v1_tracks + bizarro_tracks
    }

    browser.update_ipod_known_albums(known, artist_counts, ipod_album_data, ipod_artist_tracks)

    # 1. Select artist
    browser.selected_artist = artist
    browser._refresh_album_list_badges()

    # Verify artist badge is 1/2
    assert "◐ 1/2 albums" in browser.artist_list.item(0).text()

    # Verify album list: alb1 has ✓, alb2 does not
    assert len(browser.displayed_albums) == 2
    assert browser.displayed_albums[0].title == "Locked Down and Stripped Back"
    assert browser.displayed_albums[1].title == "Locked Down and Stripped Back, Volume 2"

    # In grid/list mode, check status
    status1, on1, _ = browser.get_album_ipod_status(alb1.artist_name, alb1.title, alb1.track_count)
    status2, on2, _ = browser.get_album_ipod_status(alb2.artist_name, alb2.title, alb2.track_count)
    assert status1 == "complete"
    assert status2 == "none"

    # Verify sync button says + Add Missing (1)
    assert "+ Add Missing (1)" in browser.sync_artist_btn.text()

    # 2. Select Volume 2 and load its tracks (including Brassneck which exists on Bizarro)
    browser.selected_album = alb2
    vol2_tracks = [
        PlexTrackDetail(rating_key="201", title="Brassneck", artist_name="The Wedding Present", album_title=alb2.title, track_number=1, size_bytes=1000, duration_ms=180000),
        PlexTrackDetail(rating_key="202", title="No", artist_name="The Wedding Present", album_title=alb2.title, track_number=2, size_bytes=1000, duration_ms=180000),
    ]
    browser._on_tracks_loaded(alb2.rating_key, vol2_tracks)

    # Tracks must NOT match across artist_tracks
    assert browser.track_table.rowCount() == 2
    assert browser.track_table.item(0, 2).toolTip() == "Not Synced"
    assert browser.track_table.item(1, 2).toolTip() == "Not Synced"
    assert "0/2 synced" in browser.track_header.text()

    # Album 2 must NOT be marked as on iPod
    v2_key = normalize_music_key("The Wedding Present", "Locked Down and Stripped Back, Volume 2")
    assert v2_key not in browser.on_ipod_albums

    # Artist count must remain 1/2
    assert "◐ 1/2 albums" in browser.artist_list.item(0).text()
    assert "+ Add Missing (1)" in browser.sync_artist_btn.text()

    # 3. Simulate Plex returning 404 for all Volume 2 tracks
    plex.mark_track_unavailable("201")
    plex.mark_track_unavailable("202")
    browser._on_tracks_loaded(alb2.rating_key, vol2_tracks)

    # Sync album button must be disabled with 404 notice
    assert browser.sync_album_btn.isEnabled() is False
    assert "⚠ Missing on Plex (404)" in browser.sync_album_btn.text()

    # Album list item for Volume 2 must show 404 badge
    assert "⚠" in browser.album_list.item(1).text()
    assert "404" in browser.album_list.item(1).text()


def test_status_icon_badge_alignment(qapp):
    """
    Verifies that the artist list, album list (grid & list mode), and track table
    consistently use high-DPI icon badges aligned with the playlists browser.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from vibetunes.core.plex_client import (
        PlexManager, PlexArtistSummary, PlexAlbumSummary, normalize_music_key
    )
    from vibetunes.ui.widgets.plex_browser import (
        PlexBrowserWidget, badge_pixmap_with_status
    )

    plex = PlexManager()
    browser = PlexBrowserWidget(plex)

    # 1. Verify track table header has "Status" column header matching playlists
    assert browser.track_table.horizontalHeaderItem(2).text() == "Status"

    # 2. Test badge_pixmap_with_status for all statuses
    dummy_pix = QPixmap(60, 60)
    dummy_pix.fill(Qt.black)
    for st in ("complete", "partial", "warning", "syncing", "queued", "none"):
        badged = badge_pixmap_with_status(dummy_pix, st, badge_size=18)
        assert not badged.isNull()
        assert badged.width() == 60
        assert badged.height() == 60

    # 3. Setup artist with 2 albums
    art = PlexArtistSummary(rating_key="10", name="Slowdive", album_count=2, thumb_url="")
    browser.artists = [art]

    alb1 = PlexAlbumSummary(rating_key="101", title="Souvlaki", artist_name="Slowdive", year=1993, track_count=10)
    alb2 = PlexAlbumSummary(rating_key="102", title="Pygmalion", artist_name="Slowdive", year=1995, track_count=9)
    browser.current_albums = [alb1, alb2]

    # iPod has only alb1
    norm_art = normalize_music_key("Slowdive")
    alb1_key = normalize_music_key("Slowdive", "Souvlaki")
    browser.update_ipod_known_albums(
        album_keys={alb1_key},
        artist_counts={norm_art: 1},
        ipod_album_data={alb1_key: {"track_count": 10, "tracks": []}},
    )

    # Verify Artist list item
    assert browser.artist_list.count() == 1
    art_item = browser.artist_list.item(0)
    assert not art_item.icon().isNull()
    assert art_item.data(Qt.UserRole + 2) == "partial"
    assert art_item.foreground().color().name() == "#fab387"
    assert "Slowdive" in art_item.text()
    assert "◐ 1/2 albums" in art_item.text()

    # 4. Select artist & verify Album list in Grid mode
    browser.selected_artist = art
    browser._refresh_album_list_badges()
    assert browser.album_list.count() == 2

    # Grid item 0 (Souvlaki - complete)
    grid_item0 = browser.album_list.item(0)
    assert not grid_item0.icon().isNull()
    assert grid_item0.data(Qt.UserRole + 2) == "complete"
    assert grid_item0.foreground().color().name() == "#a6e3a1"
    # Clean caption: title first, subtitle has ✓ on iPod
    lines0 = grid_item0.text().split("\n")
    assert lines0[0] == "Souvlaki"
    assert "✓ on iPod" in lines0[1]

    # Grid item 1 (Pygmalion - none)
    grid_item1 = browser.album_list.item(1)
    assert not grid_item1.icon().isNull()
    assert grid_item1.data(Qt.UserRole + 2) == "none"
    assert grid_item1.foreground().color().name() == "#cdd6f4"
    lines1 = grid_item1.text().split("\n")
    assert lines1[0] == "Pygmalion"

    # 5. Switch to List mode & verify Album list
    browser._set_album_view_mode("list")
    assert browser.album_list.count() == 2

    list_item0 = browser.album_list.item(0)
    assert not list_item0.icon().isNull()
    assert list_item0.data(Qt.UserRole + 2) == "complete"
    list_lines0 = list_item0.text().split("\n")
    assert list_lines0[0] == "Souvlaki (1993)"
    assert "10 tracks • ✓ on iPod" in list_lines0[1]

    list_item1 = browser.album_list.item(1)
    assert not list_item1.icon().isNull()
    assert list_item1.data(Qt.UserRole + 2) == "none"
    list_lines1 = list_item1.text().split("\n")
    assert list_lines1[0] == "Pygmalion (1995)"
    assert list_lines1[1] == "9 tracks"

    # 6. Verify active sync and queued badge statuses in album list
    browser.update_sync_queue_keys(queued_keys={"102"}, active_key="101")
    item0_syncing = browser.album_list.item(0)
    assert item0_syncing.data(Qt.UserRole + 2) == "syncing"
    assert "● Syncing" in item0_syncing.text()

    item1_queued = browser.album_list.item(1)
    assert item1_queued.data(Qt.UserRole + 2) == "queued"
    assert "⏱ Queued" in item1_queued.text()



