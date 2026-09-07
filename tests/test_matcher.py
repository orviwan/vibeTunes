from pathlib import Path

from podplex.core.matcher import find_match, normalize
from podplex.core.plex_client import PlexTrack
from podplex.core.storage_analyzer import TrackFile


def _track(title, artist="Sigur Ros"):
    return PlexTrack(
        key="k", title=title, artist=artist, album="()", track_number=1,
        year=2002, disc_number=1, duration_ms=1, file_path=f"/d/{title}.flac", size_bytes=100,
    )


def test_normalize_strips_diacritics_and_punctuation():
    assert normalize("Sigur Rós") == "sigur ros"
    assert normalize("AC/DC: T.N.T.!") == "ac dc t n t"


def test_find_match_exact():
    track = _track("Svefn-g-englar")
    candidates = [TrackFile(Path("/ipod/Sigur Ros/()/01 Svefn-g-englar.flac"), "Sigur Ros", "()", 100)]
    match = find_match(track, candidates)
    assert match is candidates[0]


def test_find_match_tolerates_diacritics_and_track_number_prefix():
    track = _track("Svefn-g-englar", artist="Sigur Rós")
    candidates = [TrackFile(Path("/ipod/Sigur Ros/2002 - ()/01 svefn g englar.mp3"), "Sigur Ros", "2002 - ()", 100)]
    match = find_match(track, candidates)
    assert match is candidates[0]


def test_find_match_returns_none_when_no_close_candidate():
    track = _track("Completely Different Song", artist="Some Artist")
    candidates = [TrackFile(Path("/ipod/Other/Album/01 Unrelated Track.flac"), "Other Artist", "Album", 100)]
    assert find_match(track, candidates) is None


def test_find_match_returns_none_for_empty_candidates():
    track = _track("Song")
    assert find_match(track, []) is None
