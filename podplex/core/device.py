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
