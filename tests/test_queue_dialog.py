import time

from podplex.core.sync_engine import SyncEngine, SyncTask, SyncTrack
from podplex.ui.queue_dialog import QueueDialog


class SlowDownloader:
    def download(self, url, dest, on_progress, should_cancel):
        while not should_cancel():
            time.sleep(0.01)


def _task(tmp_path, task_id):
    return SyncTask(
        name=f"Album {task_id}",
        tracks=[SyncTrack(source_url="http://x", dest_path=tmp_path / f"{task_id}.mp3", size_bytes=1, title="T")],
        task_id=task_id,
    )


def test_queue_dialog_lists_pending_tasks(qapp, tmp_path):
    engine = SyncEngine(SlowDownloader())
    engine.enqueue(_task(tmp_path, "blocker"))
    engine.enqueue(_task(tmp_path, "t2"))
    dialog = QueueDialog(engine)
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "Album t2"
    engine.cancel_all()


def test_queue_dialog_remove_button_removes_task(qapp, tmp_path):
    engine = SyncEngine(SlowDownloader())
    engine.enqueue(_task(tmp_path, "blocker"))
    engine.enqueue(_task(tmp_path, "t2"))
    dialog = QueueDialog(engine)
    dialog._remove("t2")
    assert dialog.table.rowCount() == 0
    assert all(t.task_id != "t2" for t in engine.pending_tasks())
    engine.cancel_all()


def test_queue_dialog_clear_pending_empties_table(qapp, tmp_path):
    engine = SyncEngine(SlowDownloader())
    engine.enqueue(_task(tmp_path, "blocker"))
    engine.enqueue(_task(tmp_path, "t2"))
    engine.enqueue(_task(tmp_path, "t3"))
    dialog = QueueDialog(engine)
    dialog._clear_pending()
    assert dialog.table.rowCount() == 0
    assert engine.pending_tasks() == []
    engine.cancel_all()
