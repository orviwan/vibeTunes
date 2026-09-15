"""Demo data generator and mock engine for vibesTunes screenshot capture."""
import time
import math
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set, Any
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QPainterPath, QColor, QFont, QPen,
    QLinearGradient, QRadialGradient, QBrush
)

from vibestunes.core.plex_client import (
    PlexManager, PlexArtistSummary, PlexAlbumSummary,
    PlexPlaylistSummary, PlexTrackDetail, normalize_music_key
)
from vibestunes.core.device import iPodDevice
from vibestunes.core.ipod_scanner import iPodArtist, iPodAlbum, iPodTrack
from vibestunes.core.sync_engine import SyncWorker, SyncTask, SyncPlaylistTask, DeleteTask

# Palette themes for fictional artists
ARTIST_PALETTES = {
    "The Solar Echoes": {
        "grad_start": "#0f172a", "grad_end": "#1e1b4b", "accent": "#38bdf8", "sub": "#818cf8",
        "style": "cosmic", "genre": "Space Rock / Ambient"
    },
    "Neon Mirage": {
        "grad_start": "#2e0854", "grad_end": "#18002e", "accent": "#f43f5e", "sub": "#06b6d4",
        "style": "synthwave", "genre": "Synthwave / Electronic"
    },
    "Velvet Horizon": {
        "grad_start": "#3b1d2e", "grad_end": "#1f1322", "accent": "#f472b6", "sub": "#c084fc",
        "style": "shoegaze", "genre": "Shoegaze / Dream Pop"
    },
    "Subatomic Pulse": {
        "grad_start": "#064e3b", "grad_end": "#022c22", "accent": "#34d399", "sub": "#a7f3d0",
        "style": "electronic", "genre": "IDM / Downtempo"
    },
    "The Paper Birds": {
        "grad_start": "#451a03", "grad_end": "#1c1917", "accent": "#fbbf24", "sub": "#fde68a",
        "style": "folk", "genre": "Indie Folk / Acoustic"
    },
    "Prism Frequency": {
        "grad_start": "#1e293b", "grad_end": "#0f172a", "accent": "#fb923c", "sub": "#facc15",
        "style": "jazz", "genre": "Modern Jazz / Fusion"
    },
    "Monolith Echo": {
        "grad_start": "#18181b", "grad_end": "#09090b", "accent": "#a1a1aa", "sub": "#e4e4e7",
        "style": "metal", "genre": "Post-Metal / Ambient"
    },
    "Aurora Borealis Ensemble": {
        "grad_start": "#082f49", "grad_end": "#0c4a6e", "accent": "#22d3ee", "sub": "#a5f3fc",
        "style": "classical", "genre": "Neo-Classical / Orchestral"
    },
}

DEFAULT_PALETTE = {
    "grad_start": "#181825", "grad_end": "#11111b", "accent": "#89b4fa", "sub": "#b4befe",
    "style": "abstract", "genre": "Indie"
}

def generate_demo_art(thumb_url: str, is_artist: bool = False, size: int = 300) -> QPixmap:
    """Generates a high-quality procedural album jacket or artist avatar."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    # Decode url: e.g. "demo://artist/The Solar Echoes" or "demo://album/The Solar Echoes/Heliosphere"
    artist_name = "Unknown Artist"
    album_title = ""
    if thumb_url.startswith("demo://"):
        parts = thumb_url[len("demo://"):].split("/")
        if len(parts) >= 2 and parts[0] == "artist":
            artist_name = parts[1]
        elif len(parts) >= 3 and parts[0] == "album":
            artist_name = parts[1]
            album_title = parts[2]

    palette = ARTIST_PALETTES.get(artist_name, DEFAULT_PALETTE)
    c_start = QColor(palette["grad_start"])
    c_end = QColor(palette["grad_end"])
    c_accent = QColor(palette["accent"])
    c_sub = QColor(palette["sub"])

    if is_artist:
        # Draw circular artist avatar
        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0.0, c_start)
        grad.setColorAt(1.0, c_end)

        painter.setPen(QPen(c_accent, 3.0))
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(4, 4, size - 8, size - 8)

        # Monogram initials
        initials = "".join([w[0] for w in artist_name.split() if w])[:2].upper()
        font = QFont("sans-serif", int(size * 0.36), QFont.Bold)
        painter.setFont(font)
        painter.setPen(c_sub)
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, initials)
        painter.end()
        return pix

    # Album cover art (square)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, c_start)
    grad.setColorAt(1.0, c_end)
    painter.fillRect(0, 0, size, size, grad)

    # Stylized geometric background elements based on style
    style = palette.get("style", "abstract")
    if style == "cosmic":
        # Concentric rings & glowing orb
        center_x = size * 0.5
        center_y = size * 0.42
        r_grad = QRadialGradient(center_x, center_y, size * 0.35)
        r_grad.setColorAt(0.0, c_accent)
        r_grad.setColorAt(0.5, QColor(c_accent.red(), c_accent.green(), c_accent.blue(), 120))
        r_grad.setColorAt(1.0, Qt.transparent)
        painter.setPen(Qt.NoPen)
        painter.setBrush(r_grad)
        painter.drawEllipse(QPointF(center_x, center_y), size * 0.35, size * 0.35)

        painter.setPen(QPen(c_sub, 1.5, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(center_x, center_y), size * 0.28, size * 0.28)
        painter.drawEllipse(QPointF(center_x, center_y), size * 0.42, size * 0.42)

    elif style == "synthwave":
        # Retro perspective grid & neon sun
        sun_y = size * 0.38
        sun_grad = QLinearGradient(0, sun_y - 60, 0, sun_y + 60)
        sun_grad.setColorAt(0.0, c_sub)
        sun_grad.setColorAt(1.0, c_accent)
        painter.setPen(Qt.NoPen)
        painter.setBrush(sun_grad)
        painter.drawEllipse(QPointF(size * 0.5, sun_y), size * 0.26, size * 0.26)

        # Horizon lines
        painter.setPen(QPen(c_sub, 1.5))
        for y_pct in [0.65, 0.72, 0.81, 0.92]:
            y = size * y_pct
            painter.drawLine(0, int(y), size, int(y))

    elif style == "shoegaze":
        # Soft blurred overlapping pastel discs
        painter.setPen(Qt.NoPen)
        d1 = QRadialGradient(size * 0.35, size * 0.4, size * 0.4)
        d1.setColorAt(0.0, QColor(c_accent.red(), c_accent.green(), c_accent.blue(), 180))
        d1.setColorAt(1.0, Qt.transparent)
        painter.setBrush(d1)
        painter.drawEllipse(QPointF(size * 0.35, size * 0.4), size * 0.35, size * 0.35)

        d2 = QRadialGradient(size * 0.65, size * 0.45, size * 0.38)
        d2.setColorAt(0.0, QColor(c_sub.red(), c_sub.green(), c_sub.blue(), 160))
        d2.setColorAt(1.0, Qt.transparent)
        painter.setBrush(d2)
        painter.drawEllipse(QPointF(size * 0.65, size * 0.45), size * 0.35, size * 0.35)

    elif style == "electronic":
        # Minimalist matrix grid dots & circuit track
        painter.setPen(Qt.NoPen)
        painter.setBrush(c_accent)
        step = int(size * 0.1)
        for gx in range(step, size - step + 1, step):
            for gy in range(step, int(size * 0.6), step):
                if (gx + gy) % (step * 2) == 0:
                    painter.drawEllipse(gx - 2, gy - 2, 4, 4)

        painter.setPen(QPen(c_sub, 2.0))
        painter.drawLine(step, int(size * 0.5), int(size * 0.6), int(size * 0.5))
        painter.drawLine(int(size * 0.6), int(size * 0.5), int(size * 0.8), int(size * 0.3))

    elif style == "folk":
        # Minimalist mountain / tree silhouette geometry
        path = QPainterPath()
        path.moveTo(size * 0.1, size * 0.65)
        path.lineTo(size * 0.45, size * 0.28)
        path.lineTo(size * 0.65, size * 0.45)
        path.lineTo(size * 0.9, size * 0.65)
        path.closeSubpath()
        painter.setPen(QPen(c_accent, 2.0))
        painter.setBrush(QColor(c_start.red() + 30, c_start.green() + 20, c_start.blue() + 10, 200))
        painter.drawPath(path)

    elif style == "jazz":
        # Off-center geometric prisms & diagonal stripes
        painter.setPen(QPen(c_accent, 4.0))
        painter.drawLine(0, int(size * 0.2), int(size * 0.8), size)
        painter.setPen(QPen(c_sub, 2.0))
        painter.drawLine(int(size * 0.2), 0, size, int(size * 0.8))

        painter.setBrush(QColor(c_accent.red(), c_accent.green(), c_accent.blue(), 100))
        painter.drawRect(int(size * 0.3), int(size * 0.25), int(size * 0.35), int(size * 0.35))

    elif style == "metal":
        # Monolithic dark angled slab
        path = QPainterPath()
        path.moveTo(size * 0.35, size * 0.15)
        path.lineTo(size * 0.65, size * 0.15)
        path.lineTo(size * 0.72, size * 0.68)
        path.lineTo(size * 0.28, size * 0.68)
        path.closeSubpath()
        painter.setPen(QPen(c_sub, 1.5))
        painter.setBrush(QColor(25, 25, 28, 220))
        painter.drawPath(path)

    elif style == "classical":
        # Fluid curved wave arcs
        painter.setPen(QPen(c_accent, 2.5))
        painter.setBrush(Qt.NoBrush)
        for offset in range(0, 50, 10):
            painter.drawArc(
                int(size * 0.1) - offset, int(size * 0.2) - offset,
                int(size * 0.8) + (offset * 2), int(size * 0.5) + (offset * 2),
                30 * 16, 120 * 16
            )

    # Subtle vinyl groove line at top
    painter.setPen(QPen(QColor(255, 255, 255, 25), 1.0))
    painter.drawRect(1, 1, size - 2, size - 2)

    # Hi-Res / FLAC Badge in top-right
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(0, 0, 0, 160))
    painter.drawRoundedRect(size - 68, 12, 56, 18, 4, 4)
    painter.setPen(c_accent)
    badge_font = QFont("monospace", 8, QFont.Bold)
    painter.setFont(badge_font)
    painter.drawText(QRectF(size - 68, 12, 56, 18), Qt.AlignCenter, "FLAC 24")

    # Lower Typography: Artist and Album Title
    # Dark gradient banner for typography legibility
    text_overlay = QLinearGradient(0, size * 0.6, 0, size)
    text_overlay.setColorAt(0.0, Qt.transparent)
    text_overlay.setColorAt(0.5, QColor(0, 0, 0, 180))
    text_overlay.setColorAt(1.0, QColor(0, 0, 0, 240))
    painter.fillRect(0, int(size * 0.6), size, int(size * 0.4), text_overlay)

    # Album Title
    album_font = QFont("sans-serif", int(size * 0.068), QFont.Bold)
    painter.setFont(album_font)
    painter.setPen(QColor("#ffffff"))
    title_rect = QRectF(14, size * 0.72, size - 28, size * 0.14)
    painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignBottom, album_title or artist_name)

    # Artist Name
    artist_font = QFont("sans-serif", int(size * 0.046), QFont.Normal)
    painter.setFont(artist_font)
    painter.setPen(c_sub)
    artist_rect = QRectF(14, size * 0.86, size - 28, size * 0.10)
    painter.drawText(artist_rect, Qt.AlignLeft | Qt.AlignTop, artist_name.upper())

    painter.end()
    return pix

def get_demo_pixmap(thumb_url: str, is_artist: bool = False, size: int = 300) -> QPixmap:
    return generate_demo_art(thumb_url, is_artist=is_artist, size=size)

# -------------------------------------------------------------------------
# Fictional Catalog Definitions
# -------------------------------------------------------------------------

DEMO_CATALOG = [
    {
        "artist": "The Solar Echoes",
        "genres": ["Space Rock", "Ambient", "Post-Rock"],
        "albums": [
            {
                "title": "Signals Across the Void",
                "year": 2021,
                "synced_status": "complete",  # ✓ Complete
                "tracks": [
                    ("Cosmic Dawn", 342000, 48 * 1024 * 1024),
                    ("Pulsar Frequency", 298000, 42 * 1024 * 1024),
                    ("Radio Astronomy", 412000, 58 * 1024 * 1024),
                    ("Interstellar Drift", 520000, 74 * 1024 * 1024),
                    ("Kuiper Belt Odyssey", 380000, 53 * 1024 * 1024),
                    ("Gravity Assist", 265000, 37 * 1024 * 1024),
                    ("The Void Whispers", 445000, 62 * 1024 * 1024),
                    ("Orbital Decay", 390000, 55 * 1024 * 1024),
                    ("Signal Received", 215000, 30 * 1024 * 1024),
                ]
            },
            {
                "title": "Heliosphere",
                "year": 2023,
                "synced_status": "complete",  # ✓ Complete
                "tracks": [
                    ("Solar Wind", 310000, 44 * 1024 * 1024),
                    ("Coronal Mass", 425000, 60 * 1024 * 1024),
                    ("Magnetosphere", 360000, 51 * 1024 * 1024),
                    ("Ion Storm", 285000, 40 * 1024 * 1024),
                    ("Perihelion", 490000, 69 * 1024 * 1024),
                    ("Chromosphere Echoes", 335000, 47 * 1024 * 1024),
                    ("Terminal Shock", 410000, 58 * 1024 * 1024),
                    ("Beyond the Flare", 270000, 38 * 1024 * 1024),
                ]
            }
        ]
    },
    {
        "artist": "Neon Mirage",
        "genres": ["Synthwave", "Retrowave", "Electronic"],
        "albums": [
            {
                "title": "Midnight Expressway",
                "year": 2020,
                "synced_status": "complete",  # ✓ Complete
                "tracks": [
                    ("Nightdrive", 245000, 35 * 1024 * 1024),
                    ("Chrome Horizon", 280000, 39 * 1024 * 1024),
                    ("Synthetic Sunset", 315000, 44 * 1024 * 1024),
                    ("Cyber Arcade", 220000, 31 * 1024 * 1024),
                    ("Outrun 1986", 260000, 37 * 1024 * 1024),
                    ("Turbo Charged", 195000, 27 * 1024 * 1024),
                    ("Highway 101", 330000, 46 * 1024 * 1024),
                    ("Laser Grid", 275000, 39 * 1024 * 1024),
                    ("Neon Boulevard", 290000, 41 * 1024 * 1024),
                    ("Fade to Cyan", 340000, 48 * 1024 * 1024),
                ]
            },
            {
                "title": "Cybernetic Dreams",
                "year": 2022,
                "synced_status": "partial",  # ◐ Partial (7 of 11 synced)
                "tracks": [
                    ("Neural Link", 210000, 29 * 1024 * 1024),
                    ("Silicon Heartbeat", 285000, 40 * 1024 * 1024),
                    ("Ghost in the Matrix", 320000, 45 * 1024 * 1024),
                    ("Holographic Alley", 240000, 34 * 1024 * 1024),
                    ("Data Stream 9", 265000, 37 * 1024 * 1024),
                    ("Overclocked", 198000, 28 * 1024 * 1024),
                    ("Android Serenade", 345000, 49 * 1024 * 1024),
                    # Below 4 are not on iPod
                    ("Subroutine Zero", 230000, 32 * 1024 * 1024),
                    ("Memory Leak", 310000, 43 * 1024 * 1024),
                    ("Virtual Sanctuary", 360000, 51 * 1024 * 1024),
                    ("Mainframe Awakening", 420000, 59 * 1024 * 1024),
                ]
            },
            {
                "title": "Afterlight",
                "year": 2024,
                "synced_status": "none",  # Not synced
                "tracks": [
                    ("Dawn Patrol", 255000, 36 * 1024 * 1024),
                    ("Prismatic", 290000, 41 * 1024 * 1024),
                    ("Glass Cities", 340000, 48 * 1024 * 1024),
                    ("Mirror Shield", 270000, 38 * 1024 * 1024),
                    ("Echoes of Tomorrow", 325000, 46 * 1024 * 1024),
                    ("Solitary Frequency", 380000, 54 * 1024 * 1024),
                    ("End of Transmission", 410000, 58 * 1024 * 1024),
                ]
            }
        ]
    },
    {
        "artist": "Velvet Horizon",
        "genres": ["Shoegaze", "Dream Pop", "Indie Rock"],
        "albums": [
            {
                "title": "Slow Decay",
                "year": 2018,
                "synced_status": "complete",  # ✓ Complete
                "tracks": [
                    ("Reverberate", 360000, 51 * 1024 * 1024),
                    ("Sea of Gauze", 410000, 58 * 1024 * 1024),
                    ("Distant Shimmer", 290000, 41 * 1024 * 1024),
                    ("Fuzz & Honey", 340000, 48 * 1024 * 1024),
                    ("Submerged", 480000, 68 * 1024 * 1024),
                    ("Overcast Sun", 315000, 44 * 1024 * 1024),
                    ("Softest Murmur", 390000, 55 * 1024 * 1024),
                    ("Fading Light", 440000, 62 * 1024 * 1024),
                ]
            },
            {
                "title": "Lavender Skies",
                "year": 2021,
                "synced_status": "none",  # Not synced
                "tracks": [
                    ("Morning Mist", 270000, 38 * 1024 * 1024),
                    ("Petal Fall", 320000, 45 * 1024 * 1024),
                    ("Violet Hour", 355000, 50 * 1024 * 1024),
                    ("Static Cloud", 410000, 58 * 1024 * 1024),
                    ("Driftwood", 380000, 54 * 1024 * 1024),
                    ("Amber Sleep", 295000, 41 * 1024 * 1024),
                    ("Velvet Rain", 430000, 61 * 1024 * 1024),
                    ("Echoes in Bloom", 365000, 51 * 1024 * 1024),
                    ("Dusk Lullaby", 240000, 34 * 1024 * 1024),
                ]
            }
        ]
    },
    {
        "artist": "Subatomic Pulse",
        "genres": ["IDM", "Downtempo", "Glitch"],
        "albums": [
            {
                "title": "Quantum Resonance",
                "year": 2019,
                "synced_status": "partial",  # ◐ Partial (4 of 10 synced)
                "tracks": [
                    ("Wavefunction", 310000, 44 * 1024 * 1024),
                    ("Entanglement", 280000, 39 * 1024 * 1024),
                    ("Spin State", 330000, 46 * 1024 * 1024),
                    ("Higgs Field", 260000, 37 * 1024 * 1024),
                    # Below are not on iPod
                    ("Superposition", 390000, 55 * 1024 * 1024),
                    ("Plancks Constant", 245000, 34 * 1024 * 1024),
                    ("Neutrino Flux", 315000, 44 * 1024 * 1024),
                    ("Quark Triplet", 370000, 52 * 1024 * 1024),
                    ("Tunneling Effect", 420000, 59 * 1024 * 1024),
                    ("Zero Point", 450000, 64 * 1024 * 1024),
                ]
            },
            {
                "title": "Particle Shift",
                "year": 2022,
                "synced_status": "none",
                "tracks": [
                    ("Decoherence", 305000, 43 * 1024 * 1024),
                    ("Lattice Dynamics", 345000, 49 * 1024 * 1024),
                    ("Muon Cascade", 290000, 41 * 1024 * 1024),
                    ("Antimatter Drift", 410000, 58 * 1024 * 1024),
                    ("Symmetry Breaking", 360000, 51 * 1024 * 1024),
                    ("Gluon Plasma", 325000, 46 * 1024 * 1024),
                    ("String Harmonic", 440000, 62 * 1024 * 1024),
                    ("Vacuum State", 275000, 39 * 1024 * 1024),
                ]
            }
        ]
    },
    {
        "artist": "The Paper Birds",
        "genres": ["Indie Folk", "Acoustic", "Americana"],
        "albums": [
            {
                "title": "North & Byways",
                "year": 2017,
                "synced_status": "complete",  # ✓ Complete
                "tracks": [
                    ("Cedar & Pine", 230000, 32 * 1024 * 1024),
                    ("The Old Creek Road", 280000, 39 * 1024 * 1024),
                    ("Campfire Smoke", 310000, 43 * 1024 * 1024),
                    ("Porch Light Hymn", 260000, 36 * 1024 * 1024),
                    ("Timberline", 340000, 48 * 1024 * 1024),
                    ("Wild Geese", 290000, 41 * 1024 * 1024),
                    ("Autumn Frost", 250000, 35 * 1024 * 1024),
                    ("Lantern in the Fog", 325000, 46 * 1024 * 1024),
                    ("Return Home", 220000, 31 * 1024 * 1024),
                ]
            },
            {
                "title": "Winter Migration",
                "year": 2020,
                "synced_status": "none",
                "tracks": [
                    ("First Snow", 245000, 34 * 1024 * 1024),
                    ("Frozen Lake", 300000, 42 * 1024 * 1024),
                    ("Cabin in the Hills", 280000, 39 * 1024 * 1024),
                    ("Northbound Train", 260000, 36 * 1024 * 1024),
                    ("Hearth Fire", 335000, 47 * 1024 * 1024),
                    ("Cold River Wading", 290000, 41 * 1024 * 1024),
                    ("Sparrow on the Fence", 215000, 30 * 1024 * 1024),
                    ("The Thawing Woods", 350000, 49 * 1024 * 1024),
                    ("Spring Equinox", 270000, 38 * 1024 * 1024),
                ]
            },
            {
                "title": "Morning Cedar",
                "year": 2023,
                "synced_status": "none",
                "tracks": [
                    ("Awakening", 210000, 29 * 1024 * 1024),
                    ("Golden Meadow", 275000, 38 * 1024 * 1024),
                    ("Mountain Laurel", 310000, 43 * 1024 * 1024),
                    ("Hollow Tree", 250000, 35 * 1024 * 1024),
                    ("Bluebird Song", 235000, 33 * 1024 * 1024),
                    ("Shaded Valley", 340000, 48 * 1024 * 1024),
                    ("River Stones", 285000, 40 * 1024 * 1024),
                    ("Sunset Ridge", 300000, 42 * 1024 * 1024),
                ]
            }
        ]
    },
    {
        "artist": "Prism Frequency",
        "genres": ["Modern Jazz", "Jazz Fusion", "Instrumental"],
        "albums": [
            {
                "title": "Chromatic Etudes",
                "year": 2022,
                "synced_status": "none",
                "tracks": [
                    ("Blue Spectrum", 390000, 55 * 1024 * 1024),
                    ("Synapse Improvisation", 460000, 65 * 1024 * 1024),
                    ("5/4 in Indigo", 330000, 46 * 1024 * 1024),
                    ("Modal Reflections", 520000, 73 * 1024 * 1024),
                    ("The Velocity of Light", 410000, 58 * 1024 * 1024),
                    ("Refraction", 350000, 49 * 1024 * 1024),
                ]
            }
        ]
    },
    {
        "artist": "Monolith Echo",
        "genres": ["Post-Metal", "Atmospheric Sludge", "Ambient"],
        "albums": [
            {
                "title": "Basalt Horizons",
                "year": 2020,
                "synced_status": "complete",  # ✓ Complete
                "tracks": [
                    ("Tectonic Awakening", 540000, 76 * 1024 * 1024),
                    ("Strata of Sorrow", 620000, 87 * 1024 * 1024),
                    ("Pillars of Obsidian", 480000, 67 * 1024 * 1024),
                    ("Caldera Depths", 590000, 83 * 1024 * 1024),
                    ("Stone Whispers", 710000, 99 * 1024 * 1024),
                ]
            },
            {
                "title": "Geology of Shadows",
                "year": 2024,
                "synced_status": "complete",  # ✓ Complete
                "tracks": [
                    ("Fossilized Dreams", 510000, 72 * 1024 * 1024),
                    ("Mantle Flow", 580000, 81 * 1024 * 1024),
                    ("Sediment", 430000, 60 * 1024 * 1024),
                    ("Rift Valley", 650000, 91 * 1024 * 1024),
                    ("Metamorphic Core", 600000, 84 * 1024 * 1024),
                    ("Continental Drift", 730000, 102 * 1024 * 1024),
                ]
            }
        ]
    },
    {
        "artist": "Aurora Borealis Ensemble",
        "genres": ["Neo-Classical", "Chamber", "Ambient Orchestral"],
        "albums": [
            {
                "title": "Frozen Tundra Suite",
                "year": 2021,
                "synced_status": "none",
                "tracks": [
                    ("I. Glacial Morning", 380000, 53 * 1024 * 1024),
                    ("II. Dance of the Green Veil", 440000, 62 * 1024 * 1024),
                    ("III. Solstice Silence", 310000, 43 * 1024 * 1024),
                    ("IV. Polar Winds", 490000, 69 * 1024 * 1024),
                    ("V. Cello in the Snow", 360000, 50 * 1024 * 1024),
                    ("VI. Aurora Nocturne", 530000, 74 * 1024 * 1024),
                    ("VII. Permafrost Lullaby", 420000, 59 * 1024 * 1024),
                ]
            }
        ]
    }
]

DEMO_PLAYLISTS = [
    {
        "title": "Late Night Driving",
        "key": "pl_101",
        "thumb": "demo://album/Neon Mirage/Midnight Expressway",
        "tracks": [
            ("Neon Mirage", "Midnight Expressway", "Nightdrive", 245000, 35 * 1024 * 1024),
            ("Neon Mirage", "Midnight Expressway", "Chrome Horizon", 280000, 39 * 1024 * 1024),
            ("The Solar Echoes", "Signals Across the Void", "Pulsar Frequency", 298000, 42 * 1024 * 1024),
            ("Velvet Horizon", "Slow Decay", "Reverberate", 360000, 51 * 1024 * 1024),
            ("Neon Mirage", "Midnight Expressway", "Outrun 1986", 260000, 37 * 1024 * 1024),
            ("The Solar Echoes", "Heliosphere", "Solar Wind", 310000, 44 * 1024 * 1024),
            ("Subatomic Pulse", "Quantum Resonance", "Wavefunction", 310000, 44 * 1024 * 1024),
            ("Neon Mirage", "Cybernetic Dreams", "Silicon Heartbeat", 285000, 40 * 1024 * 1024),
            ("The Solar Echoes", "Signals Across the Void", "Interstellar Drift", 520000, 74 * 1024 * 1024),
            ("Velvet Horizon", "Slow Decay", "Distant Shimmer", 290000, 41 * 1024 * 1024),
            ("Neon Mirage", "Cybernetic Dreams", "Ghost in the Matrix", 320000, 45 * 1024 * 1024),
            ("The Solar Echoes", "Heliosphere", "Perihelion", 490000, 69 * 1024 * 1024),
        ]
    },
    {
        "title": "Focus & Coding",
        "key": "pl_102",
        "thumb": "demo://album/Subatomic Pulse/Quantum Resonance",
        "tracks": [
            ("Subatomic Pulse", "Quantum Resonance", "Wavefunction", 310000, 44 * 1024 * 1024),
            ("Subatomic Pulse", "Quantum Resonance", "Entanglement", 280000, 39 * 1024 * 1024),
            ("Subatomic Pulse", "Quantum Resonance", "Spin State", 330000, 46 * 1024 * 1024),
            ("The Solar Echoes", "Signals Across the Void", "Radio Astronomy", 412000, 58 * 1024 * 1024),
            ("Subatomic Pulse", "Quantum Resonance", "Higgs Field", 260000, 37 * 1024 * 1024),
            ("Prism Frequency", "Chromatic Etudes", "Blue Spectrum", 390000, 55 * 1024 * 1024),
            ("The Solar Echoes", "Heliosphere", "Magnetosphere", 360000, 51 * 1024 * 1024),
            ("Aurora Borealis Ensemble", "Frozen Tundra Suite", "I. Glacial Morning", 380000, 53 * 1024 * 1024),
            ("Velvet Horizon", "Slow Decay", "Sea of Gauze", 410000, 58 * 1024 * 1024),
            ("Prism Frequency", "Chromatic Etudes", "Modal Reflections", 520000, 73 * 1024 * 1024),
        ]
    },
    {
        "title": "Acoustic Mornings",
        "key": "pl_103",
        "thumb": "demo://album/The Paper Birds/North & Byways",
        "tracks": [
            ("The Paper Birds", "North & Byways", "Cedar & Pine", 230000, 32 * 1024 * 1024),
            ("The Paper Birds", "North & Byways", "The Old Creek Road", 280000, 39 * 1024 * 1024),
            ("The Paper Birds", "North & Byways", "Campfire Smoke", 310000, 43 * 1024 * 1024),
            ("The Paper Birds", "North & Byways", "Porch Light Hymn", 260000, 36 * 1024 * 1024),
            ("The Paper Birds", "North & Byways", "Timberline", 340000, 48 * 1024 * 1024),
            ("The Paper Birds", "North & Byways", "Wild Geese", 290000, 41 * 1024 * 1024),
            ("Aurora Borealis Ensemble", "Frozen Tundra Suite", "V. Cello in the Snow", 360000, 50 * 1024 * 1024),
            ("The Paper Birds", "North & Byways", "Autumn Frost", 250000, 35 * 1024 * 1024),
        ]
    }
]

# -------------------------------------------------------------------------
# Mock PlexManager for Demo Mode
# -------------------------------------------------------------------------

class DemoPlexManager(PlexManager):
    """Provides high fidelity mock responses without needing a live Plex server."""
    def __init__(self):
        super().__init__(base_url="http://demo.vibestunes.local:32400", token="demo-token-1234")
        self.server_name = "Demo Studio Server"

    def connect(self) -> Tuple[bool, str]:
        return True, f"Connected to {self.server_name}"

    def is_connected(self) -> bool:
        return True

    def get_music_libraries(self) -> List[str]:
        return ["Lossless Music (Demo)", "Studio Archives"]

    def get_artists(self, library_name: str = "", force_refresh: bool = False) -> List[PlexArtistSummary]:
        artists = []
        for idx, entry in enumerate(DEMO_CATALOG):
            artists.append(PlexArtistSummary(
                rating_key=f"art_{idx + 1}",
                name=entry["artist"],
                thumb_url=f"demo://artist/{entry['artist']}",
                album_count=len(entry["albums"]),
                genres=entry.get("genres", [])
            ))
        return artists

    def get_playlists(self) -> List[PlexPlaylistSummary]:
        return self.get_all_playlists()

    def get_artist_albums(self, artist_key: str) -> List[PlexAlbumSummary]:
        try:
            art_idx = int(artist_key.replace("art_", "")) - 1
            entry = DEMO_CATALOG[art_idx]
        except Exception:
            return []

        albums = []
        for alb_idx, alb in enumerate(entry["albums"]):
            albums.append(PlexAlbumSummary(
                rating_key=f"alb_{art_idx + 1}_{alb_idx + 1}",
                title=alb["title"],
                artist_name=entry["artist"],
                year=alb["year"],
                thumb_url=f"demo://album/{entry['artist']}/{alb['title']}",
                track_count=len(alb["tracks"]),
                genres=entry.get("genres", [])
            ))
        return albums

    def get_album_tracks(self, album_key: str) -> List[PlexTrackDetail]:
        parts = album_key.split("_")
        if len(parts) < 3:
            return []
        try:
            art_idx = int(parts[1]) - 1
            alb_idx = int(parts[2]) - 1
            entry = DEMO_CATALOG[art_idx]
            alb = entry["albums"][alb_idx]
        except Exception:
            return []

        tracks = []
        for t_idx, (t_title, t_dur, t_size) in enumerate(alb["tracks"]):
            tracks.append(PlexTrackDetail(
                rating_key=f"trk_{art_idx + 1}_{alb_idx + 1}_{t_idx + 1}",
                title=t_title,
                artist_name=entry["artist"],
                album_title=alb["title"],
                track_number=t_idx + 1,
                disc_number=1,
                duration_ms=t_dur,
                size_bytes=t_size,
                container="flac",
                bitrate=1411,
                stream_url=f"http://demo.vibestunes.local:32400/music/{t_idx + 1}",
                part_key=f"part_{art_idx + 1}_{alb_idx + 1}_{t_idx + 1}",
                original_filename=f"{t_idx + 1:02d} - {t_title}.flac",
                year=alb["year"]
            ))
        return tracks

    def get_all_playlists(self) -> List[PlexPlaylistSummary]:
        playlists = []
        for p in DEMO_PLAYLISTS:
            total_dur = sum(t[3] for t in p["tracks"])
            playlists.append(PlexPlaylistSummary(
                rating_key=p["key"],
                title=p["title"],
                track_count=len(p["tracks"]),
                duration_ms=total_dur,
                thumb_url=p["thumb"]
            ))
        return playlists

    def get_playlist_tracks(self, playlist_key: str) -> List[PlexTrackDetail]:
        pl = next((p for p in DEMO_PLAYLISTS if p["key"] == playlist_key), None)
        if not pl:
            return []

        tracks = []
        for idx, (artist, album, title, dur, size) in enumerate(pl["tracks"]):
            tracks.append(PlexTrackDetail(
                rating_key=f"pl_trk_{playlist_key}_{idx + 1}",
                title=title,
                artist_name=artist,
                album_title=album,
                track_number=idx + 1,
                disc_number=1,
                duration_ms=dur,
                size_bytes=size,
                container="flac",
                bitrate=1411,
                stream_url=f"http://demo.vibestunes.local:32400/pl/{idx + 1}",
                part_key=f"pl_part_{playlist_key}_{idx + 1}",
                original_filename=f"{idx + 1:02d} - {title}.flac",
                year=2021
            ))
        return tracks

    def download_artwork_bytes(self, thumb_url: str) -> Optional[bytes]:
        pix = generate_demo_art(thumb_url, size=300)
        from PySide6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        pix.save(buf, "PNG")
        return bytes(buf.data())


# -------------------------------------------------------------------------
# Mock Device & iPod Library for Demo Mode
# -------------------------------------------------------------------------

def get_demo_device() -> iPodDevice:
    """Returns a realistic simulated 160 GB iPod Classic 7th Gen."""
    from vibestunes.core.device import StorageBreakdown
    total = 160 * 1000 * 1000 * 1000  # ~149.0 GiB reported by df
    music = 64 * 1024 * 1024 * 1024   # ~64.0 GiB
    rockbox = 48 * 1024 * 1024        # ~48.0 MiB
    other = 2 * 1024 * 1024 * 1024    # ~2.0 GiB
    trash = 120 * 1024 * 1024         # ~120.0 MiB
    used = music + rockbox + other + trash
    free = total - used

    st = StorageBreakdown(
        total=total,
        used=used,
        free=free,
        music=music,
        rockbox=rockbox,
        trash=trash,
        other=other,
    )

    return iPodDevice(
        mount_point="/media/ipod/DEMO_IPOD",
        target="ipod6g",
        version="3.15",
        memory_mb=64,
        model_name="iPod Classic (6th/7th Gen)",
        label="IPOD",
        device_node="/dev/sdb1",
        disk_node="/dev/sdb",
        filesystem="vfat",
        storage=st
    )

def get_demo_ipod_state() -> Tuple[Set[str], Dict[str, dict], Dict[str, int], List[iPodArtist]]:
    """
    Computes initial on-device sync maps based on DEMO_CATALOG's synced_status.
    Returns:
      (on_ipod_albums_keys, ipod_album_data, ipod_artist_album_counts, ipod_artists)
    """
    on_ipod_albums: Set[str] = set()
    ipod_album_data: Dict[str, dict] = {}
    ipod_artist_album_counts: Dict[str, int] = {}
    ipod_artists: List[iPodArtist] = []

    mount_path = Path("/media/ipod/DEMO_IPOD")

    for entry in DEMO_CATALOG:
        art_name = entry["artist"]
        norm_art = normalize_music_key(art_name)
        artist_synced_albums = 0

        demo_albums_for_artist: List[iPodAlbum] = []

        for alb in entry["albums"]:
            alb_title = alb["title"]
            norm_key = normalize_music_key(art_name, alb_title)
            status = alb.get("synced_status", "none")

            if status == "complete":
                on_ipod_albums.add(norm_key)
                artist_synced_albums += 1

                synced_tracks = []
                demo_tracks: List[iPodTrack] = []
                for t_idx, (t_title, t_dur, t_size) in enumerate(alb["tracks"]):
                    p = mount_path / art_name / alb_title / f"{t_idx+1:02d} - {t_title}.flac"
                    synced_tracks.append({
                        "title": t_title,
                        "track_number": t_idx + 1,
                        "path": str(p),
                        "size": t_size,
                    })
                    demo_tracks.append(iPodTrack(
                        filename=f"{t_idx+1:02d} - {t_title}.flac",
                        path=p,
                        size_bytes=t_size,
                        title=t_title,
                        track_number=t_idx + 1,
                    ))

                ipod_album_data[norm_key] = {
                    "track_count": len(synced_tracks),
                    "tracks": synced_tracks
                }

                demo_albums_for_artist.append(iPodAlbum(
                    title=alb_title,
                    artist_name=art_name,
                    path=mount_path / art_name / alb_title,
                    year=alb["year"],
                    tracks=demo_tracks,
                    total_size_bytes=sum(t.size_bytes for t in demo_tracks),
                    cover_art=None
                ))

            elif status == "partial":
                on_ipod_albums.add(norm_key)
                # Only first portion of tracks on device
                half = len(alb["tracks"]) - 4
                synced_tracks = []
                demo_tracks: List[iPodTrack] = []
                for t_idx in range(max(1, half)):
                    t_title, t_dur, t_size = alb["tracks"][t_idx]
                    p = mount_path / art_name / alb_title / f"{t_idx+1:02d} - {t_title}.flac"
                    synced_tracks.append({
                        "title": t_title,
                        "track_number": t_idx + 1,
                        "path": str(p),
                        "size": t_size,
                    })
                    demo_tracks.append(iPodTrack(
                        filename=f"{t_idx+1:02d} - {t_title}.flac",
                        path=p,
                        size_bytes=t_size,
                        title=t_title,
                        track_number=t_idx + 1,
                    ))

                ipod_album_data[norm_key] = {
                    "track_count": len(synced_tracks),
                    "tracks": synced_tracks
                }

                demo_albums_for_artist.append(iPodAlbum(
                    title=alb_title,
                    artist_name=art_name,
                    path=mount_path / art_name / alb_title,
                    year=alb["year"],
                    tracks=demo_tracks,
                    total_size_bytes=sum(t.size_bytes for t in demo_tracks),
                    cover_art=None
                ))

        if demo_albums_for_artist:
            ipod_artist_album_counts[norm_art] = len(demo_albums_for_artist)
            ipod_artists.append(iPodArtist(
                name=art_name,
                path=mount_path / art_name,
                albums=demo_albums_for_artist
            ))

    return on_ipod_albums, ipod_album_data, ipod_artist_album_counts, ipod_artists


# -------------------------------------------------------------------------
# Simulated Background Sync Worker for Demo Mode
# -------------------------------------------------------------------------

class DemoSyncWorker(SyncWorker):
    """
    Simulates real-time transfers with smooth progress bar updates and speed
    indicators without modifying real hardware or files.
    """
    def __init__(self, tasks: List[Any], parent=None):
        from vibestunes.core.config import AppConfig
        super().__init__(
            plex=DemoPlexManager(),
            ipod_mount="/media/ipod/DEMO_IPOD",
            config=AppConfig()
        )
        for t in tasks:
            self._queue.append(t)

    def run(self) -> None:
        self._is_cancelled = False
        self.is_finished = False
        self.completed_items_count = 0

        with self._lock:
            total_items = len(self._queue)
            self.queue_changed.emit(list(self._queue))
        self.sync_started.emit(total_items)

        overall_tracks = 0
        overall_bytes = 0
        errors = []

        try:
            while not self._is_cancelled:
                with self._lock:
                    if not self._queue:
                        self.current_task = None
                        self.current_track_title = None
                        break
                    task = self._queue.pop(0)
                    self.current_task = task
                    current_queue_len = len(self._queue)
                    snapshot = list(self._queue)

                self.queue_updated.emit(current_queue_len)
                self.queue_changed.emit(snapshot)

                item_idx = self.completed_items_count + 1
                total_items = self.completed_items_count + 1 + current_queue_len
                self.current_item_idx = item_idx
                self.total_items = total_items

                if isinstance(task, DeleteTask):
                    self.current_track_title = f"Deleting {task.display_title}"
                    self.current_track_idx = 1
                    self.total_tracks = 1
                    self.delete_started.emit(task.display_title, item_idx, total_items)
                    time.sleep(0.4)
                    self.delete_completed.emit(task, True, 350 * 1024 * 1024, f"Removed {task.display_title} from iPod")

                elif isinstance(task, SyncPlaylistTask):
                    self.current_track_title = "Resolving playlist tracks..."
                    self.current_track_idx = 0
                    self.total_tracks = 8
                    self.playlist_started.emit(task.playlist_title, item_idx, total_items)

                    for trk_i in range(1, 9):
                        if self._is_cancelled:
                            break
                        track_name = f"Track #{trk_i} for {task.playlist_title}"
                        self.current_track_title = track_name
                        self.current_track_idx = trk_i
                        self.total_tracks = 8
                        self.track_started.emit(track_name, trk_i, 8)

                        # Simulate progress
                        file_size = 42 * 1024 * 1024
                        self.bytes_total = file_size
                        for pct in range(0, 101, 20):
                            if self._is_cancelled:
                                break
                            self.bytes_done = int(file_size * (pct / 100.0))
                            self.bytes_per_sec = 8.4 * 1024 * 1024  # 8.4 MB/s
                            self.track_progress.emit(self.bytes_done, file_size, self.bytes_per_sec)
                            time.sleep(0.06)

                        overall_tracks += 1
                        overall_bytes += file_size
                        self.track_completed.emit(track_name, True, "OK")

                    self.playlist_completed.emit(task.playlist_title, 8, 8 * 42 * 1024 * 1024)

                else:  # SyncTask
                    self.album_started.emit(task.artist_name, task.album_title, item_idx, total_items)
                    num_tracks = len(task.specific_track_keys) if task.specific_track_keys else 6
                    self.total_tracks = num_tracks

                    for trk_i in range(1, num_tracks + 1):
                        if self._is_cancelled:
                            break
                        track_name = f"Track #{trk_i} - Lossless FLAC"
                        self.current_track_title = track_name
                        self.current_track_idx = trk_i
                        self.track_started.emit(track_name, trk_i, num_tracks)

                        file_size = 48 * 1024 * 1024
                        self.bytes_total = file_size
                        for pct in range(0, 101, 25):
                            if self._is_cancelled:
                                break
                            self.bytes_done = int(file_size * (pct / 100.0))
                            self.bytes_per_sec = 9.2 * 1024 * 1024
                            self.track_progress.emit(self.bytes_done, file_size, self.bytes_per_sec)
                            time.sleep(0.08)

                        overall_tracks += 1
                        overall_bytes += file_size
                        self.track_completed.emit(track_name, True, "OK")

                    self.album_completed.emit(task.album_title, num_tracks, num_tracks * 48 * 1024 * 1024)

                self.completed_items_count += 1
        finally:
            with self._lock:
                self.current_task = None
                self.current_track_title = None
                self.is_finished = True

        self.sync_finished.emit(overall_tracks, overall_bytes, errors)
