"""Modern theme and stylesheet for vibeTunes."""

DARK_STYLESHEET = """
QMainWindow {
    background-color: #181825;
    color: #cdd6f4;
}

QWidget {
    font-family: 'Inter', 'Cantarell', 'Segoe UI', sans-serif;
    font-size: 13px;
    color: #cdd6f4;
}

QTabWidget::pane {
    border: 1px solid #313244;
    background: #181825;
    border-radius: 8px;
}

QTabBar::tab {
    background: #1e1e2e;
    color: #a6adc8;
    padding: 8px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 4px;
    font-weight: bold;
}

QTabBar::tab:selected {
    background: #313244;
    color: #89b4fa;
    border-bottom: 2px solid #89b4fa;
}

QTabBar::tab:hover {
    color: #ffffff;
    background: #26283b;
}

/* Card Panels */
QFrame.card {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 10px;
    padding: 12px;
}

/* Push Buttons */
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #45475a;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #585b70;
}

QPushButton:checked {
    background-color: #89b4fa;
    color: #11111b;
    font-weight: bold;
    border: 1px solid #b4befe;
}

QPushButton:disabled {
    background-color: #181825;
    color: #585b70;
    border-color: #313244;
}

QPushButton.primary {
    background-color: #89b4fa;
    color: #11111b;
    border: none;
    font-weight: bold;
}

QPushButton.primary:hover {
    background-color: #b4befe;
}

QPushButton.danger {
    background-color: #f38ba8;
    color: #11111b;
    border: none;
    font-weight: bold;
}

QPushButton.danger:hover {
    background-color: #eba0ac;
}

QPushButton.success {
    background-color: #a6e3a1;
    color: #11111b;
    border: none;
    font-weight: bold;
}

QPushButton.success:hover {
    background-color: #94e2d5;
}

/* Line Edits & Search */
QLineEdit {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 6px 10px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
    selection-color: #11111b;
}

QLineEdit:focus {
    border: 1px solid #89b4fa;
}

/* Lists and Tables */
QListWidget, QTableWidget, QTreeWidget {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 8px;
    color: #cdd6f4;
    gridline-color: #313244;
    selection-background-color: #313244;
    selection-color: #89b4fa;
    outline: none;
}

QListWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}

QListWidget::item:hover {
    background-color: #26283b;
}

QListWidget::item:selected {
    background-color: #313244;
    color: #89b4fa;
}

QHeaderView::section {
    background-color: #181825;
    color: #a6adc8;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #313244;
    font-weight: bold;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #181825;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #45475a;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #585b70;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Progress Bar */
QProgressBar {
    background-color: #313244;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-size: 11px;
    height: 14px;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 6px;
}
"""

COLOR_MUSIC = "#3b82f6"      # Vibrant Blue
COLOR_ROCKBOX = "#f59e0b"    # Amber / Orange
COLOR_OTHER = "#8b5cf6"      # Purple
COLOR_FREE = "#313244"       # Deep Slate Gray
COLOR_TEXT = "#cdd6f4"
COLOR_MUTED = "#a6adc8"
