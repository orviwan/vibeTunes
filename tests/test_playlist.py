from pathlib import Path

from podplex.core.playlist import (
    delete_playlist,
    list_on_device_playlists,
    resolve_playlist_tracks,
    to_rockbox_path,
    write_m3u8,
)
from podplex.core.plex_client import PlexTrack
from podplex.core.storage_analyzer import TrackFile


def _track(title, artist="Art", album="Alb", num=1, year=2000, disc=1, ext=".flac"):
    return PlexTrack(
        key="k", title=title, artist=artist, album=album, track_number=num,
        year=year, disc_number=disc, duration_ms=1, file_path=f"/d/{title}{ext}", size_bytes=100,
    )


class FakeClient:
    def download_url(self, track):
        return f"http://fake{track.file_path}"


def test_to_rockbox_path_prefixes_drive_label(tmp_path):
    f = tmp_path / "Music" / "Art" / "Alb" / "01 Song.flac"
    assert to_rockbox_path(tmp_path, f) == "/<HDD0>/Music/Art/Alb/01 Song.flac"


def test_resolve_playlist_tracks_reuses_matched_existing_file(tmp_path):
    track = _track("Song One")
    existing = TrackFile(
        path=tmp_path / "Music" / "Art" / "Alb" / "01 Song One.flac", artist="Art", album="Alb", size_bytes=100
    )
    resolved, to_download = resolve_playlist_tracks([track], [existing], FakeClient(), tmp_path, "standard")
    assert resolved == [existing.path]
    assert to_download == []


def test_resolve_playlist_tracks_downloads_when_no_match(tmp_path):
    track = _track("Song One")
    resolved, to_download = resolve_playlist_tracks([track], [], FakeClient(), tmp_path, "standard")
    expected_dest = tmp_path / "Music" / "Art" / "Alb" / "01 Song One.flac"
    assert resolved == [expected_dest]
    assert len(to_download) == 1
    assert to_download[0].dest_path == expected_dest
    assert to_download[0].source_url == "http://fake/d/Song One.flac"


def test_write_m3u8_has_bom_and_rockbox_paths(tmp_path):
    paths = [tmp_path / "Music" / "Art" / "Alb" / "01 Song One.flac"]
    out_path = write_m3u8("My Playlist", tmp_path, paths)
    assert out_path == tmp_path / "Playlists" / "My Playlist.m3u8"
    raw = out_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    assert text.strip() == "/<HDD0>/Music/Art/Alb/01 Song One.flac"


def test_list_on_device_playlists_returns_m3u8_files(tmp_path):
    (tmp_path / "Playlists").mkdir()
    (tmp_path / "Playlists" / "A.m3u8").write_text("x")
    (tmp_path / "Playlists" / "B.m3u8").write_text("x")
    (tmp_path / "Playlists" / "ignore.txt").write_text("x")
    result = list_on_device_playlists(tmp_path)
    assert [p.name for p in result] == ["A.m3u8", "B.m3u8"]


def test_list_on_device_playlists_returns_empty_when_missing(tmp_path):
    assert list_on_device_playlists(tmp_path) == []


def test_delete_playlist_removes_file(tmp_path):
    (tmp_path / "Playlists").mkdir()
    p = tmp_path / "Playlists" / "A.m3u8"
    p.write_text("x")
    delete_playlist(p)
    assert not p.exists()
