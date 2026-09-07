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
from podplex.core.library_index import check_album_status, delete_album, status_label
from podplex.core.plex_client import PlexClient
from podplex.core.sync_engine import SyncEngine
from podplex.core.sync_task_builder import build_album_sync_task
from podplex.ui.queue_dialog import QueueDialog
from podplex.ui.storage_dialog import StorageDialog


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
        queue_btn = QPushButton("☰ View Queue")
        queue_btn.clicked.connect(self.open_queue_dialog)
        storage_btn = QPushButton("🔍 Largest Files & Albums")
        storage_btn.clicked.connect(self.open_storage_dialog)
        header.addWidget(self.device_label)
        header.addWidget(detect_btn)
        header.addWidget(load_btn)
        header.addWidget(queue_btn)
        header.addWidget(storage_btn)
        header.addWidget(settings_btn)
        root.addLayout(header)

        lists = QHBoxLayout()
        self.artist_list = QListWidget()
        self.artist_list.itemSelectionChanged.connect(self.on_artist_selected)
        self.album_list = QListWidget()
        self.album_list.itemSelectionChanged.connect(self.on_album_selected)
        lists.addWidget(self.artist_list)
        lists.addWidget(self.album_list)
        root.addLayout(lists)

        status_row = QHBoxLayout()
        self.album_status_label = QLabel("")
        delete_btn = QPushButton("Delete from iPod")
        delete_btn.clicked.connect(self.delete_selected_album)
        status_row.addWidget(self.album_status_label)
        status_row.addWidget(delete_btn)
        root.addLayout(status_row)

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
        self._current_album_tracks: list = []
        self._queue_dialog: QueueDialog | None = None
        self._storage_dialog: StorageDialog | None = None

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
        self.album_status_label.setText("")
        self._current_album_tracks = []
        if not items or self.plex_client is None:
            return
        artist = self._artists_by_name[items[0].text()]
        for album in self.plex_client.albums_for_artist(artist):
            self._albums_by_name[album.title] = album
            self.album_list.addItem(album.title)

    def on_album_selected(self) -> None:
        items = self.album_list.selectedItems()
        if not items or self.plex_client is None:
            self._current_album_tracks = []
            self.album_status_label.setText("")
            return
        album = self._albums_by_name[items[0].text()]
        self._current_album_tracks = self.plex_client.tracks_for_album(album)
        self._refresh_album_status()

    def _refresh_album_status(self) -> None:
        if not self._current_album_tracks or self.device_mount_path is None:
            self.album_status_label.setText("")
            return
        status = check_album_status(self.device_mount_path, self.config.naming_pattern, self._current_album_tracks)
        self.album_status_label.setText(status_label(status))

    def delete_selected_album(self) -> None:
        if not self._current_album_tracks or self.device_mount_path is None:
            return
        freed = delete_album(self.device_mount_path, self.config.naming_pattern, self._current_album_tracks)
        self.status_label.setText(f"Deleted from iPod, freed {freed} bytes")
        self._refresh_album_status()

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

    def open_queue_dialog(self) -> None:
        self._queue_dialog = QueueDialog(self.engine, self)
        self._queue_dialog.show()

    def open_storage_dialog(self) -> None:
        if self.device_mount_path is None:
            QMessageBox.warning(self, "PodPlex", "Detect your iPod first.")
            return
        self._storage_dialog = StorageDialog(self.device_mount_path, self)
        self._storage_dialog.show()
