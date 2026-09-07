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
