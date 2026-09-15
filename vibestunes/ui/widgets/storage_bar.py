"""Custom storage breakdown bar widget for iPod capacity."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtGui import QPainter, QColor, QBrush, QPen
from PySide6.QtCore import Qt, QRectF, Signal

from vibestunes.ui.theme import COLOR_MUSIC, COLOR_ROCKBOX, COLOR_OTHER, COLOR_FREE, COLOR_TEXT, COLOR_MUTED

def format_bytes(b: int) -> str:
    if b >= 1024 ** 3:
        return f"{b / (1024 ** 3):.1f} GB"
    elif b >= 1024 ** 2:
        return f"{b / (1024 ** 2):.1f} MB"
    elif b >= 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b} B"

class StorageCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(18)
        self.total = 1
        self.music = 0
        self.rockbox = 0
        self.other = 0
        self.free = 1

    def update_data(self, total: int, free: int, music: int, rockbox: int, other: int):
        self.total = max(1, total)
        self.free = max(0, free)
        self.music = max(0, music)
        self.rockbox = max(0, rockbox)
        self.other = max(0, other)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        radius = h / 2.0

        # Background (free space)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(COLOR_FREE)))
        rect = QRectF(0, 0, w, h)
        painter.drawRoundedRect(rect, radius, radius)

        if self.total <= 0:
            return

        # Calculate segment widths
        music_w = (self.music / self.total) * w
        rockbox_w = (self.rockbox / self.total) * w
        other_w = (self.other / self.total) * w

        current_x = 0.0

        # Draw Music segment
        if music_w > 0:
            painter.setBrush(QBrush(QColor(COLOR_MUSIC)))
            r_music = QRectF(current_x, 0, music_w, h)
            # Clip or draw rounded start
            painter.drawRoundedRect(r_music, radius, radius)
            current_x += music_w

        # Draw Rockbox segment
        if rockbox_w > 0:
            painter.setBrush(QBrush(QColor(COLOR_ROCKBOX)))
            r_rockbox = QRectF(current_x, 0, rockbox_w, h)
            painter.drawRect(r_rockbox)
            current_x += rockbox_w

        # Draw Other segment
        if other_w > 0:
            painter.setBrush(QBrush(QColor(COLOR_OTHER)))
            r_other = QRectF(current_x, 0, other_w, h)
            painter.drawRect(r_other)

        # Subtle border
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#45475a"), 1))
        painter.drawRoundedRect(rect, radius, radius)

class StorageBarWidget(QWidget):
    analyzer_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Top summary header
        self.header_layout = QHBoxLayout()
        self.title_label = QLabel("iPod Storage")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #cdd6f4;")
        self.header_layout.addWidget(self.title_label)

        self.analyzer_btn = QPushButton("🔍 Largest Files & Albums")
        self.analyzer_btn.setToolTip("View ranked list of largest albums, audio files, and artists on your iPod")
        self.analyzer_btn.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #89b4fa;
                font-weight: bold;
                font-size: 11px;
                padding: 3px 10px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #45475a;
                color: #b4befe;
            }
        """)
        self.analyzer_btn.clicked.connect(self.analyzer_requested.emit)
        self.header_layout.addWidget(self.analyzer_btn)

        self.header_layout.addStretch()
        self.summary_label = QLabel("Detecting...")
        self.summary_label.setStyleSheet(f"color: {COLOR_MUTED}; font-size: 12px;")
        self.header_layout.addWidget(self.summary_label)
        layout.addLayout(self.header_layout)

        # The bar itself
        self.canvas = StorageCanvas()
        layout.addWidget(self.canvas)

        # Legend row
        self.legend_layout = QHBoxLayout()
        self.legend_layout.setSpacing(18)

        self.music_legend = self._create_legend_item(COLOR_MUSIC, "Music: --")
        self.rockbox_legend = self._create_legend_item(COLOR_ROCKBOX, "Rockbox OS: --")
        self.other_legend = self._create_legend_item(COLOR_OTHER, "Other: --")
        self.free_legend = self._create_legend_item(COLOR_FREE, "Free: --")

        self.legend_layout.addWidget(self.music_legend)
        self.legend_layout.addWidget(self.rockbox_legend)
        self.legend_layout.addWidget(self.other_legend)
        self.legend_layout.addWidget(self.free_legend)
        self.legend_layout.addStretch()

        layout.addLayout(self.legend_layout)

        self.setStyleSheet("""
            StorageBarWidget {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 10px;
            }
        """)

    def _create_legend_item(self, color_hex: str, text: str) -> QWidget:
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color_hex}; font-size: 14px;")
        label = QLabel(text)
        label.setStyleSheet("font-size: 12px; color: #a6adc8;")
        container.label_widget = label

        h.addWidget(dot)
        h.addWidget(label)
        return container

    def set_storage(self, total: int, free: int, music: int, rockbox: int, other: int):
        self.canvas.update_data(total, free, music, rockbox, other)

        used = max(0, total - free)
        pct_used = (used / total * 100) if total > 0 else 0
        pct_free = (free / total * 100) if total > 0 else 0

        self.summary_label.setText(
            f"{format_bytes(used)} Used ({pct_used:.0f}%) • {format_bytes(free)} Free ({pct_free:.0f}%) of {format_bytes(total)}"
        )
        self.music_legend.label_widget.setText(f"Music: {format_bytes(music)}")
        self.rockbox_legend.label_widget.setText(f"Rockbox: {format_bytes(rockbox)}")
        self.other_legend.label_widget.setText(f"Other: {format_bytes(other)}")
        self.free_legend.label_widget.setText(f"Free Space: {format_bytes(free)}")
