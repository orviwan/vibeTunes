import sys
import argparse
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

from vibetunes.ui.main_window import MainWindow

def main():
    parser = argparse.ArgumentParser(description="vibeTunes — iPod Rockbox & Plex Manager")
    parser.add_argument("--demo", action="store_true", help="Launch in Demo Mode with fictional music catalog and device for screenshots")
    args, unknown = parser.parse_known_args()

    app = QApplication(sys.argv)
    app.setApplicationName("vibetunes")
    app.setOrganizationName("vibetunes")
    app.setApplicationDisplayName("vibeTunes")

    icon_path = Path(__file__).parent / "assets" / "vibetunes.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow(demo_mode=args.demo)
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
