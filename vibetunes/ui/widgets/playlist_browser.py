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
from vibetunes.core.ipod_scanner import iPodPlaylist, scan_ipod_playlists, delete_playlist, is_plex_track_on_ipod
from vibetunes.core.naming import clean_fat32_name
from vibetunes.core.sync_engine import SyncPlaylistTask
from vibetunes.ui.widgets.plex_browser import format_duration, make_status_icon
from vibetunes.ui.widgets.storage_bar import format_bytes

class PlaylistWorkerSignals(QObject):
    playlists_loaded = Signal(list)
    tracks_loaded = Signal(str, list)  # playlist_key, tracks

class PlaylistBrowserWidget(QWidget):
    sync_playlist_requested = Signal(object)  # SyncPlaylistTask
    playlists_changed = Signal()
    refresh_requested = Signal()

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
        self.ipod_playlists_map: Dict[str, iPodPlaylist] = {}
        self.on_ipod_tracks: Set[str] = set()
        self.ipod_artist_tracks: Dict[str, List[Any]] = {}
        self.queued_playlist_keys: Set[str] = set()
        self.active_sync_playlist_key: Optional[str] = None
        self._icon_on_ipod = make_status_icon(True)
        self._icon_missing = make_status_icon(False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 8, 0, 0)
        main_layout.setSpacing(10)

        # Top Bar: Search + Unified Refresh
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search playlists...")
        self.search_input.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.search_input, stretch=2)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Refresh playlists and iPod status")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        top_bar.addWidget(self.refresh_btn)

        main_layout.addLayout(top_bar)

        # 2-Pane Splitter: Plex Playlists | Playlist Tracks
        splitter = QSplitter(Qt.Horizontal)

        # --- Pane 1: Playlists List ---
        plex_pane = QWidget()
        plex_layout = QVBoxLayout(plex_pane)
        plex_layout.setContentsMargins(0, 0, 0, 0)
        self.plex_header = QLabel("Playlists (0)")
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

        self.remove_btn = QPushButton("Remove from iPod")
        self.remove_btn.setStyleSheet("""
            QPushButton { color: #f38ba8; padding: 6px 14px; font-weight: bold; }
            QPushButton:hover { background-color: #452430; }
            QPushButton:disabled { color: #585b70; }
        """)
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self._on_remove_from_ipod_clicked)
        plex_actions.addWidget(self.remove_btn)

        plex_layout.addLayout(plex_actions)
        splitter.addWidget(plex_pane)

        # --- Pane 2: Tracks in Selected Playlist ---
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
        splitter.setSizes([320, 680])
        main_layout.addWidget(splitter)

        # Backwards-compatibility aliases for tests
        self.ipod_pl_list = self.plex_pl_list
        self.del_pl_btn = self.remove_btn

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

    def _is_playlist_on_ipod(self, pl: Optional[PlexPlaylistSummary]) -> Optional[iPodPlaylist]:
        if not pl:
            return None
        key1 = normalize_music_key(pl.title)
        key2 = clean_fat32_name(pl.title).lower()
        return self.ipod_playlists_map.get(key1) or self.ipod_playlists_map.get(key2)

    def reload_ipod_playlists(self):
        self.ipod_playlists_map.clear()
        if self.mount_point:
            self.ipod_playlists = scan_ipod_playlists(self.mount_point)
            for pl in self.ipod_playlists:
                self.ipod_playlists_map[normalize_music_key(pl.name)] = pl
                self.ipod_playlists_map[clean_fat32_name(pl.name).lower()] = pl
        else:
            self.ipod_playlists = []
        self._filter_playlists()

    def _on_search_changed(self, text: str):
        self._filter_playlists()

    def _filter_playlists(self):
        q = self.search_input.text().strip().lower()
        if not q:
            self.filtered_plex_playlists = list(self.plex_playlists)
        else:
            self.filtered_plex_playlists = [p for p in self.plex_playlists if q in p.title.lower()]

        self.plex_pl_list.clear()
        on_ipod_count = sum(1 for p in self.filtered_plex_playlists if self._is_playlist_on_ipod(p))
        total_count = len(self.filtered_plex_playlists)
        self.plex_header.setText(f"Playlists ({total_count}) • {on_ipod_count} on iPod")

        for pl in self.filtered_plex_playlists:
            ipod_pl = self._is_playlist_on_ipod(pl)
            dur_str = f" • {format_duration(pl.duration_ms)}" if pl.duration_ms else ""
            if ipod_pl:
                item = QListWidgetItem(self._icon_on_ipod, f" {pl.title}  (on iPod • {pl.track_count} tracks{dur_str})")
            else:
                item = QListWidgetItem(self._icon_missing, f" {pl.title}  ({pl.track_count} tracks{dur_str})")
            self.plex_pl_list.addItem(item)

        self.selected_playlist = None
        self.sync_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        self.track_table.setRowCount(0)
        self.track_header.setText("Playlist Tracks (0)")

    def _on_playlist_selected(self, row: int):
        if row < 0 or row >= len(self.filtered_plex_playlists):
            self.selected_playlist = None
            self.sync_btn.setEnabled(False)
            self.remove_btn.setEnabled(False)
            self.track_table.setRowCount(0)
            return

        self.selected_playlist = self.filtered_plex_playlists[row]
        ipod_pl = self._is_playlist_on_ipod(self.selected_playlist)

        if self.selected_playlist.rating_key == self.active_sync_playlist_key:
            self.sync_btn.setEnabled(False)
            self.sync_btn.setText("● Syncing Playlist...")
        elif self.selected_playlist.rating_key in self.queued_playlist_keys:
            self.sync_btn.setEnabled(False)
            self.sync_btn.setText("⏱ In Sync Queue")
        else:
            self.sync_btn.setEnabled(True)
            self.sync_btn.setText("Re-sync to iPod" if ipod_pl else "Sync to iPod")

        self.remove_btn.setEnabled(ipod_pl is not None)

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
        if self.selected_playlist and self.selected_playlist.track_count != len(tracks):
            self.selected_playlist.track_count = len(tracks)
            row = self.plex_pl_list.currentRow()
            if 0 <= row < self.plex_pl_list.count():
                dur_str = f" • {format_duration(self.selected_playlist.duration_ms)}" if self.selected_playlist.duration_ms else ""
                self.plex_pl_list.item(row).setText(f"♪  {self.selected_playlist.title}  ({len(tracks)} tracks{dur_str})")
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
            ipod_pl = self._is_playlist_on_ipod(self.selected_playlist)
            if self.selected_playlist.rating_key == self.active_sync_playlist_key:
                self.sync_btn.setEnabled(False)
                self.sync_btn.setText("● Syncing Playlist...")
            elif self.selected_playlist.rating_key in self.queued_playlist_keys:
                self.sync_btn.setEnabled(False)
                self.sync_btn.setText("⏱ In Sync Queue")
            else:
                self.sync_btn.setEnabled(True)
                self.sync_btn.setText("Re-sync to iPod" if ipod_pl else "Sync to iPod")

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

    def _on_remove_from_ipod_clicked(self):
        if not self.selected_playlist or not self.mount_point:
            return
        ipod_pl = self._is_playlist_on_ipod(self.selected_playlist)
        if not ipod_pl:
            return
        success, msg = delete_playlist(ipod_pl)
        if success:
            self.reload_ipod_playlists()
            self.playlists_changed.emit()
            if self.selected_playlist:
                self.remove_btn.setEnabled(False)
                self.sync_btn.setText("Sync to iPod")
        else:
            QMessageBox.warning(self, "Remove Failed", msg)

    def _on_delete_ipod_playlist(self):
        """Backwards compatibility alias for tests."""
        if not self.selected_playlist and self.ipod_playlists:
            success, msg = delete_playlist(self.ipod_playlists[0])
            if success:
                self.reload_ipod_playlists()
                self.playlists_changed.emit()
            return
        self._on_remove_from_ipod_clicked()
