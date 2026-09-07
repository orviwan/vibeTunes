from pathlib import Path

from podplex.ui.storage_dialog import StorageDialog


def _write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_storage_dialog_lists_albums_files_artists(qapp, tmp_path):
    _write(tmp_path / "Music" / "Artist A" / "Album 1" / "01.mp3", 100)
    _write(tmp_path / "Music" / "Artist B" / "Album 2" / "01.flac", 500)
    dialog = StorageDialog(tmp_path)
    assert dialog.albums_table.rowCount() == 2
    assert dialog.albums_table.item(0, 1).text() == "Album 2"  # largest first
    assert dialog.files_table.rowCount() == 2
    assert dialog.artists_table.rowCount() == 2


def test_storage_dialog_delete_album_removes_folder_and_refreshes(qapp, tmp_path):
    _write(tmp_path / "Music" / "Artist A" / "Album 1" / "01.mp3", 100)
    dialog = StorageDialog(tmp_path)
    assert dialog.albums_table.rowCount() == 1
    dialog._delete_album("Artist A", "Album 1")
    assert dialog.albums_table.rowCount() == 0
    assert not (tmp_path / "Music" / "Artist A" / "Album 1").exists()


def test_storage_dialog_delete_file_removes_file_and_refreshes(qapp, tmp_path):
    _write(tmp_path / "Music" / "Artist A" / "Album 1" / "01.mp3", 100)
    dialog = StorageDialog(tmp_path)
    file_path = dialog.tracks[0].path
    dialog._delete_file(file_path)
    assert not file_path.exists()
    assert dialog.files_table.rowCount() == 0
