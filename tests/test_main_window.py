from podplex.core.config import Config
from podplex.core.plex_client import PlexTrack
from podplex.ui.main_window import MainWindow, SettingsDialog


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


def test_start_oauth_login_opens_browser_and_shows_pin(qapp, monkeypatch):
    opened = []
    monkeypatch.setattr("podplex.ui.main_window.webbrowser.open", lambda url: opened.append(url))

    class FakeOAuthLogin:
        pin = "WXYZ"
        oauth_url = "https://plex.tv/link?pin=WXYZ"

        def run(self, on_authorized):
            pass

    monkeypatch.setattr("podplex.ui.main_window.PlexOAuthLogin", FakeOAuthLogin)
    dialog = SettingsDialog(Config())
    dialog.start_oauth_login()
    assert opened == ["https://plex.tv/link?pin=WXYZ"]
    assert "WXYZ" in dialog.oauth_status_label.text()


def test_oauth_token_received_fills_token_field(qapp):
    dialog = SettingsDialog(Config())
    dialog._on_oauth_token("secret-token")
    assert dialog.token_edit.text() == "secret-token"
    assert "Signed in" in dialog.oauth_status_label.text()


def test_detect_device_updates_storage_bar(qapp, tmp_path, monkeypatch):
    from podplex.core.device import DeviceInfo

    (tmp_path / "Music").mkdir()
    (tmp_path / "Music" / "f.mp3").write_bytes(b"x" * 100)
    info = DeviceInfo(mount_path=tmp_path, target="ipod6g", rockbox_version="1", read_only=False)
    monkeypatch.setattr("podplex.ui.main_window.find_device", lambda mount_override="": info)
    monkeypatch.setattr("podplex.ui.main_window.device_node_for_mount", lambda mount_path: None)
    window = MainWindow(config=Config())
    window.detect_device()
    segs = dict(window.storage_bar.segments())
    assert segs["music"] == 100


def test_eject_device_clears_storage_bar(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("podplex.ui.main_window.safe_eject", lambda node: None)
    window = MainWindow(config=Config())
    window.device_mount_path = tmp_path
    window.device_node = "/dev/sdb1"
    window.eject_device()
    assert window.storage_bar.segments() == []


def test_eject_device_resets_state(qapp, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("podplex.ui.main_window.safe_eject", lambda node: calls.append(node))
    window = MainWindow(config=Config())
    window.device_mount_path = tmp_path
    window.device_node = "/dev/sdb1"
    window.eject_device()
    assert calls == ["/dev/sdb1"]
    assert window.device_mount_path is None
    assert window.device_node is None
    assert window.device_label.text() == "Safe to Disconnect"


def test_eject_device_warns_without_device(qapp, monkeypatch):
    window = MainWindow(config=Config())
    warnings = []
    monkeypatch.setattr("podplex.ui.main_window.QMessageBox.warning", lambda *a, **k: warnings.append(a))
    window.eject_device()
    assert len(warnings) == 1


def test_fix_read_only_remounts_and_redetects(qapp, monkeypatch):
    calls = []
    monkeypatch.setattr("podplex.ui.main_window.remount_read_write", lambda node: calls.append(node))
    monkeypatch.setattr("podplex.ui.main_window.find_device", lambda mount_override="": None)
    window = MainWindow(config=Config())
    window.device_node = "/dev/sdb1"
    window.fix_read_only()
    assert calls == ["/dev/sdb1"]
    assert window.device_label.text() == "iPod: not detected"


def test_detect_device_sets_device_node(qapp, tmp_path, monkeypatch):
    from podplex.core.device import DeviceInfo

    info = DeviceInfo(mount_path=tmp_path, target="ipod6g", rockbox_version="3.15", read_only=False)
    monkeypatch.setattr("podplex.ui.main_window.find_device", lambda mount_override="": info)
    monkeypatch.setattr("podplex.ui.main_window.device_node_for_mount", lambda mount_path: "/dev/sdb1")
    window = MainWindow(config=Config())
    window.detect_device()
    assert window.device_node == "/dev/sdb1"


def test_on_device_playlists_listed_after_detect(qapp, tmp_path, monkeypatch):
    (tmp_path / "Playlists").mkdir()
    (tmp_path / "Playlists" / "Road Trip.m3u8").write_text("x")
    from podplex.core.device import DeviceInfo

    info = DeviceInfo(mount_path=tmp_path, target="ipod6g", rockbox_version="3.15", read_only=False)
    monkeypatch.setattr("podplex.ui.main_window.find_device", lambda mount_override="": info)
    monkeypatch.setattr("podplex.ui.main_window.device_node_for_mount", lambda mount_path: None)
    window = MainWindow(config=Config())
    window.detect_device()
    assert window.on_device_playlist_list.count() == 1
    assert window.on_device_playlist_list.item(0).text() == "Road Trip.m3u8"


def test_delete_selected_on_device_playlist_removes_file(qapp, tmp_path):
    (tmp_path / "Playlists").mkdir()
    p = tmp_path / "Playlists" / "Road Trip.m3u8"
    p.write_text("x")
    window = MainWindow(config=Config())
    window.device_mount_path = tmp_path
    window._refresh_on_device_playlists()
    window.on_device_playlist_list.setCurrentRow(0)
    window.delete_selected_on_device_playlist()
    assert not p.exists()
    assert window.on_device_playlist_list.count() == 0


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
