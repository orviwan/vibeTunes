from podplex.core.library_index import check_album_status, delete_album, scan_music_tree
from podplex.core.plex_client import PlexTrack


def _track(title, num, size=100, ext=".flac", artist="The Band", album="Great Album", year=1999, disc=1):
    return PlexTrack(
        key="k",
        title=title,
        artist=artist,
        album=album,
        track_number=num,
        year=year,
        disc_number=disc,
        duration_ms=1000,
        file_path=f"/data/{title}{ext}",
        size_bytes=size,
    )


def test_check_album_status_all_missing(tmp_path):
    tracks = [_track("Song One", 1), _track("Song Two", 2)]
    status = check_album_status(tmp_path, "rockbox_disc", tracks)
    assert status.state == "MISSING"
    assert status.synced_count == 0
    assert status.total_count == 2


def test_check_album_status_fully_synced(tmp_path):
    tracks = [_track("Song One", 1, size=8), _track("Song Two", 2, size=8)]
    album_dir = tmp_path / "Music" / "The Band" / "The Band-1999-Great Album" / "CD 01"
    album_dir.mkdir(parents=True)
    (album_dir / "01 Song One.flac").write_bytes(b"12345678")
    (album_dir / "02 Song Two.flac").write_bytes(b"12345678")
    status = check_album_status(tmp_path, "rockbox_disc", tracks)
    assert status.state == "ON_IPOD"
    assert status.synced_count == 2


def test_check_album_status_partial(tmp_path):
    tracks = [_track("Song One", 1, size=8), _track("Song Two", 2, size=8)]
    album_dir = tmp_path / "Music" / "The Band" / "The Band-1999-Great Album" / "CD 01"
    album_dir.mkdir(parents=True)
    (album_dir / "01 Song One.flac").write_bytes(b"12345678")
    status = check_album_status(tmp_path, "rockbox_disc", tracks)
    assert status.state == "PARTIAL"
    assert status.synced_count == 1


def test_check_album_status_size_mismatch_counts_as_missing(tmp_path):
    tracks = [_track("Song One", 1, size=8)]
    album_dir = tmp_path / "Music" / "The Band" / "The Band-1999-Great Album" / "CD 01"
    album_dir.mkdir(parents=True)
    (album_dir / "01 Song One.flac").write_bytes(b"wrong-size-data")
    status = check_album_status(tmp_path, "rockbox_disc", tracks)
    assert status.state == "MISSING"


def test_delete_album_removes_directory_and_returns_bytes_freed(tmp_path):
    tracks = [_track("Song One", 1, size=8)]
    album_dir = tmp_path / "Music" / "The Band" / "The Band-1999-Great Album" / "CD 01"
    album_dir.mkdir(parents=True)
    (album_dir / "01 Song One.flac").write_bytes(b"12345678")
    freed = delete_album(tmp_path, "rockbox_disc", tracks)
    assert freed == 8
    assert not album_dir.exists()


def test_delete_album_missing_returns_zero(tmp_path):
    tracks = [_track("Song One", 1)]
    freed = delete_album(tmp_path, "rockbox_disc", tracks)
    assert freed == 0


def test_scan_music_tree_groups_by_artist_and_album(tmp_path):
    d1 = tmp_path / "Music" / "Artist A" / "Album 1"
    d1.mkdir(parents=True)
    (d1 / "01.mp3").write_bytes(b"x" * 10)
    d2 = tmp_path / "Music" / "Artist A" / "Artist A-2000-Album 2" / "CD 01"
    d2.mkdir(parents=True)
    (d2 / "01.flac").write_bytes(b"x" * 20)
    results = scan_music_tree(tmp_path)
    by_album = {(t.artist, t.album): t.size_bytes for t in results}
    assert by_album[("Artist A", "Album 1")] == 10
    assert by_album[("Artist A", "Artist A-2000-Album 2")] == 20


def test_scan_music_tree_ignores_non_audio_files(tmp_path):
    d1 = tmp_path / "Music" / "Artist A" / "Album 1"
    d1.mkdir(parents=True)
    (d1 / "cover.jpg").write_bytes(b"x" * 10)
    results = scan_music_tree(tmp_path)
    assert results == []


def test_scan_music_tree_returns_empty_when_no_music_dir(tmp_path):
    assert scan_music_tree(tmp_path) == []
