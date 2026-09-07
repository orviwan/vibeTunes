from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from podplex.core.sync_engine import SyncEngine


class QueueDialog(QDialog):
    def __init__(self, engine: SyncEngine, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sync Queue")
        self.engine = engine

        layout = QVBoxLayout(self)
        self.active_label = QLabel("")
        layout.addWidget(self.active_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["#", "Name", ""])
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        clear_btn = QPushButton("Clear Upcoming")
        clear_btn.clicked.connect(self._clear_pending)
        cancel_btn = QPushButton("Cancel Current")
        cancel_btn.clicked.connect(self.engine.cancel_current)
        buttons.addWidget(clear_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        self.engine.queue_changed.connect(self.refresh, Qt.QueuedConnection)
        self.refresh()

    def refresh(self) -> None:
        tasks = self.engine.pending_tasks()
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(task.name))
            remove_btn = QPushButton("✕ Remove")
            remove_btn.clicked.connect(lambda _checked=False, tid=task.task_id: self._remove(tid))
            self.table.setCellWidget(row, 2, remove_btn)

    def _remove(self, task_id: str) -> None:
        self.engine.remove_pending(task_id)
        self.refresh()

    def _clear_pending(self) -> None:
        self.engine.clear_pending()
        self.refresh()
