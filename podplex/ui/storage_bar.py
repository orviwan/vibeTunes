from __future__ import annotations

from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from podplex.core.storage_analyzer import StorageBreakdown

SEGMENT_COLORS = {
    "music": QColor("#4caf50"),
    "rockbox": QColor("#2196f3"),
    "other": QColor("#ff9800"),
    "free": QColor("#e0e0e0"),
}


class StorageBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._breakdown: StorageBreakdown | None = None
        self.setMinimumHeight(20)

    def set_breakdown(self, breakdown: StorageBreakdown) -> None:
        self._breakdown = breakdown
        self.update()

    def segments(self) -> list[tuple[str, int]]:
        if self._breakdown is None or self._breakdown.total_bytes <= 0:
            return []
        b = self._breakdown
        return [
            ("music", b.music_bytes),
            ("rockbox", b.rockbox_bytes),
            ("other", b.other_bytes),
            ("free", b.free_bytes),
        ]

    def paintEvent(self, event) -> None:
        segs = self.segments()
        if not segs:
            return
        total = sum(v for _, v in segs) or 1
        painter = QPainter(self)
        x = 0.0
        width = self.width()
        height = self.height()
        for name, value in segs:
            seg_width = width * (value / total)
            painter.fillRect(int(x), 0, int(seg_width) + 1, height, SEGMENT_COLORS[name])
            x += seg_width
        painter.end()
