import threading
from typing import List, Optional, Set, Dict, Any
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFrame, QButtonGroup,
    QMenu
)
from PySide6.QtGui import QPixmap, QIcon, QColor, QPainter, QPen
from PySide6.QtCore import Qt, Signal, QObject, QSize

from vibetunes.core.plex_client import (
    PlexManager, PlexArtistSummary, PlexAlbumSummary, PlexTrackDetail, normalize_music_key
)
from vibetunes.core.sync_engine import SyncTask
from vibetunes.core.image_cache import ThumbnailManager
from vibetunes.core.ipod_scanner import is_plex_track_on_ipod
from vibetunes.ui.widgets.storage_bar import format_bytes

def format_duration(ms: int) -> str:
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"

def make_status_icon(on_ipod: bool) -> QIcon:
    """Generates a high-DPI visual status badge for tracks on/missing from iPod."""
    pix = QPixmap(16, 16)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    if on_ipod:
        # Solid vibrant green circular badge with dark checkmark
        painter.setBrush(QColor("#a6e3a1"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(1, 1, 14, 14)
        painter.setPen(QPen(QColor("#11111b"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(4, 8, 7, 11)
        painter.drawLine(7, 11, 12, 5)
    else:
        # Subtle muted ring for missing track
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#585b70"), 1.6))
        painter.drawEllipse(2, 2, 11, 11)
    painter.end()
    return QIcon(pix)

class PlexWorkerSignals(QObject):
    artists_loaded = Signal(list)
    albums_loaded = Signal(str, list)   # artist_key, albums
    tracks_loaded = Signal(str, list)   # album_key, tracks

class PlexBrowserWidget(QWidget):
    sync_album_requested = Signal(object)   # SyncTask
    sync_artist_requested = Signal(list)   # List[SyncTask]
    remove_album_requested = Signal(str, str)  # artist_name, album_title
    remove_artist_requested = Signal(str)      # artist_name
    rescan_ipod_requested = Signal()
    clean_trash_requested = Signal()

    def __init__(self, plex: PlexManager, parent=None):
        super().__init__(parent)
        self.plex = plex
        self.current_library = "Music"
        self.artists: List[PlexArtistSummary] = []
        self.filtered_artists: List[PlexArtistSummary] = []
        self.selected_artist: Optional[PlexArtistSummary] = None
        self.current_albums: List[PlexAlbumSummary] = []
        self.displayed_albums: List[PlexAlbumSummary] = []
        self.selected_album: Optional[PlexAlbumSummary] = None
        self.on_ipod_albums: Set[str] = set()
        self.ipod_artist_album_counts: Dict[str, int] = {}
        self.ipod_album_data: Dict[str, Dict[str, Any]] = {}
        self.album_view_mode: str = "grid"  # 'grid' or 'list'
        self.filter_mode: str = "all"        # 'all', 'on_ipod', 'not_on_ipod'
        self.current_tracks: List[PlexTrackDetail] = []
        self.ipod_artist_tracks: Dict[str, List[Any]] = {}
        self.queued_album_keys: Set[str] = set()
        self.active_sync_album_key: Optional[str] = None
        self._icon_on_ipod = make_status_icon(True)
        self._icon_missing = make_status_icon(False)

        self.worker_signals = PlexWorkerSignals(self)
        self.worker_signals.artists_loaded.connect(self._on_artists_loaded)
        self.worker_signals.albums_loaded.connect(self._on_albums_loaded)
        self.worker_signals.tracks_loaded.connect(self._on_tracks_loaded)

        self.thumb_manager = ThumbnailManager(self)
        self.thumb_manager.thumbnail_loaded.connect(self._on_thumbnail_loaded)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 8, 0, 0)
        main_layout.setSpacing(10)

        # Top search bar, quick filters & actions
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search artists & albums...")
        self.search_input.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.search_input, stretch=2)

        # Quick Filter: [ All Music ] [ ✓ Synced ] [ Not Synced ]
        self.filter_all_btn = QPushButton("All Music")
        self.filter_all_btn.setCheckable(True)
        self.filter_all_btn.setChecked(True)
        self.filter_all_btn.clicked.connect(lambda: self._set_filter_mode("all"))

        self.filter_ipod_btn = QPushButton("✓ Synced (0)")
        self.filter_ipod_btn.setCheckable(True)
        self.filter_ipod_btn.clicked.connect(lambda: self._set_filter_mode("on_ipod"))

        self.filter_missing_btn = QPushButton("Not Synced")
        self.filter_missing_btn.setCheckable(True)
        self.filter_missing_btn.clicked.connect(lambda: self._set_filter_mode("not_on_ipod"))

        self.filter_btn_group = QButtonGroup(self)
        self.filter_btn_group.addButton(self.filter_all_btn)
        self.filter_btn_group.addButton(self.filter_ipod_btn)
        self.filter_btn_group.addButton(self.filter_missing_btn)

        top_bar.addWidget(self.filter_all_btn)
        top_bar.addWidget(self.filter_ipod_btn)
        top_bar.addWidget(self.filter_missing_btn)

        self.rescan_ipod_btn = QPushButton("Rescan iPod")
        self.rescan_ipod_btn.setToolTip("Rescan iPod filesystem for changes")
        self.rescan_ipod_btn.clicked.connect(self.rescan_ipod_requested.emit)
        top_bar.addWidget(self.rescan_ipod_btn)

        self.clean_trash_btn = QPushButton("Clean Trash")
        self.clean_trash_btn.setToolTip("Empty .Trash-1000 folder on iPod")
        self.clean_trash_btn.clicked.connect(self._on_clean_trash_clicked)
        top_bar.addWidget(self.clean_trash_btn)

        self.refresh_btn = QPushButton("Refresh Plex")
        self.refresh_btn.clicked.connect(self.reload_library)
        top_bar.addWidget(self.refresh_btn)

        main_layout.addLayout(top_bar)

        # 3-Pane Splitter: Artists | Albums | Tracks
        splitter = QSplitter(Qt.Horizontal)

        # --- Pane 1: Artists ---
        artist_pane = QWidget()
        artist_layout = QVBoxLayout(artist_pane)
        artist_layout.setContentsMargins(0, 0, 0, 0)
        artist_layout.setSpacing(6)

        self.artist_header = QLabel("Artists (0)")
        self.artist_header.setStyleSheet("font-weight: bold; color: #a6adc8; padding-bottom: 2px;")
        artist_layout.addWidget(self.artist_header)

        self.artist_list = QListWidget()
        self.artist_list.setIconSize(QSize(44, 44))
        self.artist_list.setSpacing(3)
        self.artist_list.currentRowChanged.connect(self._on_artist_selected)
        artist_layout.addWidget(self.artist_list)

        artist_actions = QHBoxLayout()
        self.sync_artist_btn = QPushButton("+ Add All to iPod")
        self.sync_artist_btn.setStyleSheet("""
            QPushButton { background-color: #89b4fa; color: #11111b; font-weight: bold; }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton:disabled { background-color: #313244; color: #585b70; }
        """)
        self.sync_artist_btn.setEnabled(False)
        self.sync_artist_btn.clicked.connect(self._on_sync_artist)
        artist_actions.addWidget(self.sync_artist_btn)

        self.delete_artist_btn = QPushButton("Remove from iPod")
        self.delete_artist_btn.setStyleSheet("""
            QPushButton { background-color: #31202b; color: #f38ba8; font-weight: bold; border: 1px solid #f38ba8; }
            QPushButton:hover { background-color: #452430; color: #ff9ab3; }
            QPushButton:disabled { background-color: #313244; color: #585b70; border: none; }
        """)
        self.delete_artist_btn.setEnabled(False)
        self.delete_artist_btn.setVisible(False)
        self.delete_artist_btn.clicked.connect(self._on_delete_artist)
        artist_actions.addWidget(self.delete_artist_btn)

        artist_layout.addLayout(artist_actions)
        splitter.addWidget(artist_pane)

        # --- Pane 2: Albums ---
        album_pane = QWidget()
        album_layout = QVBoxLayout(album_pane)
        album_layout.setContentsMargins(0, 0, 0, 0)
        album_layout.setSpacing(6)

        album_header_row = QHBoxLayout()
        self.album_header = QLabel("Albums (0)")
        self.album_header.setStyleSheet("font-weight: bold; color: #a6adc8; padding-bottom: 2px;")
        album_header_row.addWidget(self.album_header)
        album_header_row.addStretch()

        # View mode toggle (Grid vs List)
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
        self.sync_album_btn = QPushButton("+ Add to iPod")
        self.sync_album_btn.setStyleSheet("""
            QPushButton { background-color: #89b4fa; color: #11111b; font-weight: bold; }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton:disabled { background-color: #313244; color: #585b70; }
        """)
        self.sync_album_btn.setEnabled(False)
        self.sync_album_btn.clicked.connect(self._on_sync_album)
        album_actions.addWidget(self.sync_album_btn)

        self.resync_album_btn = QPushButton("Re-sync")
        self.resync_album_btn.setStyleSheet("""
            QPushButton { background-color: #45475a; color: #cdd6f4; font-weight: bold; }
            QPushButton:hover { background-color: #585b70; }
        """)
        self.resync_album_btn.setEnabled(False)
        self.resync_album_btn.setVisible(False)
        self.resync_album_btn.clicked.connect(self._on_resync_album)
        album_actions.addWidget(self.resync_album_btn)

        self.delete_album_btn = QPushButton("Remove from iPod")
        self.delete_album_btn.setStyleSheet("""
            QPushButton { background-color: #31202b; color: #f38ba8; font-weight: bold; border: 1px solid #f38ba8; }
            QPushButton:hover { background-color: #452430; color: #ff9ab3; }
            QPushButton:disabled { background-color: #313244; color: #585b70; border: none; }
        """)
        self.delete_album_btn.setEnabled(False)
        self.delete_album_btn.setVisible(False)
        self.delete_album_btn.clicked.connect(self._on_delete_album)
        album_actions.addWidget(self.delete_album_btn)

        album_layout.addLayout(album_actions)
        splitter.addWidget(album_pane)

        # --- Pane 3: Tracks ---
        track_pane = QWidget()
        track_layout = QVBoxLayout(track_pane)
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(6)

        self.track_header = QLabel("Tracks (0)")
        self.track_header.setStyleSheet("font-weight: bold; color: #a6adc8; padding-bottom: 2px;")
        track_layout.addWidget(self.track_header)

        self.track_table = QTableWidget()
        self.track_table.setColumnCount(6)
        self.track_table.setHorizontalHeaderLabels(["#", "Title", "iPod", "Duration", "Format", "Size"])
        self.track_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.track_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.track_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.track_table.setColumnWidth(2, 48)
        self.track_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.track_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.track_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.track_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.track_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.track_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.track_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.track_table.customContextMenuRequested.connect(self._on_track_table_context_menu)
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
        self._refresh_album_list_badges()

    def _set_filter_mode(self, mode: str):
        if self.filter_mode == mode:
            return
        self.filter_mode = mode
        self.filter_all_btn.setChecked(mode == "all")
        self.filter_ipod_btn.setChecked(mode == "on_ipod")
        self.filter_missing_btn.setChecked(mode == "not_on_ipod")
        self._filter_artists()
        if self.selected_artist:
            self._refresh_album_list_badges()

    def _update_filter_button_counts(self):
        total_artists = len(self.artists)
        on_ipod_cnt = sum(1 for a in self.artists if self.ipod_artist_album_counts.get(normalize_music_key(a.name), 0) > 0)
        missing_cnt = sum(1 for a in self.artists if self.ipod_artist_album_counts.get(normalize_music_key(a.name), 0) < a.album_count)
        self.filter_all_btn.setText(f"All Music ({total_artists})")
        self.filter_ipod_btn.setText(f"✓ Synced ({on_ipod_cnt})")
        self.filter_missing_btn.setText(f"Not Synced ({missing_cnt})")

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

    def set_library(self, library_name: str):
        self.current_library = library_name
        self.reload_library()

    def update_ipod_known_albums(
        self,
        album_keys: Set[str],
        artist_counts: Optional[Dict[str, int]] = None,
        ipod_album_data: Optional[Dict[str, Dict[str, Any]]] = None,
        ipod_artist_tracks: Optional[Dict[str, List[Any]]] = None,
    ):
        self.on_ipod_albums = album_keys
        if artist_counts is not None:
            self.ipod_artist_album_counts = artist_counts
        if ipod_album_data is not None:
            self.ipod_album_data = ipod_album_data
        else:
            self.ipod_album_data = {k: {"track_count": 9999, "tracks": []} for k in album_keys}

        if ipod_artist_tracks is not None:
            self.ipod_artist_tracks = ipod_artist_tracks

        self._update_filter_button_counts()
        self._filter_artists()
        if self.selected_artist:
            self._refresh_album_list_badges()
        if self.selected_album:
            self._update_album_actions()
            if self.current_tracks:
                self._render_tracks_table(self.current_tracks)

    def _is_track_on_ipod(self, track: PlexTrackDetail) -> bool:
        if not self.selected_album:
            return False
        lookup_key = normalize_music_key(self.selected_album.artist_name, self.selected_album.title)
        device_info = self.ipod_album_data.get(lookup_key)
        if not device_info:
            norm_art = normalize_music_key(self.selected_album.artist_name)
            norm_alb = normalize_music_key(self.selected_album.title)
            for k, v in self.ipod_album_data.items():
                if k.startswith(f"{norm_art}::"):
                    k_alb = k.split("::", 1)[1]
                    if norm_alb in k_alb or k_alb in norm_alb:
                        device_info = v
                        break

        ipod_tracks = list(device_info.get("tracks", [])) if device_info else []
        norm_art = normalize_music_key(self.selected_album.artist_name)
        artist_tracks = self.ipod_artist_tracks.get(norm_art, [])
        return is_plex_track_on_ipod(track, ipod_tracks) or is_plex_track_on_ipod(track, artist_tracks)

    def get_album_ipod_status(self, artist_name: str, album_title: str, total_plex_tracks: int = 0) -> tuple[str, int, int]:
        """
        Returns (status, on_ipod_count, missing_count).
        status:
          - 'none': 0 tracks on iPod
          - 'partial': 1 <= on_ipod_count < total_plex_tracks
          - 'complete': on_ipod_count >= total_plex_tracks (or on_ipod_count > 0 when total_plex_tracks unknown)
        """
        lookup_key = normalize_music_key(artist_name, album_title)
        info = self.ipod_album_data.get(lookup_key)
        if not info:
            norm_art = normalize_music_key(artist_name)
            norm_alb = normalize_music_key(album_title)
            for k, v in self.ipod_album_data.items():
                if k.startswith(f"{norm_art}::"):
                    k_alb = k.split("::", 1)[1]
                    if norm_alb in k_alb or k_alb in norm_alb:
                        info = v
                        break

        if not info or info.get("track_count", 0) == 0:
            if lookup_key in self.on_ipod_albums:
                return ("complete", total_plex_tracks or 1, 0)
            return ("none", 0, total_plex_tracks)

        on_cnt = info["track_count"]
        if total_plex_tracks <= 0:
            return ("complete", on_cnt, 0)
        if on_cnt < total_plex_tracks:
            return ("partial", on_cnt, max(0, total_plex_tracks - on_cnt))
        return ("complete", on_cnt, 0)

    def reload_library(self):
        if not self.plex.is_connected():
            self.artist_header.setText("Plex Not Connected")
            self.artist_list.clear()
            return

        self.artist_header.setText("Loading artists...")
        lib = self.current_library
        def worker():
            artists = self.plex.get_artists(lib)
            try:
                self.worker_signals.artists_loaded.emit(artists)
            except (RuntimeError, AttributeError):
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _on_artists_loaded(self, artists: List[PlexArtistSummary]):
        self.artists = artists
        self._update_filter_button_counts()
        self._filter_artists()

    def _on_search_changed(self, text: str):
        self._filter_artists()

    def _filter_artists(self):
        query = self.search_input.text().strip().lower()
        filtered = []
        for a in self.artists:
            if query and query not in a.name.lower():
                continue
            norm_art = normalize_music_key(a.name)
            ipod_cnt = self.ipod_artist_album_counts.get(norm_art, 0)
            total_cnt = a.album_count

            if self.filter_mode == "on_ipod" and ipod_cnt == 0:
                continue
            if self.filter_mode == "not_on_ipod" and total_cnt > 0 and ipod_cnt >= total_cnt:
                continue

            filtered.append(a)

        self.filtered_artists = filtered
        self._render_artists(self.filtered_artists)

    def _render_artists(self, artists: List[PlexArtistSummary]):
        current_artist_key = self.selected_artist.rating_key if self.selected_artist else None
        target_row = -1

        self.artist_list.blockSignals(True)
        self.artist_list.clear()
        self.artist_header.setText(f"Artists ({len(artists)})")

        for idx, a in enumerate(artists):
            if current_artist_key and a.rating_key == current_artist_key:
                target_row = idx

            pix = self.thumb_manager.get_thumbnail(a.thumb_url, self.plex.token, is_artist=True, size=44)
            norm_art = normalize_music_key(a.name)
            ipod_cnt = self.ipod_artist_album_counts.get(norm_art, 0)
            total_cnt = a.album_count

            if total_cnt > 0 and ipod_cnt >= total_cnt:
                badge = f"✓ {total_cnt} album{'s' if total_cnt != 1 else ''}"
                color = QColor("#a6e3a1")
            elif ipod_cnt > 0:
                badge = f"◐ {ipod_cnt}/{total_cnt} albums"
                color = QColor("#89dceb")
            else:
                badge = f"{total_cnt} album{'s' if total_cnt != 1 else ''}"
                color = QColor("#cdd6f4")

            item = QListWidgetItem(QIcon(pix), f"{a.name}\n{badge}")
            item.setForeground(color)
            item.setData(Qt.UserRole + 1, a.thumb_url)
            self.artist_list.addItem(item)

        self.artist_list.blockSignals(False)

        if target_row >= 0:
            self.artist_list.setCurrentRow(target_row)
        else:
            self.selected_artist = None
            self.selected_album = None
            self.sync_artist_btn.setEnabled(False)
            self.delete_artist_btn.setVisible(False)
            self.delete_artist_btn.setEnabled(False)
            self.album_list.clear()
            self.album_header.setText("Albums (0)")
            self.track_table.setRowCount(0)
            self.track_header.setText("Tracks (0)")

    def _on_artist_selected(self, row: int):
        if row < 0 or row >= len(self.filtered_artists):
            self.selected_artist = None
            self.sync_artist_btn.setEnabled(False)
            self.album_list.clear()
            return

        self.selected_artist = self.filtered_artists[row]
        self.sync_artist_btn.setEnabled(True)

        self.album_header.setText("Loading albums...")
        self.album_list.clear()
        art_key = self.selected_artist.rating_key
        def worker():
            albums = self.plex.get_artist_albums(art_key)
            self.worker_signals.albums_loaded.emit(art_key, albums)
        threading.Thread(target=worker, daemon=True).start()

    def _on_albums_loaded(self, artist_key: str, albums: List[PlexAlbumSummary]):
        if not self.selected_artist or self.selected_artist.rating_key != artist_key:
            return
        self.current_albums = albums
        self.album_header.setText(f"Albums ({len(albums)})")
        self._refresh_album_list_badges()

    def _refresh_album_list_badges(self):
        prev_selected_key = self.selected_album.rating_key if self.selected_album else None
        self.album_list.clear()
        is_grid = (self.album_view_mode == "grid")
        icon_size = 110 if is_grid else 56

        self.displayed_albums = []
        missing_count = 0
        for alb in self.current_albums:
            status, on_cnt, miss_cnt = self.get_album_ipod_status(alb.artist_name, alb.title, alb.track_count)
            if status != "complete":
                missing_count += 1
            if self.filter_mode == "on_ipod" and status == "none":
                continue
            if self.filter_mode == "not_on_ipod" and status == "complete":
                continue
            self.displayed_albums.append(alb)

        if len(self.displayed_albums) == len(self.current_albums):
            self.album_header.setText(f"Albums ({len(self.displayed_albums)})")
        else:
            self.album_header.setText(f"Albums ({len(self.displayed_albums)} of {len(self.current_albums)})")

        for alb in self.displayed_albums:
            yr_str = f" ({alb.year})" if alb.year else ""
            status, on_cnt, miss_cnt = self.get_album_ipod_status(alb.artist_name, alb.title, alb.track_count)

            pix = self.thumb_manager.get_thumbnail(alb.thumb_url, self.plex.token, is_artist=False, size=icon_size)

            if is_grid:
                if alb.rating_key == self.active_sync_album_key:
                    status_header = "● SYNCING\n"
                    color = QColor("#a6e3a1")
                elif alb.rating_key in self.queued_album_keys:
                    status_header = "⏱ QUEUED\n"
                    color = QColor("#cba6f7")
                elif status == "complete":
                    status_header = "✓\n"
                    color = QColor("#a6e3a1")
                elif status == "partial":
                    status_header = f"◐ {on_cnt}/{alb.track_count}\n"
                    color = QColor("#fab387")
                else:
                    status_header = ""
                    color = QColor("#cdd6f4")
                caption = f"{status_header}{alb.title}\n{yr_str.strip() or 'Album'}"
            else:
                if alb.rating_key == self.active_sync_album_key:
                    status_suffix = " • Syncing"
                    prefix = "● "
                    color = QColor("#a6e3a1")
                elif alb.rating_key in self.queued_album_keys:
                    status_suffix = " • Queued"
                    prefix = "⏱ "
                    color = QColor("#cba6f7")
                elif status == "complete":
                    status_suffix = ""
                    prefix = "✓ "
                    color = QColor("#a6e3a1")
                elif status == "partial":
                    status_suffix = f" ({on_cnt}/{alb.track_count})"
                    prefix = "◐ "
                    color = QColor("#fab387")
                else:
                    status_suffix = ""
                    prefix = ""
                    color = QColor("#cdd6f4")
                caption = f"{prefix}{alb.title}{yr_str}{status_suffix}\n{alb.track_count} tracks"

            item = QListWidgetItem(QIcon(pix), caption)
            item.setData(Qt.UserRole + 1, alb.thumb_url)
            if is_grid:
                item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)

            item.setForeground(color)
            self.album_list.addItem(item)

        # Update artist action buttons
        if self.selected_artist:
            norm_art = normalize_music_key(self.selected_artist.name)
            ipod_art_count = self.ipod_artist_album_counts.get(norm_art, 0)
            if ipod_art_count > 0:
                self.delete_artist_btn.setVisible(True)
                self.delete_artist_btn.setEnabled(True)
                self.delete_artist_btn.setText(f"Remove Artist ({ipod_art_count})")
            else:
                self.delete_artist_btn.setVisible(False)
                self.delete_artist_btn.setEnabled(False)

            if self.current_albums:
                self.sync_artist_btn.setEnabled(True)
                if missing_count == 0:
                    self.sync_artist_btn.setText("✓ Synced (Re-sync)")
                    self.sync_artist_btn.setStyleSheet("""
                        QPushButton { background-color: #45475a; color: #cdd6f4; font-weight: bold; }
                        QPushButton:hover { background-color: #585b70; }
                    """)
                elif missing_count < len(self.current_albums):
                    self.sync_artist_btn.setText(f"+ Add Missing ({missing_count})")
                    self.sync_artist_btn.setStyleSheet("""
                        QPushButton { background-color: #89b4fa; color: #11111b; font-weight: bold; }
                        QPushButton:hover { background-color: #b4befe; }
                    """)
                else:
                    self.sync_artist_btn.setText(f"+ Add All to iPod ({len(self.current_albums)})")
                    self.sync_artist_btn.setStyleSheet("""
                        QPushButton { background-color: #89b4fa; color: #11111b; font-weight: bold; }
                        QPushButton:hover { background-color: #b4befe; }
                    """)
            else:
                self.sync_artist_btn.setEnabled(False)

        # Preserve selected album if still displayed
        if prev_selected_key:
            match_idx = next((i for i, a in enumerate(self.displayed_albums) if a.rating_key == prev_selected_key), None)
            if match_idx is not None:
                self.selected_album = self.displayed_albums[match_idx]
                self.album_list.setCurrentRow(match_idx)
                self._update_album_actions()
            else:
                self.selected_album = None
                self._update_album_actions()
                self.track_table.setRowCount(0)
        else:
            self.selected_album = None
            self._update_album_actions()
            self.track_table.setRowCount(0)
        self.track_header.setText("Tracks (0)")

    def update_sync_queue_keys(self, queued_keys: Set[str], active_key: Optional[str] = None):
        self.queued_album_keys = set(queued_keys)
        self.active_sync_album_key = active_key
        self._update_album_actions()
        if self.current_albums:
            self._refresh_album_list_badges()

    def _update_album_actions(self):
        if not self.selected_album:
            self.sync_album_btn.setVisible(True)
            self.sync_album_btn.setEnabled(False)
            self.sync_album_btn.setText("+ Add to iPod")
            self.sync_album_btn.setStyleSheet("""
                QPushButton { background-color: #89b4fa; color: #11111b; font-weight: bold; padding: 6px 14px; }
                QPushButton:hover { background-color: #b4befe; }
                QPushButton:disabled { background-color: #313244; color: #585b70; }
            """)
            self.resync_album_btn.setVisible(False)
            self.resync_album_btn.setEnabled(False)
            self.delete_album_btn.setVisible(False)
            self.delete_album_btn.setEnabled(False)
            return

        # Check if currently active or in queue
        if self.selected_album.rating_key == self.active_sync_album_key:
            self.sync_album_btn.setVisible(True)
            self.sync_album_btn.setEnabled(False)
            self.sync_album_btn.setText("● Syncing Now...")
            self.sync_album_btn.setStyleSheet("""
                QPushButton { background-color: #313244; color: #a6e3a1; font-weight: bold; padding: 6px 14px; border-radius: 6px; }
            """)
            self.resync_album_btn.setVisible(False)
            self.delete_album_btn.setVisible(False)
            return

        if self.selected_album.rating_key in self.queued_album_keys:
            self.sync_album_btn.setVisible(True)
            self.sync_album_btn.setEnabled(False)
            self.sync_album_btn.setText("⏱ In Sync Queue")
            self.sync_album_btn.setStyleSheet("""
                QPushButton { background-color: #313244; color: #cba6f7; font-weight: bold; padding: 6px 14px; border-radius: 6px; }
            """)
            self.resync_album_btn.setVisible(False)
            self.delete_album_btn.setVisible(False)
            return

        status, on_cnt, miss_cnt = self.get_album_ipod_status(
            self.selected_album.artist_name, self.selected_album.title, self.selected_album.track_count
        )

        if status == "complete":
            self.sync_album_btn.setVisible(False)
            self.sync_album_btn.setEnabled(False)
            self.resync_album_btn.setVisible(True)
            self.resync_album_btn.setEnabled(True)
            self.resync_album_btn.setText("Re-sync Album")
            self.delete_album_btn.setVisible(True)
            self.delete_album_btn.setEnabled(True)
            self.delete_album_btn.setText("Remove from iPod")
        elif status == "partial":
            self.sync_album_btn.setVisible(True)
            self.sync_album_btn.setEnabled(True)
            self.sync_album_btn.setText(f"+ Add Missing ({miss_cnt} tracks)")
            self.sync_album_btn.setStyleSheet("""
                QPushButton { background-color: #fab387; color: #11111b; font-weight: bold; padding: 6px 14px; }
                QPushButton:hover { background-color: #f9e2af; }
            """)
            self.resync_album_btn.setVisible(True)
            self.resync_album_btn.setEnabled(True)
            self.resync_album_btn.setText("Re-sync Full Album")
            self.delete_album_btn.setVisible(True)
            self.delete_album_btn.setEnabled(True)
            self.delete_album_btn.setText(f"Remove from iPod ({on_cnt})")
        else:  # "none"
            self.sync_album_btn.setVisible(True)
            self.sync_album_btn.setEnabled(True)
            self.sync_album_btn.setText("+ Add to iPod")
            self.sync_album_btn.setStyleSheet("""
                QPushButton { background-color: #89b4fa; color: #11111b; font-weight: bold; padding: 6px 14px; }
                QPushButton:hover { background-color: #b4befe; }
            """)
            self.resync_album_btn.setVisible(False)
            self.resync_album_btn.setEnabled(False)
            self.delete_album_btn.setVisible(False)
            self.delete_album_btn.setEnabled(False)

    def _on_thumbnail_loaded(self, url: str, pixmap: QPixmap):
        for i in range(self.artist_list.count()):
            it = self.artist_list.item(i)
            if it.data(Qt.UserRole + 1) == url:
                it.setIcon(QIcon(pixmap))

        for i in range(self.album_list.count()):
            it = self.album_list.item(i)
            if it.data(Qt.UserRole + 1) == url:
                it.setIcon(QIcon(pixmap))

    def _on_album_selected(self, row: int):
        if row < 0 or row >= len(self.displayed_albums):
            self.selected_album = None
            self.current_tracks = []
            self._update_album_actions()
            self.track_table.setRowCount(0)
            self.track_header.setText("Tracks (0)")
            return

        self.selected_album = self.displayed_albums[row]
        self.current_tracks = []
        self._update_album_actions()

        self.track_header.setText("Loading tracks...")
        alb_key = self.selected_album.rating_key
        def worker():
            tracks = self.plex.get_album_tracks(alb_key)
            try:
                self.worker_signals.tracks_loaded.emit(alb_key, tracks)
            except (RuntimeError, AttributeError):
                pass
        threading.Thread(target=worker, daemon=True).start()

    def select_artist_and_album(self, artist_name: str, album_title: Optional[str] = None):
        """Programmatically select an artist (and optionally album) in the browser."""
        norm_art = normalize_music_key(artist_name)
        target_artist_row = -1
        for i, a in enumerate(self.displayed_artists):
            if normalize_music_key(a.name) == norm_art or norm_art in normalize_music_key(a.name):
                target_artist_row = i
                break

        if target_artist_row >= 0:
            self.artist_list.setCurrentRow(target_artist_row)
            if album_title:
                norm_alb = normalize_music_key(album_title)
                for j, alb in enumerate(self.displayed_albums):
                    if normalize_music_key(alb.title) == norm_alb or norm_alb in normalize_music_key(alb.title):
                        self.album_list.setCurrentRow(j)
                        break

    def _on_tracks_loaded(self, album_key: str, tracks: List[PlexTrackDetail]):
        if not self.selected_album or self.selected_album.rating_key != album_key:
            return
        self.current_tracks = tracks
        self._render_tracks_table(tracks)

    def _render_tracks_table(self, tracks: List[PlexTrackDetail]):
        if not self.selected_album:
            return
        total_size = sum(t.size_bytes for t in tracks)
        total_duration = sum(t.duration_ms for t in tracks)

        on_device_indices = set()
        for r, t in enumerate(tracks):
            if self._is_track_on_ipod(t):
                on_device_indices.add(r)

        on_count = len(on_device_indices)
        total_count = len(tracks)

        if on_count == total_count and total_count > 0:
            status_text = f"✓ {total_count}/{total_count}"
        elif on_count > 0:
            status_text = f"◐ {on_count}/{total_count}"
        else:
            status_text = f"0/{total_count} synced"

        self.track_header.setText(
            f"Tracks ({total_count}) • {status_text} • {format_duration(total_duration)} • {format_bytes(total_size)}"
        )
        self.track_table.setRowCount(total_count)
        for r, t in enumerate(tracks):
            is_on_device = (r in on_device_indices)

            disc_prefix = f"D{t.disc_number} " if t.disc_number > 1 else ""
            num_str = f"{disc_prefix}{t.track_number:02d}" if t.track_number > 0 else "-"
            num_item = QTableWidgetItem(num_str)
            num_item.setTextAlignment(Qt.AlignCenter)

            title_item = QTableWidgetItem(t.title)

            # Status column: visual icon badge, zero text!
            status_item = QTableWidgetItem()
            status_item.setTextAlignment(Qt.AlignCenter)
            if is_on_device:
                status_item.setIcon(self._icon_on_ipod)
                status_item.setToolTip("Synced")
                title_item.setForeground(QColor("#cdd6f4"))
            else:
                status_item.setIcon(self._icon_missing)
                status_item.setToolTip("Not Synced")
                title_item.setForeground(QColor("#7f849c"))

            dur_item = QTableWidgetItem(format_duration(t.duration_ms))
            dur_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            fmt_str = f"{t.container.upper()}" if t.container else ""
            if t.bitrate:
                fmt_str += f" ({t.bitrate} kbps)"
            fmt_item = QTableWidgetItem(fmt_str)

            size_item = QTableWidgetItem(format_bytes(t.size_bytes))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.track_table.setItem(r, 0, num_item)
            self.track_table.setItem(r, 1, title_item)
            self.track_table.setItem(r, 2, status_item)
            self.track_table.setItem(r, 3, dur_item)
            self.track_table.setItem(r, 4, fmt_item)
            self.track_table.setItem(r, 5, size_item)

    def _on_sync_album(self):
        if not self.selected_album:
            return
        status, on_cnt, miss_cnt = self.get_album_ipod_status(
            self.selected_album.artist_name, self.selected_album.title, self.selected_album.track_count
        )
        specific_keys = None
        if status == "partial" and self.current_tracks:
            missing_tracks = [t for t in self.current_tracks if not self._is_track_on_ipod(t)]
            if missing_tracks:
                specific_keys = {t.rating_key for t in missing_tracks}

        task = SyncTask(
            artist_name=self.selected_album.artist_name,
            album_title=self.selected_album.title,
            album_key=self.selected_album.rating_key,
            year=self.selected_album.year,
            thumb_url=self.selected_album.thumb_url,
            specific_track_keys=specific_keys,
            force_overwrite=False,
        )
        self.queued_album_keys.add(self.selected_album.rating_key)
        self._update_album_actions()
        if self.current_albums:
            self._refresh_album_list_badges()
        self.sync_album_requested.emit(task)

    def _on_resync_album(self):
        if not self.selected_album:
            return
        task = SyncTask(
            artist_name=self.selected_album.artist_name,
            album_title=self.selected_album.title,
            album_key=self.selected_album.rating_key,
            year=self.selected_album.year,
            thumb_url=self.selected_album.thumb_url,
            specific_track_keys=None,
            force_overwrite=True,
        )
        self.queued_album_keys.add(self.selected_album.rating_key)
        self._update_album_actions()
        if self.current_albums:
            self._refresh_album_list_badges()
        self.sync_album_requested.emit(task)

    def _sync_specific_tracks(self, tracks: List[PlexTrackDetail], force_overwrite: bool = False):
        if not self.selected_album or not tracks:
            return
        task = SyncTask(
            artist_name=self.selected_album.artist_name,
            album_title=self.selected_album.title,
            album_key=self.selected_album.rating_key,
            year=self.selected_album.year,
            thumb_url=self.selected_album.thumb_url,
            specific_track_keys={t.rating_key for t in tracks},
            force_overwrite=force_overwrite,
        )
        self.sync_album_requested.emit(task)

    def _on_track_table_context_menu(self, pos):
        if not self.selected_album or not self.current_tracks:
            return

        item_at_pos = self.track_table.itemAt(pos)
        selected_rows = sorted(set(index.row() for index in self.track_table.selectedIndexes()))

        if item_at_pos is not None:
            row_under_cursor = item_at_pos.row()
            if row_under_cursor not in selected_rows:
                self.track_table.selectRow(row_under_cursor)
                selected_rows = [row_under_cursor]

        if not selected_rows:
            return

        selected_tracks = [self.current_tracks[r] for r in selected_rows if r < len(self.current_tracks)]
        if not selected_tracks:
            return

        menu = QMenu(self)

        if len(selected_tracks) == 1:
            track = selected_tracks[0]
            is_on_dev = self._is_track_on_ipod(track)
            if is_on_dev:
                act = menu.addAction(f"Re-sync '{track.title}' to iPod")
                act.triggered.connect(lambda: self._sync_specific_tracks([track], force_overwrite=True))
            else:
                act = menu.addAction(f"+ Add '{track.title}' to iPod")
                act.triggered.connect(lambda: self._sync_specific_tracks([track], force_overwrite=False))
        else:
            act = menu.addAction(f"+ Add {len(selected_tracks)} Selected Tracks to iPod")
            act.triggered.connect(lambda: self._sync_specific_tracks(selected_tracks, force_overwrite=False))

        # Add All Missing Tracks option if applicable
        all_missing = [t for t in self.current_tracks if not self._is_track_on_ipod(t)]
        if all_missing and len(all_missing) != len(selected_tracks):
            menu.addSeparator()
            act_all_missing = menu.addAction(f"+ Add All Missing Tracks ({len(all_missing)}) to iPod")
            act_all_missing.triggered.connect(lambda: self._sync_specific_tracks(all_missing, force_overwrite=False))

        menu.addSeparator()
        act_resync_all = menu.addAction(f"Re-sync Entire Album ('{self.selected_album.title}')")
        act_resync_all.triggered.connect(self._on_resync_album)

        menu.exec(self.track_table.viewport().mapToGlobal(pos))

    def _on_sync_artist(self):
        if not self.selected_artist or not self.current_albums:
            return
        missing = [
            alb for alb in self.current_albums
            if self.get_album_ipod_status(alb.artist_name, alb.title, alb.track_count)[0] != "complete"
        ]
        to_sync = missing if missing else self.current_albums

        tasks = [
            SyncTask(
                artist_name=alb.artist_name,
                album_title=alb.title,
                album_key=alb.rating_key,
                year=alb.year,
                thumb_url=alb.thumb_url,
            )
            for alb in to_sync
        ]
        self.sync_artist_requested.emit(tasks)

    def _on_delete_album(self):
        if not self.selected_album:
            return
        reply = QMessageBox.question(
            self,
            "Remove Album from iPod",
            f"Are you sure you want to remove album '{self.selected_album.title}' by {self.selected_album.artist_name} from your iPod?\n\n"
            f"This will permanently delete the album files from the device.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.remove_album_requested.emit(self.selected_album.artist_name, self.selected_album.title)

    def _on_delete_artist(self):
        if not self.selected_artist:
            return
        norm_art = normalize_music_key(self.selected_artist.name)
        ipod_art_count = self.ipod_artist_album_counts.get(norm_art, 0)
        reply = QMessageBox.question(
            self,
            "Remove Artist from iPod",
            f"Are you sure you want to remove ALL {ipod_art_count} album(s) by '{self.selected_artist.name}' from your iPod?\n\n"
            f"This will permanently delete all music files for this artist from the device.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.remove_artist_requested.emit(self.selected_artist.name)

    def _on_clean_trash_clicked(self):
        reply = QMessageBox.question(
            self,
            "Clean iPod Trash",
            "Empty the .Trash-1000 folder on your iPod to reclaim deleted storage space?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.clean_trash_requested.emit()

