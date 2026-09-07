import pytest

from podplex.core.plex_client import PlexTrack
from podplex.core.sync_task_builder import build_album_sync_task


class FakeClient:
    def download_url(self, track):
        return f"http://fake{track.file_path}"


def _track(title, num, disc=1, ext=".flac"):
    return PlexTrack(
        key="k",
        title=title,
        artist="The Band",
        album="Great Album",
        track_number=num,
        year=1999,
        disc_number=disc,
        duration_ms=200000,
        file_path=f"/data/{title}{ext}",
        size_bytes=1000,
    )


def test_build_album_sync_task_rockbox_disc_layout(tmp_path):
    tracks = [_track("Song One", 1), _track("Song Two", 2)]
    task = build_album_sync_task(FakeClient(), tracks, tmp_path, "rockbox_disc", "task-1")
    assert task.task_id == "task-1"
    assert task.name == "The Band - Great Album"
    assert len(task.tracks) == 2
    expected_dir = tmp_path / "Music" / "The Band" / "The Band-1999-Great Album" / "CD 01"
    assert task.tracks[0].dest_path == expected_dir / "01 Song One.flac"
    assert task.tracks[0].source_url == "http://fake/data/Song One.flac"


def test_build_album_sync_task_standard_layout(tmp_path):
    tracks = [_track("Song One", 1)]
    task = build_album_sync_task(FakeClient(), tracks, tmp_path, "standard", "task-1")
    expected_dir = tmp_path / "Music" / "The Band" / "Great Album"
    assert task.tracks[0].dest_path == expected_dir / "01 Song One.flac"


def test_build_album_sync_task_raises_on_empty_tracks(tmp_path):
    with pytest.raises(ValueError):
        build_album_sync_task(FakeClient(), [], tmp_path, "standard", "task-1")
