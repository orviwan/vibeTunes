"""Storage Analyzer Dialog showing ranked views of the largest files, albums, and artists on iPod."""
from pathlib import Path
from typing import List, Optional, Dict, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QWidget,
    QProgressBar, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from vibestunes.core.ipod_scanner import (
    iPodArtist, iPodAlbum, iPodTrack, open_folder
)
from vibestunes.ui.widgets.storage_bar import format_bytes

class StorageAnalyzerDialog(QDialog):
    delete_album_requested = Signal(str, str)  # artist_name, album_title
    delete_artist_requested = Signal(str)      # artist_name
    show_album_in_library = Signal(str, str)   # artist_name, album_title
    show_artist_in_library = Signal(str)       # artist_name
    refresh_requested = Signal()

    def __init__(self, ipod_artists: List[iPodArtist], mount_point: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("iPod Storage Inspector — Largest Files & Albums")
        self.resize(880, 600)
        self.setMinimumSize(700, 460)

        self.ipod_artists = list(ipod_artists)
        self.mount_point = mount_point

        # Pre-compute flattened lists
        self.all_albums: List[Dict[str, Any]] = []
        self.all_tracks: List[Dict[str, Any]] = []
        self.all_artists: List[Dict[str, Any]] = []

        self._build_data()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # --- Top Header & Search Filter ---
        top_row = QHBoxLayout()
        title_label = QLabel("Storage Inspector")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa;")
        top_row.addWidget(title_label)

        top_row.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Filter by name, artist, album, or extension...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedWidth(320)
        self.search_input.textChanged.connect(self._on_search_changed)
        top_row.addWidget(self.search_input)

        layout.addLayout(top_row)

        # --- Tabs: Albums | Files | Artists ---
        self.tabs = QTabWidget()

        # Tab 1: Albums Table
        self.albums_table = self._create_table(["#", "Album Title", "Artist", "Tracks", "Year", "Total Size", "Formats", "Actions"])
        self.albums_table.setColumnWidth(0, 44)
        self.albums_table.setColumnWidth(3, 60)
        self.albums_table.setColumnWidth(4, 55)
        self.albums_table.setColumnWidth(5, 95)
        self.albums_table.setColumnWidth(6, 75)
        self.tabs.addTab(self.albums_table, f"💿 Largest Albums ({len(self.all_albums)})")

        # Tab 2: Individual Files Table
        self.tracks_table = self._create_table(["#", "Track Title", "Artist", "Album", "File Size", "Ext", "Actions"])
        self.tracks_table.setColumnWidth(0, 44)
        self.tracks_table.setColumnWidth(4, 95)
        self.tracks_table.setColumnWidth(5, 55)
        self.tabs.addTab(self.tracks_table, f"🎵 Largest Audio Files ({len(self.all_tracks)})")

        # Tab 3: Artists Table
        self.artists_table = self._create_table(["#", "Artist Name", "Albums", "Total Tracks", "Disk Footprint", "Actions"])
        self.artists_table.setColumnWidth(0, 44)
        self.artists_table.setColumnWidth(2, 65)
        self.artists_table.setColumnWidth(3, 85)
        self.artists_table.setColumnWidth(4, 110)
        self.tabs.addTab(self.artists_table, f"👤 Largest Artists ({len(self.all_artists)})")

        layout.addWidget(self.tabs, stretch=1)

        # --- Bottom Summary & Close Row ---
        bottom_row = QHBoxLayout()
        self.summary_label = QLabel(self._generate_summary_text())
        self.summary_label.setStyleSheet("font-size: 12px; color: #a6adc8;")
        bottom_row.addWidget(self.summary_label, stretch=1)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                font-weight: bold;
                padding: 6px 20px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """)
        close_btn.clicked.connect(self.accept)
        bottom_row.addWidget(close_btn)

        layout.addLayout(bottom_row)

        self._populate_all()

    def _create_table(self, headers: List[str]) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        return table

    def _build_data(self):
        self.all_albums.clear()
        self.all_tracks.clear()
        self.all_artists.clear()

        for art in self.ipod_artists:
            total_art_tracks = 0
            for alb in art.albums:
                formats = sorted({t.path.suffix.upper().replace(".", "") for t in alb.tracks if getattr(t, "path", None) and t.path.suffix})
                fmt_str = ", ".join(formats) if formats else "FLAC"

                alb_data = {
                    "title": alb.title,
                    "artist_name": alb.artist_name or art.name,
                    "size_bytes": alb.total_size_bytes,
                    "track_count": alb.track_count,
                    "year": alb.year,
                    "path": alb.path,
                    "formats": fmt_str,
                }
                self.all_albums.append(alb_data)

                for trk in alb.tracks:
                    total_art_tracks += 1
                    ext_str = trk.path.suffix.lower() if getattr(trk, "path", None) else ""
                    trk_data = {
                        "title": trk.title or trk.filename,
                        "filename": trk.filename,
                        "artist_name": alb.artist_name or art.name,
                        "album_title": alb.title,
                        "size_bytes": trk.size_bytes,
                        "ext": ext_str,
                        "path": trk.path,
                    }
                    self.all_tracks.append(trk_data)

            self.all_artists.append({
                "name": art.name,
                "album_count": len(art.albums),
                "track_count": total_art_tracks,
                "size_bytes": art.total_size_bytes,
                "path": art.path,
            })

        # Sort descending by size
        self.all_albums.sort(key=lambda a: a["size_bytes"], reverse=True)
        self.all_tracks.sort(key=lambda t: t["size_bytes"], reverse=True)
        self.all_artists.sort(key=lambda a: a["size_bytes"], reverse=True)

    def _generate_summary_text(self) -> str:
        total_bytes = sum(a["size_bytes"] for a in self.all_artists)
        return (
            f"Total on iPod: {format_bytes(total_bytes)} • "
            f"{len(self.all_artists)} artists • {len(self.all_albums)} albums • {len(self.all_tracks)} tracks"
        )

    def update_data(self, ipod_artists: List[iPodArtist]):
        self.ipod_artists = list(ipod_artists)
        self._build_data()
        self.tabs.setTabText(0, f"💿 Largest Albums ({len(self.all_albums)})")
        self.tabs.setTabText(1, f"🎵 Largest Audio Files ({len(self.all_tracks)})")
        self.tabs.setTabText(2, f"👤 Largest Artists ({len(self.all_artists)})")
        self.summary_label.setText(self._generate_summary_text())
        self._populate_all()

    def _on_search_changed(self, text: str):
        self._populate_all()

    def _populate_all(self):
        query = self.search_input.text().strip().lower()
        self._populate_albums(query)
        self._populate_tracks(query)
        self._populate_artists(query)

    def _populate_albums(self, query: str):
        filtered = [
            a for a in self.all_albums
            if not query or (
                query in a["title"].lower() or
                query in a["artist_name"].lower() or
                query in a["formats"].lower()
            )
        ]
        self.albums_table.setRowCount(len(filtered))

        for i, alb in enumerate(filtered):
            # Rank
            rank_item = QTableWidgetItem(f"#{i+1}")
            rank_item.setTextAlignment(Qt.AlignCenter)
            rank_item.setFlags(rank_item.flags() & ~Qt.ItemIsEditable)

            # Title
            title_item = QTableWidgetItem(alb["title"])
            title_item.setFlags(title_item.flags() & ~Qt.ItemIsEditable)

            # Artist
            art_item = QTableWidgetItem(alb["artist_name"])
            art_item.setFlags(art_item.flags() & ~Qt.ItemIsEditable)

            # Tracks
            trks_item = QTableWidgetItem(str(alb["track_count"]))
            trks_item.setTextAlignment(Qt.AlignCenter)
            trks_item.setFlags(trks_item.flags() & ~Qt.ItemIsEditable)

            # Year
            yr_str = str(alb["year"]) if alb["year"] else "—"
            yr_item = QTableWidgetItem(yr_str)
            yr_item.setTextAlignment(Qt.AlignCenter)
            yr_item.setFlags(yr_item.flags() & ~Qt.ItemIsEditable)

            # Size
            size_item = QTableWidgetItem(format_bytes(alb["size_bytes"]))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size_item.setForeground(QColor("#a6e3a1"))
            size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)

            # Formats
            fmt_item = QTableWidgetItem(alb["formats"])
            fmt_item.setTextAlignment(Qt.AlignCenter)
            fmt_item.setForeground(QColor("#89dceb"))
            fmt_item.setFlags(fmt_item.flags() & ~Qt.ItemIsEditable)

            # Actions container
            action_widget = QWidget()
            act_layout = QHBoxLayout(action_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(4)

            jump_btn = QPushButton("Library")
            jump_btn.setToolTip("View this album in Music Library")
            jump_btn.setStyleSheet("QPushButton { background-color: #313244; color: #89b4fa; font-size: 11px; padding: 2px 6px; border-radius: 4px; } QPushButton:hover { background-color: #45475a; }")
            jump_btn.clicked.connect(lambda chk=False, a=alb: self._on_jump_album(a))
            act_layout.addWidget(jump_btn)

            open_btn = QPushButton("Folder")
            open_btn.setToolTip("Open album folder in file manager")
            open_btn.setStyleSheet("QPushButton { background-color: #313244; color: #cdd6f4; font-size: 11px; padding: 2px 6px; border-radius: 4px; } QPushButton:hover { background-color: #45475a; }")
            open_btn.clicked.connect(lambda chk=False, p=alb["path"]: open_folder(p))
            act_layout.addWidget(open_btn)

            del_btn = QPushButton("✕")
            del_btn.setToolTip("Delete album from iPod to free space")
            del_btn.setStyleSheet("QPushButton { background-color: #313244; color: #f38ba8; font-weight: bold; font-size: 11px; padding: 2px 6px; border-radius: 4px; } QPushButton:hover { background-color: #452430; }")
            del_btn.clicked.connect(lambda chk=False, a=alb: self._on_delete_album(a))
            act_layout.addWidget(del_btn)

            self.albums_table.setItem(i, 0, rank_item)
            self.albums_table.setItem(i, 1, title_item)
            self.albums_table.setItem(i, 2, art_item)
            self.albums_table.setItem(i, 3, trks_item)
            self.albums_table.setItem(i, 4, yr_item)
            self.albums_table.setItem(i, 5, size_item)
            self.albums_table.setItem(i, 6, fmt_item)
            self.albums_table.setCellWidget(i, 7, action_widget)

    def _populate_tracks(self, query: str):
        filtered = [
            t for t in self.all_tracks
            if not query or (
                query in t["title"].lower() or
                query in t["artist_name"].lower() or
                query in t["album_title"].lower() or
                query in t["ext"]
            )
        ]
        self.tracks_table.setRowCount(len(filtered))

        for i, trk in enumerate(filtered):
            rank_item = QTableWidgetItem(f"#{i+1}")
            rank_item.setTextAlignment(Qt.AlignCenter)
            rank_item.setFlags(rank_item.flags() & ~Qt.ItemIsEditable)

            title_item = QTableWidgetItem(trk["title"])
            title_item.setFlags(title_item.flags() & ~Qt.ItemIsEditable)

            art_item = QTableWidgetItem(trk["artist_name"])
            art_item.setFlags(art_item.flags() & ~Qt.ItemIsEditable)

            alb_item = QTableWidgetItem(trk["album_title"])
            alb_item.setFlags(alb_item.flags() & ~Qt.ItemIsEditable)

            size_item = QTableWidgetItem(format_bytes(trk["size_bytes"]))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size_item.setForeground(QColor("#a6e3a1"))
            size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)

            ext_item = QTableWidgetItem(trk["ext"].upper().replace(".", ""))
            ext_item.setTextAlignment(Qt.AlignCenter)
            ext_item.setForeground(QColor("#89dceb"))
            ext_item.setFlags(ext_item.flags() & ~Qt.ItemIsEditable)

            action_widget = QWidget()
            act_layout = QHBoxLayout(action_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(4)

            jump_btn = QPushButton("Library")
            jump_btn.setStyleSheet("QPushButton { background-color: #313244; color: #89b4fa; font-size: 11px; padding: 2px 6px; border-radius: 4px; } QPushButton:hover { background-color: #45475a; }")
            jump_btn.clicked.connect(lambda chk=False, t=trk: self.show_album_in_library.emit(t["artist_name"], t["album_title"]))
            act_layout.addWidget(jump_btn)

            open_btn = QPushButton("Folder")
            open_btn.setStyleSheet("QPushButton { background-color: #313244; color: #cdd6f4; font-size: 11px; padding: 2px 6px; border-radius: 4px; } QPushButton:hover { background-color: #45475a; }")
            open_btn.clicked.connect(lambda chk=False, p=trk["path"]: open_folder(p.parent if p.is_file() else p))
            act_layout.addWidget(open_btn)

            self.tracks_table.setItem(i, 0, rank_item)
            self.tracks_table.setItem(i, 1, title_item)
            self.tracks_table.setItem(i, 2, art_item)
            self.tracks_table.setItem(i, 3, alb_item)
            self.tracks_table.setItem(i, 4, size_item)
            self.tracks_table.setItem(i, 5, ext_item)
            self.tracks_table.setCellWidget(i, 6, action_widget)

    def _populate_artists(self, query: str):
        filtered = [
            a for a in self.all_artists
            if not query or query in a["name"].lower()
        ]
        self.artists_table.setRowCount(len(filtered))

        for i, art in enumerate(filtered):
            rank_item = QTableWidgetItem(f"#{i+1}")
            rank_item.setTextAlignment(Qt.AlignCenter)
            rank_item.setFlags(rank_item.flags() & ~Qt.ItemIsEditable)

            name_item = QTableWidgetItem(art["name"])
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)

            albs_item = QTableWidgetItem(str(art["album_count"]))
            albs_item.setTextAlignment(Qt.AlignCenter)
            albs_item.setFlags(albs_item.flags() & ~Qt.ItemIsEditable)

            trks_item = QTableWidgetItem(str(art["track_count"]))
            trks_item.setTextAlignment(Qt.AlignCenter)
            trks_item.setFlags(trks_item.flags() & ~Qt.ItemIsEditable)

            size_item = QTableWidgetItem(format_bytes(art["size_bytes"]))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size_item.setForeground(QColor("#a6e3a1"))
            size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)

            action_widget = QWidget()
            act_layout = QHBoxLayout(action_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(4)

            jump_btn = QPushButton("Library")
            jump_btn.setStyleSheet("QPushButton { background-color: #313244; color: #89b4fa; font-size: 11px; padding: 2px 6px; border-radius: 4px; } QPushButton:hover { background-color: #45475a; }")
            jump_btn.clicked.connect(lambda chk=False, a=art: self.show_artist_in_library.emit(a["name"]))
            act_layout.addWidget(jump_btn)

            open_btn = QPushButton("Folder")
            open_btn.setStyleSheet("QPushButton { background-color: #313244; color: #cdd6f4; font-size: 11px; padding: 2px 6px; border-radius: 4px; } QPushButton:hover { background-color: #45475a; }")
            open_btn.clicked.connect(lambda chk=False, p=art["path"]: open_folder(p))
            act_layout.addWidget(open_btn)

            del_btn = QPushButton("✕")
            del_btn.setToolTip("Delete all albums of this artist from iPod")
            del_btn.setStyleSheet("QPushButton { background-color: #313244; color: #f38ba8; font-weight: bold; font-size: 11px; padding: 2px 6px; border-radius: 4px; } QPushButton:hover { background-color: #452430; }")
            del_btn.clicked.connect(lambda chk=False, a=art: self._on_delete_artist(a))
            act_layout.addWidget(del_btn)

            self.artists_table.setItem(i, 0, rank_item)
            self.artists_table.setItem(i, 1, name_item)
            self.artists_table.setItem(i, 2, albs_item)
            self.artists_table.setItem(i, 3, trks_item)
            self.artists_table.setItem(i, 4, size_item)
            self.artists_table.setCellWidget(i, 5, action_widget)

    def _on_jump_album(self, alb: Dict[str, Any]):
        self.show_album_in_library.emit(alb["artist_name"], alb["title"])
        self.accept()

    def _on_delete_album(self, alb: Dict[str, Any]):
        self.delete_album_requested.emit(alb["artist_name"], alb["title"])

    def _on_delete_artist(self, art: Dict[str, Any]):
        self.delete_artist_requested.emit(art["name"])
