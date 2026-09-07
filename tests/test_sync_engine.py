import time

from PySide6.QtCore import Qt

from podplex.core.sync_engine import SyncEngine, SyncTask, SyncTrack


class FakeDownloader:
    def __init__(self, content: bytes = b"hello world", chunk_delay: float = 0):
        self.content = content
        self.chunk_delay = chunk_delay
        self.calls = []

    def download(self, url, dest, on_progress, should_cancel):
        self.calls.append(url)
        total = len(self.content)
        written = 0
        with open(dest, "wb") as f:
            for i in range(0, total, 4):
                if should_cancel():
                    return
                chunk = self.content[i : i + 4]
                f.write(chunk)
                written += len(chunk)
                on_progress(written, total)
                if self.chunk_delay:
                    time.sleep(self.chunk_delay)


def _make_task(tmp_path, task_id="t1", n_tracks=1):
    tracks = [
        SyncTrack(
            source_url=f"http://x/{i}",
            dest_path=tmp_path / f"track{i}.mp3",
            size_bytes=11,
            title=f"Track {i}",
        )
        for i in range(n_tracks)
    ]
    return SyncTask(name="Test Album", tracks=tracks, task_id=task_id)


def _wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)


def test_enqueue_reports_position(tmp_path):
    engine = SyncEngine(FakeDownloader(chunk_delay=0.05))
    pos1 = engine.enqueue(_make_task(tmp_path, "t1"))
    pos2 = engine.enqueue(_make_task(tmp_path, "t2"))
    assert pos1 == 1
    assert pos2 == 2
    engine.cancel_all()


def test_track_downloads_and_renames_atomically(tmp_path):
    downloader = FakeDownloader(content=b"abcdefgh")
    engine = SyncEngine(downloader)
    completed = []
    engine.task_completed.connect(lambda tid: completed.append(tid), Qt.DirectConnection)
    task = _make_task(tmp_path, "t1")
    engine.enqueue(task)
    _wait_until(lambda: completed)
    assert completed == ["t1"]
    dest = task.tracks[0].dest_path
    assert dest.exists()
    assert dest.read_bytes() == b"abcdefgh"
    assert not dest.with_suffix(dest.suffix + ".part").exists()


def test_already_synced_tracks_are_skipped(tmp_path):
    downloader = FakeDownloader()
    engine = SyncEngine(downloader, is_already_synced=lambda t: True)
    completed_titles = []
    engine.track_completed.connect(lambda tid, title: completed_titles.append(title), Qt.DirectConnection)
    task_completed = []
    engine.task_completed.connect(lambda tid: task_completed.append(tid), Qt.DirectConnection)
    task = _make_task(tmp_path, "t1")
    engine.enqueue(task)
    _wait_until(lambda: task_completed)
    assert completed_titles == ["Track 0"]
    assert downloader.calls == []


def test_cancel_current_removes_part_file(tmp_path):
    downloader = FakeDownloader(content=b"x" * 40, chunk_delay=0.05)
    engine = SyncEngine(downloader)
    failed = []
    engine.task_failed.connect(lambda tid, err: failed.append((tid, err)), Qt.DirectConnection)
    task = _make_task(tmp_path, "t1")
    engine.enqueue(task)
    time.sleep(0.06)
    engine.cancel_current()
    _wait_until(lambda: failed)
    assert failed == [("t1", "cancelled")]
    dest = task.tracks[0].dest_path
    assert not dest.exists()
    assert not dest.with_suffix(dest.suffix + ".part").exists()


def test_remove_pending_task_is_never_processed(tmp_path):
    engine = SyncEngine(FakeDownloader(chunk_delay=0.05))
    blocker = _make_task(tmp_path, "blocker")
    engine.enqueue(blocker)
    task2 = _make_task(tmp_path, "t2")
    engine.enqueue(task2)
    removed = engine.remove_pending("t2")
    assert removed is True
    assert all(t.task_id != "t2" for t in engine.pending_tasks())

    started = []
    engine.task_started.connect(lambda tid: started.append(tid), Qt.DirectConnection)
    _wait_until(lambda: len(started) > 0, timeout=2)
    time.sleep(0.3)
    assert "t2" not in started
    engine.cancel_all()
