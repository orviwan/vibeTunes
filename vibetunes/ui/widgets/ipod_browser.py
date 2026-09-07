"""Widget for visually browsing and managing music currently stored on the iPod."""
from typing import List, Optional
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QButtonGroup
)
from PySide6.QtGui import QIcon, QPixmap, QImage
from PySide6.QtCore import Qt, Signal, QObject, QSize

import threading
from vibetunes.core.ipod_scanner import (
    iPodArtist, iPodAlbum, scan_ipod_music, delete_album, delete_artist, clean_trash, open_folder
)
from vibetunes.core.image_cache import (
    create_artist_placeholder, create_album_placeholder, create_rounded_pixmap, ThumbnailManager
)
from vibetunes.ui.widgets.storage_bar import format_bytes

class iPodScanSignals(QObject):
    finished = Signal(list)

class iPodBrowserWidget(QWidget):
    storage_changed = Signal()
    scan_finished = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mount_point: str = ""
        self.artists: List[iPodArtist] = []
        self.filtered_artists: List[iPodArtist] = []
        self.selected_artist: Optional[iPodArtist] = None
        self.selected_album: Optional[iPodAlbum] = None
        self.album_view_mode: str = "grid"

        self.thumb_manager = ThumbnailManager(self)
        self.thumb_manager.thumbnail_loaded.connect(self._on_thumbnail_loaded)
        self.scan_signals = iPodScanSignals(self)
        self.scan_signals.finished.connect(self._on_scan_finished)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 8, 0, 0)
        main_layout.setSpacing(10)

        # Top Bar: Search & Actions
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter iPod artists & albums...")
        self.search_input.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.search_input, stretch=2)

        self.rescan_btn = QPushButton("Rescan iPod")
        self.rescan_btn.clicked.connect(self.reload_library)
        top_bar.addWidget(self.rescan_btn)

        self.clean_trash_btn = QPushButton("Clean Trash")
        self.clean_trash_btn.setToolTip("Empty .Trash-1000 folder on iPod")
        self.clean_trash_btn.clicked.connect(self._on_clean_trash)
        top_bar.addWidget(self.clean_trash_btn)

        main_layout.addLayout(top_bar)

        # 3-Pane Splitter: Artists | Albums | Tracks
        splitter = QSplitter(Qt.Horizontal)

        # Pane 1: Artists List
        artist_pane = QWidget()
        artist_layout = QVBoxLayout(artist_pane)
        artist_layout.setContentsMargins(0, 0, 0, 0)
        artist_layout.setSpacing(6)

        self.artist_header = QLabel("Artists (0)")
        self.artist_header.setStyleSheet("font-weight: bold; color: #a6adc8; padding-bottom: 2px;")
        artist_layout.addWidget(self.artist_header)

        self.artist_list = QListWidget()
        self.artist_list.setIconSize(QSize(40, 40))
        self.artist_list.setSpacing(3)
        self.artist_list.currentRowChanged.connect(self._on_artist_selected)
        artist_layout.addWidget(self.artist_list)

        artist_actions = QHBoxLayout()
        self.del_artist_btn = QPushButton("Delete Artist")
        self.del_artist_btn.setStyleSheet("""
            QPushButton { color: #f38ba8; }
            QPushButton:hover { background-color: #452430; }
        """)
        self.del_artist_btn.setEnabled(False)
        self.del_artist_btn.clicked.connect(self._on_delete_artist)
        artist_actions.addWidget(self.del_artist_btn)

        self.open_artist_btn = QPushButton("Open Folder")
        self.open_artist_btn.setEnabled(False)
        self.open_artist_btn.clicked.connect(self._on_open_artist_folder)
        artist_actions.addWidget(self.open_artist_btn)
        artist_layout.addLayout(artist_actions)

        splitter.addWidget(artist_pane)

        # Pane 2: Albums List
        album_pane = QWidget()
        album_layout = QVBoxLayout(album_pane)
        album_layout.setContentsMargins(0, 0, 0, 0)
        album_layout.setSpacing(6)

        album_header_row = QHBoxLayout()
        self.album_header = QLabel("Albums (0)")
        self.album_header.setStyleSheet("font-weight: bold; color: #a6adc8; padding-bottom: 2px;")
        album_header_row.addWidget(self.album_header)
        album_header_row.addStretch()

        self.view_grid_btn = QPushButton("▦ Grid")
        self.view_grid_btn.setCheckable(True)
        self.view_grid_btn.setChecked(True)
        self.view_grid_btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")
        self.view_grid_btn.clicked.connect(lambda: self._set_album_view_mode("grid"))

        self.view_list_btn = QPushButton("☰ List")
        self.view_list_btn.setCheckable(True)
        self.view_list_btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")
        self.view_list_btn.clicked.connect(lambda: self._set_album_view_mode("list"))

        self.view_btn_group = QButtonGroup(self)
        self.view_btn_group.addButton(self.view_grid_btn)
        self.view_btn_group.addButton(self.view_list_btn)

        album_header_row.addWidget(self.view_grid_btn)
        album_header_row.addWidget(self.view_list_btn)
        album_layout.addLayout(album_header_row)

        self.album_list = QListWidget()
        self._apply_album_view_settings()
        self.album_list.currentRowChanged.connect(self._on_album_selected)
        album_layout.addWidget(self.album_list)

        album_actions = QHBoxLayout()
        self.del_album_btn = QPushButton("Delete Album")
        self.del_album_btn.setStyleSheet("""
            QPushButton { color: #f38ba8; }
            QPushButton:hover { background-color: #452430; }
        """)
        self.del_album_btn.setEnabled(False)
        self.del_album_btn.clicked.connect(self._on_delete_album)
        album_actions.addWidget(self.del_album_btn)

        self.open_album_btn = QPushButton("Open Folder")
        self.open_album_btn.setEnabled(False)
        self.open_album_btn.clicked.connect(self._on_open_album_folder)
        album_actions.addWidget(self.open_album_btn)
        album_layout.addLayout(album_actions)

        splitter.addWidget(album_pane)

        # Pane 3: Track Table
        track_pane = QWidget()
        track_layout = QVBoxLayout(track_pane)
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(6)

        self.track_header = QLabel("Tracks (0)")
        self.track_header.setStyleSheet("font-weight: bold; color: #a6adc8; padding-bottom: 2px;")
        track_layout.addWidget(self.track_header)

        self.track_table = QTableWidget()
        self.track_table.setColumnCount(3)
        self.track_table.setHorizontalHeaderLabels(["#", "Title", "Size"])
        self.track_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.track_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.track_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.track_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.track_table.setEditTriggers(QTableWidget.NoEditTriggers)
        track_layout.addWidget(self.track_table)

        splitter.addWidget(track_pane)

        splitter.setSizes([260, 380, 360])
        main_layout.addWidget(splitter)

    def _set_album_view_mode(self, mode: str):
        if self.album_view_mode == mode:
            return
        self.album_view_mode = mode
        self.view_grid_btn.setChecked(mode == "grid")
        self.view_list_btn.setChecked(mode == "list")
        self._apply_album_view_settings()
        self._refresh_album_list()

    def _apply_album_view_settings(self):
        if self.album_view_mode == "grid":
            self.album_list.setViewMode(QListWidget.IconMode)
            self.album_list.setIconSize(QSize(110, 110))
            self.album_list.setGridSize(QSize(136, 170))
            self.album_list.setSpacing(8)
            self.album_list.setMovement(QListWidget.Static)
            self.album_list.setResizeMode(QListWidget.Adjust)
            self.album_list.setWordWrap(True)
        else:
            self.album_list.setViewMode(QListWidget.ListMode)
            self.album_list.setIconSize(QSize(56, 56))
            self.album_list.setGridSize(QSize())
            self.album_list.setSpacing(4)
            self.album_list.setWordWrap(False)

    def set_mount_point(self, mount_point: str):
        self.mount_point = mount_point
        self.reload_library()

    def reload_library(self):
        if not self.mount_point:
            self.artists = []
            self._render_artists([])
            return

        self.artist_header.setText("Scanning iPod...")
        mount_pt = self.mount_point
        def worker():
            artists = scan_ipod_music(mount_pt)
            self.scan_signals.finished.emit(artists)
        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_finished(self, artists: List[iPodArtist]):
        self.artists = artists
        self._filter_artists()
        self.scan_finished.emit(artists)

    def _on_search_changed(self, text: str):
        self._filter_artists()

    def _filter_artists(self):
        query = self.search_input.text().strip().lower()
        if not query:
            self.filtered_artists = list(self.artists)
        else:
            self.filtered_artists = [
                a for a in self.artists
                if query in a.name.lower() or any(query in alb.title.lower() for alb in a.albums)
            ]
        self._render_artists(self.filtered_artists)

    def _render_artists(self, artists: List[iPodArtist]):
        self.artist_list.clear()
        self.artist_header.setText(f"Artists ({len(artists)})")
        for a in artists:
            first_alb = a.albums[0] if a.albums else None
            sample = first_alb.sample_track_path if first_alb else None
            cover = first_alb.cover_art if first_alb else None
            key = f"ipod_artist_{a.name}"
            pix = self.thumb_manager.get_local_thumbnail(
                key=key,
                cover_path=cover,
                sample_track_path=sample,
                is_artist=True,
                size=40,
            )
            item = QListWidgetItem(QIcon(pix), f"{a.name}\n{len(a.albums)} alb • {format_bytes(a.total_size_bytes)}")
            item.setData(Qt.UserRole + 1, key)
            self.artist_list.addItem(item)

        self.selected_artist = None
        self.selected_album = None
        self.del_artist_btn.setEnabled(False)
        self.open_artist_btn.setEnabled(False)
        self.del_album_btn.setEnabled(False)
        self.open_album_btn.setEnabled(False)
        self.album_list.clear()
        self.album_header.setText("Albums (0)")
        self.track_table.setRowCount(0)
        self.track_header.setText("Tracks (0)")

    def _on_artist_selected(self, row: int):
        if row < 0 or row >= len(self.filtered_artists):
            self.selected_artist = None
            self.del_artist_btn.setEnabled(False)
            self.open_artist_btn.setEnabled(False)
            self.album_list.clear()
            return

        self.selected_artist = self.filtered_artists[row]
        self.del_artist_btn.setEnabled(True)
        self.open_artist_btn.setEnabled(True)
        self.album_header.setText(f"Albums ({len(self.selected_artist.albums)})")
        self._refresh_album_list()

    def _refresh_album_list(self):
        self.album_list.clear()
        if not self.selected_artist:
            return

        is_grid = (self.album_view_mode == "grid")
        icon_size = 110 if is_grid else 56

        for alb in self.selected_artist.albums:
            yr_str = f" ({alb.year})" if alb.year else ""
            key = f"ipod_album_{alb.artist_name}_{alb.title}_{alb.year or ''}"
            pix = self.thumb_manager.get_local_thumbnail(
                key=key,
                cover_path=alb.cover_art,
                sample_track_path=alb.sample_track_path,
                is_artist=False,
                size=icon_size,
            )

            if is_grid:
                caption = f"{alb.title}\n{yr_str.strip() or 'Album'}"
            else:
                caption = f"{alb.title}{yr_str}\n{alb.track_count} trk • {format_bytes(alb.total_size_bytes)}"

            item = QListWidgetItem(QIcon(pix), caption)
            item.setData(Qt.UserRole + 1, key)
            if is_grid:
                item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self.album_list.addItem(item)

        self.selected_album = None
        self.del_album_btn.setEnabled(False)
        self.open_album_btn.setEnabled(False)
        self.track_table.setRowCount(0)
        self.track_header.setText("Tracks (0)")

    def _on_thumbnail_loaded(self, key: str, pixmap: QPixmap):
        for i in range(self.artist_list.count()):
            it = self.artist_list.item(i)
            if it.data(Qt.UserRole + 1) == key:
                it.setIcon(QIcon(pixmap))

        for i in range(self.album_list.count()):
            it = self.album_list.item(i)
            if it.data(Qt.UserRole + 1) == key:
                it.setIcon(QIcon(pixmap))

    def _on_album_selected(self, row: int):
        if not self.selected_artist or row < 0 or row >= len(self.selected_artist.albums):
            self.selected_album = None
            self.del_album_btn.setEnabled(False)
            self.open_album_btn.setEnabled(False)
            self.track_table.setRowCount(0)
            return

        self.selected_album = self.selected_artist.albums[row]
        self.del_album_btn.setEnabled(True)
        self.open_album_btn.setEnabled(True)

        tracks = self.selected_album.tracks
        self.track_header.setText(f"Tracks ({len(tracks)}) • {format_bytes(self.selected_album.total_size_bytes)}")
        self.track_table.setRowCount(len(tracks))
        for r, t in enumerate(tracks):
            num_item = QTableWidgetItem(f"{t.track_number:02d}" if t.track_number > 0 else "-")
            num_item.setTextAlignment(Qt.AlignCenter)
            title_item = QTableWidgetItem(t.title)
            size_item = QTableWidgetItem(format_bytes(t.size_bytes))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.track_table.setItem(r, 0, num_item)
            self.track_table.setItem(r, 1, title_item)
            self.track_table.setItem(r, 2, size_item)

    def _on_delete_album(self):
        if not self.selected_album:
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Delete Album",
            f"Permanently delete album '{self.selected_album.title}' by {self.selected_album.artist_name} from your iPod?\n\nThis will free {format_bytes(self.selected_album.total_size_bytes)} on your iPod.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, freed, msg = delete_album(self.selected_album)
        if success:
            QMessageBox.information(self, "Album Deleted", msg)
            self.storage_changed.emit()
            self.reload_library()
        else:
            QMessageBox.warning(self, "Delete Failed", msg)

    def _on_delete_artist(self):
        if not self.selected_artist:
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Delete Artist",
            f"Permanently delete all albums by '{self.selected_artist.name}' from your iPod?\n\nTotal space to be freed: {format_bytes(self.selected_artist.total_size_bytes)}.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, freed, msg = delete_artist(self.selected_artist)
        if success:
            QMessageBox.information(self, "Artist Deleted", msg)
            self.storage_changed.emit()
            self.reload_library()
        else:
            QMessageBox.warning(self, "Delete Failed", msg)

    def _on_clean_trash(self):
        if not self.mount_point:
            return
        success, freed, msg = clean_trash(self.mount_point)
        QMessageBox.information(self, "Clean Trash", msg)
        if freed > 0:
            self.storage_changed.emit()

    def _on_open_artist_folder(self):
        if self.selected_artist:
            open_folder(self.selected_artist.path)

    def _on_open_album_folder(self):
        if self.selected_album:
            open_folder(self.selected_album.path)
