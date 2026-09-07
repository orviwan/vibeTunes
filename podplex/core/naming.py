from __future__ import annotations

import re

FORBIDDEN_CHARS = re.compile(r'[\\/:*?"<>|]')
MAX_COMPONENT_LENGTH = 100  # bytes; conservative headroom under FAT32/VFAT limits


def sanitize_component(name: str) -> str:
    name = FORBIDDEN_CHARS.sub("_", name)
    name = name.strip(" .")
    if not name:
        return "_"
    while len(name.encode("utf-8")) > MAX_COMPONENT_LENGTH:
        name = name[:-1]
    name = name.strip(" .")
    return name or "_"


def album_directory(
    pattern: str,
    artist: str,
    album: str,
    year: str | None,
    disc: int | None,
) -> list[str]:
    """Path components (excluding the library root) for an album's directory."""
    artist_c = sanitize_component(artist)
    if pattern == "standard":
        return [artist_c, sanitize_component(album)]

    if year:
        album_folder = f"{artist}-{year}-{album}"
    else:
        album_folder = f"{artist}-{album}"
    parts = [artist_c, sanitize_component(album_folder)]
    if disc is not None:
        parts.append(sanitize_component(f"CD {disc:02d}"))
    return parts


def track_filename(track_number: int | None, title: str, extension: str) -> str:
    title_c = sanitize_component(title)
    ext = extension.lstrip(".")
    if track_number is not None:
        return sanitize_component(f"{track_number:02d} {title_c}.{ext}")
    return f"{title_c}.{ext}"
