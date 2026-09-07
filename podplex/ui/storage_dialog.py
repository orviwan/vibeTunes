from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
)

from podplex.core.library_index import album_folder_path, delete_path, scan_music_tree
from podplex.core.storage_analyzer import largest_albums, largest_artists, largest_files


def format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class StorageDialog(QDialog):
    def __init__(self, mount_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Largest Files & Albums")
        self.mount_path = mount_path
        self.tracks: list = []

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.albums_table = QTableWidget(0, 4)
        self.albums_table.setHorizontalHeaderLabels(["Artist", "Album", "Size", ""])
        self.tabs.addTab(self.albums_table, "💿 Largest Albums")

        self.files_table = QTableWidget(0, 3)
        self.files_table.setHorizontalHeaderLabels(["File", "Size", ""])
        self.tabs.addTab(self.files_table, "🎵 Largest Audio Files")

        self.artists_table = QTableWidget(0, 2)
        self.artists_table.setHorizontalHeaderLabels(["Artist", "Size"])
        self.tabs.addTab(self.artists_table, "👤 Largest Artists")

        self.refresh()

    def refresh(self) -> None:
        self.tracks = scan_music_tree(self.mount_path)

        albums = largest_albums(self.tracks)
        self.albums_table.setRowCount(len(albums))
        for row, a in enumerate(albums):
            self.albums_table.setItem(row, 0, QTableWidgetItem(a.artist))
            self.albums_table.setItem(row, 1, QTableWidgetItem(a.album))
            self.albums_table.setItem(row, 2, QTableWidgetItem(format_bytes(a.total_bytes)))
            delete_btn = QPushButton("✕ Delete")
            delete_btn.clicked.connect(
                lambda _checked=False, artist=a.artist, album=a.album: self._delete_album(artist, album)
            )
            self.albums_table.setCellWidget(row, 3, delete_btn)

        files = largest_files(self.tracks)
        self.files_table.setRowCount(len(files))
        for row, f in enumerate(files):
            self.files_table.setItem(row, 0, QTableWidgetItem(f.path.name))
            self.files_table.setItem(row, 1, QTableWidgetItem(format_bytes(f.size_bytes)))
            delete_btn = QPushButton("✕ Delete")
            delete_btn.clicked.connect(lambda _checked=False, path=f.path: self._delete_file(path))
            self.files_table.setCellWidget(row, 2, delete_btn)

        artists = largest_artists(self.tracks)
        self.artists_table.setRowCount(len(artists))
        for row, art in enumerate(artists):
            self.artists_table.setItem(row, 0, QTableWidgetItem(art.artist))
            self.artists_table.setItem(row, 1, QTableWidgetItem(format_bytes(art.total_bytes)))

    def _delete_album(self, artist: str, album: str) -> None:
        path = album_folder_path(self.mount_path, artist, album)
        delete_path(path)
        self.refresh()

    def _delete_file(self, path: Path) -> None:
        delete_path(path)
        self.refresh()
