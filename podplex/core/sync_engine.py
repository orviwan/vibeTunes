from __future__ import annotations

import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal


@dataclass
class SyncTrack:
    source_url: str
    dest_path: Path
    size_bytes: int
    title: str


@dataclass
class SyncTask:
    name: str
    tracks: list[SyncTrack]
    task_id: str


class SyncEngine(QObject):
    task_queued = Signal(str)
    task_started = Signal(str)
    track_progress = Signal(str, int, int, float)  # task_id, bytes, total, speed_bytes_per_sec
    track_completed = Signal(str, str)  # task_id, title
    task_completed = Signal(str)
    task_failed = Signal(str, str)  # task_id, error message
    queue_changed = Signal()

    def __init__(self, downloader, is_already_synced: Callable[[SyncTrack], bool] | None = None):
        super().__init__()
        self._downloader = downloader
        self._is_already_synced = is_already_synced or (lambda t: False)
        self._queue: "queue.Queue[SyncTask]" = queue.Queue()
        self._pending: list[SyncTask] = []
        self._skip_ids: set[str] = set()
        self._active_task_id: str | None = None
        self._lock = threading.Lock()
        self._cancel_current = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def enqueue(self, task: SyncTask) -> int:
        with self._lock:
            self._pending.append(task)
            active_offset = 1 if self._active_task_id is not None else 0
            position = active_offset + len(self._pending)
        self._queue.put(task)
        self.task_queued.emit(task.task_id)
        self.queue_changed.emit()
        return position

    def pending_tasks(self) -> list[SyncTask]:
        with self._lock:
            return list(self._pending)

    def remove_pending(self, task_id: str) -> bool:
        with self._lock:
            for t in self._pending:
                if t.task_id == task_id:
                    self._pending.remove(t)
                    self._skip_ids.add(task_id)
                    self.queue_changed.emit()
                    return True
        return False

    def clear_pending(self) -> None:
        with self._lock:
            ids = {t.task_id for t in self._pending}
            self._skip_ids.update(ids)
            self._pending.clear()
        self.queue_changed.emit()

    def cancel_current(self) -> None:
        self._cancel_current.set()

    def cancel_all(self) -> None:
        self._cancel_current.set()
        self.clear_pending()

    def _run(self) -> None:
        while True:
            task = self._queue.get()
            skip = False
            with self._lock:
                if task in self._pending:
                    self._pending.remove(task)
                if task.task_id in self._skip_ids:
                    self._skip_ids.discard(task.task_id)
                    skip = True
                else:
                    self._active_task_id = task.task_id
            if skip:
                continue
            self._cancel_current.clear()
            self.task_started.emit(task.task_id)
            self.queue_changed.emit()
            try:
                cancelled = self._process_task(task)
                if cancelled:
                    self.task_failed.emit(task.task_id, "cancelled")
                else:
                    self.task_completed.emit(task.task_id)
            except Exception as exc:
                self.task_failed.emit(task.task_id, str(exc))
            finally:
                with self._lock:
                    self._active_task_id = None

    def _process_task(self, task: SyncTask) -> bool:
        """Returns True if the task was cancelled partway through."""
        for track in task.tracks:
            if self._cancel_current.is_set():
                return True
            if self._is_already_synced(track):
                self.track_completed.emit(task.task_id, track.title)
                continue
            self._download_track(task, track)
            if self._cancel_current.is_set():
                return True
            self.track_completed.emit(task.task_id, track.title)
        return False

    def _download_track(self, task: SyncTask, track: SyncTrack) -> None:
        part_path = track.dest_path.with_suffix(track.dest_path.suffix + ".part")
        part_path.parent.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()

        def on_progress(downloaded: int, total: int) -> None:
            elapsed = max(time.monotonic() - start, 1e-6)
            speed = downloaded / elapsed
            self.track_progress.emit(task.task_id, downloaded, total, speed)

        self._downloader.download(track.source_url, part_path, on_progress, self._cancel_current.is_set)
        if self._cancel_current.is_set():
            part_path.unlink(missing_ok=True)
            return
        os.replace(part_path, track.dest_path)
