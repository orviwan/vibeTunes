"""Dialog to preview and execute non-destructive file and folder alignment with Plex naming conventions."""
import threading
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QMessageBox, QWidget, QFrame
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QColor, QIcon, QFont

from vibestunes.core.plex_client import PlexManager
from vibestunes.core.naming_sync import (
    RenameProposal, inspect_ipod_naming_alignment, apply_naming_alignment
)

class WorkerSignals(QObject):
    progress = Signal(int, str)
    scan_finished = Signal(list)
    apply_finished = Signal(int, list)

class NamingSyncDialog(QDialog):
    alignment_completed = Signal(int)

    def __init__(
        self,
        ipod_mount: str,
        plex: PlexManager,
        library_name: str,
        parent: Optional[QWidget] = None,
        auto_scan: bool = True,
    ):
        super().__init__(parent)
        self.ipod_mount = ipod_mount
        self.plex = plex
        self.library_name = library_name
        self.auto_scan = auto_scan
        self.proposals: List[RenameProposal] = []
        self._scan_thread: Optional[threading.Thread] = None
        self.signals = WorkerSignals()
        self.signals.progress.connect(self._on_progress)
        self.signals.scan_finished.connect(self._on_scan_finished)
        self.signals.apply_finished.connect(self._on_apply_finished)

        self.setWindowTitle("vibesTunes — Align iPod File & Folder Naming with Plex")
        self.resize(900, 560)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QLabel { color: #cdd6f4; }
            QTableWidget {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 8px;
                gridline-color: #313244;
                color: #cdd6f4;
            }
            QHeaderView::section {
                background-color: #313244;
                color: #cdd6f4;
                font-weight: bold;
                padding: 6px;
                border: none;
            }
            QProgressBar {
                background-color: #313244;
                border-radius: 6px;
                text-align: center;
                color: #cdd6f4;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #89b4fa;
                border-radius: 6px;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #45475a; }
            QPushButton:disabled { background-color: #181825; color: #585b70; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header banner
        header_layout = QVBoxLayout()
        title = QLabel("Align iPod File & Folder Naming with Plex")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #89b4fa;")
        header_layout.addWidget(title)

        banner = QFrame()
        banner.setStyleSheet("background-color: #181825; border: 1px solid #45475a; border-radius: 8px; padding: 10px;")
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(10, 8, 10, 8)
        info_lbl = QLabel(
            "🛡️ <b>Strict Non-Destructive Operation</b>: Album folders and tracks on your iPod will be renamed "
            "in-place to match the exact file and folder naming convention from your Plex server.<br>"
            "<b>No music files or folders are ever deleted.</b>"
        )
        info_lbl.setWordWrap(True)
        banner_layout.addWidget(info_lbl)
        header_layout.addWidget(banner)
        layout.addLayout(header_layout)

        # Status / Summary
        self.status_lbl = QLabel("Comparing iPod folders with Plex file and folder structure...")
        self.status_lbl.setStyleSheet("font-size: 13px; color: #a6adc8;")
        layout.addWidget(self.status_lbl)

        # Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Artist", "Album (Plex)", "Current on iPod", "Target (Plex Convention)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 140)
        self.table.setColumnWidth(1, 180)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        layout.addWidget(self.progress_bar)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.apply_btn = QPushButton("Align Names Now")
        self.apply_btn.setEnabled(False)
        self.apply_btn.setStyleSheet("""
            QPushButton { background-color: #89b4fa; color: #11111b; font-weight: bold; }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton:disabled { background-color: #313244; color: #585b70; }
        """)
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        btn_layout.addWidget(self.apply_btn)

        layout.addLayout(btn_layout)

        # Start scanning in background
        if self.auto_scan:
            self._start_scan()

    def _start_scan(self):
        self.status_lbl.setText("Scanning iPod and comparing against Plex file/folder conventions...")
        self.progress_bar.setValue(0)
        self.apply_btn.setEnabled(False)

        def worker():
            proposals = inspect_ipod_naming_alignment(
                self.ipod_mount,
                self.plex,
                self.library_name,
                progress_callback=lambda pct, msg: self.signals.progress.emit(pct, msg)
            )
            self.signals.scan_finished.emit(proposals)

        self._scan_thread = threading.Thread(target=worker, daemon=True)
        self._scan_thread.start()

    def _on_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.status_lbl.setText(msg)

    def _on_scan_finished(self, proposals: List[RenameProposal]):
        self.proposals = proposals
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)

        if not proposals:
            self.status_lbl.setText("✓ All iPod folders and files already follow Plex file/folder naming conventions!")
            self.status_lbl.setStyleSheet("font-size: 13px; color: #a6e3a1; font-weight: bold;")
            self.cancel_btn.setText("Close")
            return

        self.status_lbl.setText(
            f"Found {len(proposals)} album folder{'s' if len(proposals) != 1 else ''} to rename to match Plex conventions:"
        )
        self.status_lbl.setStyleSheet("font-size: 13px; color: #fab387; font-weight: bold;")
        self.apply_btn.setText(f"Rename {len(proposals)} Album{'s' if len(proposals) != 1 else ''}")
        self.apply_btn.setEnabled(True)

        self.table.setRowCount(len(proposals))
        for r, prop in enumerate(proposals):
            art_item = QTableWidgetItem(prop.artist_name)
            alb_item = QTableWidgetItem(prop.album_title)

            cur_str = f"{prop.current_path.name} ({prop.item_count} tracks)"
            cur_item = QTableWidgetItem(cur_str)
            cur_item.setForeground(QColor("#f38ba8"))

            tgt_str = f"{prop.target_path.name}"
            tgt_item = QTableWidgetItem(tgt_str)
            tgt_item.setForeground(QColor("#a6e3a1"))

            self.table.setItem(r, 0, art_item)
            self.table.setItem(r, 1, alb_item)
            self.table.setItem(r, 2, cur_item)
            self.table.setItem(r, 3, tgt_item)

    def _on_apply_clicked(self):
        self.apply_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_lbl.setText("Applying non-destructive renames on iPod...")

        proposals = list(self.proposals)
        mount_p = Path(self.ipod_mount) if self.ipod_mount else None
        def worker():
            renamed_cnt, errors = apply_naming_alignment(
                proposals,
                ipod_mount=mount_p,
                progress_callback=lambda pct, msg: self.signals.progress.emit(pct, msg)
            )
            self.signals.apply_finished.emit(renamed_cnt, errors)

        threading.Thread(target=worker, daemon=True).start()

    def _on_apply_finished(self, renamed_cnt: int, errors: List[str]):
        self.progress_bar.setValue(100)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Close")

        if errors:
            err_summary = "\n".join(errors[:5])
            if len(errors) > 5:
                err_summary += f"\n...and {len(errors) - 5} more."
            QMessageBox.warning(
                self,
                "Naming Alignment Completed with Warnings",
                f"Successfully aligned {renamed_cnt} item(s).\n\nSome items could not be renamed:\n{err_summary}"
            )
        else:
            QMessageBox.information(
                self,
                "Naming Alignment Completed",
                f"Successfully aligned {renamed_cnt} album folder(s) with Plex conventions.\nAll files preserved!"
            )

        self.alignment_completed.emit(renamed_cnt)
        self.accept()
