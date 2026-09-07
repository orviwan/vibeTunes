from podplex.core.storage_analyzer import StorageBreakdown
from podplex.ui.storage_bar import StorageBar


def test_segments_empty_when_no_breakdown(qapp):
    bar = StorageBar()
    assert bar.segments() == []


def test_segments_reflects_breakdown(qapp):
    bar = StorageBar()
    bar.set_breakdown(StorageBreakdown(total_bytes=100, free_bytes=40, music_bytes=30, rockbox_bytes=20, other_bytes=10))
    assert bar.segments() == [("music", 30), ("rockbox", 20), ("other", 10), ("free", 40)]


def test_segments_empty_when_total_zero(qapp):
    bar = StorageBar()
    bar.set_breakdown(StorageBreakdown(total_bytes=0, free_bytes=0, music_bytes=0, rockbox_bytes=0, other_bytes=0))
    assert bar.segments() == []
