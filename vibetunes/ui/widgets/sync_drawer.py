"""Bottom drawer widget displaying active sync transfers, progress bar, speed, and queue."""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal, QTimer

from vibetunes.ui.widgets.storage_bar import format_bytes

class SyncDrawerWidget(QFrame):
    cancel_requested = Signal()
    view_queue_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SyncDrawer")
        self.setVisible(False)  # Hidden when idle
        self._queue_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(6)

        # Top row: Status title + Enqueue notice + View Queue button + Speed + Cancel
        top_row = QHBoxLayout()
        self.title_label = QLabel("Syncing to iPod...")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #89b4fa;")
        top_row.addWidget(self.title_label)

        self.notice_label = QLabel("")
        self.notice_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #a6e3a1; padding-left: 8px;")
        top_row.addWidget(self.notice_label)

        top_row.addStretch()

        self.view_queue_btn = QPushButton("☰ View Queue (0)")
        self.view_queue_btn.setToolTip("Open the Sync Queue to see active and upcoming transfers")
        self.view_queue_btn.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #89b4fa;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #45475a;
                color: #b4befe;
            }
        """)
        self.view_queue_btn.clicked.connect(self.view_queue_requested.emit)
        top_row.addWidget(self.view_queue_btn)

        self.speed_label = QLabel("")
        self.speed_label.setStyleSheet("font-size: 12px; color: #a6adc8; padding-left: 6px;")
        top_row.addWidget(self.speed_label)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton { background-color: #313244; color: #f38ba8; font-weight: bold; padding: 4px 10px; border-radius: 6px; }
            QPushButton:hover { background-color: #452430; }
        """)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        top_row.addWidget(self.cancel_btn)

        layout.addLayout(top_row)

        # Middle row: Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(12)
        layout.addWidget(self.progress_bar)

        # Bottom row: Current file / Album info + Queue status
        bottom_row = QHBoxLayout()
        self.file_label = QLabel("Preparing transfer...")
        self.file_label.setStyleSheet("font-size: 11px; color: #cdd6f4;")
        bottom_row.addWidget(self.file_label, stretch=2)

        self.queue_label = QLabel("")
        self.queue_label.setStyleSheet("font-size: 11px; color: #a6adc8;")
        bottom_row.addWidget(self.queue_label)

        layout.addLayout(bottom_row)

        self.setStyleSheet("""
            #SyncDrawer {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 8px;
            }
        """)

    def set_sync_active(self, active: bool):
        self.setVisible(active)
        if not active:
            self.progress_bar.setValue(0)
            self.speed_label.setText("")
            self.file_label.setText("")
            self.queue_label.setText("")
            self.notice_label.setText("")
            self._queue_count = 0
            self.view_queue_btn.setText("☰ View Queue (0)")

    def set_album_started(self, artist: str, album: str, current_idx: int, total_albums: int):
        self.setVisible(True)
        self.title_label.setText(f"Syncing: {artist} - {album} ({current_idx}/{total_albums})")

    def set_playlist_started(self, playlist_title: str, current_idx: int, total_items: int):
        self.setVisible(True)
        self.title_label.setText(f"Syncing Playlist: {playlist_title} ({current_idx}/{total_items})")

    def set_delete_started(self, description: str, current_idx: int, total_items: int):
        self.setVisible(True)
        self.title_label.setText(f"{description} ({current_idx}/{total_items})")
        self.file_label.setText("Removing files from iPod...")
        self.progress_bar.setValue(0)
        self.speed_label.setText("")

    def set_track_started(self, track_title: str, current_idx: int, total_tracks: int):
        self.file_label.setText(f"Track {current_idx}/{total_tracks}: {track_title}")
        self.progress_bar.setValue(0)

    def set_track_progress(self, bytes_done: int, bytes_total: int, bytes_per_sec: float):
        if bytes_total > 0:
            pct = int((bytes_done / bytes_total) * 100)
            self.progress_bar.setValue(pct)
            speed_str = f"{format_bytes(int(bytes_per_sec))}/s"
            self.speed_label.setText(f"{format_bytes(bytes_done)} / {format_bytes(bytes_total)} ({speed_str})")
        else:
            self.progress_bar.setValue(0)
            self.speed_label.setText(format_bytes(bytes_done))

    def set_queue_status(self, remaining: int):
        self._queue_count = remaining
        self.view_queue_btn.setText(f"☰ View Queue ({remaining})")
        if remaining > 0:
            self.queue_label.setText(f"{remaining} item{'s' if remaining > 1 else ''} waiting in queue")
        else:
            self.queue_label.setText("Last item in queue")

    def show_enqueue_notice(self, item_name: str, position: int):
        self.setVisible(True)
        self.notice_label.setText(f"✓ Added '{item_name}' to queue (#{position})")
        QTimer.singleShot(4000, lambda: self.notice_label.setText(""))
