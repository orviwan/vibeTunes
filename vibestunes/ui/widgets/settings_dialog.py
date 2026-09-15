"""Settings dialog for configuring Plex connection, libraries, and sync preferences."""
import time
import threading
from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QFileDialog, QGroupBox, QFormLayout,
    QMessageBox
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import Qt, QUrl, QObject, Signal

from vibestunes.core.config import AppConfig
from vibestunes.core.plex_client import (
    PlexManager, create_plex_pin, check_plex_pin, fetch_user_servers, CLIENT_IDENTIFIER
)

class PlexPinSignals(QObject):
    pin_ready = Signal(str, str, int)   # code, auth_url, pin_id
    authenticated = Signal(str, list)    # token, servers
    timeout = Signal()

class PlexTestSignals(QObject):
    finished = Signal(bool, str, list)  # success, message, libraries

class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, plex: PlexManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.plex = plex
        self.found_servers: List[Dict[str, Any]] = []

        self.setWindowTitle("Settings - vibesTunes")
        self.setMinimumWidth(560)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)

        # --- Plex Connection Group ---
        plex_group = QGroupBox("Plex Media Server")
        plex_layout = QVBoxLayout(plex_group)
        plex_layout.setSpacing(10)

        # Quick OAuth / PIN Sign-in row
        oauth_row = QHBoxLayout()
        self.oauth_btn = QPushButton("🔑 Sign In with Plex Account (OAuth)")
        self.oauth_btn.clicked.connect(self._on_start_oauth)
        self.oauth_status = QLabel("")
        self.oauth_status.setStyleSheet("font-size: 11px; color: #a6adc8;")
        oauth_row.addWidget(self.oauth_btn)
        oauth_row.addWidget(self.oauth_status, stretch=1)
        plex_layout.addLayout(oauth_row)

        form = QFormLayout()
        form.setSpacing(8)

        # Server picker (if servers discovered via OAuth)
        self.server_combo = QComboBox()
        self.server_combo.setVisible(False)
        self.server_combo.currentIndexChanged.connect(self._on_server_selected)
        form.addRow("Discovered Servers:", self.server_combo)

        self.url_input = QLineEdit(self.config.plex_url)
        self.url_input.setPlaceholderText("http://192.168.0.239:32400 or http://localhost:32400")
        form.addRow("Server URL:", self.url_input)

        self.token_input = QLineEdit(self.config.plex_token)
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_input.setPlaceholderText("Plex Authentication Token (X-Plex-Token)")
        form.addRow("Plex Token:", self.token_input)

        # Test Connection & Library Picker
        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._on_test_connection)
        self.test_status = QLabel("")
        self.test_status.setStyleSheet("font-size: 11px;")
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_status, stretch=1)
        form.addRow("", test_row)

        self.library_combo = QComboBox()
        self.library_combo.setEditable(True)
        self.library_combo.addItem(self.config.plex_library or "Music")
        form.addRow("Music Library:", self.library_combo)

        plex_layout.addLayout(form)
        main_layout.addWidget(plex_group)

        # --- iPod & Sync Preferences Group ---
        sync_group = QGroupBox("iPod & Sync Preferences")
        sync_layout = QFormLayout(sync_group)
        sync_layout.setSpacing(8)

        # Custom mount path
        mount_row = QHBoxLayout()
        self.mount_input = QLineEdit(self.config.custom_ipod_path)
        self.mount_input.setPlaceholderText("Auto-detect (Leave empty for automatic detection)")
        self.browse_mount_btn = QPushButton("Browse...")
        self.browse_mount_btn.clicked.connect(self._on_browse_mount)
        mount_row.addWidget(self.mount_input, stretch=1)
        mount_row.addWidget(self.browse_mount_btn)
        sync_layout.addRow("iPod Mount Path:", mount_row)

        # Naming Pattern
        self.pattern_combo = QComboBox()
        self.pattern_combo.addItem("Plex Server File/Folder Structure (Exact layout from Plex server, FAT32-safe) - Recommended", "plex_exact")
        self.pattern_combo.addItem("Rockbox Disc Style (Artist/Artist-Year-Album/CD 01/Track - Title.flac)", "rockbox_disc")
        self.pattern_combo.addItem("Standard Style (Artist/Album/Track - Title.flac)", "standard")
        cur_idx = self.pattern_combo.findData(self.config.naming_pattern)
        if cur_idx >= 0:
            self.pattern_combo.setCurrentIndex(cur_idx)
        sync_layout.addRow("Folder Structure:", self.pattern_combo)

        # Transcode Mode
        self.transcode_combo = QComboBox()
        self.transcode_combo.addItem("Original Audio (Lossless/Direct Stream - Recommended)", "original")
        self.transcode_combo.addItem("Transcode Lossless to MP3 VBR V0 (~245 kbps)", "transcode_mp3_v0")
        self.transcode_combo.addItem("Transcode Lossless to MP3 CBR 320 kbps", "transcode_mp3_320k")
        t_idx = self.transcode_combo.findData(self.config.transcode_mode)
        if t_idx >= 0:
            self.transcode_combo.setCurrentIndex(t_idx)
        sync_layout.addRow("Audio Quality:", self.transcode_combo)

        # Artwork
        self.artwork_check = QCheckBox("Save album cover (cover.jpg) for Rockbox WPS")
        self.artwork_check.setChecked(self.config.download_artwork)
        sync_layout.addRow("Album Artwork:", self.artwork_check)

        main_layout.addWidget(sync_group)

        # --- Bottom Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold;")
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)

        main_layout.addLayout(btn_layout)

    def _on_start_oauth(self):
        self.oauth_btn.setEnabled(False)
        self.oauth_status.setText("Requesting login code...")

        self.pin_signals = PlexPinSignals()
        self.pin_signals.pin_ready.connect(self._on_pin_ready)
        self.pin_signals.authenticated.connect(self._on_pin_authenticated)
        self.pin_signals.timeout.connect(self._on_pin_timeout)

        def worker():
            pin_data = create_plex_pin()
            if not pin_data:
                self.pin_signals.timeout.emit()
                return

            pin_id = pin_data.get("id")
            code = pin_data.get("code")
            auth_url = f"https://app.plex.tv/auth#?clientID={CLIENT_IDENTIFIER}&code={code}"
            self.pin_signals.pin_ready.emit(code, auth_url, pin_id)

            for _ in range(60):
                time.sleep(2)
                token = check_plex_pin(pin_id)
                if token:
                    servers = fetch_user_servers(token)
                    self.pin_signals.authenticated.emit(token, servers)
                    return

            self.pin_signals.timeout.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _on_pin_ready(self, code: str, auth_url: str, pin_id: int):
        self.oauth_status.setText(f"Waiting for authorization (Code: {code})...")
        QDesktopServices.openUrl(QUrl(auth_url))

    def _on_pin_authenticated(self, token: str, servers: list):
        self.token_input.setText(token)
        self.oauth_status.setText("✓ Authorized via Plex!")
        self.oauth_btn.setEnabled(True)
        self.found_servers = servers
        if servers:
            self.server_combo.clear()
            self.server_combo.setVisible(True)
            for s in servers:
                self.server_combo.addItem(f"{s['name']} ({s['uri']})", s)
            first = servers[0]
            self.url_input.setText(first["uri"])
            self.token_input.setText(first["token"])
            self._on_test_connection()

    def _on_pin_timeout(self):
        self.oauth_btn.setEnabled(True)
        self.oauth_status.setText("Login timed out. Try again.")

    def _on_server_selected(self, idx: int):
        if 0 <= idx < len(self.found_servers):
            srv = self.found_servers[idx]
            self.url_input.setText(srv.get("uri", ""))
            self.token_input.setText(srv.get("token", ""))
            self._on_test_connection()

    def _on_test_connection(self):
        url = self.url_input.text().strip()
        token = self.token_input.text().strip()
        if not url or not token:
            self.test_status.setText("Enter URL and Token")
            self.test_status.setStyleSheet("color: #f38ba8;")
            return

        self.test_status.setText("Connecting...")
        self.test_status.setStyleSheet("color: #fab387;")
        self.test_btn.setEnabled(False)

        self.test_signals = PlexTestSignals()
        self.test_signals.finished.connect(self._on_test_finished)

        def worker():
            temp_plex = PlexManager(url, token)
            success, msg = temp_plex.connect()
            libs = temp_plex.get_music_libraries() if success else []
            self.test_signals.finished.emit(success, msg, libs)

        threading.Thread(target=worker, daemon=True).start()

    def _on_test_finished(self, success: bool, msg: str, libs: list):
        self.test_btn.setEnabled(True)
        if success:
            self.test_status.setText(f"✓ {msg}")
            self.test_status.setStyleSheet("color: #a6e3a1;")
            if libs:
                self.library_combo.clear()
                self.library_combo.addItems(libs)
        else:
            self.test_status.setText(f"✗ {msg}")
            self.test_status.setStyleSheet("color: #f38ba8;")

    def _on_browse_mount(self):
        folder = QFileDialog.getExistingDirectory(self, "Select iPod Mount Folder")
        if folder:
            self.mount_input.setText(folder)

    def _on_save(self):
        self.config.plex_url = self.url_input.text().strip()
        self.config.plex_token = self.token_input.text().strip()
        self.config.plex_library = self.library_combo.currentText().strip() or "Music"
        self.config.custom_ipod_path = self.mount_input.text().strip()
        self.config.naming_pattern = self.pattern_combo.currentData()
        self.config.transcode_mode = self.transcode_combo.currentData()
        self.config.download_artwork = self.artwork_check.isChecked()
        self.config.save()
        self.accept()
