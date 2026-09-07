from podplex.core.config import Config
from podplex.core.plex_client import PlexTrack
from podplex.ui.main_window import MainWindow


def test_main_window_constructs_with_no_device_detected(qapp):
    window = MainWindow(config=Config())
    assert window.windowTitle() == "PodPlex"
    assert window.device_label.text() == "iPod: not detected"


def test_detect_device_updates_label_when_none_found(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("podplex.ui.main_window.find_device", lambda mount_override="": None)
    window = MainWindow(config=Config())
    window.detect_device()
    assert window.device_label.text() == "iPod: not detected"


class FakePlexClientForStatus:
    def __init__(self, tracks):
        self._tracks = tracks

    def tracks_for_album(self, album):
        return self._tracks


def _select_fake_album(window, tmp_path, track):
    window.device_mount_path = tmp_path
    window.plex_client = FakePlexClientForStatus([track])
    window.artist_list.addItem("Art")
    window._artists_by_name["Art"] = object()
    window.album_list.addItem("Alb")
    window._albums_by_name["Alb"] = object()
    window.album_list.setCurrentRow(0)


def test_album_selection_shows_on_ipod_status(qapp, tmp_path):
    track = PlexTrack(
        key="k", title="Song", artist="Art", album="Alb", track_number=1,
        year=2000, disc_number=1, duration_ms=1, file_path="/d/Song.flac", size_bytes=8,
    )
    album_dir = tmp_path / "Music" / "Art" / "Art-2000-Alb" / "CD 01"
    album_dir.mkdir(parents=True)
    (album_dir / "01 Song.flac").write_bytes(b"12345678")

    window = MainWindow(config=Config())
    _select_fake_album(window, tmp_path, track)
    assert window.album_status_label.text() == "✓ ON IPOD"


def test_delete_selected_album_removes_files_and_refreshes_status(qapp, tmp_path):
    track = PlexTrack(
        key="k", title="Song", artist="Art", album="Alb", track_number=1,
        year=2000, disc_number=1, duration_ms=1, file_path="/d/Song.flac", size_bytes=8,
    )
    album_dir = tmp_path / "Music" / "Art" / "Art-2000-Alb" / "CD 01"
    album_dir.mkdir(parents=True)
    (album_dir / "01 Song.flac").write_bytes(b"12345678")

    window = MainWindow(config=Config())
    _select_fake_album(window, tmp_path, track)
    assert window.album_status_label.text() == "✓ ON IPOD"

    window.delete_selected_album()
    assert not album_dir.exists()
    assert window.album_status_label.text() == "Not on iPod"


def test_album_selection_loads_cover_art_when_available(qapp, tmp_path, monkeypatch):
    track = PlexTrack(
        key="k", title="Song", artist="Art", album="Alb", track_number=1,
        year=2000, disc_number=1, duration_ms=1, file_path="/d/Song.flac", size_bytes=8,
    )
    album_dir = tmp_path / "Music" / "Art" / "Art-2000-Alb" / "CD 01"
    album_dir.mkdir(parents=True)
    (album_dir / "01 Song.flac").write_bytes(b"12345678")

    window = MainWindow(config=Config())
    monkeypatch.setattr(window.thumbnail_cache, "get_or_extract", lambda p: b"fake-art-bytes")
    _select_fake_album(window, tmp_path, track)
    assert window._last_cover_bytes == b"fake-art-bytes"


def test_album_selection_clears_cover_art_when_not_on_device(qapp, tmp_path):
    track = PlexTrack(
        key="k", title="Song", artist="Art", album="Alb", track_number=1,
        year=2000, disc_number=1, duration_ms=1, file_path="/d/Song.flac", size_bytes=8,
    )
    window = MainWindow(config=Config())
    _select_fake_album(window, tmp_path, track)
    assert window._last_cover_bytes is None


class FakePlaylist:
    def __init__(self, title):
        self.title = title


class FakePlexClientForPlaylists:
    def __init__(self, playlists, tracks):
        self._playlists = playlists
        self._tracks = tracks

    def playlists(self):
        return self._playlists

    def tracks_for_playlist(self, playlist):
        return self._tracks

    def download_url(self, track):
        return f"http://fake{track.file_path}"


def test_load_playlists_populates_list(qapp):
    window = MainWindow(config=Config())
    window.plex_client = FakePlexClientForPlaylists([FakePlaylist("Road Trip")], [])
    window.load_playlists()
    assert window.playlist_list.count() == 1
    assert window.playlist_list.item(0).text() == "Road Trip"


def test_on_playlist_selected_lists_tracks(qapp):
    track = PlexTrack(
        key="k", title="Song", artist="Art", album="Alb", track_number=1,
        year=2000, disc_number=1, duration_ms=1, file_path="/d/Song.flac", size_bytes=8,
    )
    window = MainWindow(config=Config())
    window.plex_client = FakePlexClientForPlaylists([FakePlaylist("Road Trip")], [track])
    window.load_playlists()
    window.playlist_list.setCurrentRow(0)
    assert window.playlist_track_list.count() == 1
    assert window.playlist_track_list.item(0).text() == "Art - Song"


def test_sync_selected_playlist_writes_m3u8_and_queues_missing_tracks(qapp, tmp_path):
    track = PlexTrack(
        key="k", title="Song", artist="Art", album="Alb", track_number=1,
        year=2000, disc_number=1, duration_ms=1, file_path="/d/Song.flac", size_bytes=8,
    )
    window = MainWindow(config=Config())
    window.device_mount_path = tmp_path
    window.plex_client = FakePlexClientForPlaylists([FakePlaylist("Road Trip")], [track])
    window.load_playlists()
    window.playlist_list.setCurrentRow(0)
    window.sync_selected_playlist()
    out_path = tmp_path / "Playlists" / "Road Trip.m3u8"
    assert out_path.exists()
    assert "queued for download" in window.playlist_status_label.text()
    window.engine.cancel_all()


def test_sync_selected_playlist_reuses_existing_track(qapp, tmp_path):
    track = PlexTrack(
        key="k", title="Song", artist="Art", album="Alb", track_number=1,
        year=2000, disc_number=1, duration_ms=1, file_path="/d/Song.flac", size_bytes=8,
    )
    existing_dir = tmp_path / "Music" / "Art" / "Alb"
    existing_dir.mkdir(parents=True)
    (existing_dir / "01 Song.flac").write_bytes(b"12345678")

    window = MainWindow(config=Config())
    window.device_mount_path = tmp_path
    window.plex_client = FakePlexClientForPlaylists([FakePlaylist("Road Trip")], [track])
    window.load_playlists()
    window.playlist_list.setCurrentRow(0)
    window.sync_selected_playlist()
    assert "all tracks already on iPod" in window.playlist_status_label.text()
    assert window.engine.pending_tasks() == []


def test_open_queue_dialog_creates_dialog(qapp):
    window = MainWindow(config=Config())
    window.open_queue_dialog()
    assert window._queue_dialog is not None
    window._queue_dialog.close()


def test_open_storage_dialog_warns_without_device(qapp, monkeypatch):
    window = MainWindow(config=Config())
    warnings = []
    monkeypatch.setattr("podplex.ui.main_window.QMessageBox.warning", lambda *a, **k: warnings.append(a))
    window.open_storage_dialog()
    assert len(warnings) == 1


def test_open_storage_dialog_creates_dialog_when_device_set(qapp, tmp_path):
    window = MainWindow(config=Config())
    window.device_mount_path = tmp_path
    window.open_storage_dialog()
    assert window._storage_dialog is not None
    window._storage_dialog.close()
