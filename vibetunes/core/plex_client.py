"""Plex API integration for vibeTunes."""
import time
import requests
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from plexapi.server import PlexServer
from plexapi.exceptions import Unauthorized, NotFound

CLIENT_IDENTIFIER = "vibetunes-rockbox-manager"
PRODUCT_NAME = "vibeTunes"
VERSION = "0.1.0"

PLEX_HEADERS = {
    "X-Plex-Product": PRODUCT_NAME,
    "X-Plex-Version": VERSION,
    "X-Plex-Client-Identifier": CLIENT_IDENTIFIER,
    "Accept": "application/json",
}

import unicodedata
import re

def normalize_music_key(artist: str, album: str = "") -> str:
    """
    Normalizes artist and album strings for reliable matching across
    Plex metadata and filesystem folder names (removes diacritics, curly quotes,
    punctuation, and excess whitespace).
    """
    def clean(s: str) -> str:
        s = unicodedata.normalize("NFKD", s).casefold()
        s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
        s = re.sub(r"[^\w\s]", "", s)
        return re.sub(r"\s+", " ", s).strip()

    if album:
        return f"{clean(artist)}::{clean(album)}"
    return clean(artist)

@dataclass
class PlexArtistSummary:
    rating_key: str
    name: str
    thumb_url: Optional[str] = None
    album_count: int = 0
    genres: List[str] = field(default_factory=list)

@dataclass
class PlexAlbumSummary:
    rating_key: str
    title: str
    artist_name: str
    year: Optional[int] = None
    thumb_url: Optional[str] = None
    track_count: int = 0
    genres: List[str] = field(default_factory=list)

@dataclass
class PlexPlaylistSummary:
    rating_key: str
    title: str
    track_count: int = 0
    duration_ms: int = 0
    thumb_url: Optional[str] = None

@dataclass
class PlexTrackDetail:
    rating_key: str
    title: str
    artist_name: str
    album_title: str
    track_number: int = 0
    disc_number: int = 1
    duration_ms: int = 0
    size_bytes: int = 0
    container: str = ""
    bitrate: int = 0
    stream_url: str = ""
    part_key: str = ""
    original_filename: str = ""
    year: Optional[int] = None

class PlexManager:
    def __init__(self, base_url: str = "", token: str = ""):
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.token = token
        self.server: Optional[PlexServer] = None
        self._cache_artists: Dict[str, List[PlexArtistSummary]] = {}
        self._cache_albums: Dict[str, List[PlexAlbumSummary]] = {}

    def connect(self) -> Tuple[bool, str]:
        """Attempts to connect to Plex. Returns (success, message_or_name)."""
        if not self.base_url or not self.token:
            return False, "Server URL and Token are required."
        try:
            self.server = PlexServer(self.base_url, self.token, timeout=10)
            return True, f"Connected to {self.server.friendlyName}"
        except Unauthorized:
            return False, "Unauthorized: Invalid Plex Token."
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    def is_connected(self) -> bool:
        return self.server is not None

    def get_music_libraries(self) -> List[str]:
        """Returns list of music section names (type == 'artist')."""
        if not self.server:
            return []
        try:
            return [s.title for s in self.server.library.sections() if s.type == "artist"]
        except Exception:
            return []

    def get_artists(self, library_name: str, force_refresh: bool = False) -> List[PlexArtistSummary]:
        if not self.server:
            return []
        if not force_refresh and library_name in self._cache_artists:
            return self._cache_artists[library_name]

        try:
            section = self.server.library.section(library_name)
            raw_artists = section.all()

            # Query all albums in section to determine exact album counts per artist
            album_counts: Dict[str, int] = {}
            try:
                raw_albums = section.albums()
                for alb in raw_albums:
                    pk = str(getattr(alb, "parentRatingKey", "") or "")
                    if pk:
                        album_counts[pk] = album_counts.get(pk, 0) + 1
            except Exception as ae:
                print(f"Notice: could not bulk-fetch album counts: {ae}")

            artists = []
            for a in raw_artists:
                thumb = self.get_thumb_url(a.thumb) if a.thumb else None
                genres = [g.tag for g in getattr(a, "genres", [])]
                rk = str(a.ratingKey)
                cnt = album_counts.get(rk, getattr(a, "childCount", 0))
                artists.append(PlexArtistSummary(
                    rating_key=rk,
                    name=a.title,
                    thumb_url=thumb,
                    album_count=cnt,
                    genres=genres,
                ))
            artists.sort(key=lambda x: x.name.lower())
            self._cache_artists[library_name] = artists
            return artists
        except Exception as e:
            print(f"Error fetching artists: {e}")
            return []

    def get_artist_albums(self, artist_key: str) -> List[PlexAlbumSummary]:
        if not self.server:
            return []
        if artist_key in self._cache_albums:
            return self._cache_albums[artist_key]

        try:
            artist = self.server.fetchItem(int(artist_key))
            raw_albums = artist.albums()
            albums = []
            for alb in raw_albums:
                try:
                    thumb = self.get_thumb_url(alb.thumb) if alb.thumb else None
                    year = alb.year if hasattr(alb, "year") else None
                    genres = [g.tag for g in getattr(alb, "genres", [])]
                    albums.append(PlexAlbumSummary(
                        rating_key=str(alb.ratingKey),
                        title=alb.title,
                        artist_name=artist.title,
                        year=year,
                        thumb_url=thumb,
                        track_count=getattr(alb, "leafCount", 0),
                        genres=genres,
                    ))
                except Exception as ie:
                    print(f"Warning: skipping album due to parse error: {ie}")
            # Sort albums by year if available
            albums.sort(key=lambda a: (a.year or 9999, a.title.lower()))
            self._cache_albums[artist_key] = albums
            return albums
        except Exception as e:
            print(f"Error fetching albums for artist {artist_key}: {e}")
            return []

    def get_album_tracks(self, album_key: str) -> List[PlexTrackDetail]:
        if not self.server:
            return []
        try:
            album = self.server.fetchItem(int(album_key))
            raw_tracks = album.tracks()
            tracks = []
            for t in raw_tracks:
                part_key = ""
                size = 0
                container = ""
                bitrate = 0
                orig_file = ""
                if t.media and len(t.media) > 0 and t.media[0].parts:
                    p = t.media[0].parts[0]
                    part_key = p.key
                    size = p.size or 0
                    container = p.container or ""
                    bitrate = t.media[0].bitrate or 0
                    orig_file = p.file or ""

                alb_year = getattr(album, "year", None)
                if alb_year is None and hasattr(album, "originallyAvailableAt") and album.originallyAvailableAt:
                    alb_year = getattr(album.originallyAvailableAt, "year", None)

                stream_url = self.server.url(part_key) if part_key else ""
                tracks.append(PlexTrackDetail(
                    rating_key=str(t.ratingKey),
                    title=t.title,
                    artist_name=album.parentTitle or getattr(t, "originalTitle", "") or "",
                    album_title=album.title,
                    track_number=getattr(t, "index", 0) or 0,
                    disc_number=getattr(t, "parentIndex", 1) or 1,
                    duration_ms=t.duration or 0,
                    size_bytes=size,
                    container=container,
                    bitrate=bitrate,
                    stream_url=stream_url,
                    part_key=part_key,
                    original_filename=orig_file,
                    year=alb_year,
                ))
            tracks.sort(key=lambda tr: (tr.disc_number, tr.track_number))
            return tracks
        except Exception as e:
            print(f"Error fetching tracks for album {album_key}: {e}")
            return []

    def get_thumb_url(self, thumb_path: str, width: int = 300, height: int = 300) -> str:
        """Returns transcode URL or direct URL for thumbnail."""
        if not self.server or not thumb_path:
            return ""
        # Return direct thumb URL with token
        return self.server.url(f"/photo/:/transcode?width={width}&height={height}&minSize=1&upscale=1&url={thumb_path}")

    def download_artwork_bytes(self, thumb_path: str) -> Optional[bytes]:
        if not self.server or not thumb_path:
            return None
        try:
            if thumb_path.startswith("http://") or thumb_path.startswith("https://"):
                url = thumb_path
            else:
                url = self.server.url(thumb_path)
            r = requests.get(url, headers={"X-Plex-Token": self.token}, timeout=15)
            if r.status_code == 200:
                return r.content
        except Exception:
            pass
        return None

    def get_playlists(self) -> List[PlexPlaylistSummary]:
        if not self.server:
            return []
        try:
            playlists = []
            for p in self.server.playlists():
                if getattr(p, "playlistType", "") == "audio" or getattr(p, "isAudio", False):
                    cnt = getattr(p, "leafCount", 0)
                    if not cnt and hasattr(p, "items"):
                        try:
                            cnt = len(p.items())
                        except Exception:
                            cnt = 0
                    playlists.append(PlexPlaylistSummary(
                        rating_key=str(p.ratingKey),
                        title=p.title,
                        track_count=cnt,
                        duration_ms=getattr(p, "duration", 0) or 0,
                        thumb_url=self.get_thumb_url(p.thumb) if getattr(p, "thumb", None) else None,
                    ))
            playlists.sort(key=lambda x: x.title.lower())
            return playlists
        except Exception as e:
            print(f"Error fetching playlists: {e}")
            return []

    def get_playlist_tracks(self, playlist_key: str) -> List[PlexTrackDetail]:
        if not self.server:
            return []
        try:
            pl = self.server.fetchItem(int(playlist_key))
            raw_tracks = pl.items()
            tracks = []
            for t in raw_tracks:
                part_key = ""
                size = 0
                container = ""
                bitrate = 0
                orig_file = ""
                if hasattr(t, "media") and t.media and len(t.media) > 0 and t.media[0].parts:
                    p = t.media[0].parts[0]
                    part_key = p.key
                    size = p.size or 0
                    container = p.container or ""
                    bitrate = t.media[0].bitrate or 0
                    orig_file = p.file or ""

                track_year = getattr(t, "parentYear", None) or getattr(t, "year", None)
                if track_year is None and hasattr(t, "originallyAvailableAt") and t.originallyAvailableAt:
                    track_year = getattr(t.originallyAvailableAt, "year", None)

                stream_url = self.server.url(part_key) if part_key else ""
                tracks.append(PlexTrackDetail(
                    rating_key=str(t.ratingKey),
                    title=t.title,
                    artist_name=getattr(t, "grandparentTitle", "") or getattr(t, "originalTitle", "") or "Unknown Artist",
                    album_title=getattr(t, "parentTitle", "") or "Unknown Album",
                    track_number=getattr(t, "index", 0) or 0,
                    disc_number=getattr(t, "parentIndex", 1) or 1,
                    duration_ms=getattr(t, "duration", 0) or 0,
                    size_bytes=size,
                    container=container,
                    bitrate=bitrate,
                    stream_url=stream_url,
                    part_key=part_key,
                    original_filename=orig_file,
                    year=track_year,
                ))
            return tracks
        except Exception as e:
            print(f"Error fetching tracks for playlist {playlist_key}: {e}")
            return []

# OAuth / PIN Helpers for easy Plex login
def create_plex_pin() -> Optional[Dict[str, Any]]:
    """Requests a new OAuth PIN from plex.tv."""
    try:
        r = requests.post("https://plex.tv/api/v2/pins?strong=true", headers=PLEX_HEADERS, timeout=10)
        if r.status_code == 201:
            return r.json()
    except Exception as e:
        print(f"Failed to create Plex PIN: {e}")
    return None

def check_plex_pin(pin_id: int) -> Optional[str]:
    """Polls plex.tv for the authToken of a PIN. Returns authToken or None."""
    try:
        r = requests.get(f"https://plex.tv/api/v2/pins/{pin_id}", headers=PLEX_HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("authToken")
    except Exception:
        pass
    return None

def fetch_user_servers(auth_token: str) -> List[Dict[str, Any]]:
    """Fetches user's accessible Plex Media Servers from plex.tv and probes for working connection."""
    headers = dict(PLEX_HEADERS)
    headers["X-Plex-Token"] = auth_token
    servers = []
    try:
        r = requests.get("https://plex.tv/api/v2/resources?includeHttps=1", headers=headers, timeout=10)
        if r.status_code == 200:
            for item in r.json():
                if "server" in item.get("provides", ""):
                    name = item.get("name")
                    conns = item.get("connections", [])
                    server_token = item.get("accessToken", auth_token)

                    # Build candidate URLs in priority order:
                    # 1. Local direct plain HTTP (avoids DNS rebinding issues with plex.direct)
                    # 2. Local HTTPS
                    # 3. Remote plain HTTP
                    # 4. Remote HTTPS
                    candidates = []
                    for c in conns:
                        addr = c.get("address")
                        port = c.get("port")
                        uri = c.get("uri")
                        is_local = c.get("local", False)
                        if addr and port:
                            plain = f"http://{addr}:{port}"
                            if plain not in candidates:
                                if is_local:
                                    candidates.insert(0, plain)
                                else:
                                    candidates.append(plain)
                        if uri and uri not in candidates:
                            candidates.append(uri)

                    # Quick probe each candidate URL (1s timeout)
                    best_uri = None
                    for cand in candidates:
                        try:
                            test_url = cand.rstrip("/") + "/identity"
                            res = requests.get(test_url, headers={"X-Plex-Token": server_token}, timeout=1.0, verify=False)
                            if res.status_code == 200:
                                best_uri = cand
                                break
                        except Exception:
                            pass

                    # Fallback to first candidate if none responded in time
                    if not best_uri and candidates:
                        best_uri = candidates[0]

                    servers.append({
                        "name": name,
                        "uri": best_uri or "",
                        "token": server_token,
                        "connections": conns,
                        "candidates": candidates,
                    })
    except Exception as e:
        print(f"Failed to fetch servers: {e}")
    return servers

