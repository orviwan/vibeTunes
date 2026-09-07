from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

import requests


class Downloader(Protocol):
    def download(
        self,
        url: str,
        dest: Path,
        on_progress: Callable[[int, int], None],
        should_cancel: Callable[[], bool],
    ) -> None: ...


class HttpDownloader:
    def __init__(self, chunk_size: int = 65536):
        self.chunk_size = chunk_size

    def download(
        self,
        url: str,
        dest: Path,
        on_progress: Callable[[int, int], None],
        should_cancel: Callable[[], bool],
    ) -> None:
        with requests.get(url, stream=True, timeout=30) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", 0))
            written = 0
            with open(dest, "wb") as f:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if should_cancel():
                        return
                    if not chunk:
                        continue
                    f.write(chunk)
                    written += len(chunk)
                    on_progress(written, total)
