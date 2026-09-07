# PodPlex for Linux — Design Spec

Date: 2026-09-07
Status: Approved for implementation

## 1. Purpose

PodPlex is a Linux desktop application that bridges a self-hosted Plex Media
Server music library with a Rockbox-modded Apple iPod. It presents the full
Plex music catalog with on-device status overlays, lets the user queue
albums/tracks/playlists for transfer, manages a background sync queue,
analyzes on-device storage usage, generates Rockbox-compatible `.m3u8`
playlists, and provides safe device ejection.

Target user for this build: has a live Plex server and a Rockbox iPod
available for real-hardware testing during development.

Scope: full feature set as originally specified (no MVP trimming), built in
ordered implementation phases. Transcoding is out of scope for this build —
only direct byte-copy transfers are implemented; the `transcode_mode` config
key exists but only `"direct"` is honored.

## 2. Tech Stack

- Python 3.10+
- PySide6 (Qt6) for the GUI
- `plexapi` for all Plex Media Server communication, including PIN-based
  OAuth linking (`plexapi.myplex.MyPlexPinLogin`) and manual token auth
- `mutagen` for embedded cover art / tag extraction (ID3v2, FLAC/Vorbis,
  MP4/AAC)
- `Pillow` for thumbnail generation
- `rapidfuzz` for fuzzy track/album matching during playlist sync
- `pytest` for tests, run with `QT_QPA_PLATFORM=offscreen`
- Packaging via `uv` / `pyproject.toml`, console entry point `podplex`
- System dependency: `udisks2` (`udisksctl`) for mount/unmount/power-off

## 3. Project Structure

```
podplex/
  __init__.py
  main.py                  # entry point, builds QApplication + MainWindow
  core/
    config.py               # Config dataclass, load/save ~/.config/podplex/config.json
    plex_client.py           # thin wrapper over plexapi: auth, library, streaming URLs
    device.py                # iPod detection, mount info, Rockbox metadata, read-only fix, eject
    storage_analyzer.py      # largest albums/files/artists ranking, storage bar breakdown
    sync_engine.py           # background sync worker, queue, signals, .part file handling
    naming.py                # FAT32-safe sanitization, path layout (rockbox_disc vs standard)
    matcher.py                # tolerant track matching for playlist reuse
    playlist.py               # m3u8 generation, internal drive path mapping
    artwork.py                # embedded art extraction, thumbnail cache (memory LRU + disk)
    library_index.py          # on-device library scan -> artist/album/track presence map
  ui/
    main_window.py
    plex_browser.py           # artist/album/track panes, grid & list modes, filters, badges
    playlist_browser.py
    sync_drawer.py            # bottom drawer: active transfer, progress, queue button
    queue_dialog.py
    storage_dialog.py         # "Largest Files & Albums" dialog
    settings_dialog.py
  assets/
    podplex.svg
    podplex.desktop
tests/
  test_config.py
  test_naming.py
  test_matcher.py
  test_playlist.py
  test_storage_analyzer.py
  test_sync_engine.py
  test_device.py
  test_artwork.py
  test_library_index.py
  conftest.py                # offscreen QApplication fixture
pyproject.toml
README.md
LICENSE
```

Each `core/` module is independently unit-testable without a live Plex
server or a real iPod mounted — device/plex interactions are wrapped behind
small interfaces (`DeviceInfo`, `PlexTrack`, etc.) that tests construct
directly or via lightweight fakes.

## 4. Config

`~/.config/podplex/config.json`, loaded/saved via a `Config` dataclass with
`to_dict`/`from_dict`. Fields match the spec's configuration reference:
`plex_url`, `plex_token`, `plex_library_name` (default `"Music"`),
`ipod_mount_override`, `naming_pattern` (`"rockbox_disc"` default or
`"standard"`), `download_artwork` (default `True`), `transcode_mode`
(default `"direct"`, only value honored).

## 5. Plex Integration

`core/plex_client.py` wraps `plexapi`:
- **OAuth PIN linking**: `MyPlexPinLogin` generates a 4-character PIN,
  opens `https://plex.tv/link` in the user's default browser
  (`webbrowser.open`), and polls for authorization on a background thread.
  On success, retrieves the account's servers and lets the user pick one
  (mirrors "Sign In with Plex Account" in the spec).
- **Manual auth**: user supplies `plex_url` + `X-Plex-Token` directly;
  `PlexServer(url, token)` validates via a `Test Connection` action.
- **Library access**: lists music sections, artists, albums, tracks;
  exposes track streaming/download URLs for the sync engine.

## 6. Device Detection & Storage

`core/device.py`:
- Scans `/run/media/$USER/*` and `/media/*` (plus `ipod_mount_override` if
  set) for a mounted volume containing a `.rockbox` directory.
- Parses `.rockbox/rockbox-info.txt` for hardware target, Rockbox version.
- Determines read-only state via `/proc/mounts`; exposes a "Fix Read-Only"
  action that runs `udisksctl mount -o remount,rw` and surfaces the exact
  command to the user if it needs elevated privileges rather than silently
  escalating.
- Safe eject: `os.sync()` → `udisksctl unmount -b <device>` →
  `udisksctl power-off -b <device>`, each step reported via signals so the
  UI can show "Flushing Cache..." → "Safe to Disconnect".

`core/storage_analyzer.py`:
- Storage bar breakdown: `os.statvfs` for total/free bytes; directory walk
  splitting used space into Music, `.rockbox` (system), and
  other/trash.
- Ranking views: largest albums (by summed track file size), largest
  individual audio files, largest artists (summed across albums) — each
  with a jump-to-library and open-folder (`xdg-open`, not
  distro-specific) and delete action.

`core/library_index.py` builds the on-device presence map (artist → album →
set of tracks present, with file size) used to render `ON IPOD` /
`PARTIAL (X/Y)` badges and to support deletion and dedup checks.

## 7. Sync Engine

`core/sync_engine.py`:
- A `SyncEngine(QObject)` holds a `queue.Queue` of `SyncTask` items (album,
  selected tracks, or playlist). A single `threading.Thread(daemon=True)`
  worker pulls tasks in order and processes them; the GUI thread only ever
  talks to the engine through method calls that enqueue work and `Signal`s
  the engine emits back, connected `Qt.QueuedConnection`.
- Signals: `task_queued`, `task_started`, `track_progress(bytes, total,
  speed)`, `track_completed`, `task_completed`, `task_failed`,
  `queue_changed`.
- Each track downloads to `<dest>.part` via streamed HTTP (through
  `plexapi`'s underlying `requests` session) and is atomically `os.rename`d
  to its final name on success; a `.part` left behind after a crash is
  ignored/cleaned up on next scan.
- Skip logic: a track is considered already synced if a file with matching
  artist/album/title/track-number path already exists on-device with the
  same byte size — checked against `library_index` before download.
- Cancellation: cancel-current-track (closes the stream, removes the
  `.part`) and cancel-all (drains the queue) are both supported.

## 8. Naming & Layout

`core/naming.py`:
- Sanitizes each path component against FAT32/VFAT-forbidden characters
  (`/ \ : * ? " < > |`) and control characters, and truncates components
  that would exceed safe length limits.
- Two layouts per the `naming_pattern` config:
  - `rockbox_disc`: `Artist/Artist-Year-Album/CD 01/NN Title.ext`
  - `standard`: `Artist/Album/NN Title.ext`
- `download_artwork=True` places a `cover.jpg` in each album directory.

## 9. Playlist Sync

`core/matcher.py`: given a Plex track's artist/album/title/track-number and
a set of on-device candidate paths (from `library_index`), scores matches
tolerating: differing folder conventions (year/disc prefixes), Unicode
normalization (diacritics stripped for comparison, not for stored
filenames), punctuation differences, and container/extension differences.
Uses `rapidfuzz.fuzz` ratios above a tuned threshold; falls back to "no
match, needs download" when no candidate clears the threshold.

`core/playlist.py`:
- For each playlist track: reuse the matched on-device file if found,
  otherwise enqueue a download into the correct artist/album folder.
- Generates a UTF-8-with-BOM `.m3u8` under `<iPod>/Playlists/<name>.m3u8`,
  using Rockbox-internal paths (e.g. `/<HDD0>/Artist/Album/Track.flac`),
  where the drive label is derived from which mounted volume the file
  physically lives under. Single-drive setups (the common case) resolve to
  one label; the mapping is a small function so a second drive can be
  added later without touching call sites.
- On-device playlist manager: list/open (via `xdg-open`)/delete existing
  `.m3u8` files under `<iPod>/Playlists/`.

## 10. Artwork

`core/artwork.py`:
- Extraction: `mutagen` reads embedded art from ID3v2 (`APIC`), FLAC/Vorbis
  (`picture`), and MP4/AAC (`covr`) tags for files already on the device.
- Two-tier cache: an in-process `OrderedDict`-based LRU (bounded by count,
  not just recency) for `QPixmap` thumbnails, backed by a persistent disk
  cache at `~/.cache/podplex/thumbs/<hash>.jpg` keyed by a hash of the
  source path + mtime, so restarts don't require re-extracting art.

## 11. GUI

- `MainWindow`: header (Plex connection status, device summary, storage
  bar, Fix Read-Only / Eject buttons, Settings gear), a tab widget for
  **Library** and **Playlists**, and a bottom `SyncDrawer` that slides up
  when a transfer is active or queued.
- `PlexBrowser` (Library tab): three-pane `QSplitter` — artist list (with
  All/On iPod/Missing filter and counts), album pane (grid or list mode
  toggle, cover art, on-device badges), track table (per-track on-device
  dot indicators, multi-select, "+ Add to iPod" / "+ Add Selected to
  iPod" / "⏱ In Sync Queue" state).
- `PlaylistBrowser` (Playlists tab): playlist list, track list with
  on-device badges, "Sync to iPod" action, on-device playlist manager
  panel.
- `SyncDrawer`: active task name, per-track progress bar, transfer speed,
  "☰ View Queue (N)" button, cancel button.
- `QueueDialog`: active-transfer card + reorderable/removable upcoming
  tasks table + clear-all/cancel-all actions.
- `StorageDialog`: three tabs (Largest Albums / Largest Audio Files /
  Largest Artists) each with jump-to-library, open-folder, and delete
  actions, live-updating badges after a delete.
- `SettingsDialog`: Plex connection (OAuth button + manual fields + Test
  Connection), library picker, naming pattern, artwork toggle, mount
  override.

## 12. Threading & Signal Discipline

All long-running work (Plex metadata fetches, file transfers, directory
scans, `udisksctl` calls) runs on plain `threading.Thread(daemon=True)`
instances — never `QThread` — to avoid the GC-destroyed-while-running
crash noted in the original spec. Each background component exposes a
`QObject`-derived signal emitter; every cross-thread UI update goes through
a `Signal` connected with `Qt.QueuedConnection`. No background thread ever
touches a Qt widget directly.

## 13. Error Handling

Only handle failures that can actually occur at real boundaries: network
errors talking to Plex (connection refused, auth expired, HTTP errors),
filesystem errors writing to the iPod (disk full, permission denied,
device unplugged mid-transfer), and `udisksctl` command failures. These
surface as a status message in the relevant UI area (sync drawer, device
header, settings dialog) rather than silent failure or a crash. Internal
invariants (e.g. a `SyncTask` always having a valid destination path
because the caller constructed it) are not defensively re-validated.

## 14. Testing

`pytest`, `QT_QPA_PLATFORM=offscreen` for any test touching Qt widgets.
Coverage matches the original spec's 33-test baseline, reorganized by
module:
- `test_config.py` — serialization round-trip, defaults
- `test_naming.py` — FAT32 sanitization, both naming patterns, truncation
- `test_matcher.py` — fuzzy matching across year/disc/diacritic/extension
  variance, correct "no match" behavior
- `test_playlist.py` — m3u8 BOM/encoding, internal drive path mapping,
  reuse-vs-download decisions
- `test_storage_analyzer.py` — ranking correctness, storage bar math
- `test_sync_engine.py` — queue ordering, signal emission, cancellation,
  `.part` file handling, skip-if-already-synced logic
- `test_device.py` — mount discovery, read-only detection (using fixture
  `/proc/mounts`-style data, not real hardware)
- `test_artwork.py` — tag extraction across ID3v2/FLAC/MP4, LRU eviction
- `test_library_index.py` — presence-map construction, partial-album
  counting

Tests use fakes/fixtures for Plex (no live server needed) and for device
mount state (no real iPod needed), so the suite runs in CI or on any
machine. Manual verification against the user's real Plex server and
Rockbox iPod happens during development as each phase lands.

## 15. Packaging & Desktop Integration

`pyproject.toml` with a `podplex` console-script entry point, run via
`uv run podplex`. `podplex/assets/podplex.svg` (new icon, simple design)
and `podplex/assets/podplex.desktop` installed to the user's local
`~/.local/share/icons` / `~/.local/share/applications` per the spec's
install steps. `README.md` adapted from the original feature description
to reflect the actual implementation.

## 16. Implementation Phases

Built in order, each independently testable:
1. Project scaffold, config, packaging skeleton
2. Plex client (manual token + OAuth) and library browsing (read-only UI)
3. Device detection, storage bar, read-only fix, safe eject
4. Naming/layout + sync engine (single album/track transfer, queue of 1)
5. Full sync queue (multi-task, reorder, cancel) + sync drawer + queue
   dialog
6. Library index + on-device badges + delete actions in browser
7. Storage analyzer dialog (largest albums/files/artists)
8. Artwork extraction + caching + grid views
9. Track matcher + playlist sync + on-device playlist manager
10. Desktop integration, packaging polish, README
11. Full test suite across all modules

## 17. Out of Scope for This Build

- Transcoding (`transcode_mode` config key reserved but unimplemented)
- Windows/macOS support
- Dual-drive (`MICROSD1`) Rockbox path mapping beyond the extensibility
  point described in §9 — implemented generically but not exercised
  against real dual-card hardware unless the user's device has one
