from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

from podplex.core.plex_client import PlexTrack
from podplex.core.storage_analyzer import TrackFile

MATCH_THRESHOLD = 85.0


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return text


def find_match(track: PlexTrack, candidates: list[TrackFile]) -> TrackFile | None:
    if not candidates:
        return None
    target_artist = normalize(track.artist)
    target_title = normalize(track.title)
    best: TrackFile | None = None
    best_score = 0.0
    for candidate in candidates:
        artist_score = fuzz.ratio(normalize(candidate.artist), target_artist)
        title_score = fuzz.partial_ratio(normalize(candidate.path.stem), target_title)
        score = (artist_score + title_score) / 2
        if score > best_score:
            best_score = score
            best = candidate
    return best if best_score >= MATCH_THRESHOLD else None
