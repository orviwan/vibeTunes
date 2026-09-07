import pytest

from podplex.core import plex_client as pc
from podplex.core.plex_client import PlexClient, PlexTrack, _to_plex_track


class FakePart:
    def __init__(self, file, size):
        self.file = file
        self.size = size


class FakeMedia:
    def __init__(self, parts):
        self.parts = parts


class FakeAlbum:
    def __init__(self, year):
        self.year = year


class FakeTrack:
    def __init__(self, title, grandparentTitle, parentTitle, index, parentIndex, duration, file, size, album_year=2001):
        self.key = f"/library/metadata/{title}"
        self.title = title
        self.grandparentTitle = grandparentTitle
        self.parentTitle = parentTitle
        self.index = index
        self.parentIndex = parentIndex
        self.duration = duration
        self.media = [FakeMedia([FakePart(file, size)])]
        self._album_year = album_year

    def album(self):
        return FakeAlbum(self._album_year)


def test_to_plex_track_maps_fields():
    t = FakeTrack("Song", "Artist", "Album", 3, 1, 210000, "/data/Artist/Album/03 Song.flac", 12345678)
    pt = _to_plex_track(t)
    assert pt.title == "Song"
    assert pt.artist == "Artist"
    assert pt.album == "Album"
    assert pt.track_number == 3
    assert pt.disc_number == 1
    assert pt.file_path == "/data/Artist/Album/03 Song.flac"
    assert pt.size_bytes == 12345678


class FakeSection:
    def __init__(self, title, type_):
        self.title = title
        self.type = type_

    def searchArtists(self):
        return ["artist1", "artist2"]


class FakeLibrary:
    def __init__(self, sections):
        self._sections = sections

    def sections(self):
        return self._sections

    def section(self, name):
        for s in self._sections:
            if s.title == name:
                return s
        raise KeyError(name)


class FakeServer:
    def __init__(self, sections):
        self.library = FakeLibrary(sections)

    def url(self, part, includeToken=True):
        return f"http://fake{part}?X-Plex-Token=abc"


def test_music_library_names_filters_artist_type():
    server = FakeServer([FakeSection("Music", "artist"), FakeSection("Movies", "movie")])
    client = PlexClient(server, "Music")
    assert client.music_library_names() == ["Music"]


def test_artists_uses_configured_library():
    server = FakeServer([FakeSection("Music", "artist")])
    client = PlexClient(server, "Music")
    assert client.artists() == ["artist1", "artist2"]


class FakeServerWithPlaylists(FakeServer):
    def playlists(self, playlistType="audio"):
        return [f"playlist-{playlistType}"]


def test_playlists_requests_audio_playlist_type():
    server = FakeServerWithPlaylists([FakeSection("Music", "artist")])
    client = PlexClient(server, "Music")
    assert client.playlists() == ["playlist-audio"]


def test_test_connection_true_on_success():
    server = FakeServer([FakeSection("Music", "artist")])
    client = PlexClient(server, "Music")
    assert client.test_connection() is True


def test_test_connection_false_on_exception():
    class BrokenLibrary:
        def sections(self):
            raise ConnectionError("nope")

    class BrokenServer:
        library = BrokenLibrary()

    client = PlexClient(BrokenServer(), "Music")
    assert client.test_connection() is False


def test_download_url_includes_token():
    server = FakeServer([FakeSection("Music", "artist")])
    client = PlexClient(server, "Music")
    track = PlexTrack("k", "t", "a", "al", 1, 2020, 1, 1000, "/data/f.flac", 100)
    url = client.download_url(track)
    assert url == "http://fake/data/f.flac?X-Plex-Token=abc"


class FakePinLogin:
    def __init__(self, oauth=True):
        self.pin = "ABCD"
        self.token = None

    def oauthUrl(self):
        return "https://plex.tv/link?pin=ABCD"

    def run(self, timeout=120):
        pass

    def waitForLogin(self):
        self.token = "sometoken"


def test_oauth_login_calls_callback_with_token(monkeypatch):
    monkeypatch.setattr(pc, "MyPlexPinLogin", FakePinLogin)
    login = pc.PlexOAuthLogin()
    assert login.pin == "ABCD"
    assert login.oauth_url == "https://plex.tv/link?pin=ABCD"
    received = []
    login.run(on_authorized=received.append)
    assert received == ["sometoken"]
