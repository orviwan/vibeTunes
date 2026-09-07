"""Unit tests for music key normalization and artwork extraction helpers."""
from pathlib import Path
from vibetunes.core.plex_client import normalize_music_key
from vibetunes.core.image_cache import extract_embedded_art, _url_hash

def test_normalize_music_key():
    # Test curly apostrophe vs straight
    k1 = normalize_music_key("Arctic Monkeys", "Whatever People Say I Am, That’s What I’m Not")
    k2 = normalize_music_key("Arctic Monkeys", "Whatever People Say I Am, That's What I'm Not")
    assert k1 == k2

    # Test accents / diacritics
    k3 = normalize_music_key("a-ha", "Hunting High and Low")
    k4 = normalize_music_key("a‐ha", "Hunting High and Low")
    assert k3 == k4

    # Test case and spacing
    k5 = normalize_music_key("  ABBA  ", "  Arrival  ")
    k6 = normalize_music_key("abba", "arrival")
    assert k5 == k6

def test_url_hash():
    h1 = _url_hash("http://192.168.0.239:32400/photo/:/transcode?url=/thumb1")
    h2 = _url_hash("http://192.168.0.239:32400/photo/:/transcode?url=/thumb1")
    h3 = _url_hash("http://192.168.0.239:32400/photo/:/transcode?url=/thumb2")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 24

def test_extract_embedded_art_missing_file():
    # Graceful handling of None or non-existent file
    assert extract_embedded_art(None) is None
    assert extract_embedded_art(Path("/does/not/exist/track.flac")) is None
