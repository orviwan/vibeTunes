import tempfile
from pathlib import Path
from vibestunes.core.ipod_scanner import parse_album_folder_name, scan_ipod_music

def test_parse_album_folder_name():
    title, yr = parse_album_folder_name("Radiohead-1997-OK Computer", "Radiohead")
    assert title == "OK Computer"
    assert yr == 1997

    title2, yr2 = parse_album_folder_name("Kid A (2000)", "Radiohead")
    assert yr2 == 2000

    title3, yr3 = parse_album_folder_name("Amnesiac", "Radiohead")
    assert title3 == "Amnesiac"
    assert yr3 is None

    title4, yr4 = parse_album_folder_name("Radiohead-The Bends", "Radiohead")
    assert title4 == "The Bends"
    assert yr4 is None

    title5, yr5 = parse_album_folder_name("Ash-1977", "Ash")
    assert title5 == "1977"

    title6, yr6 = parse_album_folder_name("Ash-1996-1977", "Ash")
    assert title6 == "1977"
    assert yr6 == 1996

    title7, yr7 = parse_album_folder_name("The Beatles - Abbey Road", "The Beatles")
    assert title7 == "Abbey Road"
    assert yr7 is None

def test_scan_ipod_music_mock():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".rockbox").mkdir()
        (root / "Radiohead" / "Radiohead-1997-OK Computer").mkdir(parents=True)
        (root / "Radiohead" / "Radiohead-1997-OK Computer" / "01 - Airbag.flac").write_bytes(b"mock" * 100)

        artists = scan_ipod_music(tmpdir)
        assert len(artists) == 1
        assert artists[0].name == "Radiohead"
        assert len(artists[0].albums) == 1
        assert artists[0].albums[0].title == "OK Computer"
        assert artists[0].albums[0].year == 1997
        assert artists[0].albums[0].track_count == 1

def test_find_and_delete_ipod_album():
    from vibestunes.core.ipod_scanner import find_and_delete_ipod_album
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        alb_dir = root / "Radiohead" / "Radiohead-1997-OK Computer"
        alb_dir.mkdir(parents=True)
        (alb_dir / "01 - Airbag.flac").write_bytes(b"test" * 100)

        success, freed, msg = find_and_delete_ipod_album(tmpdir, "Radiohead", "OK Computer")
        assert success is True
        assert freed == 400
        assert not alb_dir.exists()
        assert not (root / "Radiohead").exists()

def test_find_and_delete_ipod_artist():
    from vibestunes.core.ipod_scanner import find_and_delete_ipod_artist
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        art_dir = root / "Radiohead"
        alb1 = art_dir / "Radiohead-1997-OK Computer"
        alb2 = art_dir / "Radiohead-2000-Kid A"
        alb1.mkdir(parents=True)
        alb2.mkdir(parents=True)
        (alb1 / "01.flac").write_bytes(b"x" * 100)
        (alb2 / "01.flac").write_bytes(b"y" * 200)

        success, freed, msg = find_and_delete_ipod_artist(tmpdir, "Radiohead")
        assert success is True
        assert freed == 300
        assert not art_dir.exists()

def test_clean_trash():
    from vibestunes.core.ipod_scanner import clean_trash
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        trash = root / ".Trash-1000"
        trash.mkdir()
        (trash / "file.flac").write_bytes(b"trash" * 100)

        success, freed, msg = clean_trash(tmpdir)
        assert success is True
        assert freed == 500
        assert not trash.exists()
