"""Tests for removal of confirmation prompts and accuracy of artist/album/track counters."""
import os
import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox

os.environ["QT_QPA_PLATFORM"] = "offscreen"

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_no_confirmation_prompts_on_remove(qapp, monkeypatch):
    """Verifies that remove/delete actions do not block on modal QMessageBox.question dialogs."""
    from vibetunes.core.plex_client import PlexManager, PlexArtistSummary, PlexAlbumSummary
    from vibetunes.ui.widgets.plex_browser import PlexBrowserWidget
    from vibetunes.ui.widgets.storage_analyzer_dialog import StorageAnalyzerDialog
    from vibetunes.ui.widgets.playlist_browser import PlaylistBrowserWidget
    from vibetunes.ui.widgets.queue_dialog import SyncQueueDialog
    from vibetunes.ui.widgets.device_header import DeviceHeaderWidget
    from vibetunes.core.device import iPodDevice
    from vibetunes.core.ipod_scanner import iPodPlaylist

    # Monkeypatch QMessageBox.question so that if it is called, the test fails
    def fail_on_question(*args, **kwargs):
        pytest.fail("QMessageBox.question was called unexpectedly!")

    monkeypatch.setattr(QMessageBox, "question", fail_on_question)

    # 1. PlexBrowserWidget delete album & artist & clean trash
    plex = PlexManager()
    browser = PlexBrowserWidget(plex)
    art = PlexArtistSummary(rating_key="1", name="Radiohead", album_count=1)
    alb = PlexAlbumSummary(rating_key="101", title="OK Computer", artist_name="Radiohead", year=1997, track_count=12)
    browser.selected_artist = art
    browser.selected_album = alb

    emitted_album_removals = []
    emitted_artist_removals = []
    emitted_clean_trash = []

    browser.remove_album_requested.connect(lambda a, b: emitted_album_removals.append((a, b)))
    browser.remove_artist_requested.connect(lambda a: emitted_artist_removals.append(a))
    browser.clean_trash_requested.connect(lambda: emitted_clean_trash.append(True))

    browser._on_delete_album()
    assert emitted_album_removals == [("Radiohead", "OK Computer")]

    browser._on_delete_artist()
    assert emitted_artist_removals == ["Radiohead"]

    browser._on_clean_trash_clicked()
    assert emitted_clean_trash == [True]

    # 2. StorageAnalyzerDialog delete album & artist
    analyzer = StorageAnalyzerDialog([], "/fake/mount")
    analyzer_album_removals = []
    analyzer_artist_removals = []
    analyzer.delete_album_requested.connect(lambda a, b: analyzer_album_removals.append((a, b)))
    analyzer.delete_artist_requested.connect(lambda a: analyzer_artist_removals.append(a))

    analyzer._on_delete_album({"artist_name": "Blur", "title": "Parklife", "size_bytes": 1000})
    assert analyzer_album_removals == [("Blur", "Parklife")]

    analyzer._on_delete_artist({"name": "Blur", "size_bytes": 5000, "album_count": 2})
    assert analyzer_artist_removals == ["Blur"]

    # 3. PlaylistBrowserWidget delete playlist
    pl_browser = PlaylistBrowserWidget(plex)
    pl_browser.mount_point = "/fake/mount"
    fake_pl = iPodPlaylist(name="Mix90s", filename="Mix90s.m3u8", path=Path("/fake/mount/Mix90s.m3u8"), track_count=10)
    pl_browser.ipod_playlists = [fake_pl]
    pl_browser.ipod_pl_list.addItem("Mix90s")
    pl_browser.ipod_pl_list.setCurrentRow(0)

    # Mock delete_playlist so it succeeds
    monkeypatch.setattr("vibetunes.ui.widgets.playlist_browser.delete_playlist", lambda p: (True, "Deleted"))
    monkeypatch.setattr(pl_browser, "reload_ipod_playlists", lambda: None)
    pl_browser._on_delete_ipod_playlist()  # Should not prompt!

    # 4. SyncQueueDialog clear & cancel
    queue_dlg = SyncQueueDialog()
    cleared = []
    cancelled = []
    queue_dlg.clear_queue_requested.connect(lambda: cleared.append(True))
    queue_dlg.cancel_all_requested.connect(lambda: cancelled.append(True))

    queue_dlg._on_clear_queue_clicked()
    assert cleared == [True]

    queue_dlg._on_cancel_all_clicked()
    assert cancelled == [True]

    # 5. DeviceHeaderWidget safe eject
    header = DeviceHeaderWidget()
    header.current_device = iPodDevice(mount_point="/fake/mount", model_name="iPod Classic")
    header._on_eject_clicked()  # Should not prompt!
    assert header.eject_btn.text() == "Ejecting..."


def test_filter_button_counts_match_list_exact(qapp):
    """Verifies that filter button counts (All, Synced, Not Synced) match the list row counts exactly."""
    from vibetunes.core.plex_client import PlexManager, PlexArtistSummary, normalize_music_key
    from vibetunes.ui.widgets.plex_browser import PlexBrowserWidget

    plex = PlexManager()
    browser = PlexBrowserWidget(plex)

    a1 = PlexArtistSummary(rating_key="1", name="Radiohead", album_count=3)
    a2 = PlexArtistSummary(rating_key="2", name="Portishead", album_count=2)
    a3 = PlexArtistSummary(rating_key="3", name="Massive Attack", album_count=1)
    a4 = PlexArtistSummary(rating_key="4", name="Ghost Artist", album_count=0)  # Edge case: 0 albums
    browser.artists = [a1, a2, a3, a4]

    # Set up iPod counts:
    # Radiohead: fully synced (3 on device)
    # Portishead: partially synced (1 on device)
    # Massive Attack: not synced (0 on device)
    # Ghost Artist: 0 on device
    known = {
        normalize_music_key("Radiohead", "OK Computer"),
        normalize_music_key("Radiohead", "Kid A"),
        normalize_music_key("Radiohead", "Amnesiac"),
        normalize_music_key("Portishead", "Dummy"),
    }
    artist_counts = {
        normalize_music_key("Radiohead"): 3,
        normalize_music_key("Portishead"): 1,
        normalize_music_key("Massive Attack"): 0,
        normalize_music_key("Ghost Artist"): 0,
    }
    browser.update_ipod_known_albums(known, artist_counts)

    # 1. All Music
    browser._set_filter_mode("all")
    assert "All Music (4)" in browser.filter_all_btn.text()
    assert len(browser.filtered_artists) == 4

    # 2. Synced: Radiohead (3/3) and Portishead (1/2) have tracks on device -> 2
    browser._set_filter_mode("on_ipod")
    assert "✓ Synced (2)" in browser.filter_ipod_btn.text()
    assert len(browser.filtered_artists) == 2
    assert {a.name for a in browser.filtered_artists} == {"Radiohead", "Portishead"}

    # 3. Not Synced: Portishead (1/2 missing 1) and Massive Attack (0/1 missing 1) -> 2
    browser._set_filter_mode("not_on_ipod")
    assert "Not Synced (2)" in browser.filter_missing_btn.text()
    assert len(browser.filtered_artists) == 2
    assert {a.name for a in browser.filtered_artists} == {"Portishead", "Massive Attack"}


def test_album_and_track_count_auto_synchronization(qapp):
    """Verifies that artist album_count and album track_count synchronize with actual loaded items."""
    from vibetunes.core.plex_client import PlexManager, PlexArtistSummary, PlexAlbumSummary, PlexTrackDetail
    from vibetunes.ui.widgets.plex_browser import PlexBrowserWidget

    plex = PlexManager()
    browser = PlexBrowserWidget(plex)

    art = PlexArtistSummary(rating_key="1", name="Radiohead", album_count=1)  # Summary says 1
    browser.artists = [art]
    browser._filter_artists()
    browser.selected_artist = art

    # Now get_artist_albums actually returns 2 albums
    alb1 = PlexAlbumSummary(rating_key="101", title="OK Computer", artist_name="Radiohead", year=1997, track_count=10)
    alb2 = PlexAlbumSummary(rating_key="102", title="Kid A", artist_name="Radiohead", year=2000, track_count=10)

    browser._on_albums_loaded("1", [alb1, alb2])

    # Verified: selected_artist.album_count and art.album_count updated to 2
    assert browser.selected_artist.album_count == 2
    assert browser.artists[0].album_count == 2
    assert "All Music (1)" in browser.filter_all_btn.text()

    # Select OK Computer (summary said 10 tracks)
    browser.selected_album = alb1
    # Now get_album_tracks returns 12 tracks
    tracks = [
        PlexTrackDetail(rating_key=str(i), title=f"Track {i}", artist_name="Radiohead", album_title="OK Computer", track_number=i)
        for i in range(1, 13)
    ]
    browser._on_tracks_loaded("101", tracks)

    assert browser.selected_album.track_count == 12
    assert browser.current_albums[0].track_count == 12
    assert "Tracks (12)" in browser.track_header.text()
