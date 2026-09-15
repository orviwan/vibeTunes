"""Unit tests for StorageAnalyzerDialog and largest files/albums inspection."""
from pathlib import Path
from PySide6.QtCore import Qt

from vibestunes.core.ipod_scanner import iPodArtist, iPodAlbum, iPodTrack
from vibestunes.core.plex_client import PlexManager, PlexArtistSummary, PlexAlbumSummary
from vibestunes.ui.widgets.storage_analyzer_dialog import StorageAnalyzerDialog
from vibestunes.ui.widgets.plex_browser import PlexBrowserWidget

def test_storage_analyzer_aggregation_and_sorting(qapp):
    # Setup mock iPod data
    t1 = iPodTrack(filename="01 - Track A.flac", path=Path("/ipod/Art1/Alb1/01.flac"), size_bytes=50 * 1024 * 1024, title="Track A", track_number=1)
    t2 = iPodTrack(filename="02 - Track B.flac", path=Path("/ipod/Art1/Alb1/02.flac"), size_bytes=100 * 1024 * 1024, title="Track B", track_number=2)
    alb1 = iPodAlbum(title="Album One", artist_name="Artist One", path=Path("/ipod/Art1/Alb1"), tracks=[t1, t2], total_size_bytes=150 * 1024 * 1024, year=2000)

    t3 = iPodTrack(filename="01 - Song X.mp3", path=Path("/ipod/Art2/Alb2/01.mp3"), size_bytes=10 * 1024 * 1024, title="Song X", track_number=1)
    alb2 = iPodAlbum(title="Album Two", artist_name="Artist Two", path=Path("/ipod/Art2/Alb2"), tracks=[t3], total_size_bytes=10 * 1024 * 1024, year=2010)

    art1 = iPodArtist(name="Artist One", path=Path("/ipod/Art1"), albums=[alb1], total_size_bytes=150 * 1024 * 1024)
    art2 = iPodArtist(name="Artist Two", path=Path("/ipod/Art2"), albums=[alb2], total_size_bytes=10 * 1024 * 1024)

    dialog = StorageAnalyzerDialog([art2, art1], "/ipod")

    # Verify ranked albums: alb1 (150MB) should be #1, alb2 (10MB) should be #2
    assert len(dialog.all_albums) == 2
    assert dialog.all_albums[0]["title"] == "Album One"
    assert dialog.all_albums[0]["size_bytes"] == 150 * 1024 * 1024
    assert dialog.all_albums[1]["title"] == "Album Two"

    # Verify ranked tracks: t2 (100MB) #1, t1 (50MB) #2, t3 (10MB) #3
    assert len(dialog.all_tracks) == 3
    assert dialog.all_tracks[0]["title"] == "Track B"
    assert dialog.all_tracks[0]["size_bytes"] == 100 * 1024 * 1024
    assert dialog.all_tracks[1]["title"] == "Track A"
    assert dialog.all_tracks[2]["title"] == "Song X"

    # Verify ranked artists: art1 (150MB) #1, art2 (10MB) #2
    assert len(dialog.all_artists) == 2
    assert dialog.all_artists[0]["name"] == "Artist One"
    assert dialog.all_artists[1]["name"] == "Artist Two"

    # Verify tables populated
    assert dialog.albums_table.rowCount() == 2
    assert dialog.albums_table.item(0, 1).text() == "Album One"
    assert "150.0 MB" in dialog.albums_table.item(0, 5).text()

    assert dialog.tracks_table.rowCount() == 3
    assert dialog.tracks_table.item(0, 1).text() == "Track B"
    assert "100.0 MB" in dialog.tracks_table.item(0, 4).text()

    assert dialog.artists_table.rowCount() == 2
    assert dialog.artists_table.item(0, 1).text() == "Artist One"

    # Verify search filtering
    dialog.search_input.setText("Song X")
    assert dialog.tracks_table.rowCount() == 1
    assert dialog.tracks_table.item(0, 1).text() == "Song X"
    assert dialog.albums_table.rowCount() == 0

    # Reset search
    dialog.search_input.setText("")
    assert dialog.tracks_table.rowCount() == 3
    assert dialog.albums_table.rowCount() == 2

    # Verify jump signal
    jumped_album = []
    dialog.show_album_in_library.connect(lambda art, alb: jumped_album.append((art, alb)))
    dialog._on_jump_album(dialog.all_albums[0])
    assert jumped_album == [("Artist One", "Album One")]

def test_plex_browser_select_artist_and_album(qapp):
    plex = PlexManager()
    browser = PlexBrowserWidget(plex)

    art1 = PlexArtistSummary(rating_key="1", name="Radiohead", album_count=2)
    art2 = PlexArtistSummary(rating_key="2", name="Ash", album_count=1)
    browser.artists = [art1, art2]
    browser.displayed_artists = [art1, art2]
    browser._filter_artists()

    alb = PlexAlbumSummary(rating_key="10", title="1977", artist_name="Ash", year=1996, track_count=12)
    browser.current_albums = [alb]
    browser.displayed_albums = [alb]

    # Select Ash and 1977
    browser.select_artist_and_album("Ash", "1977")
    assert browser.selected_artist == art2
