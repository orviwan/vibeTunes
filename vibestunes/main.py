import sys
import argparse
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

from vibestunes.ui.main_window import MainWindow

def main():
    parser = argparse.ArgumentParser(description="vibesTunes — iPod Rockbox & Plex Manager")
    parser.add_argument("--demo", action="store_true", help="Launch in Demo Mode with fictional music catalog and device for screenshots")
    parser.add_argument("--fullscreen", action="store_true", help="Launch in full screen mode")
    parser.add_argument("--maximized", action="store_true", help="Launch maximized")
    args, unknown = parser.parse_known_args()

    app = QApplication(sys.argv)
    app.setApplicationName("vibestunes")
    app.setOrganizationName("vibestunes")
    app.setApplicationDisplayName("vibesTunes")

    icon_path = Path(__file__).parent / "assets" / "vibesTunes.svg"
    if not icon_path.exists():
        icon_path = Path(__file__).parent / "assets" / "vibetunes.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow(demo_mode=args.demo)
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    if args.fullscreen:
        window.showFullScreen()
    elif args.maximized:
        window.showMaximized()
    else:
        window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
