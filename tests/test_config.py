import tempfile
from pathlib import Path
from vibetunes.core.config import AppConfig

def test_default_config():
    cfg = AppConfig()
    assert cfg.plex_library == "Music"
    assert cfg.naming_pattern == "plex_exact"
    assert cfg.transcode_mode == "original"
    assert cfg.download_artwork is True

def test_save_and_load(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_file = Path(tmpdir) / "config.json"
        monkeypatch.setattr("vibetunes.core.config.CONFIG_FILE", tmp_file)
        monkeypatch.setattr("vibetunes.core.config.CONFIG_DIR", Path(tmpdir))

        cfg = AppConfig(plex_url="http://192.168.1.100:32400", plex_token="secret_token", naming_pattern="standard")
        cfg.save()

        assert tmp_file.exists()
        loaded = AppConfig.load()
        assert loaded.plex_url == "http://192.168.1.100:32400"
        assert loaded.plex_token == "secret_token"
        assert loaded.naming_pattern == "standard"
