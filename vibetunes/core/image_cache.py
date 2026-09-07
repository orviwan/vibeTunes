"""Disk and memory caching for artist avatars and album artwork."""
import os
import hashlib
import threading
import queue
from pathlib import Path
from typing import Optional, Dict
import requests

from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath, QColor, QFont, QPen
from PySide6.QtCore import Qt, QRectF, QObject, Signal

CACHE_DIR = Path.home() / ".cache" / "vibetunes" / "thumbs"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

IPOD_CACHE_DIR = Path.home() / ".cache" / "vibetunes" / "ipod_thumbs"
IPOD_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]

def extract_embedded_art(file_path: Optional[Path]) -> Optional[bytes]:
    """Extracts embedded front cover art from FLAC, MP3, or MP4/M4A audio files."""
    if not file_path or not file_path.exists():
        return None
    try:
        import mutagen
        from mutagen.flac import FLAC
        mf = mutagen.File(str(file_path))
        if mf is None:
            return None
        if isinstance(mf, FLAC) or hasattr(mf, "pictures"):
            if mf.pictures:
                return mf.pictures[0].data
        if hasattr(mf, "tags") and mf.tags:
            for k, tag in mf.tags.items():
                if k.startswith("APIC") and hasattr(tag, "data"):
                    return tag.data
                if k == "covr" and isinstance(tag, list) and len(tag) > 0:
                    return bytes(tag[0])
                if getattr(tag, "mime", None) and getattr(tag, "data", None):
                    return tag.data
    except Exception:
        pass
    return None

def create_rounded_pixmap(src: QPixmap, radius: float = 8.0, size: int = 64) -> QPixmap:
    if src.isNull():
        return src
    scaled = src.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setClipPath(path)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter.drawPixmap(x, y, scaled)
    painter.end()
    return out

def create_artist_placeholder(size: int = 44) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setPen(QPen(QColor("#45475a"), 1.5))
    painter.setBrush(QColor("#24273a"))
    painter.drawEllipse(1, 1, size - 2, size - 2)

    painter.setPen(QColor("#89b4fa"))
    font = QFont("sans-serif", int(size * 0.38), QFont.Bold)
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, "👤")
    painter.end()
    return pix

def create_album_placeholder(size: int = 60) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setPen(QPen(QColor("#45475a"), 1.5))
    painter.setBrush(QColor("#24273a"))
    painter.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), 6.0, 6.0)

    painter.setPen(QColor("#cdd6f4"))
    font = QFont("sans-serif", int(size * 0.36))
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, "♪")
    painter.end()
    return pix

class ThumbnailManager(QObject):
    thumbnail_loaded = Signal(str, QPixmap)  # key (URL or local identifier), pixmap

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mem_cache: Dict[str, QPixmap] = {}
        self._queue: queue.Queue = queue.Queue()
        self._enqueued_keys = set()
        self._lock = threading.Lock()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def get_thumbnail(self, url: str, token: str, is_artist: bool = False, size: int = 60) -> QPixmap:
        """Retrieves or asynchronously downloads a Plex thumbnail."""
        if not url:
            return create_artist_placeholder(size) if is_artist else create_album_placeholder(size)

        cache_key = f"{url}_{size}_{'a' if is_artist else 'l'}"
        with self._lock:
            if cache_key in self._mem_cache:
                return self._mem_cache[cache_key]

        if url.startswith("demo://"):
            from vibetunes.core.demo_data import get_demo_pixmap
            pix = get_demo_pixmap(url, is_artist=is_artist, size=size)
            radius = (size / 2.0) if is_artist else 6.0
            rounded = create_rounded_pixmap(pix, radius=radius, size=size)
            with self._lock:
                self._mem_cache[cache_key] = rounded
            return rounded

        # Check disk cache
        h = _url_hash(url)
        disk_path = CACHE_DIR / f"{h}_{size}.jpg"
        if disk_path.exists():
            img = QImage(str(disk_path))
            if not img.isNull():
                pix = QPixmap.fromImage(img)
                radius = (size / 2.0) if is_artist else 6.0
                rounded = create_rounded_pixmap(pix, radius=radius, size=size)
                with self._lock:
                    self._mem_cache[cache_key] = rounded
                return rounded

        # Enqueue background fetch
        placeholder = create_artist_placeholder(size) if is_artist else create_album_placeholder(size)
        with self._lock:
            if url not in self._enqueued_keys:
                self._enqueued_keys.add(url)
                self._queue.put(("remote", url, token, is_artist, size, cache_key, disk_path))

        return placeholder

    def get_local_thumbnail(
        self,
        key: str,
        cover_path: Optional[Path] = None,
        sample_track_path: Optional[Path] = None,
        is_artist: bool = False,
        size: int = 60,
    ) -> QPixmap:
        """
        Retrieves or asynchronously extracts local album/artist artwork from iPod.
        Checks for existing cover.jpg or extracts embedded ID3/FLAC artwork.
        """
        if not key:
            return create_artist_placeholder(size) if is_artist else create_album_placeholder(size)

        cache_key = f"local_{key}_{size}_{'a' if is_artist else 'l'}"
        with self._lock:
            if cache_key in self._mem_cache:
                return self._mem_cache[cache_key]

        h = _url_hash(key)
        disk_path = IPOD_CACHE_DIR / f"{h}_{size}.jpg"
        if disk_path.exists():
            img = QImage(str(disk_path))
            if not img.isNull():
                pix = QPixmap.fromImage(img)
                radius = (size / 2.0) if is_artist else 6.0
                rounded = create_rounded_pixmap(pix, radius=radius, size=size)
                with self._lock:
                    self._mem_cache[cache_key] = rounded
                return rounded

        # Enqueue background extraction
        placeholder = create_artist_placeholder(size) if is_artist else create_album_placeholder(size)
        with self._lock:
            if key not in self._enqueued_keys:
                self._enqueued_keys.add(key)
                self._queue.put(("local", key, cover_path, sample_track_path, is_artist, size, cache_key, disk_path))

        return placeholder

    def _worker_loop(self):
        while True:
            try:
                task = self._queue.get()
                task_type = task[0]

                if task_type == "remote":
                    _, url, token, is_artist, size, cache_key, disk_path = task
                    headers = {"X-Plex-Token": token} if token else {}
                    try:
                        r = requests.get(url, headers=headers, timeout=8)
                        if r.status_code == 200 and r.content:
                            try:
                                with open(disk_path, "wb") as f:
                                    f.write(r.content)
                            except Exception:
                                pass

                            img = QImage.fromData(r.content)
                            if not img.isNull():
                                pix = QPixmap.fromImage(img)
                                radius = (size / 2.0) if is_artist else 6.0
                                rounded = create_rounded_pixmap(pix, radius=radius, size=size)
                                with self._lock:
                                    self._mem_cache[cache_key] = rounded
                                self.thumbnail_loaded.emit(url, rounded)
                    except Exception:
                        pass

                elif task_type == "local":
                    _, key, cover_path, sample_track_path, is_artist, size, cache_key, disk_path = task
                    raw_data = None
                    try:
                        if cover_path and Path(cover_path).exists():
                            with open(cover_path, "rb") as f:
                                raw_data = f.read()
                        elif sample_track_path:
                            raw_data = extract_embedded_art(Path(sample_track_path))

                        if raw_data:
                            try:
                                with open(disk_path, "wb") as f:
                                    f.write(raw_data)
                            except Exception:
                                pass

                            img = QImage.fromData(raw_data)
                            if not img.isNull():
                                pix = QPixmap.fromImage(img)
                                radius = (size / 2.0) if is_artist else 6.0
                                rounded = create_rounded_pixmap(pix, radius=radius, size=size)
                                with self._lock:
                                    self._mem_cache[cache_key] = rounded
                                self.thumbnail_loaded.emit(key, rounded)
                    except Exception:
                        pass

                self._queue.task_done()
            except Exception:
                pass

