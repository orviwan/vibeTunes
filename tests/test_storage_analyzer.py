from pathlib import Path

from podplex.core.storage_analyzer import (
    TrackFile,
    compute_storage_bar,
    largest_albums,
    largest_artists,
    largest_files,
)


def _write_file(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_compute_storage_bar_splits_music_and_rockbox(tmp_path):
    _write_file(tmp_path / "Music" / "Artist" / "Album" / "01.mp3", 1000)
    _write_file(tmp_path / ".rockbox" / "rockbox.zip", 500)
    breakdown = compute_storage_bar(tmp_path)
    assert breakdown.music_bytes == 1000
    assert breakdown.rockbox_bytes == 500
    assert breakdown.total_bytes > 0
    assert breakdown.free_bytes >= 0


def test_largest_albums_sorted_descending():
    tracks = [
        TrackFile(Path("a1.mp3"), "Artist A", "Album 1", 100),
        TrackFile(Path("a2.mp3"), "Artist A", "Album 1", 150),
        TrackFile(Path("b1.mp3"), "Artist B", "Album 2", 500),
    ]
    result = largest_albums(tracks)
    assert result[0].artist == "Artist B"
    assert result[0].total_bytes == 500
    assert result[1].artist == "Artist A"
    assert result[1].total_bytes == 250
    assert result[1].track_count == 2


def test_largest_files_sorted_descending():
    tracks = [
        TrackFile(Path("small.mp3"), "A", "Al", 10),
        TrackFile(Path("big.mp3"), "A", "Al", 900),
    ]
    result = largest_files(tracks)
    assert [t.path.name for t in result] == ["big.mp3", "small.mp3"]


def test_largest_artists_aggregates_across_albums():
    tracks = [
        TrackFile(Path("a1.mp3"), "Artist A", "Album 1", 100),
        TrackFile(Path("a2.mp3"), "Artist A", "Album 2", 200),
        TrackFile(Path("b1.mp3"), "Artist B", "Album 3", 50),
    ]
    result = largest_artists(tracks)
    assert result[0].artist == "Artist A"
    assert result[0].total_bytes == 300


def test_limit_truncates_results():
    tracks = [TrackFile(Path(f"{i}.mp3"), f"Artist {i}", "Al", i) for i in range(10)]
    assert len(largest_files(tracks, limit=3)) == 3
