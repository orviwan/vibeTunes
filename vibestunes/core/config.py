"""Configuration management for vibesTunes."""
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".config" / "vibestunes"
CONFIG_FILE = CONFIG_DIR / "config.json"
LEGACY_CONFIG_FILE = Path.home() / ".config" / "vibetunes" / "config.json"

@dataclass
class AppConfig:
    plex_url: str = "http://localhost:32400"
    plex_token: str = ""
    plex_library: str = "Music"
    custom_ipod_path: str = ""
    naming_pattern: str = "plex_exact"  # 'plex_exact', 'rockbox_disc', or 'standard'
    transcode_mode: str = "original"     # 'original', 'transcode_mp3_v0', 'transcode_mp3_320k'
    download_artwork: bool = True
    theme_mode: str = "dark"

    @classmethod
    def load(cls) -> "AppConfig":
        target_file = CONFIG_FILE if CONFIG_FILE.exists() else (LEGACY_CONFIG_FILE if LEGACY_CONFIG_FILE.exists() else None)
        if not target_file:
            return cls()
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception:
            return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
