"""Interactive Sync Queue Dialog for inspecting and managing upcoming sync tasks."""
from typing import List, Optional, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QProgressBar, QMessageBox
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, Signal

from vibetunes.ui.widgets.storage_bar import format_bytes

class SyncQueueDialog(QDialog):
    remove_task_requested = Signal(int)   # 0-based index of queued item to remove
    clear_queue_requested = Signal()
    cancel_all_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sync Queue - vibeTunes")
        self.resize(680, 520)
        self.setMinimumSize(540, 400)

        self._active_task: Optional[Any] = None
        self._queued_tasks: List[Any] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        # --- 1. Currently Syncing Card ---
        self.active_frame = QFrame()
        self.active_frame.setObjectName("ActiveFrame")
        self.active_frame.setStyleSheet("""
            #ActiveFrame {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 10px;
                padding: 12px;
            }
        """)
        active_layout = QVBoxLayout(self.active_frame)
        active_layout.setSpacing(8)

        # Active header row
        hdr_row = QHBoxLayout()
        self.active_badge = QLabel("● ACTIVE")
        self.active_badge.setStyleSheet("""
            background-color: #313244;
            color: #a6e3a1;
            font-size: 11px;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 8px;
        """)
        hdr_row.addWidget(self.active_badge)

        self.active_title_label = QLabel("No active transfer (Idle)")
        self.active_title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #cdd6f4;")
        hdr_row.addWidget(self.active_title_label, stretch=1)

        self.active_type_badge = QLabel("")
        self.active_type_badge.setStyleSheet("""
            background-color: #313244;
            color: #89b4fa;
            font-size: 11px;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 8px;
        """)
        self.active_type_badge.setVisible(False)
        hdr_row.addWidget(self.active_type_badge)

        active_layout.addLayout(hdr_row)

        # Current track & speed row
        sub_row = QHBoxLayout()
        self.active_track_label = QLabel("Waiting to begin...")
        self.active_track_label.setStyleSheet("font-size: 12px; color: #a6adc8;")
        sub_row.addWidget(self.active_track_label, stretch=1)

        self.active_speed_label = QLabel("")
        self.active_speed_label.setStyleSheet("font-size: 11px; color: #a6adc8;")
        sub_row.addWidget(self.active_speed_label)

        active_layout.addLayout(sub_row)

        # Progress bar
        self.active_progress = QProgressBar()
        self.active_progress.setRange(0, 100)
        self.active_progress.setValue(0)
        self.active_progress.setFixedHeight(12)
        active_layout.addWidget(self.active_progress)

        layout.addWidget(self.active_frame)

        # --- 2. Upcoming Queue Section ---
        queue_header_row = QHBoxLayout()
        self.queue_header_label = QLabel("Upcoming in Queue (0)")
        self.queue_header_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #cdd6f4;")
        queue_header_row.addWidget(self.queue_header_label)

        queue_header_row.addStretch()

        self.clear_queue_btn = QPushButton("Clear Queue")
        self.clear_queue_btn.setToolTip("Remove all pending items from queue (keeps active download running)")
        self.clear_queue_btn.setEnabled(False)
        self.clear_queue_btn.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #f38ba8;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #452430;
            }
            QPushButton:disabled {
                background-color: #1e1e2e;
                color: #585b70;
            }
        """)
        self.clear_queue_btn.clicked.connect(self._on_clear_queue_clicked)
        queue_header_row.addWidget(self.clear_queue_btn)

        layout.addLayout(queue_header_row)

        # Table for queued tasks
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(5)
        self.queue_table.setHorizontalHeaderLabels(["#", "Type", "Title / Artist", "Details", "Action"])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.queue_table.setColumnWidth(0, 44)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.queue_table.setColumnWidth(1, 80)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.queue_table.setColumnWidth(4, 80)
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.queue_table.setSelectionMode(QTableWidget.SingleSelection)
        self.queue_table.setAlternatingRowColors(True)

        layout.addWidget(self.queue_table, stretch=1)

        # Empty state label (shown when queue is empty)
        self.empty_label = QLabel("No items waiting in queue.\nWhen you add albums or playlists while syncing, they will appear here.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #6c7086; font-size: 13px; padding: 20px;")
        layout.addWidget(self.empty_label)

        # --- 3. Bottom Button Row ---
        bottom_row = QHBoxLayout()

        self.cancel_all_btn = QPushButton("Cancel Entire Sync")
        self.cancel_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #f38ba8;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #452430;
            }
        """)
        self.cancel_all_btn.clicked.connect(self._on_cancel_all_clicked)
        bottom_row.addWidget(self.cancel_all_btn)

        bottom_row.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #11111b;
                font-weight: bold;
                padding: 6px 20px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
        """)
        self.close_btn.clicked.connect(self.accept)
        bottom_row.addWidget(self.close_btn)

        layout.addLayout(bottom_row)

        self._apply_empty_state(True)

    def _apply_empty_state(self, is_empty: bool):
        self.queue_table.setVisible(not is_empty)
        self.empty_label.setVisible(is_empty)
        self.clear_queue_btn.setEnabled(not is_empty)

    def update_queue(self, queued_tasks: List[Any]):
        """Updates the table of upcoming queued tasks."""
        self._queued_tasks = list(queued_tasks)
        count = len(self._queued_tasks)
        self.queue_header_label.setText(f"Upcoming in Queue ({count})")

        if count == 0:
            self.queue_table.setRowCount(0)
            self._apply_empty_state(True)
            return

        self._apply_empty_state(False)
        self.queue_table.setRowCount(count)

        for i, task in enumerate(self._queued_tasks):
            # 0: Rank #1, #2...
            rank_item = QTableWidgetItem(f"#{i+1}")
            rank_item.setTextAlignment(Qt.AlignCenter)
            rank_item.setFlags(rank_item.flags() & ~Qt.ItemIsEditable)

            # 1: Type badge
            type_label = getattr(task, "item_type_label", "Item")
            type_item = QTableWidgetItem(type_label)
            type_item.setTextAlignment(Qt.AlignCenter)
            if type_label == "Playlist":
                type_item.setForeground(Qt.GlobalColor.cyan)
            elif type_label == "Delete":
                type_item.setForeground(QColor("#f38ba8"))
            else:
                type_item.setForeground(Qt.GlobalColor.white)
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)

            # 2: Title & Artist
            title_text = getattr(task, "display_title", str(task))
            title_item = QTableWidgetItem(title_text)
            title_item.setFlags(title_item.flags() & ~Qt.ItemIsEditable)

            # 3: Details
            details_text = getattr(task, "details_label", "")
            details_item = QTableWidgetItem(details_text)
            details_item.setForeground(Qt.GlobalColor.gray)
            details_item.setFlags(details_item.flags() & ~Qt.ItemIsEditable)

            # 4: Action button
            remove_btn = QPushButton("✕ Remove")
            remove_btn.setStyleSheet("""
                QPushButton {
                    background-color: #313244;
                    color: #f38ba8;
                    font-size: 11px;
                    padding: 2px 6px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #452430;
                }
            """)
            remove_btn.clicked.connect(lambda checked=False, idx=i: self._on_remove_task_clicked(idx))

            self.queue_table.setItem(i, 0, rank_item)
            self.queue_table.setItem(i, 1, type_item)
            self.queue_table.setItem(i, 2, title_item)
            self.queue_table.setItem(i, 3, details_item)
            self.queue_table.setCellWidget(i, 4, remove_btn)

    def set_active_state(self, status: dict):
        """Immediately sets the active card state from a worker status snapshot."""
        task = status.get("task")
        if not task or status.get("is_finished", False):
            self.set_sync_finished()
            return

        item_idx = status.get("item_idx", 1)
        total_items = status.get("total_items", 1)

        from vibetunes.core.sync_engine import DeleteTask, SyncPlaylistTask

        if isinstance(task, DeleteTask):
            self.set_active_delete(task.display_title, item_idx, total_items)
        elif isinstance(task, SyncPlaylistTask):
            self.set_active_playlist(task.playlist_title, item_idx, total_items)
        else:
            artist = getattr(task, "artist_name", "")
            album = getattr(task, "album_title", "")
            self.set_active_album(artist, album, item_idx, total_items)

        track_title = status.get("track_title")
        track_idx = status.get("track_idx", 0)
        total_tracks = status.get("total_tracks", 0)
        if track_title:
            if total_tracks > 0:
                self.active_track_label.setText(f"Track {track_idx}/{total_tracks}: {track_title}")
            else:
                self.active_track_label.setText(track_title)

        bytes_done = status.get("bytes_done", 0)
        bytes_total = status.get("bytes_total", 0)
        speed = status.get("speed", 0.0)
        if bytes_total > 0 or bytes_done > 0:
            self.set_track_progress(bytes_done, bytes_total, speed)

    def set_active_delete(self, description: str, current_idx: int, total_items: int):
        self.active_badge.setText("● DELETING")
        self.active_badge.setStyleSheet("background-color: #313244; color: #f38ba8; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 8px;")
        self.active_title_label.setText(f"{description} ({current_idx}/{total_items})")
        self.active_type_badge.setText("Delete")
        self.active_type_badge.setStyleSheet("background-color: #313244; color: #f38ba8; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 8px;")
        self.active_type_badge.setVisible(True)
        self.active_track_label.setText("Removing files from iPod...")
        self.active_speed_label.setText("")
        self.active_progress.setValue(0)

    def set_active_album(self, artist: str, album: str, current_idx: int, total_items: int):
        self.active_badge.setText("● ACTIVE")
        self.active_badge.setStyleSheet("background-color: #313244; color: #a6e3a1; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 8px;")
        self.active_title_label.setText(f"{artist} - {album} ({current_idx}/{total_items})")
        self.active_type_badge.setText("Album")
        self.active_type_badge.setVisible(True)
        self.active_track_label.setText("Starting album transfer...")
        self.active_progress.setValue(0)

    def set_active_playlist(self, playlist_title: str, current_idx: int, total_items: int):
        self.active_badge.setText("● ACTIVE")
        self.active_badge.setStyleSheet("background-color: #313244; color: #a6e3a1; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 8px;")
        self.active_title_label.setText(f"Playlist: {playlist_title} ({current_idx}/{total_items})")
        self.active_type_badge.setText("Playlist")
        self.active_type_badge.setVisible(True)
        self.active_track_label.setText("Resolving tracks...")
        self.active_progress.setValue(0)

    def set_track_started(self, track_title: str, track_idx: int, total_tracks: int):
        self.active_track_label.setText(f"Track {track_idx}/{total_tracks}: {track_title}")
        self.active_progress.setValue(0)

    def set_track_progress(self, bytes_done: int, bytes_total: int, bytes_per_sec: float):
        if bytes_total > 0:
            pct = int((bytes_done / bytes_total) * 100)
            self.active_progress.setValue(pct)
            speed_str = f"{format_bytes(int(bytes_per_sec))}/s"
            self.active_speed_label.setText(f"{format_bytes(bytes_done)} / {format_bytes(bytes_total)} ({speed_str})")
        else:
            self.active_progress.setValue(0)
            self.active_speed_label.setText(format_bytes(bytes_done))

    def set_sync_finished(self):
        self.active_badge.setText("IDLE")
        self.active_badge.setStyleSheet("background-color: #313244; color: #a6adc8; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 8px;")
        self.active_title_label.setText("No active transfer (Idle)")
        self.active_type_badge.setVisible(False)
        self.active_track_label.setText("Sync complete.")
        self.active_speed_label.setText("")
        self.active_progress.setValue(0)
        self.update_queue([])

    def _on_remove_task_clicked(self, idx: int):
        if 0 <= idx < len(self._queued_tasks):
            self.remove_task_requested.emit(idx)

    def _on_clear_queue_clicked(self):
        self.clear_queue_requested.emit()

    def _on_cancel_all_clicked(self):
        self.cancel_all_requested.emit()
        self.accept()
