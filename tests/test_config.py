import json

from podplex.core.config import Config


def test_defaults():
    c = Config()
    assert c.plex_library_name == "Music"
    assert c.naming_pattern == "rockbox_disc"
    assert c.download_artwork is True
    assert c.transcode_mode == "direct"


def test_round_trip(tmp_path):
    path = tmp_path / "config.json"
    c = Config(plex_url="http://x:32400", plex_token="abc", naming_pattern="standard")
    c.save(path)
    loaded = Config.load(path)
    assert loaded == c


def test_load_missing_file_returns_defaults(tmp_path):
    path = tmp_path / "nope.json"
    loaded = Config.load(path)
    assert loaded == Config()


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"plex_url": "http://x", "bogus_key": "z"}))
    loaded = Config.load(path)
    assert loaded.plex_url == "http://x"


def test_load_corrupt_json_returns_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not valid json")
    loaded = Config.load(path)
    assert loaded == Config()
