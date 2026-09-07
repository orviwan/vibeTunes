# PodPlex

A Linux desktop app for syncing a Plex Media Server music library to a
Rockbox-modded Apple iPod. Built with Python and PySide6 (Qt6).

## Features

- **Plex connection**: 1-click OAuth sign-in (opens `plex.tv/link`, fills in
  the token automatically) or manual server URL + token entry.
- **Library browsing**: browse Plex artists, albums, and tracks; sync a full
  album to the iPod in one click.
- **Device detection**: auto-detects a mounted Rockbox iPod under
  `/run/media/$USER/*` or `/media/*`, reads its Rockbox target/version, and
  shows a visual storage bar (Music / Rockbox system / other / free).
- **Read-only fix & safe eject**: one-click remount if Linux mounted the
  device read-only, and a safe eject that flushes the write cache, unmounts,
  and powers off the USB connection via `udisksctl`.
- **On-device sync status**: albums show `✓ ON IPOD`, `◐ PARTIAL (x/y)`, or
  "Not on iPod", with a one-click delete-from-iPod action and cached cover
  art preview extracted from the on-device files.
- **Background sync queue**: transfers run on a background thread with a
  live Sync Queue dialog (reorderable view, remove/clear pending items,
  cancel the active transfer). Downloads stream to `.part` files and
  atomically rename on completion.
- **Storage analyzer**: a "Largest Files & Albums" dialog ranks on-device
  albums, individual audio files, and artists by size, each with a delete
  action.
- **Playlist sync**: syncs a Plex playlist to the iPod, reusing already-synced
  tracks via tolerant fuzzy matching (tolerates diacritics, punctuation,
  track-number prefixes, and folder-naming differences) and downloading only
  what's missing. Generates a UTF-8-with-BOM `.m3u8` using Rockbox internal
  paths (`/<HDD0>/...`). Includes an on-device playlist manager (list/delete).
- **FAT32-safe naming**: sanitizes forbidden characters and truncates long
  names; supports both a `rockbox_disc` layout
  (`Artist/Artist-Year-Album/CD 01/NN Title.ext`) and a flat `standard`
  layout (`Artist/Album/NN Title.ext`).

## Installation

Requires Python 3.10+, [uv](https://github.com/astral-sh/uv), and `udisks2`
(standard on most Linux desktops).

```bash
uv sync
uv run podplex
```

## Desktop Integration

```bash
mkdir -p ~/.local/share/icons/hicolor/scalable/apps
cp podplex/assets/podplex.svg ~/.local/share/icons/hicolor/scalable/apps/podplex.svg

mkdir -p ~/.local/share/applications
cp podplex/assets/podplex.desktop ~/.local/share/applications/podplex.desktop

update-desktop-database ~/.local/share/applications/
```

## Configuration

Stored at `~/.config/podplex/config.json`:

| Key | Default | Description |
|---|---|---|
| `plex_url` | `""` | Plex server URL, e.g. `http://192.168.1.100:32400` |
| `plex_token` | `""` | `X-Plex-Token` |
| `plex_library_name` | `"Music"` | Plex music library section name |
| `ipod_mount_override` | `""` | Manual mount path (empty for auto-detect) |
| `naming_pattern` | `"rockbox_disc"` | `"rockbox_disc"` or `"standard"` |
| `download_artwork` | `true` | Reserved for future `cover.jpg` writing on sync |
| `transcode_mode` | `"direct"` | Only `"direct"` (byte copy) is implemented |

## Known Simplifications

This build favors a solid, well-tested core over full feature parity with
every polish item in the original concept:

- **No transcoding** — only direct byte-copy transfers.
- **Cover art preview, not full icon-grid views** — the library browser is
  list-based with a cover preview panel for the selected album, rather than
  a grid of album art tiles.
- **Single-drive Rockbox path mapping** — playlists assume one drive
  (`HDD0`); dual-card (`MICROSD0`/`MICROSD1`) setups aren't auto-detected.
- **Playlist downloads are queued, not blocking** — the `.m3u8` is written
  immediately with each track's target path; tracks still in the sync queue
  will play once their download completes.

## Development

```bash
uv sync
QT_QPA_PLATFORM=offscreen uv run pytest -v
```

Tests use fakes for Plex (`plexapi`) and device mount state, so the suite
runs without a live Plex server or a real iPod attached.

## License

MIT.

*Apple and iPod are trademarks of Apple Inc. Rockbox is an open-source
firmware project. Plex is a trademark of Plex, Inc. PodPlex is an
independent project not affiliated with or endorsed by either.*
