from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from plexapi.myplex import MyPlexPinLogin
from plexapi.server import PlexServer


@dataclass(frozen=True)
class PlexTrack:
    key: str
    title: str
    artist: str
    album: str
    track_number: int | None
    year: int | None
    disc_number: int | None
    duration_ms: int | None
    file_path: str
    size_bytes: int


class PlexClient:
    def __init__(self, server, library_name: str = "Music"):
        self._server = server
        self._library_name = library_name

    @classmethod
    def connect(cls, url: str, token: str, library_name: str = "Music") -> "PlexClient":
        server = PlexServer(url, token)
        return cls(server, library_name)

    def test_connection(self) -> bool:
        try:
            self._server.library.sections()
            return True
        except Exception:
            return False

    def music_library_names(self) -> list[str]:
        return [s.title for s in self._server.library.sections() if s.type == "artist"]

    def artists(self):
        section = self._server.library.section(self._library_name)
        return section.searchArtists()

    def albums_for_artist(self, artist):
        return artist.albums()

    def playlists(self):
        return self._server.playlists(playlistType="audio")

    def tracks_for_album(self, album) -> list[PlexTrack]:
        return [_to_plex_track(t) for t in album.tracks()]

    def tracks_for_playlist(self, playlist) -> list[PlexTrack]:
        return [_to_plex_track(t) for t in playlist.items()]

    def download_url(self, track: PlexTrack) -> str:
        return self._server.url(track.file_path, includeToken=True)


def _to_plex_track(t) -> PlexTrack:
    part = t.media[0].parts[0]
    year = None
    if hasattr(t, "album"):
        year = getattr(t.album(), "year", None)
    return PlexTrack(
        key=t.key,
        title=t.title,
        artist=t.grandparentTitle,
        album=t.parentTitle,
        track_number=getattr(t, "index", None),
        year=year,
        disc_number=getattr(t, "parentIndex", None),
        duration_ms=getattr(t, "duration", None),
        file_path=part.file,
        size_bytes=getattr(part, "size", 0) or 0,
    )


class PlexOAuthLogin:
    """Wraps plexapi's PIN-based OAuth linking flow (plex.tv/link)."""

    def __init__(self):
        self._pinlogin = MyPlexPinLogin(oauth=True)

    @property
    def pin(self) -> str:
        return self._pinlogin.pin

    @property
    def oauth_url(self) -> str:
        return self._pinlogin.oauthUrl()

    def run(self, on_authorized: Callable[[str], None], timeout: int = 120) -> None:
        self._pinlogin.run(timeout=timeout)
        self._pinlogin.waitForLogin()
        if self._pinlogin.token:
            on_authorized(self._pinlogin.token)
