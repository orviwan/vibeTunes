# PodPlex Foundation & Core Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build a runnable PodPlex application that can authenticate to a Plex
server, detect a mounted Rockbox iPod, browse the Plex music library, and
sync a selected album to the device with progress reporting — the core
sync loop, end to end.

**Architecture:** A Python package (`podplex/`) with a `core/` layer of
independently unit-testable modules (config, naming, device detection,
storage analysis, Plex client wrapper, HTTP downloader, background sync
engine) and a thin `ui/` layer (PySide6) that wires them together. All
background work runs on plain `threading.Thread(daemon=True)` instances;
cross-thread UI updates go through Qt `Signal`s.

**Tech Stack:** Python 3.10+, PySide6 (Qt6), `plexapi`, `requests`,
`pytest`, packaged with `uv`/`pyproject.toml` (hatchling backend).

**Relationship to the design spec:** This is Plan 1 of several. It covers
phases 1–4 of `docs/superpowers/specs/2026-09-07-podplex-linux-design.md`
(scaffold, Plex client + read-only library browsing, device detection +
storage bar, naming + core sync engine). Queue management UI, the storage
analyzer dialog, on-device library indexing/badges, artwork caching,
playlist sync, and desktop packaging/polish are covered by follow-up plans
built on top of this foundation.

---

### Task 1: Project Scaffold & Packaging

**Files:**
- Create: `pyproject.toml`
- Create: `podplex/__init__.py`
- Create: `podplex/core/__init__.py`
- Create: `podplex/ui/__init__.py`
- Create: `tests/conftest.py`
- Create: `.gitignore`

- [x] **Step 1: Create the package directories and empty `__init__.py` files**

```bash
mkdir -p podplex/core podplex/ui podplex/assets tests
touch podplex/__init__.py podplex/core/__init__.py podplex/ui/__init__.py
```

- [x] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "podplex"
version = "0.1.0"
description = "Sync a Plex music library to a Rockbox-modded iPod on Linux"
requires-python = ">=3.10"
dependencies = [
    "PySide6>=6.6",
    "plexapi>=4.15",
    "requests>=2.31",
    "mutagen>=1.47",
    "Pillow>=10.0",
    "rapidfuzz>=3.5",
]

[project.scripts]
podplex = "podplex.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["podplex"]

[dependency-groups]
dev = ["pytest>=8.0"]
```

- [x] **Step 3: Write `tests/conftest.py`**

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
```

- [x] **Step 4: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
*.egg-info/
```

- [x] **Step 5: Install dependencies and verify the package imports**

Run: `uv sync`
Expected: dependency resolution succeeds, `.venv/` created

Run: `uv run python -c "import podplex; import PySide6; import plexapi; print('ok')"`
Expected: `ok`

- [x] **Step 6: Commit**

```bash
git add pyproject.toml podplex tests/conftest.py .gitignore
git commit -m "$(cat <<'EOF'
Scaffold PodPlex package and packaging config

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Config Module

**Files:**
- Create: `podplex/core/config.py`
- Test: `tests/test_config.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_config.py
import json

from podplex.core.config import Config


def test_defaults():
    c = Config()
    assert c.plex_library_name == "Music"
    assert c.naming_pattern == "rockbox_disc"
    assert c.download_artwork is True
    assert c.transcode_mode == "direct"


def test_round_trip(tmp_path):
    path = tmp_path / "config.json"
    c = Config(plex_url="http://x:32400", plex_token="abc", naming_pattern="standard")
    c.save(path)
    loaded = Config.load(path)
    assert loaded == c


def test_load_missing_file_returns_defaults(tmp_path):
    path = tmp_path / "nope.json"
    loaded = Config.load(path)
    assert loaded == Config()


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"plex_url": "http://x", "bogus_key": "z"}))
    loaded = Config.load(path)
    assert loaded.plex_url == "http://x"


def test_load_corrupt_json_returns_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not valid json")
    loaded = Config.load(path)
    assert loaded == Config()
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'podplex.core.config'`

- [x] **Step 3: Write `podplex/core/config.py`**

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "podplex"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class Config:
    plex_url: str = ""
    plex_token: str = ""
    plex_library_name: str = "Music"
    ipod_mount_override: str = ""
    naming_pattern: str = "rockbox_disc"
    download_artwork: bool = True
    transcode_mode: str = "direct"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls.from_dict(data)

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 5 passed

- [x] **Step 5: Commit**

```bash
git add podplex/core/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
Add Config dataclass with JSON load/save

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Naming Module

**Files:**
- Create: `podplex/core/naming.py`
- Test: `tests/test_naming.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_naming.py
from podplex.core.naming import album_directory, sanitize_component, track_filename


def test_sanitize_component_replaces_forbidden_chars():
    assert sanitize_component('AC/DC: Best?') == 'AC_DC_ Best_'


def test_sanitize_component_all_forbidden_chars_becomes_underscores():
    assert sanitize_component('???') == '___'


def test_sanitize_component_strips_trailing_dots_and_spaces():
    assert sanitize_component('Trailing... ') == 'Trailing'


def test_sanitize_component_truncates_long_names():
    long_name = "x" * 300
    result = sanitize_component(long_name)
    assert len(result.encode("utf-8")) <= 100


def test_sanitize_component_empty_after_strip_becomes_underscore():
    assert sanitize_component('   ') == '_'


def test_album_directory_rockbox_disc_with_year_and_disc():
    parts = album_directory("rockbox_disc", "The Band", "Great Album", "1999", 1)
    assert parts == ["The Band", "The Band-1999-Great Album", "CD 01"]


def test_album_directory_rockbox_disc_without_disc():
    parts = album_directory("rockbox_disc", "The Band", "Great Album", "1999", None)
    assert parts == ["The Band", "The Band-1999-Great Album"]


def test_album_directory_rockbox_disc_without_year():
    parts = album_directory("rockbox_disc", "The Band", "Great Album", None, None)
    assert parts == ["The Band", "The Band-Great Album"]


def test_album_directory_standard_ignores_year_and_disc():
    parts = album_directory("standard", "The Band", "Great Album", "1999", 2)
    assert parts == ["The Band", "Great Album"]


def test_track_filename_with_number():
    assert track_filename(3, "Song Title", ".flac") == "03 Song Title.flac"


def test_track_filename_without_number():
    assert track_filename(None, "Song Title", "mp3") == "Song Title.mp3"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_naming.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'podplex.core.naming'`

- [x] **Step 3: Write `podplex/core/naming.py`**

```python
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
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_naming.py -v`
Expected: 11 passed

- [x] **Step 5: Commit**

```bash
git add podplex/core/naming.py tests/test_naming.py
git commit -m "$(cat <<'EOF'
Add FAT32-safe naming and album/track path layout

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Device Detection Module

**Files:**
- Create: `podplex/core/device.py`
- Test: `tests/test_device.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_device.py
from pathlib import Path

from podplex.core.device import (
    device_node_for_mount,
    find_device,
    is_read_only,
    parse_rockbox_info,
    remount_read_write,
    safe_eject,
)


def _make_fake_ipod(root: Path, target="ipod6g", version="3.15") -> Path:
    mount = root / "IPOD"
    rockbox_dir = mount / ".rockbox"
    rockbox_dir.mkdir(parents=True)
    (rockbox_dir / "rockbox-info.txt").write_text(f"Target: {target}\nVersion: {version}\n")
    return mount


def test_find_device_locates_rockbox_mount(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    mount = _make_fake_ipod(media_root)
    device = find_device(scan_roots=(str(media_root),))
    assert device is not None
    assert device.mount_path == mount
    assert device.target == "ipod6g"
    assert device.rockbox_version == "3.15"


def test_find_device_returns_none_when_no_rockbox_dir(tmp_path):
    media_root = tmp_path / "media"
    (media_root / "SOMEDRIVE").mkdir(parents=True)
    device = find_device(scan_roots=(str(media_root),))
    assert device is None


def test_find_device_uses_mount_override(tmp_path):
    mount = _make_fake_ipod(tmp_path, target="ipodvideo")
    device = find_device(mount_override=str(mount))
    assert device is not None
    assert device.target == "ipodvideo"


def test_parse_rockbox_info_missing_file_returns_none(tmp_path):
    target, version = parse_rockbox_info(tmp_path / "nope.txt")
    assert target is None
    assert version is None


def test_is_read_only_true_when_ro_option_present(tmp_path):
    mounts = tmp_path / "mounts"
    mounts.write_text("/dev/sdb1 /media/IPOD vfat ro,relatime 0 0\n")
    assert is_read_only(Path("/media/IPOD"), mounts_path=mounts) is True


def test_is_read_only_false_when_rw(tmp_path):
    mounts = tmp_path / "mounts"
    mounts.write_text("/dev/sdb1 /media/IPOD vfat rw,relatime 0 0\n")
    assert is_read_only(Path("/media/IPOD"), mounts_path=mounts) is False


def test_is_read_only_false_when_mount_not_found(tmp_path):
    mounts = tmp_path / "mounts"
    mounts.write_text("/dev/sda1 /home ext4 rw 0 0\n")
    assert is_read_only(Path("/media/IPOD"), mounts_path=mounts) is False


def test_device_node_for_mount(tmp_path):
    mounts = tmp_path / "mounts"
    mounts.write_text("/dev/sdb1 /media/IPOD vfat rw,relatime 0 0\n")
    assert device_node_for_mount(Path("/media/IPOD"), mounts_path=mounts) == "/dev/sdb1"


def test_remount_read_write_invokes_udisksctl(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, text):
        calls.append(cmd)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("podplex.core.device.subprocess.run", fake_run)
    remount_read_write("/dev/sdb1")
    assert calls == [["udisksctl", "mount", "-b", "/dev/sdb1", "-o", "remount,rw"]]


def test_safe_eject_syncs_unmounts_and_powers_off(monkeypatch):
    calls = []
    monkeypatch.setattr("podplex.core.device.os.sync", lambda: calls.append("sync"))

    def fake_run(cmd, capture_output, text):
        calls.append(cmd)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("podplex.core.device.subprocess.run", fake_run)
    safe_eject("/dev/sdb1")
    assert calls == [
        "sync",
        ["udisksctl", "unmount", "-b", "/dev/sdb1"],
        ["udisksctl", "power-off", "-b", "/dev/sdb1"],
    ]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_device.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'podplex.core.device'`

- [x] **Step 3: Write `podplex/core/device.py`**

```python
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SCAN_ROOTS = ("/run/media/{user}", "/media/{user}", "/media")


@dataclass
class DeviceInfo:
    mount_path: Path
    target: str | None
    rockbox_version: str | None
    read_only: bool


def candidate_mount_roots(scan_roots=DEFAULT_SCAN_ROOTS, user: str | None = None) -> list[Path]:
    user = user or os.environ.get("USER", "")
    roots = []
    for root in scan_roots:
        resolved = root.format(user=user)
        p = Path(resolved)
        if p.exists():
            roots.append(p)
    return roots


def find_device(
    scan_roots=DEFAULT_SCAN_ROOTS,
    mount_override: str = "",
    user: str | None = None,
) -> DeviceInfo | None:
    if mount_override:
        p = Path(mount_override)
        if (p / ".rockbox").is_dir():
            return _build_device_info(p)
        return None
    for root in candidate_mount_roots(scan_roots, user):
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if (entry / ".rockbox").is_dir():
                return _build_device_info(entry)
    return None


def _build_device_info(mount_path: Path) -> DeviceInfo:
    target, version = parse_rockbox_info(mount_path / ".rockbox" / "rockbox-info.txt")
    read_only = is_read_only(mount_path, mounts_path=Path("/proc/mounts"))
    return DeviceInfo(mount_path=mount_path, target=target, rockbox_version=version, read_only=read_only)


def parse_rockbox_info(info_path: Path) -> tuple[str | None, str | None]:
    if not info_path.exists():
        return None, None
    target = None
    version = None
    for line in info_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "target":
            target = value
        elif key == "version":
            version = value
    return target, version


def is_read_only(mount_path: Path, mounts_path: Path = Path("/proc/mounts")) -> bool:
    mount_str = str(mount_path)
    try:
        lines = mounts_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        fields = line.split()
        if len(fields) < 4 or fields[1] != mount_str:
            continue
        return "ro" in fields[3].split(",")
    return False


def device_node_for_mount(mount_path: Path, mounts_path: Path = Path("/proc/mounts")) -> str | None:
    mount_str = str(mount_path)
    try:
        lines = mounts_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == mount_str:
            return fields[0]
    return None


def remount_read_write(device_node: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["udisksctl", "mount", "-b", device_node, "-o", "remount,rw"],
        capture_output=True,
        text=True,
    )


def safe_eject(device_node: str) -> list[subprocess.CompletedProcess]:
    results = []
    os.sync()
    results.append(subprocess.run(["udisksctl", "unmount", "-b", device_node], capture_output=True, text=True))
    results.append(subprocess.run(["udisksctl", "power-off", "-b", device_node], capture_output=True, text=True))
    return results
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_device.py -v`
Expected: 11 passed

- [x] **Step 5: Commit**

```bash
git add podplex/core/device.py tests/test_device.py
git commit -m "$(cat <<'EOF'
Add Rockbox iPod device detection and safe eject

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Storage Analyzer Module

**Files:**
- Create: `podplex/core/storage_analyzer.py`
- Test: `tests/test_storage_analyzer.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_storage_analyzer.py
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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storage_analyzer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'podplex.core.storage_analyzer'`

- [x] **Step 3: Write `podplex/core/storage_analyzer.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrackFile:
    path: Path
    artist: str
    album: str
    size_bytes: int


@dataclass
class StorageBreakdown:
    total_bytes: int
    free_bytes: int
    music_bytes: int
    rockbox_bytes: int
    other_bytes: int


def compute_storage_bar(mount_path: Path) -> StorageBreakdown:
    stat = os.statvfs(mount_path)
    total = stat.f_frsize * stat.f_blocks
    free = stat.f_frsize * stat.f_bavail
    used = total - free
    music_bytes = _dir_size(mount_path / "Music") if (mount_path / "Music").is_dir() else 0
    rockbox_bytes = _dir_size(mount_path / ".rockbox") if (mount_path / ".rockbox").is_dir() else 0
    other_bytes = max(used - music_bytes - rockbox_bytes, 0)
    return StorageBreakdown(total, free, music_bytes, rockbox_bytes, other_bytes)


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


@dataclass(frozen=True)
class AlbumSize:
    artist: str
    album: str
    total_bytes: int
    track_count: int


@dataclass(frozen=True)
class ArtistSize:
    artist: str
    total_bytes: int


def largest_albums(tracks: list[TrackFile], limit: int = 50) -> list[AlbumSize]:
    grouped: dict[tuple[str, str], list[TrackFile]] = {}
    for t in tracks:
        grouped.setdefault((t.artist, t.album), []).append(t)
    albums = [
        AlbumSize(artist=a, album=al, total_bytes=sum(t.size_bytes for t in ts), track_count=len(ts))
        for (a, al), ts in grouped.items()
    ]
    albums.sort(key=lambda x: x.total_bytes, reverse=True)
    return albums[:limit]


def largest_files(tracks: list[TrackFile], limit: int = 50) -> list[TrackFile]:
    return sorted(tracks, key=lambda t: t.size_bytes, reverse=True)[:limit]


def largest_artists(tracks: list[TrackFile], limit: int = 50) -> list[ArtistSize]:
    grouped: dict[str, int] = {}
    for t in tracks:
        grouped[t.artist] = grouped.get(t.artist, 0) + t.size_bytes
    artists = [ArtistSize(artist=a, total_bytes=b) for a, b in grouped.items()]
    artists.sort(key=lambda x: x.total_bytes, reverse=True)
    return artists[:limit]
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_storage_analyzer.py -v`
Expected: 5 passed

- [x] **Step 5: Commit**

```bash
git add podplex/core/storage_analyzer.py tests/test_storage_analyzer.py
git commit -m "$(cat <<'EOF'
Add storage bar breakdown and largest-albums/files/artists ranking

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Plex Client Module

**Files:**
- Create: `podplex/core/plex_client.py`
- Test: `tests/test_plex_client.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_plex_client.py
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
```

Note: `PlexTrack` is a plain dataclass constructed positionally in
`test_download_url_includes_token` — field order must match the
implementation in Step 3 exactly: `key, title, artist, album,
track_number, year, disc_number, duration_ms, file_path, size_bytes`.

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_plex_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'podplex.core.plex_client'`

- [x] **Step 3: Write `podplex/core/plex_client.py`**

```python
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
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_plex_client.py -v`
Expected: 7 passed

- [x] **Step 5: Commit**

```bash
git add podplex/core/plex_client.py tests/test_plex_client.py
git commit -m "$(cat <<'EOF'
Add Plex client wrapper with manual token and OAuth PIN auth

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: HTTP Downloader Module

**Files:**
- Create: `podplex/core/downloader.py`
- Test: `tests/test_downloader.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_downloader.py
from podplex.core import downloader as dl
from podplex.core.downloader import HttpDownloader


class FakeResponse:
    def __init__(self, chunks, total):
        self._chunks = chunks
        self.headers = {"Content-Length": str(total)}

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_http_downloader_writes_file_and_reports_progress(tmp_path, monkeypatch):
    chunks = [b"hell", b"o wo", b"rld!"]
    total = sum(len(c) for c in chunks)

    def fake_get(url, stream, timeout):
        assert url == "http://example/track.mp3"
        return FakeResponse(chunks, total)

    monkeypatch.setattr(dl.requests, "get", fake_get)
    progress_calls = []
    dest = tmp_path / "out.mp3"
    HttpDownloader().download(
        "http://example/track.mp3",
        dest,
        on_progress=lambda w, t: progress_calls.append((w, t)),
        should_cancel=lambda: False,
    )
    assert dest.read_bytes() == b"hello world!"
    assert progress_calls[-1] == (12, 12)


def test_http_downloader_stops_when_cancelled(tmp_path, monkeypatch):
    chunks = [b"aa", b"bb", b"cc"]

    def fake_get(url, stream, timeout):
        return FakeResponse(chunks, 6)

    monkeypatch.setattr(dl.requests, "get", fake_get)
    dest = tmp_path / "out.mp3"
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > 1

    HttpDownloader().download("http://x", dest, on_progress=lambda w, t: None, should_cancel=should_cancel)
    assert dest.read_bytes() == b"aa"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_downloader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'podplex.core.downloader'`

- [x] **Step 3: Write `podplex/core/downloader.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

import requests


class Downloader(Protocol):
    def download(
        self,
        url: str,
        dest: Path,
        on_progress: Callable[[int, int], None],
        should_cancel: Callable[[], bool],
    ) -> None: ...


class HttpDownloader:
    def __init__(self, chunk_size: int = 65536):
        self.chunk_size = chunk_size

    def download(
        self,
        url: str,
        dest: Path,
        on_progress: Callable[[int, int], None],
        should_cancel: Callable[[], bool],
    ) -> None:
        with requests.get(url, stream=True, timeout=30) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", 0))
            written = 0
            with open(dest, "wb") as f:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if should_cancel():
                        return
                    if not chunk:
                        continue
                    f.write(chunk)
                    written += len(chunk)
                    on_progress(written, total)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_downloader.py -v`
Expected: 2 passed

- [x] **Step 5: Commit**

```bash
git add podplex/core/downloader.py tests/test_downloader.py
git commit -m "$(cat <<'EOF'
Add streaming HTTP downloader with progress and cancellation

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Sync Engine Module

**Files:**
- Create: `podplex/core/sync_engine.py`
- Test: `tests/test_sync_engine.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_sync_engine.py
import time

from PySide6.QtCore import Qt

from podplex.core.sync_engine import SyncEngine, SyncTask, SyncTrack


class FakeDownloader:
    def __init__(self, content: bytes = b"hello world", chunk_delay: float = 0):
        self.content = content
        self.chunk_delay = chunk_delay
        self.calls = []

    def download(self, url, dest, on_progress, should_cancel):
        self.calls.append(url)
        total = len(self.content)
        written = 0
        with open(dest, "wb") as f:
            for i in range(0, total, 4):
                if should_cancel():
                    return
                chunk = self.content[i : i + 4]
                f.write(chunk)
                written += len(chunk)
                on_progress(written, total)
                if self.chunk_delay:
                    time.sleep(self.chunk_delay)


def _make_task(tmp_path, task_id="t1", n_tracks=1):
    tracks = [
        SyncTrack(
            source_url=f"http://x/{i}",
            dest_path=tmp_path / f"track{i}.mp3",
            size_bytes=11,
            title=f"Track {i}",
        )
        for i in range(n_tracks)
    ]
    return SyncTask(name="Test Album", tracks=tracks, task_id=task_id)


def _wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)


def test_enqueue_reports_position(tmp_path):
    engine = SyncEngine(FakeDownloader(chunk_delay=0.05))
    pos1 = engine.enqueue(_make_task(tmp_path, "t1"))
    pos2 = engine.enqueue(_make_task(tmp_path, "t2"))
    assert pos1 == 1
    assert pos2 == 2
    engine.cancel_all()


def test_track_downloads_and_renames_atomically(tmp_path):
    downloader = FakeDownloader(content=b"abcdefgh")
    engine = SyncEngine(downloader)
    completed = []
    engine.task_completed.connect(lambda tid: completed.append(tid), Qt.DirectConnection)
    task = _make_task(tmp_path, "t1")
    engine.enqueue(task)
    _wait_until(lambda: completed)
    assert completed == ["t1"]
    dest = task.tracks[0].dest_path
    assert dest.exists()
    assert dest.read_bytes() == b"abcdefgh"
    assert not dest.with_suffix(dest.suffix + ".part").exists()


def test_already_synced_tracks_are_skipped(tmp_path):
    downloader = FakeDownloader()
    engine = SyncEngine(downloader, is_already_synced=lambda t: True)
    completed_titles = []
    engine.track_completed.connect(lambda tid, title: completed_titles.append(title), Qt.DirectConnection)
    task_completed = []
    engine.task_completed.connect(lambda tid: task_completed.append(tid), Qt.DirectConnection)
    task = _make_task(tmp_path, "t1")
    engine.enqueue(task)
    _wait_until(lambda: task_completed)
    assert completed_titles == ["Track 0"]
    assert downloader.calls == []


def test_cancel_current_removes_part_file(tmp_path):
    downloader = FakeDownloader(content=b"x" * 40, chunk_delay=0.05)
    engine = SyncEngine(downloader)
    failed = []
    engine.task_failed.connect(lambda tid, err: failed.append((tid, err)), Qt.DirectConnection)
    task = _make_task(tmp_path, "t1")
    engine.enqueue(task)
    time.sleep(0.06)
    engine.cancel_current()
    _wait_until(lambda: failed)
    assert failed == [("t1", "cancelled")]
    dest = task.tracks[0].dest_path
    assert not dest.exists()
    assert not dest.with_suffix(dest.suffix + ".part").exists()


def test_remove_pending_task_is_never_processed(tmp_path):
    engine = SyncEngine(FakeDownloader(chunk_delay=0.05))
    blocker = _make_task(tmp_path, "blocker")
    engine.enqueue(blocker)
    task2 = _make_task(tmp_path, "t2")
    engine.enqueue(task2)
    removed = engine.remove_pending("t2")
    assert removed is True
    assert all(t.task_id != "t2" for t in engine.pending_tasks())

    started = []
    engine.task_started.connect(lambda tid: started.append(tid), Qt.DirectConnection)
    _wait_until(lambda: "blocker" in started or len(started) > 0, timeout=2)
    time.sleep(0.3)
    assert "t2" not in started
    engine.cancel_all()
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sync_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'podplex.core.sync_engine'`

- [x] **Step 3: Write `podplex/core/sync_engine.py`**

```python
from __future__ import annotations

import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal


@dataclass
class SyncTrack:
    source_url: str
    dest_path: Path
    size_bytes: int
    title: str


@dataclass
class SyncTask:
    name: str
    tracks: list[SyncTrack]
    task_id: str


class SyncEngine(QObject):
    task_queued = Signal(str)
    task_started = Signal(str)
    track_progress = Signal(str, int, int, float)  # task_id, bytes, total, speed_bytes_per_sec
    track_completed = Signal(str, str)  # task_id, title
    task_completed = Signal(str)
    task_failed = Signal(str, str)  # task_id, error message
    queue_changed = Signal()

    def __init__(self, downloader, is_already_synced: Callable[[SyncTrack], bool] | None = None):
        super().__init__()
        self._downloader = downloader
        self._is_already_synced = is_already_synced or (lambda t: False)
        self._queue: "queue.Queue[SyncTask]" = queue.Queue()
        self._pending: list[SyncTask] = []
        self._skip_ids: set[str] = set()
        self._active_task_id: str | None = None
        self._lock = threading.Lock()
        self._cancel_current = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def enqueue(self, task: SyncTask) -> int:
        with self._lock:
            self._pending.append(task)
            active_offset = 1 if self._active_task_id is not None else 0
            position = active_offset + len(self._pending)
        self._queue.put(task)
        self.task_queued.emit(task.task_id)
        self.queue_changed.emit()
        return position

    def pending_tasks(self) -> list[SyncTask]:
        with self._lock:
            return list(self._pending)

    def remove_pending(self, task_id: str) -> bool:
        with self._lock:
            for t in self._pending:
                if t.task_id == task_id:
                    self._pending.remove(t)
                    self._skip_ids.add(task_id)
                    self.queue_changed.emit()
                    return True
        return False

    def clear_pending(self) -> None:
        with self._lock:
            ids = {t.task_id for t in self._pending}
            self._skip_ids.update(ids)
            self._pending.clear()
        self.queue_changed.emit()

    def cancel_current(self) -> None:
        self._cancel_current.set()

    def cancel_all(self) -> None:
        self._cancel_current.set()
        self.clear_pending()

    def _run(self) -> None:
        while True:
            task = self._queue.get()
            skip = False
            with self._lock:
                if task in self._pending:
                    self._pending.remove(task)
                if task.task_id in self._skip_ids:
                    self._skip_ids.discard(task.task_id)
                    skip = True
                else:
                    self._active_task_id = task.task_id
            if skip:
                continue
            self._cancel_current.clear()
            self.task_started.emit(task.task_id)
            self.queue_changed.emit()
            try:
                cancelled = self._process_task(task)
                if cancelled:
                    self.task_failed.emit(task.task_id, "cancelled")
                else:
                    self.task_completed.emit(task.task_id)
            except Exception as exc:
                self.task_failed.emit(task.task_id, str(exc))
            finally:
                with self._lock:
                    self._active_task_id = None

    def _process_task(self, task: SyncTask) -> bool:
        """Returns True if the task was cancelled partway through."""
        for track in task.tracks:
            if self._cancel_current.is_set():
                return True
            if self._is_already_synced(track):
                self.track_completed.emit(task.task_id, track.title)
                continue
            self._download_track(task, track)
            if self._cancel_current.is_set():
                return True
            self.track_completed.emit(task.task_id, track.title)
        return False

    def _download_track(self, task: SyncTask, track: SyncTrack) -> None:
        part_path = track.dest_path.with_suffix(track.dest_path.suffix + ".part")
        part_path.parent.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()

        def on_progress(downloaded: int, total: int) -> None:
            elapsed = max(time.monotonic() - start, 1e-6)
            speed = downloaded / elapsed
            self.track_progress.emit(task.task_id, downloaded, total, speed)

        self._downloader.download(track.source_url, part_path, on_progress, self._cancel_current.is_set)
        if self._cancel_current.is_set():
            part_path.unlink(missing_ok=True)
            return
        os.replace(part_path, track.dest_path)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sync_engine.py -v`
Expected: 5 passed

- [x] **Step 5: Commit**

```bash
git add podplex/core/sync_engine.py tests/test_sync_engine.py
git commit -m "$(cat <<'EOF'
Add background sync engine with queue, cancellation, and skip logic

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Sync Task Builder Module

**Files:**
- Create: `podplex/core/sync_task_builder.py`
- Test: `tests/test_sync_task_builder.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_sync_task_builder.py
import pytest

from podplex.core.plex_client import PlexTrack
from podplex.core.sync_task_builder import build_album_sync_task


class FakeClient:
    def download_url(self, track):
        return f"http://fake{track.file_path}"


def _track(title, num, disc=1, ext=".flac"):
    return PlexTrack(
        key="k",
        title=title,
        artist="The Band",
        album="Great Album",
        track_number=num,
        year=1999,
        disc_number=disc,
        duration_ms=200000,
        file_path=f"/data/{title}{ext}",
        size_bytes=1000,
    )


def test_build_album_sync_task_rockbox_disc_layout(tmp_path):
    tracks = [_track("Song One", 1), _track("Song Two", 2)]
    task = build_album_sync_task(FakeClient(), tracks, tmp_path, "rockbox_disc", "task-1")
    assert task.task_id == "task-1"
    assert task.name == "The Band - Great Album"
    assert len(task.tracks) == 2
    expected_dir = tmp_path / "Music" / "The Band" / "The Band-1999-Great Album" / "CD 01"
    assert task.tracks[0].dest_path == expected_dir / "01 Song One.flac"
    assert task.tracks[0].source_url == "http://fake/data/Song One.flac"


def test_build_album_sync_task_standard_layout(tmp_path):
    tracks = [_track("Song One", 1)]
    task = build_album_sync_task(FakeClient(), tracks, tmp_path, "standard", "task-1")
    expected_dir = tmp_path / "Music" / "The Band" / "Great Album"
    assert task.tracks[0].dest_path == expected_dir / "01 Song One.flac"


def test_build_album_sync_task_raises_on_empty_tracks(tmp_path):
    with pytest.raises(ValueError):
        build_album_sync_task(FakeClient(), [], tmp_path, "standard", "task-1")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sync_task_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'podplex.core.sync_task_builder'`

- [x] **Step 3: Write `podplex/core/sync_task_builder.py`**

```python
from __future__ import annotations

from pathlib import Path

from podplex.core.naming import album_directory, track_filename
from podplex.core.plex_client import PlexTrack
from podplex.core.sync_engine import SyncTask, SyncTrack


def build_album_sync_task(
    client,
    tracks: list[PlexTrack],
    mount_path: Path,
    naming_pattern: str,
    task_id: str,
) -> SyncTask:
    if not tracks:
        raise ValueError("cannot build a sync task with no tracks")
    first = tracks[0]
    disc = first.disc_number if naming_pattern == "rockbox_disc" else None
    year = str(first.year) if first.year else None
    dir_parts = album_directory(naming_pattern, first.artist, first.album, year, disc)
    album_dir = mount_path.joinpath("Music", *dir_parts)

    sync_tracks = []
    for t in tracks:
        ext = Path(t.file_path).suffix
        filename = track_filename(t.track_number, t.title, ext)
        dest = album_dir / filename
        sync_tracks.append(
            SyncTrack(source_url=client.download_url(t), dest_path=dest, size_bytes=t.size_bytes, title=t.title)
        )
    name = f"{first.artist} - {first.album}"
    return SyncTask(name=name, tracks=sync_tracks, task_id=task_id)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sync_task_builder.py -v`
Expected: 3 passed

- [x] **Step 5: Commit**

```bash
git add podplex/core/sync_task_builder.py tests/test_sync_task_builder.py
git commit -m "$(cat <<'EOF'
Add sync task builder wiring Plex tracks to on-device paths

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Main Window & Entry Point

**Files:**
- Create: `podplex/ui/main_window.py`
- Create: `podplex/main.py`
- Test: `tests/test_main_window.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_main_window.py
from podplex.core.config import Config
from podplex.ui.main_window import MainWindow


def test_main_window_constructs_with_no_device_detected(qapp):
    window = MainWindow(config=Config())
    assert window.windowTitle() == "PodPlex"
    assert window.device_label.text() == "iPod: not detected"


def test_detect_device_updates_label_when_none_found(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("podplex.ui.main_window.find_device", lambda mount_override="": None)
    window = MainWindow(config=Config())
    window.detect_device()
    assert window.device_label.text() == "iPod: not detected"
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main_window.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'podplex.ui.main_window'`

- [x] **Step 3: Write `podplex/ui/main_window.py`**

```python
from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from podplex.core.config import Config
from podplex.core.device import find_device
from podplex.core.downloader import HttpDownloader
from podplex.core.plex_client import PlexClient
from podplex.core.sync_engine import SyncEngine
from podplex.core.sync_task_builder import build_album_sync_task


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.config = config
        layout = QFormLayout(self)
        self.url_edit = QLineEdit(config.plex_url)
        self.token_edit = QLineEdit(config.plex_token)
        self.library_edit = QLineEdit(config.plex_library_name)
        layout.addRow("Plex URL", self.url_edit)
        layout.addRow("Plex Token", self.token_edit)
        layout.addRow("Library Name", self.library_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def updated_config(self) -> Config:
        self.config.plex_url = self.url_edit.text().strip()
        self.config.plex_token = self.token_edit.text().strip()
        self.config.plex_library_name = self.library_edit.text().strip() or "Music"
        return self.config


class MainWindow(QMainWindow):
    def __init__(self, config: Config | None = None):
        super().__init__()
        self.setWindowTitle("PodPlex")
        self.config = config if config is not None else Config.load()
        self.plex_client: PlexClient | None = None
        self.device_mount_path: Path | None = None

        self.engine = SyncEngine(HttpDownloader())
        self.engine.task_started.connect(self._on_task_started, Qt.QueuedConnection)
        self.engine.track_progress.connect(self._on_track_progress, Qt.QueuedConnection)
        self.engine.task_completed.connect(self._on_task_completed, Qt.QueuedConnection)
        self.engine.task_failed.connect(self._on_task_failed, Qt.QueuedConnection)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        header = QHBoxLayout()
        self.device_label = QLabel("iPod: not detected")
        detect_btn = QPushButton("Detect iPod")
        detect_btn.clicked.connect(self.detect_device)
        load_btn = QPushButton("Load Library")
        load_btn.clicked.connect(self.load_library)
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings)
        header.addWidget(self.device_label)
        header.addWidget(detect_btn)
        header.addWidget(load_btn)
        header.addWidget(settings_btn)
        root.addLayout(header)

        lists = QHBoxLayout()
        self.artist_list = QListWidget()
        self.artist_list.itemSelectionChanged.connect(self.on_artist_selected)
        self.album_list = QListWidget()
        lists.addWidget(self.artist_list)
        lists.addWidget(self.album_list)
        root.addLayout(lists)

        sync_row = QHBoxLayout()
        sync_btn = QPushButton("Sync Album to iPod")
        sync_btn.clicked.connect(self.sync_selected_album)
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("")
        sync_row.addWidget(sync_btn)
        sync_row.addWidget(self.progress_bar)
        sync_row.addWidget(self.status_label)
        root.addLayout(sync_row)

        self._artists_by_name = {}
        self._albums_by_name = {}

    def detect_device(self) -> None:
        device = find_device(mount_override=self.config.ipod_mount_override)
        if device is None:
            self.device_label.setText("iPod: not detected")
            self.device_mount_path = None
        else:
            self.device_mount_path = device.mount_path
            ro = " (READ-ONLY)" if device.read_only else ""
            self.device_label.setText(f"iPod: {device.target or 'unknown'} @ {device.mount_path}{ro}")

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.Accepted:
            self.config = dialog.updated_config()
            self.config.save()

    def load_library(self) -> None:
        if not self.config.plex_url or not self.config.plex_token:
            QMessageBox.warning(self, "PodPlex", "Configure Plex connection in Settings first.")
            return
        self.plex_client = PlexClient.connect(self.config.plex_url, self.config.plex_token, self.config.plex_library_name)
        self.artist_list.clear()
        self._artists_by_name.clear()
        for artist in self.plex_client.artists():
            self._artists_by_name[artist.title] = artist
            self.artist_list.addItem(artist.title)

    def on_artist_selected(self) -> None:
        items = self.artist_list.selectedItems()
        self.album_list.clear()
        self._albums_by_name.clear()
        if not items or self.plex_client is None:
            return
        artist = self._artists_by_name[items[0].text()]
        for album in self.plex_client.albums_for_artist(artist):
            self._albums_by_name[album.title] = album
            self.album_list.addItem(album.title)

    def sync_selected_album(self) -> None:
        album_items = self.album_list.selectedItems()
        if not album_items or self.plex_client is None or self.device_mount_path is None:
            QMessageBox.warning(self, "PodPlex", "Select an artist, album, and detect your iPod first.")
            return
        album = self._albums_by_name[album_items[0].text()]
        tracks = self.plex_client.tracks_for_album(album)
        task_id = str(uuid.uuid4())
        task = build_album_sync_task(self.plex_client, tracks, self.device_mount_path, self.config.naming_pattern, task_id)
        self.engine.enqueue(task)
        self.status_label.setText(f"Queued: {task.name}")

    def _on_task_started(self, task_id: str) -> None:
        self.status_label.setText("Syncing...")

    def _on_track_progress(self, task_id: str, downloaded: int, total: int, speed: float) -> None:
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(downloaded)

    def _on_task_completed(self, task_id: str) -> None:
        self.status_label.setText("Sync complete")
        self.progress_bar.setValue(0)

    def _on_task_failed(self, task_id: str, error: str) -> None:
        self.status_label.setText(f"Sync failed: {error}")
```

- [x] **Step 4: Write `podplex/main.py`**

```python
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from podplex.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(900, 600)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_main_window.py -v`
Expected: 2 passed

- [x] **Step 6: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests across every module pass (config, naming, device, storage_analyzer, plex_client, downloader, sync_engine, sync_task_builder, main_window)

- [x] **Step 7: Manual smoke test against real hardware**

Run: `uv run podplex`
Expected: window opens. Click **Settings**, enter your real Plex URL and
token, **Save**. Plug in the Rockbox iPod, click **Detect iPod** — label
shows the detected target and mount path. Click **Load Library** — artist
list populates. Select an artist, select an album, click **Sync Album to
iPod** — progress bar advances and status shows "Sync complete"; verify
the files exist on the iPod at the expected path for the configured
`naming_pattern`.

- [x] **Step 8: Commit**

```bash
git add podplex/ui/main_window.py podplex/main.py tests/test_main_window.py
git commit -m "$(cat <<'EOF'
Add MainWindow and entry point wiring Plex, device, and sync engine

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Plan Self-Review Notes

- **Spec coverage:** Tasks 1–10 implement design spec sections 2 (Config),
  5 (Plex Integration, manual + OAuth), 6 (Device Detection & Storage —
  detection, read-only, eject; ranking views land in a follow-up plan
  alongside the Storage Analyzer dialog), 8 (Naming & Layout), 7 (Sync
  Engine core), and a minimal slice of 11 (GUI) sufficient for an
  end-to-end manual test. Sections 9 (Playlist Sync), 10 (Artwork), the
  rest of 11 (grid views, queue dialog, storage dialog), and 15 (packaging
  polish/desktop integration) are explicitly deferred to follow-up plans
  per the "Relationship to the design spec" note above — not gaps, but
  intentional phase boundaries.
- **Placeholder scan:** No TBD/TODO markers; every step has runnable code
  and concrete expected output.
- **Type consistency:** `PlexTrack` field order/names match between
  `plex_client.py` and every consumer (`sync_task_builder.py`, both test
  files). `SyncTask`/`SyncTrack` field names match between `sync_engine.py`
  and `sync_task_builder.py`/its tests. `DeviceInfo` fields match between
  `device.py` and `main_window.py`'s usage (`.target`, `.mount_path`,
  `.read_only`). `Downloader` protocol signature
  (`download(url, dest, on_progress, should_cancel)`) matches across
  `downloader.py`, `sync_engine.py`, and both test fakes.
