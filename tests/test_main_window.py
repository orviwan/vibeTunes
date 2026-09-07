from podplex.core.config import Config
from podplex.ui.main_window import MainWindow


def test_main_window_constructs_with_no_device_detected(qapp):
    window = MainWindow(config=Config())
    assert window.windowTitle() == "PodPlex"
    assert window.device_label.text() == "iPod: not detected"


def test_detect_device_updates_label_when_none_found(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("podplex.ui.main_window.find_device", lambda mount_override="": None)
    window = MainWindow(config=Config())
    window.detect_device()
    assert window.device_label.text() == "iPod: not detected"
