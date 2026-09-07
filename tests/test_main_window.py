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
