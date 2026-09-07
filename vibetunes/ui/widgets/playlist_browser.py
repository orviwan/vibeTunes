import threading
from typing import List, Optional, Set, Dict, Any
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFrame, QGroupBox
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, Signal, QObject

from vibetunes.core.plex_client import PlexManager, PlexPlaylistSummary, PlexTrackDetail, normalize_music_key
from vibetunes.core.ipod_scanner import iPodPlaylist, scan_ipod_playlists, delete_playlist, open_folder, is_plex_track_on_ipod
from vibetunes.core.sync_engine import SyncPlaylistTask
from vibetunes.ui.widgets.plex_browser import format_duration, make_status_icon
from vibetunes.ui.widgets.storage_bar import format_bytes

class PlaylistWorkerSignals(QObject):
    playlists_loaded = Signal(list)
    tracks_loaded = Signal(str, list)  # playlist_key, tracks

class PlaylistBrowserWidget(QWidget):
    sync_playlist_requested = Signal(object)  # SyncPlaylistTask
    playlists_changed = Signal()

    def __init__(self, plex: PlexManager, parent=None):
        super().__init__(parent)
        self.plex = plex
        self.mount_point: str = ""
        self.worker_signals = PlaylistWorkerSignals()
        self.worker_signals.playlists_loaded.connect(self._on_plex_playlists_loaded, Qt.QueuedConnection)
        self.worker_signals.tracks_loaded.connect(self._on_tracks_loaded, Qt.QueuedConnection)
        self.plex_playlists: List[PlexPlaylistSummary] = []
        self.filtered_plex_playlists: List[PlexPlaylistSummary] = []
        self.selected_playlist: Optional[PlexPlaylistSummary] = None
        self.current_tracks: List[PlexTrackDetail] = []
        self.ipod_playlists: List[iPodPlaylist] = []
        self.on_ipod_tracks: Set[str] = set()
        self.ipod_artist_tracks: Dict[str, List[Any]] = {}
        self.queued_playlist_keys: Set[str] = set()
        self.active_sync_playlist_key: Optional[str] = None
        self._icon_on_ipod = make_status_icon(True)
        self._icon_missing = make_status_icon(False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 8, 0, 0)
        main_layout.setSpacing(10)

        # Top Bar
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search Plex playlists...")
        self.search_input.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.search_input, stretch=2)

        self.refresh_btn = QPushButton("Refresh Playlists")
        self.refresh_btn.clicked.connect(self.reload_all)
        top_bar.addWidget(self.refresh_btn)

        main_layout.addLayout(top_bar)

        # Splitter: Plex Playlists | Playlist Tracks | On-iPod Playlists
        splitter = QSplitter(Qt.Horizontal)

        # Pane 1: Plex Playlists List
        plex_pane = QWidget()
        plex_layout = QVBoxLayout(plex_pane)
        plex_layout.setContentsMargins(0, 0, 0, 0)
        self.plex_header = QLabel("Plex Playlists (0)")
        self.plex_header.setStyleSheet("font-weight: bold; color: #a6adc8; padding-bottom: 4px;")
        plex_layout.addWidget(self.plex_header)

        self.plex_pl_list = QListWidget()
        self.plex_pl_list.currentRowChanged.connect(self._on_playlist_selected)
        plex_layout.addWidget(self.plex_pl_list)

        plex_actions = QHBoxLayout()
        self.sync_btn = QPushButton("Sync to iPod")
        self.sync_btn.setStyleSheet("""
            QPushButton { background-color: #89b4fa; color: #11111b; font-weight: bold; padding: 6px 14px; }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton:disabled { background-color: #313244; color: #585b70; }
        """)
        self.sync_btn.setEnabled(False)
        self.sync_btn.clicked.connect(self._on_sync_clicked)
        plex_actions.addWidget(self.sync_btn)
        plex_layout.addLayout(plex_actions)

        splitter.addWidget(plex_pane)

        # Pane 2: Tracks in Selected Playlist
        track_pane = QWidget()
        track_layout = QVBoxLayout(track_pane)
        track_layout.setContentsMargins(0, 0, 0, 0)
        self.track_header = QLabel("Playlist Tracks (0)")
        self.track_header.setStyleSheet("font-weight: bold; color: #a6adc8; padding-bottom: 4px;")
        track_layout.addWidget(self.track_header)

        self.track_table = QTableWidget()
        self.track_table.setColumnCount(6)
        self.track_table.setHorizontalHeaderLabels(["#", "Title", "iPod", "Artist", "Album", "Duration"])
        self.track_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.track_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.track_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.track_table.setColumnWidth(2, 48)
        self.track_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.track_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.track_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.track_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.track_table.setEditTriggers(QTableWidget.NoEditTriggers)
        track_layout.addWidget(self.track_table)

        splitter.addWidget(track_pane)

        # Pane 3: On-iPod Playlists
        ipod_pane = QWidget()
        ipod_layout = QVBoxLayout(ipod_pane)
        ipod_layout.setContentsMargins(0, 0, 0, 0)
        self.ipod_header = QLabel("On-iPod Playlists (0)")
        self.ipod_header.setStyleSheet("font-weight: bold; color: #a6adc8; padding-bottom: 4px;")
        ipod_layout.addWidget(self.ipod_header)

        self.ipod_pl_list = QListWidget()
        self.ipod_pl_list.currentRowChanged.connect(self._on_ipod_pl_selected)
        ipod_layout.addWidget(self.ipod_pl_list)

        ipod_actions = QHBoxLayout()
        self.del_pl_btn = QPushButton("Delete Playlist")
        self.del_pl_btn.setStyleSheet("""
            QPushButton { color: #f38ba8; }
            QPushButton:hover { background-color: #452430; }
        """)
        self.del_pl_btn.setEnabled(False)
        self.del_pl_btn.clicked.connect(self._on_delete_ipod_playlist)
        ipod_actions.addWidget(self.del_pl_btn)

        self.open_pl_btn = QPushButton("Open Folder")
        self.open_pl_btn.setEnabled(False)
        self.open_pl_btn.clicked.connect(self._on_open_playlists_folder)
        ipod_actions.addWidget(self.open_pl_btn)
        ipod_layout.addLayout(ipod_actions)

        splitter.addWidget(ipod_pane)

        splitter.setSizes([260, 480, 260])
        main_layout.addWidget(splitter)

    def set_mount_point(self, mount_point: str):
        self.mount_point = mount_point
        self.reload_ipod_playlists()

    def reload_all(self):
        self.reload_plex_playlists()
        self.reload_ipod_playlists()

    def reload_plex_playlists(self):
        if not self.plex.is_connected():
            self.plex_header.setText("Plex Not Connected")
            self.plex_pl_list.clear()
            return

        self.plex_header.setText("Loading Plex playlists...")
        def worker():
            playlists = self.plex.get_playlists()
            self.worker_signals.playlists_loaded.emit(playlists)

        threading.Thread(target=worker, daemon=True).start()

    def _on_plex_playlists_loaded(self, playlists: List[PlexPlaylistSummary]):
        self.plex_playlists = playlists
        self._filter_playlists()

    def reload_ipod_playlists(self):
        if not self.mount_point:
            self.ipod_playlists = []
            self.ipod_pl_list.clear()
            self.ipod_header.setText("On-iPod Playlists (0)")
            return

        self.ipod_playlists = scan_ipod_playlists(self.mount_point)
        self.ipod_pl_list.clear()
        self.ipod_header.setText(f"On-iPod Playlists ({len(self.ipod_playlists)})")
        for pl in self.ipod_playlists:
            item = QListWidgetItem(f"♪  {pl.name}  ({pl.track_count} tracks)")
            self.ipod_pl_list.addItem(item)

        self.del_pl_btn.setEnabled(False)
        self.open_pl_btn.setEnabled(bool(self.ipod_playlists))

    def _on_search_changed(self, text: str):
        self._filter_playlists()

    def _filter_playlists(self):
        q = self.search_input.text().strip().lower()
        if not q:
            self.filtered_plex_playlists = list(self.plex_playlists)
        else:
            self.filtered_plex_playlists = [p for p in self.plex_playlists if q in p.title.lower()]

        self.plex_pl_list.clear()
        self.plex_header.setText(f"Plex Playlists ({len(self.filtered_plex_playlists)})")
        for pl in self.filtered_plex_playlists:
            dur_str = f" • {format_duration(pl.duration_ms)}" if pl.duration_ms else ""
            item = QListWidgetItem(f"♪  {pl.title}  ({pl.track_count} tracks{dur_str})")
            self.plex_pl_list.addItem(item)

        self.selected_playlist = None
        self.sync_btn.setEnabled(False)
        self.track_table.setRowCount(0)
        self.track_header.setText("Playlist Tracks (0)")

    def _on_playlist_selected(self, row: int):
        if row < 0 or row >= len(self.filtered_plex_playlists):
            self.selected_playlist = None
            self.sync_btn.setEnabled(False)
            self.track_table.setRowCount(0)
            return

        self.selected_playlist = self.filtered_plex_playlists[row]
        if self.selected_playlist.rating_key == self.active_sync_playlist_key:
            self.sync_btn.setEnabled(False)
            self.sync_btn.setText("● Syncing Playlist...")
        elif self.selected_playlist.rating_key in self.queued_playlist_keys:
            self.sync_btn.setEnabled(False)
            self.sync_btn.setText("⏱ In Sync Queue")
        else:
            self.sync_btn.setEnabled(True)
            self.sync_btn.setText("Sync to iPod")

        self.track_header.setText("Loading playlist tracks...")
        pl_key = self.selected_playlist.rating_key
        def worker():
            tracks = self.plex.get_playlist_tracks(pl_key)
            self.worker_signals.tracks_loaded.emit(pl_key, tracks)

        threading.Thread(target=worker, daemon=True).start()

    def update_ipod_tracks(self, ipod_artist_tracks: Dict[str, List[Any]]):
        self.ipod_artist_tracks = ipod_artist_tracks
        if self.current_tracks:
            self._render_tracks_table(self.current_tracks)

    def _is_track_on_ipod(self, track: PlexTrackDetail) -> bool:
        norm_art = normalize_music_key(track.artist_name)
        artist_tracks = self.ipod_artist_tracks.get(norm_art, [])
        return is_plex_track_on_ipod(track, artist_tracks)

    def _on_tracks_loaded(self, arg1: Any, arg2: Optional[List[PlexTrackDetail]] = None):
        if arg2 is None:
            tracks = arg1
        else:
            playlist_key = arg1
            tracks = arg2
            if not self.selected_playlist or self.selected_playlist.rating_key != playlist_key:
                return  # Stale response from previously selected playlist
        self.current_tracks = tracks
        self._render_tracks_table(tracks)

    def _render_tracks_table(self, tracks: List[PlexTrackDetail]):
        total_duration = sum(t.duration_ms for t in tracks)
        on_device_indices = set()
        for r, t in enumerate(tracks):
            if self._is_track_on_ipod(t):
                on_device_indices.add(r)

        on_count = len(on_device_indices)
        total_tracks = len(tracks)
        if on_count == total_tracks and total_tracks > 0:
            sync_badge = f"✓ {total_tracks}/{total_tracks}"
        elif on_count > 0:
            sync_badge = f"◐ {on_count}/{total_tracks}"
        else:
            sync_badge = f"0/{total_tracks}"

        self.track_header.setText(
            f"Tracks ({total_tracks}) • {sync_badge} • {format_duration(total_duration)} total"
        )
        self.track_table.setRowCount(total_tracks)
        for r, t in enumerate(tracks):
            is_on_dev = (r in on_device_indices)

            num_item = QTableWidgetItem(f"{r + 1}")
            num_item.setTextAlignment(Qt.AlignCenter)

            title_item = QTableWidgetItem(t.title)

            status_item = QTableWidgetItem()
            status_item.setTextAlignment(Qt.AlignCenter)
            if is_on_dev:
                status_item.setIcon(self._icon_on_ipod)
                status_item.setToolTip("Synced")
                title_item.setForeground(QColor("#cdd6f4"))
            else:
                status_item.setIcon(self._icon_missing)
                status_item.setToolTip("Not Synced")
                title_item.setForeground(QColor("#7f849c"))

            artist_item = QTableWidgetItem(t.artist_name)
            album_item = QTableWidgetItem(t.album_title)
            dur_item = QTableWidgetItem(format_duration(t.duration_ms))
            dur_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.track_table.setItem(r, 0, num_item)
            self.track_table.setItem(r, 1, title_item)
            self.track_table.setItem(r, 2, status_item)
            self.track_table.setItem(r, 3, artist_item)
            self.track_table.setItem(r, 4, album_item)
            self.track_table.setItem(r, 5, dur_item)

    def update_sync_queue_keys(self, queued_keys: Set[str], active_key: Optional[str] = None):
        self.queued_playlist_keys = set(queued_keys)
        self.active_sync_playlist_key = active_key
        if self.selected_playlist:
            if self.selected_playlist.rating_key == self.active_sync_playlist_key:
                self.sync_btn.setEnabled(False)
                self.sync_btn.setText("● Syncing Playlist...")
            elif self.selected_playlist.rating_key in self.queued_playlist_keys:
                self.sync_btn.setEnabled(False)
                self.sync_btn.setText("⏱ In Sync Queue")
            else:
                self.sync_btn.setEnabled(True)
                self.sync_btn.setText("Sync to iPod")

    def _on_sync_clicked(self):
        if not self.selected_playlist:
            return
        task = SyncPlaylistTask(
            playlist_title=self.selected_playlist.title,
            playlist_key=self.selected_playlist.rating_key,
        )
        self.queued_playlist_keys.add(self.selected_playlist.rating_key)
        self.sync_btn.setEnabled(False)
        self.sync_btn.setText("⏱ In Sync Queue")
        self.sync_playlist_requested.emit(task)

    def _on_ipod_pl_selected(self, row: int):
        has_sel = 0 <= row < len(self.ipod_playlists)
        self.del_pl_btn.setEnabled(has_sel)
        self.open_pl_btn.setEnabled(True)

    def _on_delete_ipod_playlist(self):
        row = self.ipod_pl_list.currentRow()
        if row < 0 or row >= len(self.ipod_playlists):
            return

        pl = self.ipod_playlists[row]
        confirm = QMessageBox.question(
            self,
            "Delete Playlist",
            f"Are you sure you want to delete playlist '{pl.name}' from your iPod?\n(Audio files will not be deleted)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        success, msg = delete_playlist(pl)
        if success:
            QMessageBox.information(self, "Playlist Deleted", msg)
            self.reload_ipod_playlists()
            self.playlists_changed.emit()
        else:
            QMessageBox.warning(self, "Delete Failed", msg)

    def _on_open_playlists_folder(self):
        if self.mount_point:
            pl_dir = Path(self.mount_point) / "Playlists"
            pl_dir.mkdir(parents=True, exist_ok=True)
            open_folder(pl_dir)
